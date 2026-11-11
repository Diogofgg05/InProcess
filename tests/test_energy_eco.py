from dataclasses import replace
import math

import pytest

from expecto_process_manager.core.cancellation import Cancellation, Cancelled
from expecto_process_manager.core.energy import integrate_power, load_power_csv
from expecto_process_manager.optimization.eco import (
    PolicyRun, compare_policies, load_policy_csv, synthetic_policy_runs,
)


def test_constant_power_energy_and_units():
    energy = integrate_power([20, 25, 30], [50, 50, 50])
    assert energy.joules == pytest.approx(500)
    assert energy.watt_hours == pytest.approx(500/3600)
    assert energy.duration == 10
    assert energy.average_power == 50
    assert energy.peak_power == 50


def test_irregular_samples_integrate_linear_power_exactly():
    result = integrate_power([0, .25, 2, 5], [2, 2.5, 6, 12])
    assert result.joules == pytest.approx(35)


def test_lower_power_does_not_imply_lower_energy():
    result = compare_policies(synthetic_policy_runs())
    rows = {row.policy: row for row in result.rows}
    assert rows["NORMAL"].energy_j == 600
    assert rows["ECO"].energy_j == 675
    assert rows["ECO"].average_power < rows["NORMAL"].average_power
    assert result.recommendation == "ULTRA ECO"
    assert result.comparable
    assert "não demonstram poupança real" in result.report
    assert rows["NORMAL"].efficiency == pytest.approx(1/600)


def test_duration_and_temperature_constraints_filter_profiles():
    runs = synthetic_policy_runs()
    deadline = compare_policies(runs, max_duration=18)
    assert deadline.recommendation == "NORMAL"
    assert [row.policy for row in deadline.feasible] == ["NORMAL", "ECO"]
    restricted = compare_policies(runs, max_duration=18, max_temperature=65)
    assert restricted.recommendation == "ECO"
    none = compare_policies(runs, max_duration=12, max_temperature=65)
    assert none.recommendation is None
    assert not none.feasible


def test_missing_temperature_cannot_certify_temperature_limit():
    runs = [replace(run, temperatures=None) for run in synthetic_policy_runs()]
    assert compare_policies(runs).recommendation == "ULTRA ECO"
    limited = compare_policies(runs, max_temperature=80)
    assert not limited.feasible
    assert limited.recommendation is None


@pytest.mark.parametrize("change", [
    {"task_id": "outra tarefa"}, {"work_units": 2}, {"work_label": "outro trabalho"},
    {"work_completed": False}, {"provenance": "MEASURED"}, {"powers": None},
])
def test_incomparable_work_or_provenance_never_recommends(change):
    runs = synthetic_policy_runs()
    runs[1] = replace(runs[1], **change)
    comparison = compare_policies(runs)
    assert not comparison.comparable
    assert comparison.recommendation is None
    assert comparison.reasons


def test_task_identity_is_required_and_single_profile_is_not_comparison():
    runs = [replace(run, task_id="") for run in synthetic_policy_runs()]
    assert compare_policies(runs).recommendation is None
    assert compare_policies(synthetic_policy_runs()[:1]).recommendation is None


def test_zero_trace_has_no_infinite_efficiency():
    runs = synthetic_policy_runs()
    runs[0] = replace(runs[0], powers=[0, 0, 0])
    metrics = compare_policies(runs).rows[0]
    assert metrics.energy_j == 0
    assert metrics.efficiency is None


@pytest.mark.parametrize("times,powers", [([0], [50]), ([1, 1], [1, 2]), ([2, 1], [1, 2]),
                                        ([0, 1], [1]), ([0, 1], [-1, 2]),
                                        ([0, math.nan], [1, 2]), ([0, 1], [math.inf, 2]),
                                        ([-1e308, 1e308], [1, 2])])
def test_invalid_energy_data_rejected(times, powers):
    with pytest.raises(ValueError):
        integrate_power(times, powers)


def test_csv_import_and_metadata_are_explicit_and_independent(tmp_path):
    path = tmp_path/"energy.csv"
    path.write_text("time_s,power_w,temperature_c\n0,50,40\n10,50,45\n", encoding="utf-8")
    trace = load_power_csv(path)
    assert trace.powers == (50, 50)
    assert trace.temperatures == (40, 45)
    run = load_policy_csv(path, policy="ECO", work_units=3, work_label="frames",
                          provenance="MEASURED", task_id="render-frame-set",
                          temperature_provenance="ESTIMATED")
    assert run.provenance == "MEASURED"
    assert run.temperature_provenance == "ESTIMATED"
    assert run.work_units == 3
    with pytest.raises(ValueError, match="CSV"):
        path.write_text("time_s,cpu_percent\n0,50\n10,50\n", encoding="utf-8")
        load_power_csv(path)


@pytest.mark.parametrize("text", ["time_s,power_w\n0,1,2\n1,2\n",
                                  "time_s,power_w,temperature_c\n0,10,\n1,20,30\n",
                                  "time_s,power_w\n0,nan\n1,20\n",
                                  "time_s,power_w,power_w\n0,10,20\n1,20,30\n"])
def test_malformed_or_partial_csv_rejected(tmp_path, text):
    path = tmp_path/"bad.csv"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        load_power_csv(path)


def test_cancellation_is_honored():
    token = Cancellation()
    token.cancel()
    with pytest.raises(Cancelled):
        integrate_power([0, 1], [50, 50], token)
    with pytest.raises(Cancelled):
        compare_policies(synthetic_policy_runs(), token=token)


def test_duplicate_policies_and_invalid_metadata_rejected():
    run = synthetic_policy_runs()[0]
    with pytest.raises(ValueError):
        compare_policies([run, run])
    with pytest.raises(ValueError):
        replace(run, provenance="CPU%")
    with pytest.raises(ValueError):
        replace(run, work_units=0)
    with pytest.raises(ValueError):
        replace(run, temperatures=[40, 50])
