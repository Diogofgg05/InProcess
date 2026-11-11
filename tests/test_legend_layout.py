"""Regression checks for complete, wrapping chart legends at narrow widths."""
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QLabel

from expecto_process_manager.interface.charts import Plot
from expecto_process_manager.interface.gravity_visuals import OrbitPlot
from expecto_process_manager.interface.legend import SeriesLegend


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf"
    if font.exists():
        QFontDatabase.addApplicationFont(str(font))
        application.setFont(QFont("Segoe UI", 10))
    return application


def close_widget(widget, app):
    widget.close()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def test_legend_wraps_full_names_inside_narrow_width(app):
    legend = SeriesLegend()
    entries = [("Euler explícito", "#21b9ff"), ("Euler simplético", "#b366ff"),
               ("Velocity Verlet", "#28d58b"), ("Referência circular independente", "#e6b454")]
    try:
        legend.set_entries(entries)
        narrow = legend.flow.heightForWidth(220)
        wide = legend.flow.heightForWidth(1000)
        assert narrow > wide
        legend.resize(220, narrow)
        legend.show()
        app.processEvents()
        text = [label.text() for label in legend.findChildren(QLabel) if label.text()]
        assert text == [name for name, _ in entries]
        assert all("…" not in label and "..." not in label for label in text)
        for index in range(legend.flow.count()):
            cell = legend.flow.itemAt(index)
            assert cell.geometry().left() >= 0
            assert cell.geometry().right() < legend.width()
            assert cell.geometry().bottom() < legend.height()
    finally:
        close_widget(legend, app)


def test_unchanged_series_reuses_legend_labels(app):
    plot = Plot("Métodos numéricos", "K")
    names = ("Euler explícito", "Euler simplético", "Velocity Verlet")
    try:
        plot.update_series([0, 1], {name: [20, 21] for name in names})
        original = [label for label in plot.legend.findChildren(QLabel) if label.text()]
        for i in range(20):
            plot.update_series([0, 1], {name: [20, 21 + i] for name in names})
        assert [label.text() for label in original] == list(names)
        assert [label for label in plot.legend.findChildren(QLabel) if label.text()] == original
        assert not plot.chart.legend().isVisible()
    finally:
        close_widget(plot, app)


def test_orbit_legend_identifies_all_methods_and_reference(app):
    orbit = OrbitPlot()
    names = ("Euler explícito", "Euler simplético", "Velocity Verlet", "Referência circular")
    try:
        orbit.set_orbits({name: [(0, 1), (1, 0), (0, -1)] for name in names})
        assert [name for name, _ in orbit.legend.entries] == ["Massa central", *names]
        orbit.resize(440, 350)
        orbit.show()
        app.processEvents()
        assert orbit.legend.flow.heightForWidth(220) > orbit.legend.flow.heightForWidth(1000)
        assert not orbit.chart.legend().isVisible()
    finally:
        close_widget(orbit, app)
