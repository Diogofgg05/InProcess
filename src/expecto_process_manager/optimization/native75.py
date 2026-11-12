"""InProcess 7.5 — explicit *isolated workload* native efficiency experiments.

Do not modify arbitrary live PIDs, power plans, system services or global
policies. Windows EcoQoS is applied only to a newly launched child owned by
this experiment. Linux systemd-run --user --scope CPUWeight=50 isolates only
the selected command; there is no sudo/root escalation. The task is ended
at timeout, never another process. All actions require authorized=True.

Integration is OPT-IN through this API; none runs at application startup.
"""
from dataclasses import dataclass
import ctypes
import math
import os
import platform
import shutil
import subprocess
import time


@dataclass(frozen=True)
class NativeCapability:
    system: str
    supported: bool
    mechanism: str
    limitations: tuple[str,...]


@dataclass(frozen=True)
class NativeRun:
    mechanism: str
    status: str
    elapsed_s: float
    return_code: int
    warning: str


def native_capability(system=None):
    system=system or platform.system()
    if system=="Windows":
        return NativeCapability(
            system,True,"WINDOWS_ECOQOS_CHILD_ONLY",
            ("A API só atua numa tarefa nova criada para o ensaio.",
             "EcoQoS é uma preferência do escalonador, não medição de poupança.",
             "É necessário Windows compatível com ProcessPowerThrottling.")
        )
    if system=="Linux":
        enabled=bool(shutil.which("systemd-run"))
        return NativeCapability(
            system,enabled,"LINUX_SYSTEMD_USER_SCOPE_CPUWEIGHT",
            ("Requer sessão systemd --user funcional e cgroups compatíveis.",
             "CPUWeight é peso relativo, não quota absoluta nem poupança garantida.",
             "Não requer execução da aplicação como root.")
        )
    return NativeCapability(system,False,"UNSUPPORTED",("Nenhuma operação nativa disponível.",))


def _apply_windows_ecoqos(child):
    """SetProcessInformation(child HANDLE, ProcessPowerThrottling=4, state).

    Constants from Microsoft processthreadsapi.h; no global policy changes.
    """
    if platform.system()!="Windows":
        raise OSError("EcoQoS exclusivo de Windows.")
    class PowerState(ctypes.Structure):
        _fields_=[("Version",ctypes.c_ulong),("ControlMask",ctypes.c_ulong),
                  ("StateMask",ctypes.c_ulong)]
    state=PowerState(1,1,1)
    kernel=ctypes.windll.kernel32
    fn=kernel.SetProcessInformation
    fn.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p,ctypes.c_ulong]
    fn.restype=ctypes.c_int
    handle=getattr(child,"_handle",None)
    if handle is None:
        raise RuntimeError("Processo filho sem handle nativo.")
    if not fn(ctypes.c_void_p(int(handle)),4,ctypes.byref(state),
              ctypes.sizeof(state)):
        raise ctypes.WinError()


def native_workload_trial(command, *, authorized=False, timeout_s=20.,
                          cpu_weight=50) -> NativeRun:
    if authorized is not True:
        raise PermissionError("É necessária autorização explícita para iniciar a tarefa.")
    if (not isinstance(command,(tuple,list)) or not command or
            not all(isinstance(x,str) and x for x in command)):
        raise ValueError("A tarefa deve usar argumentos explícitos, sem shell.")
    if (isinstance(timeout_s,bool) or not isinstance(timeout_s,(int,float))
            or not math.isfinite(timeout_s) or not 1<=timeout_s<=60):
        raise ValueError("Timeout de 1 a 60 segundos.")
    if type(cpu_weight) is not int or not 1<=cpu_weight<=100:
        raise ValueError("CPUWeight do ensaio deve estar entre 1 e 100.")
    cap=native_capability()
    if not cap.supported:
        raise RuntimeError("; ".join(cap.limitations))
    started=time.perf_counter()
    if cap.system=="Linux":
        args=["systemd-run","--user","--scope","--quiet","--wait",
              f"--property=CPUWeight={cpu_weight}","--",*command]
    else:
        args=list(command)
    child=subprocess.Popen(args,shell=False,stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
    try:
        if cap.system=="Windows":
            try:
                _apply_windows_ecoqos(child)
            except Exception:
                if child.poll() is None:
                    child.terminate()
                    try:child.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait()
                raise
        try:
            code=child.wait(timeout=timeout_s)
            status="SUCCESS" if code==0 else "FAILED_WORKLOAD"
        except subprocess.TimeoutExpired:
            child.terminate()
            try:child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
            status="TIMEOUT"
            code=child.returncode
    finally:
        if child.poll() is None:
            child.terminate()
            try:child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
    return NativeRun(cap.mechanism,status,time.perf_counter()-started,
                     code,"Operação limitada à tarefa lançada; potência elétrica não medida.")
