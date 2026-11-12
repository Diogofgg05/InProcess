"""Numerical Physics Lab 6.1: real convergence and energy consistency checks."""
from dataclasses import replace
import math
import pytest

from expecto_process_manager.physics.physical_lab6 import HeatSlab
from expecto_process_manager.physics.heat_implicit import (
    METHODS, solve_heat_61, semidiscrete_exact_center,
    temporal_order_study, spatial_order_study,
)


@pytest.mark.parametrize("method", METHODS)
def test_all_three_methods_match_independent_solution(method):
    model = HeatSlab(nodes=21)
    result = solve_heat_61(model, duration_s=4, dt_s=.04, method=method)
    assert result.positions_m[0] == 0
    assert result.times_s[-1] == pytest.approx(4)
    assert result.profiles_c[-1][0] == pytest.approx(model.ambient_c)
    assert result.profiles_c[-1][-1] == pytest.approx(model.ambient_c)
    assert result.rmse_c < .1
    assert result.max_error_c < .1
    assert abs(result.balance_error_j) < 1e-6


@pytest.mark.parametrize("method", ("backward_euler", "crank_nicolson"))
def test_implicit_solvers_allow_fourier_above_explicit_stability_limit(method):
    model = HeatSlab(nodes=21)
    result = solve_heat_61(model, duration_s=4,dt_s=1.0,method=method)
    assert result.fourier > .5
    assert math.isfinite(result.profiles_c[-1][model.nodes//2])
    assert abs(result.balance_error_j) < 1e-6


def test_explicit_rejects_same_unstable_fourier():
    with pytest.raises(ValueError, match="instável"):
        solve_heat_61(HeatSlab(),duration_s=4,dt_s=1.0,method="explicit")


def test_cn_is_more_accurate_than_backward_euler_at_equal_step():
    model = HeatSlab()
    be = solve_heat_61(model,duration_s=4,dt_s=.2,method="backward_euler")
    cn = solve_heat_61(model,duration_s=4,dt_s=.2,method="crank_nicolson")
    assert cn.max_error_c < be.max_error_c


def test_center_reference_has_continuous_initial_value():
    model = HeatSlab(nodes=21)
    assert semidiscrete_exact_center(model,0) == pytest.approx(model.initial_c)
    assert semidiscrete_exact_center(model,4) < model.initial_c


@pytest.mark.parametrize("method,expected_order", [
    ("explicit", 1), ("backward_euler", 1), ("crank_nicolson", 2),
])
def test_global_temporal_order_is_compared_to_semidiscrete_reference(method,expected_order):
    rows = temporal_order_study(HeatSlab(nodes=21),duration_s=4,method=method)
    assert len(rows) == 4
    assert [row["steps"] for row in rows] == [20,40,80,160]
    assert rows[-1]["error_c"] < rows[0]["error_c"]
    assert rows[-1]["observed_order"] == pytest.approx(expected_order,abs=.12)
    assert all(abs(row["energy_balance_j"]) < 1e-6 for row in rows)


def test_spatial_order_is_near_two_without_time_error():
    rows = spatial_order_study(HeatSlab(),duration_s=4)
    assert len(rows) == 5
    assert rows[-1]["error_c"] < rows[0]["error_c"]
    assert rows[-1]["observed_order"] == pytest.approx(2,abs=.06)


def test_reference_rejects_even_grid_and_negative_time():
    with pytest.raises(ValueError, match="ímpar"):
        semidiscrete_exact_center(HeatSlab(nodes=20),4)
    with pytest.raises(ValueError, match="Tempo"):
        semidiscrete_exact_center(HeatSlab(),-1)
    with pytest.raises(ValueError, match="ímpar"):
        temporal_order_study(HeatSlab(nodes=20))


@pytest.mark.parametrize("invalid", [0,-1,float("nan"),float("inf"),True,".1"])
def test_invalid_implicit_step_rejected(invalid):
    with pytest.raises(ValueError):
        solve_heat_61(dt_s=invalid)


def test_big_implicit_job_is_rejected_without_allocating_dense_matrix():
    with pytest.raises(ValueError,match="Orçamento"):
        solve_heat_61(HeatSlab(nodes=401),duration_s=10000,dt_s=.01)


def test_invalid_method_is_not_silently_replaced():
    with pytest.raises(ValueError,match="Método"):
        solve_heat_61(method="rk4")


def test_existing_explicit_solver_and_new_api_match_exactly():
    from expecto_process_manager.physics.physical_lab6 import solve_heat
    model=HeatSlab()
    assert solve_heat_61(model,duration_s=3,method="explicit") == solve_heat(model,duration_s=3)


def test_energy_conservation_at_large_implicit_fourier():
    model=HeatSlab(nodes=21)
    for method in ("backward_euler","crank_nicolson"):
        result=solve_heat_61(model,duration_s=10,dt_s=2,method=method)
        assert result.energy_initial_j > result.energy_final_j
        assert result.boundary_energy_j > 0
        assert abs(result.balance_error_j) < 1e-7


def test_cancellation_checks_are_respected():
    from expecto_process_manager.core.cancellation import Cancellation, Cancelled
    token=Cancellation()
    token.cancel()
    with pytest.raises(Cancelled):
        solve_heat_61(HeatSlab(),duration_s=4,dt_s=.01,token=token)
