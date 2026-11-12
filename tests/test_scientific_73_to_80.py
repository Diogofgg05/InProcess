"""Safety and scientific-regression tests for InProcess 7.3 to 8.0."""
from dataclasses import replace
import math
import os
import sys

import pytest

from expecto_process_manager.optimization.benchmarks71 import BenchmarkTrial
from expecto_process_manager.optimization.statistics73 import analyse_benchmarks
from expecto_process_manager.optimization.energy76 import (
    EnergyTrace,EnergyReading,load_energy_trace_csv,integrate_energy,compare_energy_traces,
)
from expecto_process_manager.optimization.recommendations80 import (
    recommend_energy,recommend_from_benchmark,combine_recommendations,
)
from expecto_process_manager.optimization import native75,watchdog74


def _trial(label,duration):
    return BenchmarkTrial(
        label=label,workload_digest="same-task",host_fingerprint="same-host",
        platform_name="Linux",observer_pid=None if label=="BASELINE" else 1234,
        observer_name=None if label=="BASELINE" else label,
        observer_start_time=None if label=="BASELINE" else 1000.,
        workload_exit_code=0,task_duration_s=duration,
        observer_cpu_core_percent=None if label=="BASELINE" else 5.,
        observer_peak_rss_mib=None if label=="BASELINE" else 40.,
        observer_samples=0 if label=="BASELINE" else 5,
        sample_gap_p95_ms=150.,sample_gap_max_ms=160.,
        ui_input_latency_ms=None,ui_latency_provenance="NOT_MEASURED",
        status="SUCCESS",warnings=(),
    )


def test_scientific_stats_require_repetitions_and_do_not_invent_latency():
    trials=[_trial("BASELINE",x) for x in (1,1.01,.99)]+[
        _trial("INPROCESS",x) for x in (1.2,1.22,1.18)
    ]
    result=analyse_benchmarks(trials)
    assert result.comparable
    assert len(result.impacts)==1
    assert result.impacts[0].slowdown_pct==pytest.approx(20)
    assert result.metadata["ui_latency"]=="NOT_MEASURED"
    assert result.metadata["energy"]=="NOT_MEASURED"
    assert result.impacts[0].difference_ci95_pct[0]<=result.impacts[0].slowdown_pct<=result.impacts[0].difference_ci95_pct[1]
    assert analyse_benchmarks(trials)==result
    advisor=recommend_from_benchmark(result)
    assert advisor.action=="REVIEW_BACKGROUND_LOAD"
    assert advisor.status=="REVIEW_ONLY"


def test_insufficient_trials_cannot_trigger_action():
    data=[_trial("BASELINE",1),_trial("INPROCESS",2)]
    report=analyse_benchmarks(data)
    assert not report.comparable
    assert not report.impacts
    assert recommend_from_benchmark(report).action=="NO_CHANGE"


def test_energy_exact_constant_watts_and_explicit_scope():
    trace=EnergyTrace((
        EnergyReading(0,20,25),EnergyReading(2,20,26),
        EnergyReading(5,20,27)
    ),"computer","plug-meter","system-wall", "MEASURED_UNVERIFIED")
    energy=integrate_energy(trace)
    assert energy.joules==pytest.approx(100)
    assert energy.watt_hours==pytest.approx(100/3600)
    assert energy.duration_s==5
    assert energy.temperature_min_c==25
    assert energy.provenance=="MEASURED_UNVERIFIED"


def test_energy_csv_metadata_is_not_silently_trusted(tmp_path):
    p=tmp_path/"meter.csv"
    p.write_text("time_s,power_w,temperature_c\n0,15,26\n1,17,27\n2,16,28\n",
                 encoding="utf-8")
    trace=load_energy_trace_csv(p,device="laptop",sensor="meter",
                                power_scope="wall")
    assert trace.provenance=="MEASURED_UNVERIFIED"
    assert integrate_energy(trace).joules==pytest.approx(32.5)


def test_energy_invalid_sources_and_comparison_refusals():
    trace=EnergyTrace((EnergyReading(0,10),EnergyReading(1,10),
                       EnergyReading(2,10)),"pc","meter","wall")
    different=replace(trace,sensor="cpu-internal",power_scope="package")
    not_comparable=compare_energy_traces({"A":trace,"B":different},
                                         comparable_work=True)
    assert not not_comparable["comparable"]
    assert not_comparable["best_energy"] is None
    assert recommend_energy(not_comparable).action=="NO_CHANGE"
    same=compare_energy_traces({"A":trace,"B":trace},comparable_work=True)
    assert same["comparable"]
    assert recommend_energy(same).action=="REVIEW_ENERGY_PROFILE"
    assert recommend_energy(same).status=="REVIEW_ONLY"


@pytest.mark.parametrize("samples",[
    (EnergyReading(0,10),EnergyReading(0,10),EnergyReading(1,10)),
    (EnergyReading(0,-1),EnergyReading(1,10),EnergyReading(2,10)),
    (EnergyReading(0,float("nan")),EnergyReading(1,10),EnergyReading(2,10)),
])
def test_energy_rejects_invalid_physics(samples):
    with pytest.raises(ValueError):
        EnergyTrace(samples,"pc","meter","wall")


def test_advisor_has_no_automatic_os_actions():
    report=combine_recommendations()
    assert report["mode"]=="READ_ONLY"
    assert report["automatic_os_actions"] is False
    assert report["recommendations"][0]["action"]=="NO_CHANGE"


