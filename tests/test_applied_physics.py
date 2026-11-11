import math

import pytest

from expecto_process_manager.core.cancellation import Cancellation, Cancelled
from expecto_process_manager.physics.motion import MotionConfig, run_motion
from expecto_process_manager.physics.thermodynamics import (
    analyze_compression, import_compression_csv, synthetic_compression,
)


def test_agv_braking_resolves_event_and_never_moves_after_stop():
    experiment = run_motion(MotionConfig(velocity=10, deceleration=2, dt=.3, duration=9))
    assert experiment.reference.stopping_time == pytest.approx(5)
    assert experiment.reference.stopping_distance == pytest.approx(25)
    for method, trajectory in experiment.trajectories.items():
        assert trajectory.stopping_time == pytest.approx(5, abs=1e-11)
        assert min(trajectory.velocities) >= 0
        stopped = [i for i, time in enumerate(experiment.times) if time > trajectory.stopping_time]
        assert all(trajectory.positions[i] == trajectory.positions[stopped[0]] for i in stopped)
        assert all(trajectory.velocities[i] == 0 for i in stopped)
        if method != "Euler":
            assert trajectory.stopping_distance == pytest.approx(25, abs=1e-10)


def test_euler_stopping_distance_converges_without_replacing_by_exact_result():
    errors = []
    for dt in (.2, .1, .05):
        experiment = run_motion(MotionConfig(dt=dt))
        errors.append(abs(experiment.trajectories["Euler"].stopping_distance-25))
    assert errors[2] < errors[1] < errors[0]
    assert errors[1] == pytest.approx(errors[0]/2)


def test_drag_reference_and_rk4_converge_and_small_drag_is_stable():
    experiment = run_motion(MotionConfig(friction=.15, dt=.05))
    reference = math.log1p(.15*10/2)/.15
    assert experiment.reference.stopping_time == pytest.approx(reference)
    assert experiment.trajectories["RK4"].stopping_time == pytest.approx(reference, abs=1e-6)
    tiny_drag = run_motion(MotionConfig(friction=1e-14))
    assert tiny_drag.reference.stopping_distance == pytest.approx(25, abs=1e-10)


def test_initially_stationary_vehicle_does_not_move_during_braking():
    experiment = run_motion(MotionConfig(velocity=0, position=12))
    for trajectory in experiment.trajectories.values():
        assert trajectory.positions == [12]*len(experiment.times)
        assert trajectory.stopping_distance == 0


@pytest.mark.parametrize("arguments", [{"dt": 0}, {"velocity": -1}, {"friction": 20},
                                      {"position": math.nan}, {"duration": 1e9}])
def test_invalid_motion_parameters_rejected(arguments):
    with pytest.raises(ValueError):
        MotionConfig(**arguments)


def test_compression_work_sign_and_simpson_exact_polynomial():
    volumes = [1, .75, .5, .25, .125]
    constant = analyze_compression(volumes, [2]*5)
    assert constant.work_by_gas == pytest.approx(-1.75)
    assert constant.work_on_gas == pytest.approx(1.75)
    assert constant.simpson_work is None  # Uneven final interval is not hidden.
    volumes = [1, .75, .5, .25, .1]  # still not uniform
    assert analyze_compression(volumes, [v*v for v in volumes]).simpson_work is None
    volumes = [1, .8, .6, .4, .2]
    polynomial = analyze_compression(volumes, [v*v for v in volumes])
    assert polynomial.simpson_work == pytest.approx((.2**3-1)/3)


def test_polytropic_fit_recovers_synthetic_exponent():
    experiment = synthetic_compression(samples=101, exponent=1.3)
    assert experiment.polytropic_index == pytest.approx(1.3)
    assert experiment.fit_rmse < 1e-8
    assert "simulado" in experiment.provenance
    assert experiment.work_by_gas < 0
    assert experiment.fitted_pressures == pytest.approx(experiment.pressures)


def test_cycles_preserve_order_and_signed_work_without_global_fit():
    experiment = analyze_compression([1, 2, 2, 1, 1], [1, 1, 2, 2, 1])
    assert experiment.volumes == [1, 2, 2, 1, 1]
    assert experiment.work_by_gas == pytest.approx(-1)
    assert experiment.simpson_work is None
    assert experiment.polytropic_index is None
    assert experiment.fitted_pressures is None


@pytest.mark.parametrize("volumes,pressures", [([], []), ([1, 2], [1]), ([1, 0], [1, 2]),
                                              ([1, 2], [math.inf, 2]), ([1, 2], [-1, 2])])
def test_invalid_compression_samples_rejected(volumes, pressures):
    with pytest.raises(ValueError):
        analyze_compression(volumes, pressures)


def test_import_csv_requires_explicit_units_and_rejects_malformed_rows(tmp_path):
    path = tmp_path/"compressor.csv"
    path.write_text("volume_m3,pressure_pa\n0.01,100000\n0.005,200000\n", encoding="utf-8")
    result = import_compression_csv(path)
    assert result.work_by_gas == pytest.approx(-750)
    assert "não verificada" in result.provenance
    path.write_text("volume,pressure\n1,2\n2,3\n", encoding="utf-8")
    with pytest.raises(ValueError, match="cabeçalhos"):
        import_compression_csv(path)
    path.write_text("volume_m3,pressure_pa\n1,2,3\n2,3\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Linha 2"):
        import_compression_csv(path)


def test_applied_experiments_honor_cancellation():
    token = Cancellation()
    token.cancel()
    with pytest.raises(Cancelled):
        run_motion(MotionConfig(), token)
    with pytest.raises(Cancelled):
        synthetic_compression(token=token)
