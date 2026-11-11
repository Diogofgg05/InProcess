import csv
import math
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from expecto_process_manager.core.cancellation import Cancellation, Cancelled
from expecto_process_manager.interface.numerical_page import (
    DERIVATIVE_NAMES, METHOD_NAMES, QUADRATURE_NAMES, calculate_numerical, export_numerical,
)


def test_square_derivative_reference_and_boundary_errors():
    result = calculate_numerical({"mode": "derivatives", "preset": "square", "start": 0, "end": 1, "intervals": 100})
    rows = {row["method"]: row for row in result.results_table}
    assert rows[DERIVATIVE_NAMES["central"]]["maximum_error"] < 1e-11
    assert rows["Diferença centrada · segunda derivada"]["maximum_error"] < 1e-9
    assert rows[DERIVATIVE_NAMES["forward"]]["maximum_error"] == pytest.approx(.01)
    assert rows[DERIVATIVE_NAMES["backward"]]["maximum_error"] == pytest.approx(.01)
    assert result.series["Referência analítica · primeira derivada"] == [2 * t for t in result.times]
    assert result.provenance == "SIMULATED"
    assert "σ²/(2h²)" in result.report and "extremos" in result.report


def test_noise_seed_reproduces_signal_and_filter_effect():
    parameters = {"mode": "derivatives", "preset": "sine", "end": 2 * math.pi,
                  "intervals": 400, "noise_sigma": .05, "seed": 123, "filter_window": 7}
    first = calculate_numerical(parameters)
    second = calculate_numerical(parameters)
    assert first.input_series == second.input_series
    rows = {row["method"]: row for row in first.results_table}
    assert rows["Diferença centrada · sinal filtrado"]["rmse"] < rows[DERIVATIVE_NAMES["central"]]["rmse"]
    changed = calculate_numerical({**parameters, "seed": 124})
    assert changed.input_series["Observação sintética com ruído"] != first.input_series["Observação sintética com ruído"]
    assert changed.context["parameters"]["seed"] == 124


def test_true_midpoint_rule_differs_from_trapezoid_and_simpson_is_exact():
    result = calculate_numerical({"mode": "integration", "preset": "square", "start": 0, "end": 1, "intervals": 4})
    values = {row["method"]: row["value"] for row in result.results_table}
    assert values[QUADRATURE_NAMES["left"]] == pytest.approx(.21875)
    assert values[QUADRATURE_NAMES["right"]] == pytest.approx(.46875)
    assert values[QUADRATURE_NAMES["midpoint"]] == pytest.approx(.328125)
    assert values[QUADRATURE_NAMES["trapezoid"]] == pytest.approx(.34375)
    assert values[QUADRATURE_NAMES["simpson"]] == pytest.approx(1 / 3)
    assert QUADRATURE_NAMES["simpson"] not in result.series
    assert result.results_table[-1]["exact"] == pytest.approx(1 / 3)
    assert "efetivamente avaliada" in result.report


@pytest.mark.parametrize("preset,start,end,exact", [
    ("sine", 0., math.pi, 2.),
    ("decay", 1., 3., math.exp(-1) - math.exp(-3)),
    ("square", -1., 1., 2 / 3),
])
def test_integration_analytic_reference_for_all_presets(preset, start, end, exact):
    result = calculate_numerical({"mode": "integration", "preset": preset, "start": start, "end": end, "intervals": 100})
    assert all(row["exact"] == pytest.approx(exact) for row in result.results_table)
    assert result.results_table[-1]["absolute_error"] < 1e-6
    assert result.times[0] == start and result.times[-1] == end


def test_zero_integral_does_not_fabricate_relative_error():
    result = calculate_numerical({"mode": "integration", "preset": "sine", "start": -1, "end": 1, "intervals": 20})
    assert all(row["exact"] == 0 for row in result.results_table)
    assert all(row["relative_error"] is None for row in result.results_table)
    assert "indefinido (referência nula)" in result.report


def test_decay_ode_nonzero_start_convergence_orders_and_reference():
    result = calculate_numerical({"mode": "ode", "ode_model": "decay", "start": 5, "end": 6,
                                 "initial": 3, "coefficient": 2, "dt": .05})
    rows = {row["method"]: row for row in result.results_table}
    assert result.series["Referência analítica"][0] == 3
    assert result.series["Referência analítica"][-1] == pytest.approx(3 * math.exp(-2))
    assert rows[METHOD_NAMES["rk4"]]["absolute_error"] < 1e-6
    assert rows[METHOD_NAMES["euler"]]["observed_order"] == pytest.approx(1, abs=.15)
    assert rows[METHOD_NAMES["heun"]]["observed_order"] == pytest.approx(2, abs=.15)
    assert rows[METHOD_NAMES["rk4"]]["observed_order"] == pytest.approx(4, abs=.15)
    assert all(len(points) == 4 for points in result.convergence.values())
    assert all(points[-1][1] < points[0][1] for points in result.convergence.values())
    assert "Estabilidade" in result.report


