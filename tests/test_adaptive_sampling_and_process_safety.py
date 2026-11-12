"""Regression tests for overhead control and process mutation safeguards."""
import os
from types import SimpleNamespace
from unittest.mock import Mock

import psutil
import pytest

from expecto_process_manager.core import processes
from expecto_process_manager.core.processes import ProcessService, _critical_process_name
from expecto_process_manager.core.sampling_policy import effective_interval_ms


@pytest.mark.parametrize("configured,hidden,expected", [
    (250, False, 250), (250, True, 3000),
    (1000, True, 3000), (3000, True, 3000),
    (5000, True, 5000), (5000, False, 5000),
])
def test_minimized_monitoring_never_overrides_a_slower_preference(configured, hidden, expected):
    assert effective_interval_ms(configured, minimized=hidden) == expected


@pytest.mark.parametrize("invalid", [0, 100, 10_001, 500.0, True, None, "1000"])
def test_reject_invalid_monitoring_intervals(invalid):
    with pytest.raises(ValueError):
        effective_interval_ms(invalid, minimized=True)


@pytest.mark.parametrize("platform_name,critical", [
    ("Windows", "CSRSS.EXE"), ("Windows", "wininit.exe"),
    ("Linux", "systemd"), ("Darwin", "kernel_task"),
])
def test_platform_critical_names_are_normalized(platform_name, critical):
    assert _critical_process_name(critical, platform_name)
    assert not _critical_process_name("editor.exe", platform_name)
    assert not _critical_process_name(Mock(), platform_name)


@pytest.mark.parametrize("action", ["suspend", "resume", "terminate"])
def test_immediate_parent_is_protected_before_os_control(monkeypatch, action):
    parent_pid = 765432
    monkeypatch.setattr(processes.os, "getppid", lambda: parent_pid)
    target = Mock()
    monkeypatch.setattr(psutil, "Process", lambda pid: target)
    with pytest.raises(ValueError, match="antecessores"):
        ProcessService().control(parent_pid, 100, action, authorized=True)
    target.suspend.assert_not_called()
    target.resume.assert_not_called()
    target.terminate.assert_not_called()


def test_more_distant_ancestor_is_protected(monkeypatch):
    ancestor_pid = 765433
    target = Mock()
    target.parents.return_value = [SimpleNamespace(pid=ancestor_pid)]
    monkeypatch.setattr(psutil, "Process", lambda pid: target)
    with pytest.raises(ValueError, match="antecessores"):
        ProcessService().control(ancestor_pid, 100, "terminate", authorized=True)
    target.terminate.assert_not_called()


@pytest.mark.parametrize("action", ["suspend", "terminate"])
def test_critical_windows_process_is_not_modified(monkeypatch, action):
    target = Mock()
    target.create_time.return_value = 100
    target.name.return_value = "CSRSS.EXE"
    monkeypatch.setattr(psutil, "Process", lambda pid: target)
    monkeypatch.setattr(processes.platform, "system", lambda: "Windows")
    with pytest.raises(PermissionError, match="crítico"):
        ProcessService().control(765434, 100, action, authorized=True)
    getattr(target, action).assert_not_called()


def test_normal_authorized_process_control_still_works(monkeypatch):
    target = Mock()
    target.create_time.return_value = 100
    target.name.return_value = "notepad.exe"
    monkeypatch.setattr(psutil, "Process", lambda pid: target)
    monkeypatch.setattr(processes.platform, "system", lambda: "Windows")
    ProcessService().control(765435, 100, "terminate", authorized=True)
    target.terminate.assert_called_once_with()


def test_parent_guard_does_not_disable_pid_reuse_check(monkeypatch):
    target = Mock()
    target.create_time.return_value = 200
    target.name.return_value = "notepad.exe"
    monkeypatch.setattr(psutil, "Process", lambda pid: target)
    with pytest.raises(psutil.NoSuchProcess):
        ProcessService().control(765436, 100, "terminate", authorized=True)
    target.terminate.assert_not_called()
