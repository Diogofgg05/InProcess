"""The existing thermal experiment now compares three genuinely integrated methods."""
import json
import math

import pytest

from expecto_process_manager.core.cancellation import Cancellation, Cancelled
from expecto_process_manager.physics.euler import simulate
from expecto_process_manager.physics.integration import integrate
from expecto_process_manager.physics.thermal_model import ThermalModel
from expecto_process_manager.simulation.experiments import (
    ExperimentConfig, load_experiment, run_experiment, save_experiment,
)
from expecto_process_manager.simulation.scenarios import SCENARIOS, power_profile


def test_three_thermal_methods_match_independent_constant_power_formula():
    config = ExperimentConfig(initial=30, ambient=22, power=45, capacity=10,
                              dissipation=2, duration=10, dt=.25, noise=0)
    experiment = run_experiment(config)
    reference = [44.5 + (30 - 44.5) * math.exp(-.2 * t) for t in experiment.simulation.times]
    assert experiment.simulation.reference == pytest.approx(reference, abs=1e-12)
    assert set(experiment.method_solutions) == {"Euler", "Heun", "RK4"}
    assert experiment.method_solutions["Euler"] == experiment.simulation.temperatures
    assert experiment.error == experiment.method_errors["Euler"]
    errors = {name: values["rmse"] for name, values in experiment.method_errors.items()}
    assert errors["RK4"] < errors["Heun"] < errors["Euler"]
    assert errors["RK4"] < 1e-6


@pytest.mark.parametrize("method,expected", [("Euler", 1), ("Heun", 2), ("RK4", 4)])
def test_thermal_study_observes_first_second_and_fourth_orders(method, expected):
    experiment = run_experiment(ExperimentConfig(initial=30, capacity=10, dissipation=2, duration=10, dt=.1))
    rows = experiment.method_convergence[method]
    assert [row["dt"] for row in rows] == [1, .5, .1, .05, .01]
    selected = next(row for row in rows if row["dt"] == .05)
    assert selected["order"] == pytest.approx(expected, abs=.1)
    assert selected["seconds"] >= 0
    assert all(row["steps"] <= 20000 for row in rows if row["omitted_reason"] is None)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_legacy_euler_contract_and_noise_preserved_for_every_scenario(scenario):
    config = ExperimentConfig(duration=3, dt=.5, seed=123, noise=.2, scenario=scenario)
    experiment = run_experiment(config)
    original = simulate(ThermalModel(config.ambient, config.capacity, config.dissipation), config.initial,
                        power_profile(scenario, config.power, config.duration), config.duration, config.dt)
    assert experiment.simulation == original
    assert experiment.method_solutions["Euler"] == original.temperatures
    assert len(experiment.noisy) == len(original.times)
    assert len(experiment.derivatives) == 3
    assert [step for step, _error in experiment.convergence] == [.01, .05, .1, .5, 1]


def test_all_stages_keep_interval_power_at_a_csv_jump_and_ignore_final_future_power():
    config = ExperimentConfig(initial=22, ambient=22, capacity=10, dissipation=1,
                              duration=3, dt=.5, noise=0, source_times=[10, 11, 12, 13],
                              source_powers=[0, 50, 0, 1000], provenance="importado; origem não verificada")
    experiment = run_experiment(config)
    for values in experiment.method_solutions.values():
        # If Heun/RK4 sampled P(t+h), heat would appear before the jump t=1.
        assert values[:3] == [22, 22, 22]
    expected = 22 + 50 * (1 - math.exp(-1 / 10)) * math.exp(-1 / 10)
    assert experiment.simulation.reference[-1] == pytest.approx(expected)
    assert experiment.method_solutions["RK4"][-1] == pytest.approx(expected, abs=5e-7)
    assert experiment.energy_zoh[-1] == 50
    assert experiment.energy[-1] == 300  # endpoint interpolation differs from held input
    assert experiment.simulation.provenance == "simulado"


def test_unaligned_jump_reference_describes_held_simulation_and_states_limitation():
    config = ExperimentConfig(initial=22, ambient=22, duration=1.5, dt=1,
                              source_times=[0, .75, 1.5], source_powers=[0, 60, 0],
                              provenance="importado; origem não verificada")
    experiment = run_experiment(config)
    assert experiment.energy_zoh[-1] == 30  # 60 W held over [1,1.5]
    assert experiment.method_solutions["Heun"][1] == 22
    assert experiment.method_solutions["RK4"][1] == 22
    assert "não é a solução exata de saltos não alinhados" in experiment.report


def test_energy_units_and_trapezoid_loss_balance_are_explicit():
    config = ExperimentConfig(initial=47, ambient=22, power=50, dissipation=2,
                              duration=10, dt=.5, noise=0)
    experiment = run_experiment(config)
    assert experiment.energy_zoh[-1] == 500  # W*s = J
    assert experiment.energy_zoh[-1] / 3600 == pytest.approx(5 / 36)
    for method, values in experiment.method_solutions.items():
        assert values == [47] * len(values)
        assert experiment.energy_balance[method] == pytest.approx([0] * len(values), abs=1e-10)
        losses = integrate(experiment.simulation.times, [2 * (value - 22) for value in values])
        assert losses == 500


def test_nontrivial_energy_residual_converges_with_loss_quadrature():
    residuals = []
    for step in (.2, .1, .05):
        config = ExperimentConfig(initial=30, capacity=10, dissipation=2, duration=10, dt=step, noise=0)
        experiment = run_experiment(config)
        temperature = experiment.method_solutions["RK4"]
        losses = integrate(experiment.simulation.times, [2 * (value - 22) for value in temperature])
        residual = experiment.energy_zoh[-1] - 10 * (temperature[-1] - 30) - losses
        assert experiment.energy_balance["RK4"][-1] == pytest.approx(residual, abs=1e-10)
        residuals.append(abs(residual))
    assert residuals[0] / residuals[1] == pytest.approx(4, rel=.01)
    assert residuals[1] / residuals[2] == pytest.approx(4, rel=.01)


def test_bounded_convergence_records_omissions_and_real_timing_scope():
    experiment = run_experiment(ExperimentConfig(duration=360, dt=1))
    rows = [row for values in experiment.method_convergence.values() for row in values]
    assert sum(row["steps"] for row in rows if row["omitted_reason"] is None) <= 60000
    assert any(row["omitted_reason"] and row["seconds"] is None for row in rows)
    assert all(math.isfinite(value) and value >= 0 for value in experiment.method_timings.values())
    assert "apenas o ciclo de temperaturas" in experiment.report
    assert "omitido" in experiment.report


def test_comparisons_saved_as_optional_true_results_and_legacy_files_recomputed(tmp_path):
    experiment = run_experiment(ExperimentConfig(duration=3, dt=.1, noise=.1))
    path = tmp_path / "three-methods.json"
    save_experiment(str(path), experiment, Cancellation())
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["comparison"]["method_solutions"] == experiment.method_solutions
    assert payload["comparison"]["method_timings_s"] == experiment.method_timings
    assert payload["comparison"]["energy_zoh_j"] == experiment.energy_zoh
    payload.pop("comparison")
    payload["results"]["temperatures"] = [999]
    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_experiment(str(path), Cancellation())
    assert loaded.simulation == experiment.simulation
    assert loaded.method_solutions == experiment.method_solutions
    assert loaded.report == experiment.report


def test_comparison_obeys_cooperative_cancellation():
    token = Cancellation()
    token.cancel()
    with pytest.raises(Cancelled):
        run_experiment(ExperimentConfig(), token)
