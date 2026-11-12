"""InProcess 7.2 — tightly scoped, reversible process priority control.

Controls only a specific existing PID+creation-time identity. Never acts on
system-critical names, the current process or its ancestors, other users'
processes, or a process that is not explicitly approved.

On Windows: a process may temporarily move to BELOW_NORMAL_PRIORITY_CLASS
only from NORMAL_PRIORITY_CLASS. On Linux: nice 0 -> nice 5 is only
permitted when running as root, since otherwise restoring nice 0 can be
forbidden by the OS. No privilege escalation is performed.

Rollback occurs on normal completion, exception and cooperative cancel.
A crash/power-loss can prevent rollback; never promise crash-proof restore.
The API does not suspend, terminate or control real fans.
"""
from dataclasses import dataclass
from contextlib import contextmanager
import math
import os
import platform
import time
import psutil

from ..core.processes import _critical_process_name, _protected_process_ids


@dataclass(frozen=True)
class PriorityPreview:
    pid: int
    created: float
    name: str
    user: str
    original_priority: int
    temporary_priority: int
    platform_name: str
    reversible: bool
    reasons: tuple[str,...]


@dataclass(frozen=True)
class PriorityOutcome:
    pid: int
    action: str
    before: int
    temporary: int
    restored: int | None
    elapsed_s: float
    restoration_confirmed: bool
    details: str


def _process_identity(pid:int,created:float):
    if type(pid) is not int or pid<=1:
        raise ValueError("PID inválido ou reservado.")
    if isinstance(created,bool) or not isinstance(created,(int,float)) or not math.isfinite(created) or created<=0:
        raise ValueError("Instante de criação do PID inválido.")
    if pid in _protected_process_ids():
        raise PermissionError("Não alterar o próprio InProcess, antecessores ou PID protegido.")
    p=psutil.Process(pid)
    if p.create_time()!=created:
        raise psutil.NoSuchProcess(pid,msg="PID reutilizado; identidade diferente da autorizada.")
    if not p.is_running():
        raise psutil.NoSuchProcess(pid)
    if _critical_process_name(p.name(),platform.system()):
        raise PermissionError("Processo essencial ao sistema operativo.")
    if p.username()!=psutil.Process(os.getpid()).username():
        raise PermissionError("Processo de outro utilizador: não autorizado.")
    return p


def preview_priority(pid:int,created:float) -> PriorityPreview:
    """Read only; refusals are explicit rather than pretending to be reversible."""
    p=_process_identity(pid,created)
    system=platform.system()
    current=int(p.nice())
    reasons=[]
    target=current
    if system=="Windows":
        if current==int(psutil.NORMAL_PRIORITY_CLASS):
            target=int(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        else:
            reasons.append("Só a classe NORMAL do Windows pode ser reduzida nesta versão.")
    elif system=="Linux":
        if os.geteuid()!=0:
            reasons.append("Linux: reverter nice 5 para nice 0 exige privilégios; requer execução como root, sem elevação automática.")
        elif current==0:
            target=5
        else:
            reasons.append("Linux: são admitidos apenas processos que começam com nice=0.")
    else:
        reasons.append("A alteração só é implementada em Windows e Linux.")
    return PriorityPreview(pid,created,p.name(),p.username(),
                           current,target,system,not reasons,tuple(reasons))


@contextmanager
def temporary_lower_priority(pid:int,created:float,*,authorized:bool=False):
    """Explicitly approved priority-only change, reverted by finally.

    This manager restores only if identity AND current priority still match
    the changed value. If another actor changed the priority, do not overwrite.
    Restoration failure is surfaced to the caller, never swallowed.
    """
    if authorized is not True:
        raise PermissionError("A alteração de prioridade exige autorização explícita.")
    plan=preview_priority(pid,created)
    if not plan.reversible:
        raise PermissionError("; ".join(plan.reasons))
    proc=_process_identity(pid,created)
    proc.nice(plan.temporary_priority)
    try:
        yield plan
    finally:
        live=_process_identity(pid,created)
        if int(live.nice())!=plan.temporary_priority:
            raise RuntimeError("Prioridade alterada por outro interveniente; reposição automática recusada.")
        live.nice(plan.original_priority)
        if int(live.nice())!=plan.original_priority:
            raise RuntimeError("A reposição da prioridade original não pôde ser confirmada.")


def run_temporary_priority(pid:int,created:float,*,authorized:bool=False,
                           duration_s:float=8.,token=None) -> PriorityOutcome:
    """Small bounded session; cannot remain active indefinitely."""
    if isinstance(duration_s,bool) or not isinstance(duration_s,(int,float)) or not math.isfinite(duration_s) or not 1<=duration_s<=15:
        raise ValueError("Sessões de prioridade limitadas a 1–15 segundos.")
    started=time.monotonic()
    with temporary_lower_priority(pid,created,authorized=authorized) as plan:
        until=started+duration_s
        while time.monotonic()<until:
            if token is not None:
                token.check()
            # Check identity during the session; a changed PID will stop it.
            _process_identity(pid,created)
            time.sleep(min(.1,max(.0,until-time.monotonic())))
        if token is not None:
            token.check()
    finished=time.monotonic()
    live=_process_identity(pid,created)
    return PriorityOutcome(pid,"LOWER_PRIORITY_TEMPORARILY",
                           plan.original_priority,plan.temporary_priority,
                           int(live.nice()),finished-started,True,
                           "Reposição de prioridade confirmada após a sessão. "
                           "Não prova poupança energética.")
