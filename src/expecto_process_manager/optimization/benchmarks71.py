"""InProcess 7.1 — transparent, cross-platform observer benchmark protocol.

A benchmark never starts Task Manager or GNOME System Monitor on the user's
behalf. Users start the desired observer, identify its PID and execute the
SAME deterministic workload, on the SAME host, in separate trials. Observer
CPU time is reported as percentage of ONE logical core. RSS is a sampled
sum (shared pages may be double-counted). UI input latency is NOT measured.

The runner starts only the explicitly selected workload, without a shell,
and terminates ONLY that child on timeout. No other process is controlled.
"""
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import time

import psutil


LABELS = ("BASELINE", "INPROCESS", "WINDOWS_TASK_MANAGER", "GNOME_SYSTEM_MONITOR")
PROTOCOL = "inprocess-observer-benchmark-1"


@dataclass(frozen=True)
class BenchmarkTrial:
    label: str
    workload_digest: str
    host_fingerprint: str
    platform_name: str
    observer_pid: int | None
    observer_name: str | None
    observer_start_time: float | None
    workload_exit_code: int
    task_duration_s: float
    observer_cpu_core_percent: float | None
    observer_peak_rss_mib: float | None
    observer_samples: int
    sample_gap_p95_ms: float | None
    sample_gap_max_ms: float | None
    ui_input_latency_ms: float | None
    ui_latency_provenance: str
    status: str
    warnings: tuple[str, ...]


def _identity(proc):
    return float(proc.create_time())


def _cpu_time(proc):
    t=proc.cpu_times()
    return t.user+t.system


def _observer_tree(proc, created, *, excluded_pids=()):
    if _identity(proc)!=created or not proc.is_running():
        raise psutil.NoSuchProcess(proc.pid, msg="O observador desapareceu ou o PID foi reutilizado.")
    try:
        children=proc.children(recursive=True)
    except (psutil.Error, OSError):
        children=[]
    return [p for p in [proc,*children] if p.pid not in excluded_pids]


def _fingerprint():
    # Transparent grouping key: machine and interpreter version are included,
    # but do not claim thermal, OS update, load, or battery conditions match.
    raw="|".join((platform.node(),platform.system(),platform.machine(),
                  platform.release(),str(psutil.cpu_count(logical=True)),
                  str(psutil.virtual_memory().total),platform.python_version()))
    return sha256(raw.encode("utf-8")).hexdigest()[:20]


def benchmark_trial(
    workload: list[str] | tuple[str, ...],
    *, label: str,
    observer_pid: int | None,
    timeout_s: float = 20.0,
    sample_interval_s: float = .15,
    ui_input_latency_ms: float | None = None,
) -> BenchmarkTrial:
    """Sample an externally launched observer while running a fixed task."""
    if label not in LABELS:
        raise ValueError("Nome do cenário não reconhecido.")
    if not workload or not all(isinstance(a,str) and a for a in workload):
        raise ValueError("A tarefa deve ser uma lista de argumentos, sem shell.")
    if (not math.isfinite(timeout_s) or not 1<=timeout_s<=120
            or not math.isfinite(sample_interval_s) or not .05<=sample_interval_s<=2):
        raise ValueError("Intervalos fora dos limites permitidos.")
    if (ui_input_latency_ms is not None and
            (not isinstance(ui_input_latency_ms,(int,float)) or
             isinstance(ui_input_latency_ms,bool) or
             not math.isfinite(ui_input_latency_ms) or ui_input_latency_ms<0)):
        raise ValueError("Latência manual inválida.")
    if label=="BASELINE" and observer_pid is not None:
        raise ValueError("BASELINE não pode ter observador.")
    if label!="BASELINE" and (type(observer_pid) is not int or observer_pid<=1):
        raise ValueError("É necessário o PID real do observador.")
    proc=psutil.Process(observer_pid) if observer_pid is not None else None
    created=_identity(proc) if proc is not None else None
    name=proc.name() if proc is not None else None
    digest=sha256(json.dumps(list(workload),ensure_ascii=False).encode()).hexdigest()[:20]
    seen_start={}
    seen_last={}
    peak_rss=0
    gaps=[]
    last_sample=None
    samples=0
    warnings=[
        "Latência de clique/renderização não é inferida de processos.",
        "RSS agrega processos e pode contar páginas partilhadas várias vezes.",
        "Resultados não são medições de potência ou energia elétrica.",
        "Várias aplicações, temperatura, estado da bateria e cargas de fundo podem afetar a comparação.",
    ]
    started=time.perf_counter()
    # stdout/stderr are dropped to avoid memory accumulation from a user task.
    task=subprocess.Popen(list(workload),stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL,shell=False)
    timed_out=False
    try:
        while True:
            now=time.perf_counter()
            if last_sample is not None:
                gaps.append((now-last_sample)*1000)
            last_sample=now
            if proc is not None:
                total_rss=0
                # Never count the reference workload as overhead of an
                # observer (the task is a child of InProcess when launched by
                # its own benchmark UI).
                workload_ids={task.pid}
                try:
                    workload_ids.update(child.pid for child in psutil.Process(task.pid).children(recursive=True))
                except (psutil.Error,OSError):
                    pass
                for obj in _observer_tree(proc,created,excluded_pids=workload_ids):
                    try:
                        key=(obj.pid,_identity(obj))
                        cpu=_cpu_time(obj)
                        if key not in seen_start:
                            seen_start[key]=cpu
                        seen_last[key]=cpu
                        total_rss+=obj.memory_info().rss
                    except (psutil.Error,OSError):
                        continue
                peak_rss=max(peak_rss,total_rss)
                samples+=1
            if task.poll() is not None:
                break
            if now-started>=timeout_s:
                timed_out=True
                task.terminate()
                try:
                    task.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    task.kill()
                    task.wait()
                break
            time.sleep(sample_interval_s)
    finally:
        if task.poll() is None:
            task.terminate()
            try:task.wait(timeout=2)
            except subprocess.TimeoutExpired:
                task.kill()
                task.wait()
    elapsed=time.perf_counter()-started
    cpu_s=sum(max(0,seen_last[key]-start) for key,start in seen_start.items())
    gaps=sorted(gaps)
    if timed_out: warnings.append("Tarefa terminou por timeout; ensaio inválido.")
    if proc is not None and samples<2:
        warnings.append("Amostragem insuficiente do observador.")
    status="INVALID_TIMEOUT" if timed_out else "SUCCESS" if task.returncode==0 else "INVALID_WORKLOAD"
    return BenchmarkTrial(
        label,digest,_fingerprint(),platform.platform(),
        observer_pid,name,created,task.returncode,elapsed,
        100*cpu_s/elapsed if proc is not None else None,
        peak_rss/1024**2 if proc is not None else None,
        samples,
        gaps[min(len(gaps)-1,int(.95*(len(gaps)-1)))] if gaps else None,
        max(gaps) if gaps else None,
        ui_input_latency_ms,
        "MANUAL_UNVERIFIED" if ui_input_latency_ms is not None else "NOT_MEASURED",
        status,tuple(warnings)
    )


