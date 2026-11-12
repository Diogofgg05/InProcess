"""InProcess 7.2: mock-only priority tests, never change CI OS priority."""
import os
import pytest

from expecto_process_manager.optimization import priority72 as p72


class FakeProcess:
    def __init__(self,pid=123456,created=100.0,nice=32,name="notepad.exe",user="owner"):
        self.pid=pid
        self.created=created
        self.priority=nice
        self.name_value=name
        self.user=user
        self.running=True
        self.history=[]

    def create_time(self):
        return self.created

    def nice(self,value=None):
        if value is None:return self.priority
        self.history.append(value)
        self.priority=value

    def name(self):return self.name_value
    def username(self):return self.user
    def is_running(self):return self.running


@pytest.fixture
def fake_windows(monkeypatch):
    item=FakeProcess()
    own=FakeProcess(pid=os.getpid(),created=200.0)
    monkeypatch.setattr(p72.platform,"system",lambda:"Windows")
    monkeypatch.setattr(p72,"_protected_process_ids",lambda:{0,1,own.pid})
    monkeypatch.setattr(p72.psutil,"NORMAL_PRIORITY_CLASS",32,raising=False)
    monkeypatch.setattr(p72.psutil,"BELOW_NORMAL_PRIORITY_CLASS",16384,raising=False)
    monkeypatch.setattr(p72.psutil,"Process",
                        lambda pid: own if pid==own.pid else item if pid==item.pid
                        else (_ for _ in ()).throw(p72.psutil.NoSuchProcess(pid)))
    return item


def test_windows_priority_preview_is_read_only(fake_windows):
    plan=p72.preview_priority(fake_windows.pid,fake_windows.created)
    assert plan.reversible
    assert plan.temporary_priority==16384
    assert not fake_windows.history


def test_unauthorized_session_never_changes_priority(fake_windows):
    with pytest.raises(PermissionError,match="autorização"):
        with p72.temporary_lower_priority(fake_windows.pid,fake_windows.created):
            pass
    assert not fake_windows.history


def test_authorized_session_always_restores_priorities(fake_windows):
    with p72.temporary_lower_priority(fake_windows.pid,fake_windows.created,authorized=True):
        assert fake_windows.priority==16384
    assert fake_windows.priority==32
    assert fake_windows.history==[16384,32]


def test_context_restores_when_inner_operation_fails(fake_windows):
    with pytest.raises(RuntimeError,match="failure"):
        with p72.temporary_lower_priority(fake_windows.pid,fake_windows.created,authorized=True):
            raise RuntimeError("failure")
    assert fake_windows.priority==32


def test_identity_reuse_refuses_action(fake_windows):
    with pytest.raises(p72.psutil.NoSuchProcess):
        p72.preview_priority(fake_windows.pid,fake_windows.created+2)
    assert not fake_windows.history


def test_critical_process_refused(fake_windows):
    fake_windows.name_value="CSRSS.EXE"
    with pytest.raises(PermissionError,match="essencial"):
        p72.preview_priority(fake_windows.pid,fake_windows.created)


def test_other_users_process_refused(fake_windows):
    fake_windows.user="someone-else"
    with pytest.raises(PermissionError,match="outro utilizador"):
        p72.preview_priority(fake_windows.pid,fake_windows.created)


def test_priority_changed_by_external_actor_must_not_be_overwritten(fake_windows):
    with pytest.raises(RuntimeError,match="outro interveniente"):
        with p72.temporary_lower_priority(fake_windows.pid,fake_windows.created,authorized=True):
            fake_windows.priority=256
    assert fake_windows.priority==256
    assert fake_windows.history==[16384]


def test_can_only_lower_from_normal_windows_class(fake_windows):
    fake_windows.priority=128
    plan=p72.preview_priority(fake_windows.pid,fake_windows.created)
    assert not plan.reversible
    with pytest.raises(PermissionError):
        with p72.temporary_lower_priority(fake_windows.pid,fake_windows.created,authorized=True):
            pass


def test_linux_unprivileged_refuses_mutations(fake_windows,monkeypatch):
    fake_windows.priority=0
    monkeypatch.setattr(p72.platform,"system",lambda:"Linux")
    monkeypatch.setattr(p72.os,"geteuid",lambda:1000,raising=False)
    assert not p72.preview_priority(fake_windows.pid,fake_windows.created).reversible
    assert not fake_windows.history


def test_linux_root_mock_allows_safe_temporary_nice(fake_windows,monkeypatch):
    fake_windows.priority=0
    monkeypatch.setattr(p72.platform,"system",lambda:"Linux")
    monkeypatch.setattr(p72.os,"geteuid",lambda:0,raising=False)
    with p72.temporary_lower_priority(fake_windows.pid,fake_windows.created,authorized=True):
        assert fake_windows.priority==5
    assert fake_windows.priority==0


def test_bounded_cancellation_restores_with_fake_process(fake_windows):
    from expecto_process_manager.core.cancellation import Cancellation,Cancelled
    token=Cancellation()
    token.cancel()
    with pytest.raises(Cancelled):
        p72.run_temporary_priority(fake_windows.pid,fake_windows.created,
                                   authorized=True,duration_s=1,token=token)
    assert fake_windows.history==[16384,32]


@pytest.mark.parametrize("duration",[0,0.5,16,float("nan"),True])
def test_invalid_session_duration_rejected_before_mutation(fake_windows,duration):
    with pytest.raises(ValueError):
        p72.run_temporary_priority(fake_windows.pid,fake_windows.created,
                                   authorized=True,duration_s=duration)
    assert not fake_windows.history
