"""Analytic requirements A-H; calibration identifiability is tested separately."""
import math

import pytest

from expecto_process_manager.core.cancellation import Cancellation, Cancelled
from expecto_process_manager.physics.numerical.derivatives import differentiate
from expecto_process_manager.physics.numerical.integration import integrate_midpoints, quadrature
from expecto_process_manager.physics.numerical.ode import solve_ivp
from expecto_process_manager.physics.numerical.signals import add_gaussian_noise, exponential_filter, moving_average
from expecto_process_manager.physics.numerical.thermalcomparison import compare_thermal, time_to_threshold
from expecto_process_manager.physics.numerical.validation import convergence_study, linear_stability, metrics, sensitivity_study
from expecto_process_manager.physics.thermal_model import ThermalModel


@pytest.mark.parametrize("times", [[i / 10 for i in range(11)], [0, .07, .2, .55, 1.1, 2.0]])
def test_a_quadratic_derivative_including_nonuniform_endpoints(times):
    values = [time * time for time in times]
    assert differentiate(times, values) == pytest.approx([2 * time for time in times])
    for method in ("forward", "backward", "central"):
        assert differentiate(times, values, method, order=2) == pytest.approx([2] * len(times))


@pytest.mark.parametrize("method", ["forward", "backward", "central"])
def test_first_derivative_preserves_linear_signal_and_large_time_origin(method):
    times = [1e9 + i * .25 for i in range(6)]
    assert differentiate(times, [4 + i * .75 for i in range(6)], method) == pytest.approx([3] * 6)


def test_forward_backward_are_distinct_one_sided_stencils():
    assert differentiate([0, 1, 2], [0, 1, 4], "forward") == [1, 3, 3]
    assert differentiate([0, 1, 2], [0, 1, 4], "backward") == [1, 1, 3]
    assert differentiate([0, .5], [1, 2]) == [2, 2]


def test_b_integral_of_x_squared_and_true_midpoint_inputs():
    edges = [i / 100 for i in range(101)]
    values = [x * x for x in edges]
    exact = 1 / 3
    assert quadrature(edges, values, "simpson") == pytest.approx(exact, abs=1e-14)
    left = quadrature(edges, values, "left")
    right = quadrature(edges, values, "right")
    trap = quadrature(edges, values)
    midpoint = integrate_midpoints(edges, [((a + b) / 2) ** 2 for a, b in zip(edges, edges[1:])])
    assert left < midpoint < exact < trap < right
    assert midpoint != trap
    with pytest.raises(ValueError, match="pontos médios"):
        quadrature(edges, values, "midpoint")


def test_nonuniform_trapezoid_and_midpoint_integrate_a_linear_function():
    edges = [0, .1, .3, .8, 1]
    assert quadrature(edges, [2 * x + 1 for x in edges]) == pytest.approx(2)
    assert integrate_midpoints(edges, [a + b + 1 for a, b in zip(edges, edges[1:])]) == pytest.approx(2)
    with pytest.raises(ValueError, match="uniformes"):
        quadrature(edges, [x * x for x in edges], "simpson")
    with pytest.raises(ValueError, match="par"):
        quadrature([0, 1], [0, 1], "simpson")


def test_c_euler_converges_to_exponential_and_shortens_final_interval():
    coarse = solve_ivp(lambda _t, y: -y[0], 1, (0, 1), .3)
    fine = solve_ivp(lambda _t, y: -y[0], [1], (0, 1), .03)
    assert coarse.times == [0, .3, .6, .8999999999999999, 1]
    assert abs(fine.values[-1][0] - math.exp(-1)) < abs(coarse.values[-1][0] - math.exp(-1))
    assert fine.times[-1] == 1
    assert coarse.values[0] == [1.0]


@pytest.mark.parametrize("method,expected_order", [("euler", 1), ("heun", 2), ("rk4", 4)])
def test_observed_convergence_orders(method, expected_order):
    rows = convergence_study(
        lambda dt: solve_ivp(lambda _t, y: -y[0], 1, (0, 1), dt, method).values[-1],
        [math.exp(-1)], [.2, .1, .05, .025],
    )
    assert rows[-1].observed_order == pytest.approx(expected_order, abs=.06)
    assert rows[-1].rmse < rows[0].rmse


def test_vector_ode_uses_time_and_preserves_callback_isolation():
    result = solve_ivp(lambda time, y: [y[1], -y[0] + 0 * time], [1, 0], (0, 2 * math.pi), .025, "rk4")
    assert result.values[-1] == pytest.approx([1, 0], abs=3e-8)
    def mutating_callback(_time, state):
        state[0] = 100
        return 0
    assert solve_ivp(mutating_callback, 1, (0, 1), .5).values == [[1], [1], [1]]


@pytest.mark.parametrize("method", ["left", "right", "trapezoid", "simpson"])
def test_d_constant_power_50_w_for_10_seconds_is_500_j(method):
    assert quadrature([0, 5, 10], [50, 50, 50], method) == 500
    assert integrate_midpoints([0, 5, 10], [50, 50]) == 500


