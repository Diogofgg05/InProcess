import os
import time
import pytest
from expecto_process_manager.plugin_api.interface import Manager
from expecto_process_manager.core.processes import ProcessService
from expecto_process_manager.core.monitoring import Monitor
from expecto_process_manager.core.metrics import export_csv,import_power


def test_public_api():
    manager = Manager()
    assert any(row['pid'] == os.getpid() for row in manager.list_processes())
    assert manager.get_cpu_usage()
    assert manager.get_memory_usage()['total'] > 0
    result = manager.simulate_temperature(initial_temperature=40,ambient_temperature=22,power=45,duration=120,dt=.1)
    assert result.times[-1] == 120
    assert manager.calculate_energy(times=result.times,powers=result.powers) == pytest.approx(5400)


def test_history():
    monitor = Monitor()
    first = monitor.sample()
    time.sleep(.02)
    second = monitor.sample()
    assert first.disk_bytes_s is None
    assert 0 <= second.cpu <= 100
    assert len(monitor.records()) == 2
    assert second.memory_available > 0


def test_controls_require_authorization():
    with pytest.raises(PermissionError):
        ProcessService().control(os.getpid(),0,'terminate')
    with pytest.raises(ValueError):
        ProcessService().control(os.getpid(),0,'terminate',authorized=True)


def test_csv(tmp_path):
    path = tmp_path/'power.csv'
    export_csv(path,[dict(time_s=0,power_w=10),dict(time_s=1,power_w=20)])
    times,powers,origin = import_power(path)
    assert times == [0,1]
    assert powers == [10,20]
    assert 'não verificada' in origin


def test_public_gravity_api():
    from expecto_process_manager.physics.gravity import GravityConfig
    manager=Manager()
    orbit=manager.simulate_gravity(GravityConfig(duration=100,dt=10))
    assert orbit.provenance=='simulado'
    assert len(orbit.trajectories)==3
    falling=manager.simulate_free_fall(duration=1,dt=.1)
    assert falling.reference_heights[-1]==pytest.approx(100-9.80665/2)
