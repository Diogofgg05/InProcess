import pytest

from expecto_process_manager.physics.coupled_thermal import CoupledThermalConfig, simulate_coupled


def test_internal_coupling_cancels_when_summing_component_energy_rates():
    config = CoupledThermalConfig(cpu_capacity=100, gpu_capacity=150, cpu_dissipation=0, gpu_dissipation=0, coupling=5)
    cpu_rate, gpu_rate = config.rates(80, 30, 0, 0)
    assert config.cpu_capacity * cpu_rate + config.gpu_capacity * gpu_rate == pytest.approx(0, abs=1e-12)
    assert cpu_rate < 0 < gpu_rate


@pytest.mark.parametrize("method", ["euler", "heun", "rk4"])
def test_isolated_exchange_preserves_total_energy_and_approaches_weighted_equilibrium(method):
    config = CoupledThermalConfig(cpu_capacity=100, gpu_capacity=150, cpu_dissipation=0, gpu_dissipation=0, coupling=5)
    result = simulate_coupled(config, 80, 30, 0, 0, 300, .25, method)
    equilibrium = (100 * 80 + 150 * 30) / 250
    assert result.cpu_temperatures[-1] == pytest.approx(equilibrium, abs=1e-7)
    assert result.gpu_temperatures[-1] == pytest.approx(equilibrium, abs=1e-7)
    assert max(abs(value) for value in result.stored_energy) < 1e-8
    assert max(abs(value) for value in result.balance_residual) < 1e-8


@pytest.mark.parametrize("method,tolerance", [("euler", .005), ("heun", 2e-6), ("rk4", 1e-10)])
def test_zero_coupling_matches_independent_analytic_solutions(method, tolerance):
    config = CoupledThermalConfig(coupling=0)
    result = simulate_coupled(config, duration=120, dt=.1, method=method)
    assert result.cpu_temperatures == pytest.approx(result.independent_cpu, abs=tolerance)
    assert result.gpu_temperatures == pytest.approx(result.independent_gpu, abs=tolerance)
    assert max(abs(value) for value in result.balance_residual) < 1e-8


def test_coupled_energy_balance_with_external_input_and_dissipation():
    result = simulate_coupled(CoupledThermalConfig(), duration=30, dt=.7)
    assert result.times[-1] == 30
    assert result.input_energy[-1] == pytest.approx((45 + 60) * 30)
    assert result.input_energy[-1] - result.dissipated_energy[-1] == pytest.approx(result.stored_energy[-1], abs=1e-8)
    assert "SIMULATED" in result.report
    assert "não o erro numérico" in result.report


def test_invalid_coupled_parameters_are_rejected():
    with pytest.raises(ValueError, match="positivas"):
        CoupledThermalConfig(cpu_capacity=0)
    with pytest.raises(ValueError, match="negativos"):
        CoupledThermalConfig(coupling=-1)
    with pytest.raises(ValueError, match="não negativas"):
        simulate_coupled(CoupledThermalConfig(), cpu_power=-1)
