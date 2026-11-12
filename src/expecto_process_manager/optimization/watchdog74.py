"""InProcess 7.4 — independent, best-effort priority restoration watchdog.

The watchdog is a *separate process*. It observes the original GUI process
by PID + creation time and expires after <=20 seconds, attempting to restore
a narrowly defined priority change if the owner crashes. It does not promise
restoration after OS shutdown, watchdog crash, permission loss or PID reuse.

Allowed transitions ONLY:
Windows NORMAL_PRIORITY_CLASS <-> BELOW_NORMAL_PRIORITY_CLASS,
Linux nice 0 <-> nice 5 with already-held sufficient privileges.
The helper never elevates itself or changes other process parameters.
"""
import argparse
import math
import os
import platform
import sys
import time

import psutil

from ..core.processes import _critical_process_name, _protected_process_ids


def _allowed(original, temporary, system):
    if system=="Windows":
        return (original==int(psutil.NORMAL_PRIORITY_CLASS)
                and temporary==int(psutil.BELOW_NORMAL_PRIORITY_CLASS))
    if system=="Linux":
        return original==0 and temporary==5 and getattr(os,"geteuid",lambda:1)()==0
    return False


def restore_if_expected(pid, created, original, temporary, *,
                        owner_pid, owner_created, deadline_s=20.,
                        interval_s=.12, ready=None):
    """Best-effort process-bound lease, no arbitrary OS commands.

    If the target disappears or its priority differs from the exact temporary
    value, the helper exits without touching any process. If owner dies or
    lease expires, it restores only that exact process, if still unchanged.
    """
    system=platform.system()
    if not _allowed(original,temporary,system):
        raise PermissionError("Transição privilegiada ou prioridade proibida.")
    if (type(pid) is not int or type(owner_pid) is not int or
            pid<=1 or owner_pid<=1 or pid==owner_pid):
        raise ValueError("Identificadores de processos inválidos.")
    if any(not isinstance(v,(float,int)) or isinstance(v,bool) or
           not math.isfinite(v) or v<=0 for v in (created,owner_created)):
        raise ValueError("Tempos de criação inválidos.")
    if (not 1<=deadline_s<=20 or not .05<=interval_s<=1
            or not math.isfinite(deadline_s) or not math.isfinite(interval_s)):
        raise ValueError("Limites de execução inválidos.")
    if pid in _protected_process_ids():
        raise PermissionError("Processo protegido; o watchdog não pode alterar a prioridade.")
    target=psutil.Process(pid)
    if _critical_process_name(target.name(),system):
        raise PermissionError("Processo crítico protegido.")
    if target.create_time()!=created:
        raise psutil.NoSuchProcess(pid,msg="PID reutilizado.")
    # Do not permit the helper to restore another user's process.
    if target.username()!=psutil.Process(os.getpid()).username():
        raise PermissionError("Processo de outro utilizador.")
    expiry=time.monotonic()+deadline_s
    if ready:
        ready()
    while time.monotonic()<expiry:
        try:
            target=psutil.Process(pid)
            if target.create_time()!=created:
                return "TARGET_CHANGED"
            current=int(target.nice())
            if current==original:
                return "ALREADY_RESTORED"
            if current!=temporary:
                return "CHANGED_BY_THIRD_PARTY"
            try:
                owner=psutil.Process(owner_pid)
                owner_alive=owner.is_running() and owner.create_time()==owner_created
            except (psutil.NoSuchProcess,psutil.ZombieProcess):
                owner_alive=False
            if not owner_alive:
                break
        except (psutil.NoSuchProcess,psutil.ZombieProcess):
            return "TARGET_MISSING"
        time.sleep(interval_s)
    target=psutil.Process(pid)
    if target.create_time()!=created:
        return "TARGET_CHANGED"
    if int(target.nice())!=temporary:
        return "CHANGED_OR_RESTORED"
    target.nice(original)
    if int(target.nice())!=original:
        raise RuntimeError("Restauro independente não confirmado.")
    return "RESTORED_ON_CRASH_OR_EXPIRY"


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--pid",type=int,required=True)
    parser.add_argument("--created",type=float,required=True)
    parser.add_argument("--original",type=int,required=True)
    parser.add_argument("--temporary",type=int,required=True)
    parser.add_argument("--owner-pid",type=int,required=True)
    parser.add_argument("--owner-created",type=float,required=True)
    parser.add_argument("--deadline",type=float,default=20.)
    args=parser.parse_args(argv)
    try:
        status=restore_if_expected(
            args.pid,args.created,args.original,args.temporary,
            owner_pid=args.owner_pid,owner_created=args.owner_created,
            deadline_s=args.deadline,ready=lambda:(print("READY",flush=True))
        )
        print(status,flush=True)
        return 0
    except (psutil.Error,PermissionError,ValueError,RuntimeError) as error:
        print(f"WATCHDOG_ERROR: {error}",file=sys.stderr,flush=True)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
