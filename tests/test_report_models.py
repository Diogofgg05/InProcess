from dataclasses import asdict
from types import SimpleNamespace

import pytest

from expecto_process_manager.physics.gravity import GravityConfig, free_fall_euler, run_gravity
from expecto_process_manager.physics.calibration import fit_thermal, predict_zoh
from expecto_process_manager.physics.coupled_thermal import CoupledThermalConfig, simulate_coupled
from expecto_process_manager.optimization.eco import compare_policies, synthetic_policy_runs
from expecto_process_manager.reporting.document import ScientificReport
from expecto_process_manager.reporting.model_reports import (
    gravity_report, free_fall_report, energy_report, calibration_report, coupled_report,
)
from expecto_process_manager.reporting.render import render_report


def assert_renderable(report):
    assert isinstance(report, ScientificReport)
    assert report.problem and report.assumptions and report.equations and report.methods
    assert report.tables and report.figures and report.interpretation and report.limitations and report.reproduction
    html = render_report(report)
    assert "<svg" in html
    assert "<table" in html
    assert "http-equiv" not in html
    assert "<script" not in html
    assert "\\frac" not in html
    return html


def test_gravity_report_has_equal_spatial_scale_and_analytic_validation():
    experiment = run_gravity(GravityConfig(duration=100, dt=5))
    report = gravity_report(experiment, {"metadata": {"Identificador": "ensaio <1>"}})
    html = assert_renderable(report)
    assert report.provenance == "SIMULATED"
    assert report.figures[0].equal_scale
    assert report.metadata["Identificador"] == "ensaio <1>"
    assert "ensaio &lt;1&gt;" in html
    assert len(report.figures[0].curves[0].x) == len(experiment.times)
    assert any("RMSE" in phrase for phrase in report.interpretation)


def test_non_circular_gravity_report_does_not_fabricate_position_reference():
    experiment = run_gravity(GravityConfig(duration=50, dt=5, velocity_factor=.8))
    report = gravity_report(experiment)
    assert_renderable(report)
    assert len(report.figures[0].curves) == 3
    assert not any(figure.title.startswith("Erro de posição") for figure in report.figures)
    assert all(row[4] is None for row in report.tables[0].rows)


def test_free_fall_report_uses_full_result_without_importing_qt_presentation():
    parameters = dict(height=100, initial_velocity=0, gravity=9.80665, duration=4, dt=.1)
    result = free_fall_euler(**parameters)
    presentation = SimpleNamespace(result=result, parameters=parameters)
    report = free_fall_report(presentation)
    assert_renderable(report)
    assert len(report.figures[0].curves[0].x) == len(result.times)
    assert report.tables[0].rows[0][2] > 0
    assert report.tables[0].rows[1][2] < 1e-12


def test_energy_report_qualifies_synthetic_recommendations_and_keeps_metadata():
    comparison = compare_policies(synthetic_policy_runs(), max_duration=18)
    report = energy_report(comparison, {"config": {"max_duration": 18, "max_temperature": None}})
    html = assert_renderable(report)
    assert report.provenance == "SIMULATED"
    assert "não demonstram poupança real" in html
    assert any("NORMAL" in phrase for phrase in report.interpretation)
    assert ("Prazo máximo", 18, "s") in report.parameters
    energy_curves = report.figures[1].curves
    assert [curve.y[-1] for curve in energy_curves] == pytest.approx([600, 675, 500])


def test_calibration_report_marks_estimated_parameters_unknown_input_and_holdout():
    times = [i*.5 for i in range(81)]
    powers = [45.]*len(times)
    temperatures = predict_zoh(times, powers, 30, 22, 100, 2)
    result = fit_thermal(times, temperatures, powers, 22)
    report = calibration_report(result, {"ambient": 22})
    html = assert_renderable(report)
    assert "ESTIMATED" in report.provenance and "UNKNOWN" in report.provenance
    assert "holdout" in html
    assert "sensibilidade" in html
    rows = report.tables[0].rows
    assert rows[0][3] < rows[1][2]
    assert rows[1][5] < 1e-8


def test_coupled_report_keeps_internal_cancellation_distinct_from_accuracy():
    config = CoupledThermalConfig()
    result = simulate_coupled(config, duration=10, dt=.2)
    report = coupled_report(result, {"config": {**asdict(config), "dt": .2}})
    html = assert_renderable(report)
    assert report.provenance == "SIMULATED"
    assert "cancelam exatamente" in html
    assert "não constitui uma validação independente" in html
    assert not any(table.title.startswith("Validação independente") for table in report.tables)


def test_coupled_zero_coupling_has_independent_validation_but_missing_config_not_invented():
    config = CoupledThermalConfig(coupling=0)
    result = simulate_coupled(config, duration=10, dt=.2)
    report = coupled_report(result, {"config": asdict(config)})
    assert_renderable(report)
    assert any(table.title.startswith("Validação independente") for table in report.tables)
    missing = coupled_report(result)
    assert any("Não foram inventados" in sentence for sentence in missing.limitations)
    assert not any(label == "Capacidade CPU" for label, _, _ in missing.parameters)
