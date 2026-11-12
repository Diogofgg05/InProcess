"""Advanced Control Lab 6.3: real regression checks of simulated dynamics."""
import math
import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM","offscreen")

from expecto_process_manager.physics.control_lab63 import (
    ControlScenario,simulate_control,compare_controllers,gain_sensitivity,
)


def test_three_modes_have_distinct_responses_and_identical_exogenous_load():
    results=compare_controllers()
    assert set(results)=={"P","PI","PID"}
    assert len({results[k].die_c[-1] for k in results})==3
    assert results["P"].power_w==results["PI"].power_w==results["PID"].power_w
    for name,trace in results.items():
        assert trace.mode==name and trace.provenance=="SIMULATED"
        assert len(trace.times_s)==len(trace.fan_fraction)==len(trace.die_c)
        assert all(0<=x<=1 for x in trace.fan_fraction)
        assert all(0<=x<=1 for x in trace.command_fraction)
        assert trace.metrics.observed_bounded
        assert abs(trace.metrics.energy_balance_residual_j)<1e-7
        assert trace.metrics.iae_c_s>0 and trace.metrics.itae_c_s2>0
        assert trace.metrics.peak_die_c>=trace.metrics.final_die_c


def test_disturbance_raises_temperature_when_control_action_disabled():
    s=ControlScenario(proportional_per_k=0,integral_per_k_s=0,derivative_s_per_k=0)
    with_pulse=simulate_control(s,mode="P")
    no_pulse=simulate_control(
        ControlScenario(proportional_per_k=0,integral_per_k_s=0,
                        derivative_s_per_k=0,disturbance_w=0),mode="P")
    assert with_pulse.die_c[-1]>no_pulse.die_c[-1]
    assert max(with_pulse.power_w)>max(no_pulse.power_w)


def test_pid_filtered_derivative_responds_to_sensor_perturbation():
    s=ControlScenario(sensor_noise_amplitude_c=1.0)
    p=simulate_control(s,mode="P")
    pid=simulate_control(s,mode="PID")
    assert pid.command_fraction!=p.command_fraction


def test_integral_is_bounded_and_fan_is_bounded_in_heavy_saturation():
    s=ControlScenario(target_c=20,base_power_w=250,disturbance_w=50,
                      max_integral_k_s=10,proportional_per_k=.1,
                      integral_per_k_s=.5,derivative_s_per_k=.1)
    result=simulate_control(s)
    assert result.metrics.saturated_fraction>.1
    assert all(0<=x<=1 for x in result.fan_fraction)
    assert result.metrics.fan_mean_fraction<=1
    assert abs(result.metrics.energy_balance_residual_j)<1e-6


def test_gain_sensitivity_is_reproducible_and_not_claimed_optimal():
    s=ControlScenario()
    assert gain_sensitivity(s)==gain_sensitivity(s)
    assert [v["gain_factor"] for v in gain_sensitivity(s)]==[.75,1,1.25]


def test_finite_settling_is_optional_and_must_not_claim_proof():
    s=ControlScenario(target_c=100)
    result=simulate_control(s)
    assert result.metrics.observed_settling_s is None


@pytest.mark.parametrize("kwargs",[
    {"duration_s":0},{"dt_s":-1},{"die_capacity_j_k":0},
    {"disturbance_at_s":200,"disturbance_end_s":100},
    {"disturbance_end_s":500},{"base_power_w":-1},
    {"target_c":-300},{"sensor_noise_amplitude_c":-1},
    {"derivative_filter_s":0},{"max_integral_k_s":0},
    {"fan_gain_w_k":float("inf")},{"proportional_per_k":float("nan")},
    {"dt_s":200},{"duration_s":30000,"dt_s":.01},
])
def test_invalid_configurations_rejected(kwargs):
    with pytest.raises(ValueError):
        ControlScenario(**kwargs)


def test_invalid_controller_rejected():
    with pytest.raises(ValueError,match="Controlador"):
        simulate_control(mode="UNKNOWN")


def test_cancel_token_prevents_unnecessary_computation():
    from expecto_process_manager.core.cancellation import Cancellation,Cancelled
    token=Cancellation()
    token.cancel()
    with pytest.raises(Cancelled):
        simulate_control(token=token)


def test_user_can_adjust_gains_without_activating_hardware(monkeypatch):
    monkeypatch.setattr(os,"system",lambda *_: (_ for _ in ()).throw(
        AssertionError("No OS invocation is allowed.")))
    simulate_control(ControlScenario(proportional_per_k=.04),mode="PID")


def test_advanced_control_ui_is_lazy_and_executes(tmp_path):
    from PySide6.QtWidgets import QApplication
    from expecto_process_manager.interface.main_window import MainWindow
    import time
    app=QApplication.instance() or QApplication([])
    window=MainWindow(settings_path=tmp_path/"settings.ini",
                      report_directory=tmp_path/"reports")
    try:
        assert 17 not in window.laboratory.created
        assert window.laboratory.search("controlo pid")
        assert window.laboratory.currentIndex()==17
        page=window.laboratory.ensure(17)
        page.duration.setText("20")
        page.start.setText("5")
        page.end.setText("12")
        page.execute()
        deadline=time.monotonic()+15
        while page.results is None and time.monotonic()<deadline:
            app.processEvents()
            time.sleep(.01)
        assert page.results is not None, page.note.text()
        assert set(page.results)=={"P","PI","PID"}
        assert "IAE=" in page.report.toPlainText()
        assert "SIMULATED" in page.note.text()
    finally:
        window.close()
        deadline=time.monotonic()+15
        while not window.closed_ready and time.monotonic()<deadline:
            app.processEvents()
            time.sleep(.01)
        assert window.closed_ready
