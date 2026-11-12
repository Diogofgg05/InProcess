"""InProcess 7.1: honest measurements and comparison protocol tests."""
import json
import os
import sys

import psutil
import pytest
from expecto_process_manager.optimization.benchmarks71 import (
    BenchmarkTrial,benchmark_trial,validate_comparison,write_benchmark_json,
    _observer_tree,
)
from expecto_process_manager.optimization.benchmark_workload71 import run


def test_reference_workload_is_deterministic():
    assert run(1000)==run(1000)
    assert run(2000)!=run(1000)


def test_baseline_does_not_invent_observer_cpu_or_ui_latency():
    trial=benchmark_trial(
        [sys.executable,"-c","import time;time.sleep(.15)"],
        label="BASELINE",observer_pid=None,timeout_s=2,sample_interval_s=.05
    )
    assert trial.status=="SUCCESS"
    assert trial.observer_cpu_core_percent is None
    assert trial.observer_peak_rss_mib is None
    assert trial.ui_input_latency_ms is None
    assert trial.ui_latency_provenance=="NOT_MEASURED"
    assert trial.workload_exit_code==0


def test_observer_is_sampled_and_child_exclusion_works():
    parent=psutil.Process(os.getpid())
    children=_observer_tree(parent,parent.create_time(),excluded_pids={parent.pid})
    assert all(proc.pid!=parent.pid for proc in children)
    trial=benchmark_trial(
        [sys.executable,"-c","import time;time.sleep(.45)"],
        label="INPROCESS",observer_pid=os.getpid(),timeout_s=2,
        sample_interval_s=.075
    )
    assert trial.status=="SUCCESS"
    assert trial.observer_samples>=2
    assert trial.observer_cpu_core_percent is not None
    assert trial.observer_peak_rss_mib is not None
    assert trial.sample_gap_max_ms is not None


def test_identical_baseline_and_tool_have_grounded_comparability(tmp_path):
    workload=[sys.executable,"-c","import time;time.sleep(.35)"]
    baseline=benchmark_trial(workload,label="BASELINE",observer_pid=None,timeout_s=2)
    tool=benchmark_trial(workload,label="INPROCESS",observer_pid=os.getpid(),timeout_s=2)
    report=validate_comparison([baseline,tool])
    assert report["comparable"]
    assert report["summary"]["INPROCESS"]["observer_cpu_mean_percent_one_core"] is not None
    assert report["summary"]["INPROCESS"]["ui_input_latency_ms"] is None
    assert "energia" in " ".join(report["caveats"]).lower()
    path=tmp_path/"trials.json"
    write_benchmark_json(path,[baseline,tool])
    raw=json.loads(path.read_text(encoding="utf-8"))
    assert len(raw["trials"])==2
    assert raw["analysis"]["comparable"]


def test_different_workload_never_claims_comparison():
    first=benchmark_trial([sys.executable,"-c","pass"],label="BASELINE",
                          observer_pid=None,timeout_s=2)
    second=benchmark_trial([sys.executable,"-c","print(1)"],label="INPROCESS",
                           observer_pid=os.getpid(),timeout_s=2)
    comparison=validate_comparison([first,second])
    assert not comparison["comparable"]
    assert any("tarefas não são idênticas" in s for s in comparison["reasons"])


def test_expired_task_is_invalid_and_killed_only_as_own_child():
    trial=benchmark_trial([sys.executable,"-c","import time;time.sleep(10)"],
                          label="BASELINE",observer_pid=None,
                          timeout_s=1,sample_interval_s=.15)
    assert trial.status=="INVALID_TIMEOUT"


@pytest.mark.parametrize("label,pid",[
    ("BASELINE",1234),("WINDOWS_TASK_MANAGER",None),("INVALID",None)
])
def test_invalid_label_or_pid_is_rejected(label,pid):
    with pytest.raises(ValueError):
        benchmark_trial([sys.executable,"-c","pass"],
                        label=label,observer_pid=pid)


def test_gui_is_lazy_and_never_authorizes_priority_by_default(tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
    from PySide6.QtWidgets import QApplication
    from expecto_process_manager.interface.main_window import MainWindow
    import time
    app=QApplication.instance() or QApplication([])
    win=MainWindow(settings_path=tmp_path/"settings.ini",
                   report_directory=tmp_path/"reports")
    try:
        assert 19 not in win.laboratory.created
        assert win.laboratory.search("benchmark")
        assert win.laboratory.currentIndex()==19
        page=win.laboratory.ensure(19)
        assert not page.permission.isChecked()
        assert not page.apply_button.isEnabled()
        assert page.benchmark_label.count()==4
        page.benchmark_label.setCurrentIndex(0)
        page.iterations.setText("1000")
        page.repetitions.setText("1")
        page.execute_benchmark()
        deadline=time.monotonic()+15
        while not page.trials and time.monotonic()<deadline:
            app.processEvents()
            time.sleep(.01)
        assert page.trials and page.trials[0].status=="SUCCESS"
        assert "NÃO MEDIDA" in page.benchmark_text.toPlainText()
    finally:
        win.close()
        deadline=time.monotonic()+15
        while not win.closed_ready and time.monotonic()<deadline:
            app.processEvents()
            time.sleep(.01)
        assert win.closed_ready