class FakeProc:
    def __init__(self,pid,created,priority,owner="current"):
        self.pid=pid
        self.created=created
        self.priority=priority
        self.owner=owner
        self.history=[]
    def create_time(self):return self.created
    def name(self):return 'safe-test-process.exe'
    def nice(self,arg=None):
        if arg is not None:
            self.priority=arg
            self.history.append(arg)
        return self.priority
    def username(self):return self.owner
    def is_running(self):return True


def test_watchdog_restores_on_dead_owner_windows_mock(monkeypatch):
    from expecto_process_manager.optimization import watchdog74 as wd
    target=FakeProc(70000,100.,16384)
    owner=FakeProc(70001,200.,32)
    me=FakeProc(os.getpid(),300.,32)
    monkeypatch.setattr(wd.platform,"system",lambda:"Windows")
    monkeypatch.setattr(wd,"_protected_process_ids",lambda:{0,1})
    monkeypatch.setattr(wd,"_critical_process_name",lambda name,system:False)
    monkeypatch.setattr(wd.psutil,"NORMAL_PRIORITY_CLASS",32,raising=False)
    monkeypatch.setattr(wd.psutil,"BELOW_NORMAL_PRIORITY_CLASS",16384,raising=False)
    def find(pid):
        if pid==70000:return target
        if pid==70001:raise wd.psutil.NoSuchProcess(pid)
        if pid==os.getpid():return me
        raise wd.psutil.NoSuchProcess(pid)
    monkeypatch.setattr(wd.psutil,"Process",find)
    result=wd.restore_if_expected(
        70000,100.,32,16384,owner_pid=70001,owner_created=200.,
        deadline_s=1)
    assert result=="RESTORED_ON_CRASH_OR_EXPIRY"
    assert target.history==[32]


def test_watchdog_does_not_overwrite_external_changes(monkeypatch):
    from expecto_process_manager.optimization import watchdog74 as wd
    target=FakeProc(70000,100.,128)
    me=FakeProc(os.getpid(),300.,32)
    monkeypatch.setattr(wd.platform,"system",lambda:"Windows")
    monkeypatch.setattr(wd,"_protected_process_ids",lambda:{0,1})
    monkeypatch.setattr(wd,"_critical_process_name",lambda name,system:False)
    monkeypatch.setattr(wd.psutil,"NORMAL_PRIORITY_CLASS",32,raising=False)
    monkeypatch.setattr(wd.psutil,"BELOW_NORMAL_PRIORITY_CLASS",16384,raising=False)
    monkeypatch.setattr(wd.psutil,"Process",lambda p:target if p==70000 else me)
    result=wd.restore_if_expected(
        70000,100.,32,16384,owner_pid=70001,owner_created=200.,
        deadline_s=1)
    assert result=="CHANGED_BY_THIRD_PARTY"
    assert not target.history


def test_watchdog_rejects_arbitrary_priority_escalation():
    with pytest.raises(PermissionError):
        watchdog74.restore_if_expected(70000,100.,256,32,
                                    owner_pid=70001,owner_created=200.)


def test_native_efficiency_opt_in_and_preview(monkeypatch):
    with pytest.raises(PermissionError):
        native75.native_workload_trial([sys.executable,"-c","pass"])
    monkeypatch.setattr(native75.platform,"system",lambda:"UnsupportedOS")
    capability=native75.native_capability()
    assert not capability.supported
    with pytest.raises(RuntimeError):
        native75.native_workload_trial([sys.executable,"-c","pass"],authorized=True)


def test_linux_native_scope_uses_arguments_without_root_or_shell(monkeypatch):
    monkeypatch.setattr(native75.platform,"system",lambda:"Linux")
    monkeypatch.setattr(native75.shutil,"which",lambda name:"/usr/bin/systemd-run")
    captured=[]
    class FakeChild:
        returncode=0
        def poll(self):return self.returncode
        def wait(self,timeout=None):return self.returncode
    def launch(args,**kw):
        captured.append((args,kw))
        return FakeChild()
    monkeypatch.setattr(native75.subprocess,"Popen",launch)
    out=native75.native_workload_trial(["python","-c","pass"],authorized=True)
    assert out.status=="SUCCESS"
    args,kw=captured[0]
    assert args[:4]==["systemd-run","--user","--scope","--quiet"]
    assert "--property=CPUWeight=50" in args
    assert kw["shell"] is False


def test_native_refuses_unbounded_or_invalid_configuration():
    for duration in (-1,0,61,float("nan")):
        with pytest.raises(ValueError):
            native75.native_workload_trial(["python"],authorized=True,timeout_s=duration)



def test_linux_scope_is_stopped_on_timeout(monkeypatch):
    monkeypatch.setattr(native75.platform,"system",lambda:"Linux")
    monkeypatch.setattr(native75.shutil,"which",lambda _: "/usr/bin/systemd-run")
    launched=[]
    stopped=[]
    class Child:
        returncode=None
        def poll(self):return self.returncode
        def terminate(self):self.returncode=-15
        def wait(self,timeout=None):
            if self.returncode is None:
                raise native75.subprocess.TimeoutExpired(["systemd-run"],timeout)
            return self.returncode
    def launch(args,**kw):
        launched.append(args)
        return Child()
    class Result:
        returncode=0
    monkeypatch.setattr(native75.subprocess,"Popen",launch)
    monkeypatch.setattr(native75.subprocess,"run",lambda args,**kw: (
        stopped.append(args) or Result()
    ))
    outcome=native75.native_workload_trial(
        ["python","-c","pass"],authorized=True,timeout_s=1
    )
    assert outcome.status=="TIMEOUT"
    unit=[a for a in launched[0] if a.startswith("--unit=")][0].split("=",1)[1]
    assert stopped==[["systemctl","--user","stop",unit]]
    assert unit.startswith("inprocess-bench-") and unit.endswith(".scope")
