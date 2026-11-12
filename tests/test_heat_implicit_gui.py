"""UI regression coverage for Physics Lab 6.1 without physical hardware."""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _wait(app, page, expected="implicit", timeout=12):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if page.result and page.result.get("mode") == expected:
            return
        time.sleep(.01)
    raise AssertionError("Experiment did not finish in time.")


def test_switching_modes_shows_relevant_inputs():
    from PySide6.QtWidgets import QApplication
    from expecto_process_manager.interface.physical_lab6_page import PhysicalLab6Page

    app = QApplication.instance() or QApplication([])
    page = PhysicalLab6Page()
    try:
        page.show()
        page.mode.setCurrentIndex(page.mode.findData("fan"))
        app.processEvents()
        assert page.fan_form_widget.isVisible()
        assert not page.heat_form_widget.isVisible()
        assert not page.method.isVisible()

        page.mode.setCurrentIndex(page.mode.findData("implicit"))
        app.processEvents()
        assert not page.fan_form_widget.isVisible()
        assert page.heat_form_widget.isVisible()
        assert page.method.isVisible()
        assert page.method.currentData() == "crank_nicolson"
    finally:
        page.close()
        page.deleteLater()


def test_implicit_mode_uses_parameters_and_provides_order_estimates():
    from PySide6.QtWidgets import QApplication
    from expecto_process_manager.interface.physical_lab6_page import PhysicalLab6Page

    app = QApplication.instance() or QApplication([])
    page = PhysicalLab6Page()
    try:
        page.mode.setCurrentIndex(page.mode.findData("implicit"))
        page.length.setText("0.05")
        page.alpha.setText("0.00001")
        page.nodes.setText("21")
        page.duration.setText("4")
        page.method.setCurrentIndex(page.method.findData("crank_nicolson"))
        page.execute()
        _wait(app, page)
        assert page.result["parameters"]["length_m"] == .05
        assert page.result["metadata"]["solver"] == "crank_nicolson"
        assert len(page.result["metadata"]["temporal_order"]) == 4
        assert len(page.result["metadata"]["spatial_order"]) == 5
        assert "SEMIDISCRETA" in page.report.toPlainText()
        assert "SIMULATED" in page.note.text()
    finally:
        page.close()
        page.deleteLater()


def test_pi_controller_uses_its_own_parameters():
    from PySide6.QtWidgets import QApplication
    from expecto_process_manager.interface.physical_lab6_page import PhysicalLab6Page

    app = QApplication.instance() or QApplication([])
    page = PhysicalLab6Page()
    try:
        page.mode.setCurrentIndex(page.mode.findData("fan"))
        page.target.setText("49")
        page.thermal_power.setText("65")
        page.fan_duration.setText("20")
        page.execute()
        _wait(app,page,"fan")
        assert page.result["parameters"]["target_c"] == 49
        assert page.result["parameters"]["thermal_power_w"] == 65
        assert len(page.result["times_s"]) > 2
        assert "PI" in page.report.toPlainText()
    finally:
        page.close()
        page.deleteLater()
