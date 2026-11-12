"""Read-only process insight engine: sustained signals, bounded state, safe UI."""
import os
import time
import math

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from expecto_process_manager.core.insights import ProcessInsights


def process(pid=801100, created=100.0, cpu=95.0, memory=1000,
            name="render.exe"):
    return dict(pid=pid, created=created, cpu=cpu, memory=memory, name=name)


def test_one_spike_is_not_a_diagnosis():
    engine = ProcessInsights(required_samples=3)
    assert engine.observe([process()], sampled_at=1.0) == ()
    assert engine.observe([process(cpu=0)], sampled_at=2.0) == ()
    assert engine.observe([process()], sampled_at=3.0) == ()
    assert engine.observe([process()], sampled_at=4.0) == ()
    alert = engine.observe([process()], sampled_at=5.0)
    assert len(alert) == 1 and alert[0].kind == "CPU"
    assert alert[0].samples == 3
    assert "núcleo lógico" in alert[0].message
    assert "avaria" not in alert[0].message


def test_missing_and_invalid_cpu_do_not_count_as_busy():
    engine = ProcessInsights(required_samples=2)
    for cpu in [None, float("nan"), float("inf"), -1, True, "99"]:
        engine.observe([process(cpu=cpu)], sampled_at=1.0)
        assert not engine._streaks


def test_cpu_percent_can_exceed_100_percent_of_one_core():
    engine = ProcessInsights(required_samples=2)
    assert not engine.observe([process(cpu=185)], sampled_at=1.0)
    result = engine.observe([process(cpu=180)], sampled_at=2.0)
    assert result[0].value == 180


def test_memory_needs_a_known_system_total():
    engine = ProcessInsights(required_samples=2)
    big = process(cpu=None, memory=3 * 1024**3)
    assert engine.observe([big], sampled_at=1, memory_total=0) == ()
    assert engine.observe([big], sampled_at=2, memory_total=0) == ()
    assert engine.observe([big], sampled_at=3, memory_total=8 * 1024**3) == ()
    result = engine.observe([big], sampled_at=4, memory_total=8 * 1024**3)
    assert result[0].kind == "RAM"
    assert "memória partilhada" in result[0].message


def test_ram_below_threshold_does_not_trigger():
    engine = ProcessInsights(required_samples=2)
    low = process(cpu=None, memory=512 * 1024**2)
    assert engine.observe([low], sampled_at=1, memory_total=16 * 1024**3) == ()
    assert engine.observe([low], sampled_at=2, memory_total=16 * 1024**3) == ()


def test_pid_reuse_does_not_inherit_previous_streak():
    engine = ProcessInsights(required_samples=2)
    old = process(created=100)
    new = process(created=200)
    assert engine.observe([old], sampled_at=1) == ()
    assert engine.observe([new], sampled_at=2) == ()
    assert len(engine.observe([new], sampled_at=3)) == 1
    assert not any(key[1] == 100 for key in engine._streaks)


def test_disappearing_process_prunes_its_state():
    engine = ProcessInsights(required_samples=2)
    engine.observe([process()], sampled_at=1)
    assert engine._streaks
    engine.observe([], sampled_at=2)
    assert not engine._streaks
    assert engine.observe([process()], sampled_at=3) == ()


def test_large_gap_resets_streak():
    engine = ProcessInsights(required_samples=2, max_gap_s=3)
    engine.observe([process()], sampled_at=1)
    assert engine.observe([process()], sampled_at=10) == ()
    assert engine.observe([process()], sampled_at=11)


def test_clock_reset_clears_streak():
    engine = ProcessInsights(required_samples=2)
    engine.observe([process()], sampled_at=10)
    assert engine.observe([process()], sampled_at=9) == ()
    assert engine.observe([process()], sampled_at=10)


def test_own_and_os_critical_processes_suppressed():
    engine = ProcessInsights(required_samples=2, system="Windows")
    rows = [process(pid=os.getpid()), process(pid=801101, name="CSRSS.EXE")]
    assert engine.observe(rows, sampled_at=1) == ()
    assert engine.observe(rows, sampled_at=2) == ()
    assert not engine._streaks


def test_collector_pid_exclusion():
    engine = ProcessInsights(required_samples=2)
    row = process(pid=801101)
    assert engine.observe([row], excluded_pids=(801101,), sampled_at=1) == ()
    assert engine.observe([row], excluded_pids=(801101,), sampled_at=2) == ()


def test_no_inference_from_invalid_process_identity():
    engine = ProcessInsights(required_samples=2)
    rows = [process(pid=0), process(pid="bad"), process(created=float("nan")),
            process(name=""), {}, None]
    assert not engine.observe(rows, sampled_at=1)
    assert not engine._streaks


def test_bounded_tracked_processes_and_two_visible_insights():
    engine = ProcessInsights(required_samples=2, max_tracked=2)
    rows = [process(pid=801101), process(pid=801102),
            process(pid=801103, cpu=500)]
    engine.observe(rows, sampled_at=1)
    alerts = engine.observe(rows, sampled_at=2)
    assert len(alerts) == 2
    assert all(alert.pid != 801103 for alert in alerts)
    assert len(engine._streaks) <= 2


def test_alerts_not_emitted_when_load_recovers():
    engine = ProcessInsights(required_samples=2)
    row = process()
    engine.observe([row], sampled_at=1)
    assert engine.observe([row], sampled_at=2)
    assert engine.observe([process(cpu=5)], sampled_at=3) == ()
    assert not engine._streaks


@pytest.mark.parametrize("kwargs", [
    {"required_samples":1}, {"required_samples":21}, {"required_samples":True},
    {"cpu_threshold":0}, {"cpu_threshold":float("nan")},
    {"memory_fraction":0}, {"memory_fraction":2},
    {"min_memory_bytes":-1}, {"max_gap_s":0},
    {"max_tracked":0}, {"max_tracked":True},
])
def test_invalid_configuration_is_rejected(kwargs):
    with pytest.raises(ValueError):
        ProcessInsights(**kwargs)


def test_processes_page_notice_is_plain_text_and_noninteractive():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from expecto_process_manager.interface.processes_page import ProcessesPage
    from expecto_process_manager.core.insights import ProcessInsight

    app = QApplication.instance() or QApplication([])
    page = ProcessesPage()
    try:
        assert page.insights_label.isHidden()
        assert page.insights_label.textFormat() == Qt.PlainText
        alert = ProcessInsight("CPU", 801101, 100., "<img src='http://example.com/a'>",
                               95., 3, "Processo <img> · 95% durante 3 amostras")
        page.show_insights((alert,))
        assert page.insights_label.text().startswith("Processo <img>")
        assert not page.insights_label.isHidden()
        page.show_insights(())
        assert page.insights_label.isHidden()
    finally:
        page.close()
        page.deleteLater()
