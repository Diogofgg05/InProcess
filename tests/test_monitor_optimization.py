from contextlib import nullcontext
from types import SimpleNamespace
import pytest
import psutil
from expecto_process_manager.core.processes import ProcessService
from expecto_process_manager.core.monitoring import Monitor


class Process:
    pid = 123456

    def __init__(self,created=100):
        self.created=created
        self.alive=True
        self.state='running'
        self.status_calls=0
        self.cpu_calls=0

    def oneshot(self): return nullcontext()
    def username(self): return 'test'
    def is_running(self): return self.alive
    def create_time(self): return self.created
    def name(self): return 'test-process'
    def memory_info(self): return SimpleNamespace(rss=1024)
    def io_counters(self): return SimpleNamespace(read_bytes=100,write_bytes=200)

    def cpu_percent(self):
        self.cpu_calls+=1
        return 25

    def status(self):
        self.status_calls+=1
        return self.state


def test_status_cadence_reports_age_and_keeps_cpu_fresh(monkeypatch):
    from expecto_process_manager.core import processes as module
    clock={'mono':10.0,'wall':1010.0}
    monkeypatch.setattr(module.time,'monotonic',lambda:clock['mono'])
    monkeypatch.setattr(module.time,'time',lambda:clock['wall'])
    process=Process()
    monkeypatch.setattr(psutil,'process_iter',lambda:iter([process]))
    service=ProcessService()
    first=service.list_processes()[0]
    clock.update(mono=11,wall=1011)
    process.state='stopped'
    second=service.list_processes()[0]
    assert first['cpu'] is None
    assert second['cpu']==25
    assert process.cpu_calls==2
    assert process.status_calls==1
    assert second['status']=='running'
    assert second['status_sampled_at']==1010
    assert second['status_age_s']==1
    clock.update(mono=15,wall=1015)
    third=service.list_processes()[0]
    assert process.status_calls==2
    assert third['status']=='stopped'
    assert third['status_age_s']==0


def test_cache_identity_and_pruning(monkeypatch):
    process=Process()
    current=[process]
    monkeypatch.setattr(psutil,'process_iter',lambda:iter(current))
    service=ProcessService()
    service.list_processes()
    reused=Process(created=200)
    reused.state='stopped'
    current[:]=[reused]
    row=service.list_processes()[0]
    assert row['created']==200
    assert row['cpu'] is None
    assert row['status']=='stopped'
    assert set(service._status)=={(process.pid,200)}
    reused.alive=False
    assert service.list_processes()==[]
    assert not service._status and not service._io and not service._seen


def test_control_invalidates_own_status_cache(monkeypatch):
    process=Process()
    process.resume=lambda:None
    monkeypatch.setattr(psutil,'process_iter',lambda:iter([process]))
    monkeypatch.setattr(psutil,'Process',lambda pid:process)
    service=ProcessService()
    service.list_processes()
    assert service._status
    service.control(process.pid,process.created,'resume',authorized=True)
    assert not service._status


def test_explicit_status_invalidation(monkeypatch):
    process=Process()
    monkeypatch.setattr(psutil,'process_iter',lambda:iter([process]))
    service=ProcessService()
    service.list_processes()
    service.invalidate_status(process.pid)
    assert not service._status
    service.list_processes()
    service.invalidate_status()
    assert not service._status


def patch_monitor(monkeypatch):
    from expecto_process_manager.core import monitoring as module
    clock={'mono':10.0,'wall':1010.0}
    monkeypatch.setattr(module.time,'monotonic',lambda:clock['mono'])
    monkeypatch.setattr(module.time,'time',lambda:clock['wall'])
    monkeypatch.setattr(psutil,'cpu_percent',lambda **_: [20,40])
    monkeypatch.setattr(psutil,'virtual_memory',lambda:SimpleNamespace(used=100,available=900,percent=10,total=1000))
    monkeypatch.setattr(psutil,'disk_io_counters',lambda:None)
    monkeypatch.setattr(psutil,'net_io_counters',lambda:None)
    return module,clock


def test_auxiliary_cadence_and_absent_values(monkeypatch):
    module,clock=patch_monitor(monkeypatch)
    counts={'swap':0,'temperature':0,'frequency':0}
    def swap():
        counts['swap']+=1
        return SimpleNamespace(used=40)
    def temperature():
        counts['temperature']+=1
        return 45
    def frequency():
        counts['frequency']+=1
        return SimpleNamespace(current=2500)
    monkeypatch.setattr(psutil,'swap_memory',swap)
    monkeypatch.setattr(module,'temperatures',temperature)
    monkeypatch.setattr(psutil,'cpu_freq',frequency)
    monitor=Monitor()
    first=monitor.sample()
    clock.update(mono=11,wall=1011)
    second=monitor.sample()
    assert counts==dict(swap=1,temperature=1,frequency=1)
    assert first.cpu is None and second.cpu==30
    assert second.swap_sampled_at==1010
    assert second.swap_age_s==1
    assert second.temperature_age_s==1
    assert second.frequency_age_s==1
    clock.update(mono=12.1,wall=1012.1)
    third=monitor.sample()
    assert counts==dict(swap=2,temperature=2,frequency=2)
    assert third.swap_age_s==0
    assert third.swap_sampled_at==1012.1


def test_sensor_failure_is_absent_not_zero(monkeypatch):
    module,_=patch_monitor(monkeypatch)
    def unavailable(): raise psutil.AccessDenied()
    monkeypatch.setattr(psutil,'swap_memory',unavailable)
    monkeypatch.setattr(module,'temperatures',lambda:None)
    monkeypatch.setattr(psutil,'cpu_freq',lambda:None)
    snapshot=Monitor().sample()
    assert snapshot.swap_used is None and snapshot.swap_sampled_at is None
    assert snapshot.temperature_c is None and snapshot.temperature_age_s is None
    assert snapshot.cpu_frequency_mhz is None and snapshot.frequency_age_s is None


def test_expired_sensor_failure_discards_previous_value(monkeypatch):
    module,clock=patch_monitor(monkeypatch)
    monkeypatch.setattr(psutil,'swap_memory',lambda:SimpleNamespace(used=70))
    monkeypatch.setattr(module,'temperatures',lambda:45)
    monkeypatch.setattr(psutil,'cpu_freq',lambda:SimpleNamespace(current=2000))
    monitor=Monitor()
    assert monitor.sample().swap_used==70
    def unavailable(): raise psutil.AccessDenied()
    monkeypatch.setattr(psutil,'swap_memory',unavailable)
    clock.update(mono=13,wall=1013)
    snapshot=monitor.sample()
    assert snapshot.swap_used is None
    assert snapshot.swap_sampled_at is None
    assert snapshot.swap_age_s is None


def test_catalog_rejects_pid_created_after_cached_snapshot(monkeypatch):
    from expecto_process_manager.core import providers as module
    monkeypatch.setattr(module.platform,'system',lambda:'Windows')
    provider=module.PsutilProvider()
    provider._groups=({123456},set())
    provider._groups_at=100
    provider._groups_time=module.time.monotonic()
    monkeypatch.setattr(provider.processes,'list_processes',lambda:[dict(pid=123456,created=200)])
    row=provider.list_processes()[0]
    assert row['kind']=='unknown'
    assert row['kind_sampled_at'] is None
    assert row['kind_age_s'] is None


@pytest.mark.parametrize('interval',[-1,float('nan'),float('inf')])
def test_invalid_cache_intervals(interval):
    with pytest.raises(ValueError): ProcessService(status_interval_s=interval)
    with pytest.raises(ValueError): Monitor(auxiliary_interval_s=interval)
