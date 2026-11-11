import math

import pytest

from expecto_process_manager.core.cancellation import Cancellation, Cancelled
from expecto_process_manager.physics.cooling import simulate_cooling


def test_constant_ventilation_matches_independent_analytic_cooling():
    result = simulate_cooling(initial=60, ambient=22, capacity=100,
                              base_dissipation=2, ventilation_gain=2, ventilation=.5,
                              duration=120, dt=.1)
    exact = [22 + 38 * math.exp(-3 * time / 100) for time in result.times]
    assert result.reference == pytest.approx(exact, abs=1e-12)
    assert result.coefficient_values == [3] * len(result.times)
    assert result.temperatures["RK4"] == pytest.approx(exact, abs=1e-10)
    errors = {name: max(abs(value - expected) for value, expected in zip(values, exact))
              for name, values in result.temperatures.items()}
    assert errors["RK4"] < errors["Heun"] < errors["Euler"]
    assert "SIMULATED" in result.report
    assert "hipótese ilustrativa" in result.report
    assert "não representa RPM" in result.report


def test_variable_ventilation_preserves_energy_and_does_not_claim_exact_reference():
    result = simulate_cooling(ventilation=lambda t: .5 + .4 * math.sin(t / 15), duration=33, dt=.7)
    assert result.reference is None
    assert result.times[-1] == 33
    assert max(result.coefficient_values) > min(result.coefficient_values)
    for name, temperatures in result.temperatures.items():
        residual = [100 * (temp - 60) + energy for temp, energy in zip(temperatures, result.loss_energy[name])]
        assert max(abs(value) for value in residual) < 1e-8
        assert result.loss_energy[name][-1] > 0


def test_isolated_node_and_below_ambient_signs():
    isolated = simulate_cooling(base_dissipation=0, ventilation_gain=0, duration=3)
    assert isolated.reference == [60] * len(isolated.times)
    for values in isolated.temperatures.values():
        assert values == [60] * len(values)
    warming = simulate_cooling(initial=10, ambient=22, duration=10)
    assert 10 < warming.temperatures["RK4"][-1] < 22
    assert warming.loss_energy["RK4"][-1] < 0


@pytest.mark.parametrize("value", [-.1, 1.1, math.nan, math.inf, "fast"])
def test_rejects_invalid_scalar_ventilation(value):
    with pytest.raises(ValueError):
        simulate_cooling(ventilation=value)


@pytest.mark.parametrize("function", [lambda _t: -1, lambda _t: 1.01, lambda _t: math.nan, lambda _t: [1],
                                     lambda t: 0 if t == 0 else 2])
def test_rejects_invalid_function_values_including_internal_stages(function):
    with pytest.raises(ValueError):
        simulate_cooling(ventilation=function, duration=1, dt=.5)


@pytest.mark.parametrize("kwargs", [{"capacity": 0}, {"base_dissipation": -1}, {"ventilation_gain": -1},
                                    {"ambient": math.inf}, {"dt": 0}, {"duration": -1}])
def test_rejects_invalid_physical_parameters(kwargs):
    with pytest.raises(ValueError):
        simulate_cooling(**kwargs)


def test_cooling_supports_cooperative_cancellation_and_step_limit():
    token = Cancellation()
    token.cancel()
    with pytest.raises(Cancelled):
        simulate_cooling(token=token)
    with pytest.raises(ValueError, match="passos"):
        simulate_cooling(duration=1, dt=1 / 200001)
