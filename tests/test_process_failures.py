from unittest.mock import Mock
import psutil
import pytest
from expecto_process_manager.core.processes import ProcessService


def test_collection_handles_disappearing_and_denied_processes(monkeypatch):
    vanished = Mock(pid=123)
    vanished.oneshot.side_effect = psutil.NoSuchProcess(123)
    denied = Mock(pid=456)
    denied.oneshot.side_effect = psutil.AccessDenied(456)
    monkeypatch.setattr(psutil,'process_iter',lambda:iter([vanished,denied]))
    assert ProcessService().list_processes() == []


def test_reused_pid_is_rejected(monkeypatch):
    process = Mock()
    process.create_time.return_value = 200
    monkeypatch.setattr(psutil,'Process',lambda pid:process)
    with pytest.raises(psutil.NoSuchProcess):
        ProcessService().control(123456,100,'terminate',authorized=True)
    process.terminate.assert_not_called()


@pytest.mark.parametrize('action',['suspend','resume','terminate'])
def test_authorized_dispatch_with_mock_only(monkeypatch,action):
    process = Mock()
    process.create_time.return_value = 100
    monkeypatch.setattr(psutil,'Process',lambda pid:process)
    ProcessService().control(123456,100,action,authorized=True)
    getattr(process,action).assert_called_once_with()