def test_oscillator_is_vector_system_with_independent_velocity_reference():
    result = calculate_numerical({"mode": "ode", "ode_model": "oscillator", "start": 2,
                                 "end": 2 + math.pi, "initial": 1, "initial_velocity": .2,
                                 "coefficient": 1, "dt": .05})
    assert result.series["Referência analítica"][-1] == pytest.approx(-1)
    assert result.diagnostic_series["Referência analítica · velocidade"][-1] == pytest.approx(-.2)
    assert result.series[METHOD_NAMES["rk4"]][-1] == pytest.approx(-1, abs=1e-6)
    assert result.diagnostic_series[METHOD_NAMES["rk4"]][-1] == pytest.approx(-.2, abs=1e-6)
    assert "[x, v/ω]" in result.report
    assert result.times[-1] == 2 + math.pi


def test_preview_is_bounded_without_reducing_result_samples():
    result = calculate_numerical({"mode": "integration", "intervals": 5000})
    assert len(result.times) == 5001
    assert len(result.preview_times) <= 1500
    assert result.preview_times[0] == result.times[0]
    assert result.preview_times[-1] == result.times[-1]
    assert all(len(values) == len(result.preview_times) for values in result.preview_series.values())
    assert result.context["full_samples"] == 5001
    assert result.context["display_samples"] == len(result.preview_times)


@pytest.mark.parametrize("parameters", [
    {"mode": "execute"}, {"preset": "__import__('os').system('anything')"},
    {"start": 1, "end": 1}, {"end": float("nan")}, {"intervals": True},
    {"intervals": 20001}, {"mode": "integration", "intervals": 5},
    {"noise_sigma": -1}, {"seed": 1.5}, {"filter_window": 4},
    {"mode": "ode", "dt": 0}, {"mode": "ode", "dt": .000001},
    {"mode": "ode", "ode_model": "oscillator", "coefficient": 0},
    {"mode": "ode", "coefficient": -1},
])
def test_invalid_inputs_are_rejected(parameters):
    with pytest.raises(ValueError):
        calculate_numerical(parameters)


def test_extreme_exponential_domain_and_cancel_are_reported():
    with pytest.raises(ValueError, match="domínio"):
        calculate_numerical({"preset": "decay", "start": -1000, "end": -999})
    token = Cancellation()
    token.cancel()
    with pytest.raises(Cancelled):
        calculate_numerical({}, token)


def test_export_preserves_all_samples_and_original_configuration(tmp_path):
    parameters = {"mode": "integration", "start": 0, "end": 1, "intervals": 20}
    result = calculate_numerical(parameters)
    parameters["end"] = 99
    path = tmp_path / "series.csv"
    export_numerical(path, result, Cancellation())
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 21
    assert float(rows[-1]["t"]) == 1
    assert float(rows[-1]["end"]) == 1
    assert rows[-1]["provenance"] == "SIMULATED"
    assert float(rows[-1]["whole_domain_integral::Simpson composto"]) == pytest.approx(1 / 3)


def test_page_queues_calculation_and_publishes_captured_context(monkeypatch):
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication
    from expecto_process_manager.interface import numerical_page
    app = QApplication.instance() or QApplication([])
    font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf"
    if font.exists():
        QFontDatabase.addApplicationFont(str(font))
        app.setFont(QFont("Segoe UI", 10))

    class QueuedTasks:
        def start(self, function, done, failed):
            self.queued = function, done, failed
            return SimpleNamespace(token=Cancellation())

    tasks = QueuedTasks()
    page = numerical_page.NumericalPage(tasks)
    emitted = []
    page.result_ready.connect(emitted.append)
    try:
        assert page.result is None
        page.mode.setCurrentIndex(1)
        page.fields["end"].setValue(1)
        page.intervals.setValue(20)
        page.execute()
        assert page.result is None and not page.run.isEnabled()
        page.fields["end"].setValue(9)
        function, done, _ = tasks.queued
        result = function(Cancellation())
        done(result)
        assert page.result is page.experiment is result
        assert emitted == [result]
        assert page.result_context["parameters"]["end"] == 1
        assert page.table_model.rowCount() == 5
        assert page.plots[0].lines
        assert page.plots[3].isHidden()
        assert page.run.isEnabled() and not page.cancel_button.isEnabled()
        page.display(calculate_numerical({"mode": "derivatives"}))
        # f(t)=t² has constant f''=2: roundoff must not fill the chart with
        # apparent oscillations and excessively long coordinate labels.
        assert page.plots[3].y_axis.max() - page.plots[3].y_axis.min() > .01
        assert page.plots[3].y_axis.labelFormat() == "%.5g"
    finally:
        page.close()
        page.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