def test_e_thermal_methods_against_independent_analytic_solution():
    result = compare_thermal(40, 22, 45, 100, 2, 120, .5)
    model = ThermalModel(ambient=22, capacity=100, dissipation=2)
    expected = [model.exact(40, 45, time) for time in result.times]
    assert result.reference == pytest.approx(expected)
    errors = {method: metrics(values, expected)["rmse"] for method, values in result.solutions.items()}
    assert errors["rk4"] < errors["heun"] < errors["euler"]
    assert errors["euler"] < .02
    assert "simulados" in result.report
    assert "potência elétrica medida" in result.report


def test_f_euler_unstable_above_2_over_decay_rate_and_boundary_is_marginal():
    assert linear_stability(2, .5).stable
    assert not linear_stability(2, 1).stable
    assert not linear_stability(2, 1.1).stable
    unstable = solve_ivp(lambda _t, y: -2 * y[0], 1, (0, 11), 1.1)
    assert abs(unstable.values[-1][0]) > 1
    assert linear_stability(2, 1.1, "rk4").stable


def test_g_seeded_noise_increases_derivative_error_and_filter_reduces_it():
    times = [i * .01 for i in range(1001)]
    clean = [math.sin(time) for time in times]
    noisy = add_gaussian_noise(clean, .02, seed=17)
    assert noisy == add_gaussian_noise(clean, .02, seed=17)
    assert noisy != add_gaussian_noise(clean, .02, seed=18)
    reference = [math.cos(time) for time in times][10:-10]
    clean_error = metrics(differentiate(times, clean)[10:-10], reference)["rmse"]
    noisy_error = metrics(differentiate(times, noisy)[10:-10], reference)["rmse"]
    filtered_error = metrics(differentiate(times, moving_average(noisy, 11))[10:-10], reference)["rmse"]
    assert noisy_error > clean_error * 100
    assert filtered_error < noisy_error / 3


def test_h_thermal_energy_balance_against_integrated_heat_loss():
    model = ThermalModel(ambient=22, capacity=100, dissipation=2)
    times = [index * .01 for index in range(10001)]
    temperatures = [model.exact(40, 45, time) for time in times]
    stored = model.capacity * (temperatures[-1] - temperatures[0])
    received = 45 * times[-1]
    dissipated = quadrature(times, [model.dissipation * (temp - model.ambient) for temp in temperatures], "simpson")
    assert stored + dissipated == pytest.approx(received, abs=1e-8)


def test_metrics_zero_reference_and_numerically_large_errors():
    result = metrics([1, 2], [0, 4])
    assert result["relative"] == [None, .5]
    assert result["mae"] == 1.5
    assert result["rmse"] == pytest.approx(math.sqrt(2.5))
    assert metrics([1e200], [0])["rmse"] == 1e200


def test_sensitivity_and_filters_have_explicit_parameters():
    sensitivity = sensitivity_study(lambda p: p * p, 2, .01)
    assert sensitivity.derivative == pytest.approx([4])
    assert sensitivity.relative == pytest.approx([2])
    assert moving_average([1, 2, 3], 3) == [1.5, 2, 2.5]
    assert exponential_filter([0, 1, 1], .5) == [0, .5, .75]
    assert exponential_filter([0, 1], 1, initial=5) == [5, 1]


def test_threshold_time_reaches_target_and_rejects_asymptotic_target():
    time = time_to_threshold(40, 22, 45, 100, 2, 42)
    assert time is not None and time > 0
    assert ThermalModel(22, 100, 2).exact(40, 45, time) == pytest.approx(42)
    assert time_to_threshold(40, 22, 45, 100, 2, 44.5) is None
    assert time_to_threshold(40, 22, 45, 100, 2, 30) is None
    assert time_to_threshold(40, 22, 45, 100, 2, 40) == 0


def test_ode_limits_invalid_states_dimensions_and_cooperative_cancellation():
    for dt in (0, -1, float("nan"), 1 / 200001):
        with pytest.raises(ValueError):
            solve_ivp(lambda _t, y: -y[0], 1, (0, 1), dt)
    with pytest.raises(ValueError, match="dimensão"):
        solve_ivp(lambda _t, y: [1, 2], 1, (0, 1), .1)
    with pytest.raises(ValueError, match="finitos"):
        solve_ivp(lambda _t, y: float("nan"), 1, (0, 1), .1)
    token = Cancellation()
    token.cancel()
    with pytest.raises(Cancelled):
        solve_ivp(lambda _t, y: -y[0], 1, (0, 1), .1, token=token)
    with pytest.raises(Cancelled):
        compare_thermal(40, 22, 45, 100, 2, 10, .1, token=token)


@pytest.mark.parametrize("times,values", [([0, 0], [1, 2]), ([1, 0], [1, 2]), ([0, 1], [1]), ([0, float("inf")], [1, 2])])
def test_sample_validation_shared_by_quadrature_and_derivatives(times, values):
    with pytest.raises(ValueError):
        differentiate(times, values)
    with pytest.raises(ValueError):
        quadrature(times, values)