def validate_comparison(trials: list[BenchmarkTrial]) -> dict:
    """Never rank platforms from missing observer measurements or unlike tasks."""
    if not trials or any(not isinstance(t,BenchmarkTrial) for t in trials):
        raise ValueError("Ensaios de benchmark inválidos.")
    reasons=[]
    if any(t.status!="SUCCESS" for t in trials):
        reasons.append("Existem ensaios interrompidos ou tarefas com erro.")
    if len({t.host_fingerprint for t in trials})!=1:
        reasons.append("Hosts/versões diferentes: comparar apenas com hardware e ambiente equivalentes.")
    if len({t.workload_digest for t in trials})!=1:
        reasons.append("As tarefas não são idênticas.")
    labels={t.label for t in trials}
    if "BASELINE" not in labels:
        reasons.append("Falta experiência sem observador.")
    if not labels.intersection(("INPROCESS","WINDOWS_TASK_MANAGER","GNOME_SYSTEM_MONITOR")):
        reasons.append("Falta experiência com ferramenta de monitorização.")
    if any(t.label!="BASELINE" and t.observer_samples<2 for t in trials):
        reasons.append("Não existem amostras suficientes do monitor.")
    if any(t.label!="BASELINE" and t.observer_cpu_core_percent is None for t in trials):
        reasons.append("Falta CPU do observador.")
    summary={}
    for label in LABELS:
        subset=[t for t in trials if t.label==label and t.status=="SUCCESS"]
        if subset:
            summary[label]={
                "runs":len(subset),
                "task_duration_median_s":statistics.median(t.task_duration_s for t in subset),
                "observer_cpu_mean_percent_one_core":(
                    statistics.mean(t.observer_cpu_core_percent for t in subset)
                    if label!="BASELINE" and all(t.observer_cpu_core_percent is not None for t in subset)
                    else None
                ),
                "observer_peak_rss_median_mib":(
                    statistics.median(t.observer_peak_rss_mib for t in subset)
                    if label!="BASELINE" and all(t.observer_peak_rss_mib is not None for t in subset)
                    else None
                ),
                "ui_input_latency_ms":None,
                "ui_latency_note":"Sem método instrumental comum de latência de interação.",
            }
    return {
        "protocol":PROTOCOL,
        "comparable":not reasons,
        "reasons":reasons,
        "summary":summary,
        "caveats":[
            "Picos de RSS são amostrados e podem incluir memória partilhada.",
            "Observador InProcess deve incluir o coletor auxiliar quando presente.",
            "Não medir UI latency a partir de gaps do monitor.",
            "Experiências em Windows e Linux não podem ser chamadas A/B no mesmo SO.",
            "Não inferir energia em joules de CPU% ou RAM.",
        ],
    }


def write_benchmark_json(path: str | Path,trials: list[BenchmarkTrial]):
    report=validate_comparison(trials)
    Path(path).write_text(
        json.dumps({"trials":[asdict(t) for t in trials],"analysis":report},
                   indent=2,ensure_ascii=False,allow_nan=False),encoding="utf-8"
    )
    return report
