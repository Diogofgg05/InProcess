"""Workload context remains separate from scientific energy estimates."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from expecto_process_manager.core.insights import ProcessInsight
from expecto_process_manager.optimization.workload import assess_workload
from expecto_process_manager.optimization.eco import compare_policies, synthetic_policy_runs
from expecto_process_manager.optimization.advisor import energy_advice


def sample(kind="CPU", pid=808080):
    return ProcessInsight(kind, pid, 100., "render.exe", 96., 3,
                          "render.exe: carga sustentada")


def test_no_snapshot_is_explicit_and_does_not_invent_data():
    context = assess_workload((), collected=False)
    assert context.state == "NO_SNAPSHOT"
    assert "Aguardar" in context.report
    assert "não são séries de potência" in context.report


def test_sustained_load_has_hints_but_no_energy_claim():
    context = assess_workload((sample(),), observed_processes=42)
    assert context.state == "ACTIVE_WORKLOAD"
    assert context.observed_processes == 42
    assert "PID 808080" in context.report
    assert "não valida uma comparação energética" in context.report
    assert "não são séries de potência" in context.report


def test_no_alert_does_not_certify_idle():
    context = assess_workload((), observed_processes=120)
    assert context.state == "NO_SUSTAINED_SIGNAL"
    assert "não comprova ausência" in context.report


def test_context_is_bounded_to_two_observations():
    context = assess_workload((sample(pid=808080), sample(pid=808081), sample(pid=808082)))
    assert len(context.hints) == 2
    assert "808082" not in context.report


@pytest.mark.parametrize("count", [-1, 2.5, True, "10"])
def test_bad_process_count_rejected(count):
    with pytest.raises(ValueError):
        assess_workload((), observed_processes=count)


def test_bad_insight_rejected():
    with pytest.raises(TypeError):
        assess_workload(("cpu high",), observed_processes=1)


def test_existing_energy_recommendation_is_independent_of_snapshot():
    comparison = compare_policies(synthetic_policy_runs())
    before = energy_advice(comparison, max_slowdown_percent=100)
    assess_workload((sample(),), observed_processes=200)
    after = energy_advice(comparison, max_slowdown_percent=100)
    assert before == after
    assert before.candidate == "ULTRA ECO"


def test_qt_eco_shows_real_context_without_fabricating_watts():
    from PySide6.QtWidgets import QApplication
    from expecto_process_manager.interface.eco_page import EcoPage

    app = QApplication.instance() or QApplication([])
    page = EcoPage()
    try:
        assert page.workload_context.state == "NO_SNAPSHOT"
        page.update_workload((sample(),), observed_processes=200)
        assert page.workload_context.state == "ACTIVE_WORKLOAD"
        assert "CARGA ATIVA" in page.workload_note.text()
        assert "96." not in page.workload_note.text() or "watts" not in page.workload_note.text()
        page.update_workload((), observed_processes=200)
        assert "Sem atividade persistente" in page.workload_note.text()
        assert page.result is None
    finally:
        page.close()
        page.deleteLater()


def test_main_window_does_not_create_eco_page_just_to_monitor(tmp_path):
    from PySide6.QtWidgets import QApplication
    from expecto_process_manager.interface.main_window import MainWindow
    from expecto_process_manager.core.monitoring import Snapshot

    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path / "settings.ini", report_directory=tmp_path / "reports")
    try:
        assert 6 not in window.laboratory.created
        snapshot = Snapshot(100, 30, [30], 1024, 1024, 50, None, None, None, None,
                            memory_total=8192)
        window.collected((snapshot, [dict(pid=808080, created=100., name="render.exe",
                                          cpu=100., memory=1000, user="test")], [snapshot]))
        assert 6 not in window.laboratory.created
        page = window.laboratory.ensure(6)
        assert page.workload_context.observed_processes == 1
    finally:
        window.close()
        # Existing main-window close contract waits for sampler shutdown.
        import time
        limit = time.monotonic() + 15
        while not window.closed_ready and time.monotonic() < limit:
            app.processEvents()
            time.sleep(.01)
        assert window.closed_ready
