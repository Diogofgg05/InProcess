"""Headless Qt checks for evidence reporting and safe opt-in interactions."""
import os
import time
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")


def test_evidence_ui_opens_lazily_and_refuses_unapproved_native_action(tmp_path):
    from PySide6.QtWidgets import QApplication
    from expecto_process_manager.interface.main_window import MainWindow
    app=QApplication.instance() or QApplication([])
    win=MainWindow(settings_path=tmp_path/"config.ini",
                   report_directory=tmp_path/"reports")
    try:
        assert 20 not in win.laboratory.created
        assert win.laboratory.search("energia real")
        assert win.laboratory.currentIndex()==20
        page=win.laboratory.ensure(20)
        assert not page.authorize.isChecked()
        page.execute_native()
        assert "autorização explícita" in page.results.toPlainText()
        assert page.last_report is None
    finally:
        win.close()
        deadline=time.monotonic()+15
        while not win.closed_ready and time.monotonic()<deadline:
            app.processEvents()
            time.sleep(.01)
        assert win.closed_ready


def test_energy_page_imports_csv_without_autonomous_changes(tmp_path):
    from PySide6.QtWidgets import QApplication
    from expecto_process_manager.interface.evidence_lab80_page import EvidenceLab80Page
    app=QApplication.instance() or QApplication([])
    page=EvidenceLab80Page()
    csv_file=tmp_path/"power.csv"
    csv_file.write_text("time_s,power_w,temperature_c\n"
                        "0,20,25\n2,20,26\n5,20,27\n",encoding="utf-8")
    try:
        page.csv_a.setText(str(csv_file))
        page.evaluate()
        deadline=time.monotonic()+15
        while page.last_report is None and time.monotonic()<deadline:
            app.processEvents()
            time.sleep(.01)
        assert page.last_report is not None,page.results.toPlainText()
        assert page.last_report["automatic_os_actions"] is False
        assert "100 J" in page.results.toPlainText()
        assert "INSUFFICIENT_EVIDENCE" in page.results.toPlainText()
    finally:
        page.close()
        page.deleteLater()
