"""Low-overhead, read-only insights from sustained process telemetry.

All observations use OS-reported samples. A process using a CPU core or
significant resident memory may be working normally; never infer faults,
watts, security incidents, or recommend automatic termination.
"""
from dataclasses import dataclass
import math
import os
import platform
import time

from .processes import _critical_process_name


@dataclass(frozen=True, slots=True)
class ProcessInsight:
    kind: str
    pid: int
    created: float
    name: str
    value: float
    samples: int
    message: str


class ProcessInsights:
    """Require successive observations, and prune disappeared/PID-reused work.

    This is deliberately O(number of visible snapshot rows). No system calls,
    background services, CPU polling, process writes, or external AI models.
    """

    def __init__(self, *, required_samples: int = 3, cpu_threshold: float = 85.0,
                 memory_fraction: float = .20, min_memory_bytes: int = 768 * 1024**2,
                 max_gap_s: float = 15.0, max_tracked: int = 5000, system: str | None = None):
        if type(required_samples) is not int or not 2 <= required_samples <= 20:
            raise ValueError("Número de amostras consecutivas inválido.")
        if not isinstance(cpu_threshold, (int, float)) or isinstance(cpu_threshold, bool) or not math.isfinite(cpu_threshold) or cpu_threshold <= 0:
            raise ValueError("Limite de CPU inválido.")
        if not isinstance(memory_fraction, (int, float)) or isinstance(memory_fraction, bool) or not math.isfinite(memory_fraction) or not 0 < memory_fraction <= 1:
            raise ValueError("Fração de RAM inválida.")
        if type(min_memory_bytes) is not int or min_memory_bytes <= 0:
            raise ValueError("Limite mínimo de RAM inválido.")
        if not isinstance(max_gap_s, (int, float)) or isinstance(max_gap_s, bool) or not math.isfinite(max_gap_s) or max_gap_s <= 0:
            raise ValueError("Intervalo máximo inválido.")
        if type(max_tracked) is not int or max_tracked < 1:
            raise ValueError("Limite de processos inválido.")
        self.required_samples = required_samples
        self.cpu_threshold = float(cpu_threshold)
        self.memory_fraction = float(memory_fraction)
        self.min_memory_bytes = min_memory_bytes
        self.max_gap_s = float(max_gap_s)
        self.max_tracked = max_tracked
        self.system = system or platform.system()
        self._streaks: dict[tuple[int, float, str], int] = {}
        self._last_at: float | None = None

    def reset(self) -> None:
        self._streaks.clear()
        self._last_at = None

    def observe(self, rows, *, memory_total: int = 0, excluded_pids=(),
                sampled_at: float | None = None) -> tuple[ProcessInsight, ...]:
        """Describe a maximum of two strong signals, never perform an action.

        CPU is percent of one logical core, not system-wide percentage.
        RSS may include shared pages. No power or temperature is inferred.
        """
        now = time.monotonic() if sampled_at is None else float(sampled_at)
        if not math.isfinite(now):
            raise ValueError("Relógio de amostragem inválido.")
        if self._last_at is not None and (now <= self._last_at or now - self._last_at > self.max_gap_s):
            self.reset()
        self._last_at = now
        excluded = set(excluded_pids) | {os.getpid()}
        total = memory_total if type(memory_total) is int and memory_total > 0 else 0
        mem_limit = max(self.min_memory_bytes, total * self.memory_fraction) if total else None
        next_streaks: dict[tuple[int, float, str], int] = {}
        candidates: list[tuple[float, ProcessInsight]] = []
        handled: set[tuple[int, float]] = set()

        for row in rows:
            if len(handled) >= self.max_tracked:
                break
            if not isinstance(row, dict):
                continue
            pid, created = row.get("pid"), row.get("created")
            name = row.get("name")
            if (type(pid) is not int or pid <= 0 or pid in excluded
                    or not isinstance(created, (int, float)) or not math.isfinite(created)
                    or created <= 0 or not isinstance(name, str) or not name.strip()
                    or _critical_process_name(name, self.system)):
                continue
            identity = (pid, float(created))
            if identity in handled:
                continue
            handled.add(identity)
            cpu, ram = row.get("cpu"), row.get("memory")
            for kind, value, threshold in (
                ("CPU", cpu, self.cpu_threshold),
                ("RAM", ram, mem_limit),
            ):
                if (threshold is None or not isinstance(value, (int, float))
                        or isinstance(value, bool) or not math.isfinite(value)
                        or value < threshold):
                    continue
                key = (pid, float(created), kind)
                count = min(self.required_samples, self._streaks.get(key, 0) + 1)
                next_streaks[key] = count
                if count < self.required_samples:
                    continue
                if kind == "CPU":
                    message = (f"{name} · PID {pid}: {value:.1f}% de um núcleo lógico "
                               f"em {count} amostras consecutivas. Verifica se a carga é esperada.")
                else:
                    message = (f"{name} · PID {pid}: {value / 1024**3:.2f} GiB de RAM residente "
                               f"em {count} amostras. RSS pode incluir memória partilhada.")
                candidates.append((float(value) / threshold, ProcessInsight(
                    kind, pid, float(created), name, float(value), count, message
                )))
        self._streaks = next_streaks
        candidates.sort(key=lambda item: (-item[0], item[1].pid, item[1].kind))
        return tuple(item[1] for item in candidates[:2])
