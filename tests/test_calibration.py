"""Requirement I: identifiable fitting and obligatory independent holdout."""
import math

import pytest

from expecto_process_manager.core.cancellation import Cancellation, Cancelled
from expecto_process_manager.physics.calibration import ThermalSeries, fit_thermal, predict_zoh
from expecto_process_manager.physics.numerical.signals import add_gaussian_noise


def thermal_data(start=0, count=401, step=.5, initial=30, power=45):
    times = [start + i * step for i in range(count)]
    powers = [float(power)] * count
    temperatures = predict_zoh(times, powers, initial, 22, 100, 2)
    return ThermalSeries(times, temperatures, powers)


def test_exact_zoh_recovers_parameters_and_reserves_disjoint_holdout():
    data = thermal_data()
    result = fit_thermal(data.times, data.temperatures, data.powers, 22)
    assert result.capacity == pytest.approx(100, rel=1e-8)
    assert result.dissipation == pytest.approx(2, rel=1e-8)
    assert result.time_constant == pytest.approx(50, rel=1e-8)
    assert result.training.times[-1] < result.validation.times[0]
    assert len(result.training.times) + len(result.validation.times) == len(data.times)
    assert result.validation.errors["rmse"] < 1e-9
    assert result.condition_number > 1
    assert "ESTIMATED" in result.report
    assert "não equivale a uma repetição experimental independente" in result.report


def test_exact_interval_model_handles_nonuniform_steps_and_power_changes():
    times = [0.0]
    for i in range(1, 301):
        times.append(times[-1] + (.3 if i % 3 else .8))
    powers = [10 + 40 * (i % 65 < 30) for i in range(len(times))]
    temperatures = predict_zoh(times, powers, 35, 22, 120, 1.5)
    result = fit_thermal(times, temperatures, powers, 22)
    assert result.capacity == pytest.approx(120, rel=1e-7)
    assert result.dissipation == pytest.approx(1.5, rel=1e-7)
    assert result.validation.errors["rmse"] < 1e-8


def test_derivative_regression_documents_approximation_and_recovers_smooth_case():
    data = thermal_data(step=.1)
    result = fit_thermal(data.times, data.temperatures, data.powers, 22, method="derivative")
    assert result.capacity == pytest.approx(100, rel=2e-5)
    assert result.dissipation == pytest.approx(2, rel=2e-5)
    assert "viés" in result.report
    assert "ruído" in result.report


def test_separate_holdout_does_not_affect_fitted_parameters_or_reuse_samples():
    training = thermal_data(count=200)
    holdout = thermal_data(start=200, count=100, initial=35, power=30)
    baseline = fit_thermal(training.times, training.temperatures, training.powers, 22, validation=holdout)
    changed = ThermalSeries(holdout.times, [value + .5 for value in holdout.temperatures], holdout.powers)
    fitted = fit_thermal(training.times, training.temperatures, training.powers, 22, validation=changed)
    assert fitted.capacity == baseline.capacity
    assert fitted.dissipation == baseline.dissipation
    assert fitted.validation.errors["rmse"] > baseline.validation.errors["rmse"]
    with pytest.raises(ValueError, match="disjuntas"):
        fit_thermal(training.times, training.temperatures, training.powers, 22, validation=training)


def test_noisy_synthetic_data_reports_real_residuals_and_holdout_error():
    data = thermal_data()
    noisy = add_gaussian_noise(data.temperatures, .02, seed=123)
    result = fit_thermal(data.times, noisy, data.powers, 22)
    assert result.capacity == pytest.approx(100, rel=.1)
    assert result.dissipation == pytest.approx(2, rel=.05)
    assert result.training.errors["rmse"] > 0
    assert result.validation.errors["rmse"] > 0
    assert math.isfinite(result.validation.residual_std)
    assert result.validation.residuals[0] == 0
    assert result.validation.errors["mae"] == pytest.approx(sum(abs(value) for value in result.validation.residuals[1:]) / (len(result.validation.residuals) - 1))


@pytest.mark.parametrize("method", ["integral_zoh", "derivative"])
def test_i_rejects_zero_power_cooling_where_only_k_over_c_is_identifiable(method):
    data = thermal_data(power=0, initial=50)
    with pytest.raises(ValueError, match="k/C"):
        fit_thermal(data.times, data.temperatures, data.powers, 22, method=method)


@pytest.mark.parametrize("method", ["integral_zoh", "derivative"])
def test_i_rejects_constant_equilibrium_and_insufficient_samples(method):
    with pytest.raises(ValueError, match="constante"):
        fit_thermal(list(range(20)), [44.5] * 20, [45] * 20, 22, method=method)
    with pytest.raises(ValueError, match="12"):
        fit_thermal(list(range(10)), list(range(10)), [45] * 10, 22, method=method)


def test_invalid_power_times_temperature_and_cancelled_fit():
    data = thermal_data()
    with pytest.raises(ValueError, match="não negativas"):
        fit_thermal(data.times, data.temperatures, [-1] * len(data.times), 22)
    with pytest.raises(ValueError, match="crescentes"):
        fit_thermal([0] * 20, list(range(20)), [45] * 20, 22)
    with pytest.raises(ValueError, match="finitos"):
        fit_thermal(data.times, data.temperatures, data.powers, math.nan)
    token = Cancellation()
    token.cancel()
    with pytest.raises(Cancelled):
        fit_thermal(data.times, data.temperatures, data.powers, 22, token=token)


def test_zoh_power_uses_left_sample_and_last_sample_does_not_affect_interval():
    one = predict_zoh([0, 1, 2], [0, 50, 99], 22, 22, 100, 2)
    two = predict_zoh([0, 1, 2], [0, 50, 0], 22, 22, 100, 2)
    assert one == two
    assert one[1] == 22
    assert one[2] > 22
