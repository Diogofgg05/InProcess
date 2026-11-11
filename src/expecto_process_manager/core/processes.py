import os
import time
import math
import psutil
from .models import ProcessRecord


class ProcessService:
    def __init__(self, *, status_interval_s: float = 5.0) -> None:
        if not math.isfinite(status_interval_s) or status_interval_s < 0:
            raise ValueError("Cadência de estado inválida.")
        self._seen = set()
        self._io = {}
        self._status = {}
        self.status_interval_s = status_interval_s

    def list_processes(self) -> list[ProcessRecord]:
        rows: list[ProcessRecord] = []
        seen, io_samples, statuses = set(), {}, {}
        for process in psutil.process_iter():
            # Windows PID 0 is the idle pseudo-process, not consumed CPU work.
            if process.pid == 0:
                continue
            try:
                with process.oneshot():
                    # Permission check first: do not pay for Windows CPU fallback
                    # on processes whose rows will be omitted for AccessDenied.
                    user = process.username()
                    # process_iter caches Process objects, including creation time.
                    # Validate the identity before reusing our per-process caches.
                    if not process.is_running():
                        continue
                    created = process.create_time()
                    key = (process.pid,created)
                    cpu = process.cpu_percent()
                    now = time.monotonic()
                    cached_status = self._status.get(key)
                    if cached_status is None or now-cached_status[1] >= self.status_interval_s:
                        state = process.status()
                        status_monotonic, status_at = time.monotonic(), time.time()
                    else:
                        state, status_monotonic, status_at = cached_status
                    disk = None
                    try:
                        io = process.io_counters()
                        count = io.read_bytes+io.write_bytes
                        now = time.monotonic()
                        old = self._io.get(key)
                        if old and now > old[0] and count >= old[1]:
                            disk = (count-old[1])/(now-old[0])
                        io_samples[key] = (now,count)
                    except (psutil.Error, AttributeError, OSError):
                        pass
                    rows.append(dict(pid=process.pid, name=process.name(), user=user,
                                     status=state, cpu=cpu if key in self._seen else None,
                                     memory=process.memory_info().rss, created=created,
                                     elapsed=max(0,time.time()-created) if created > 0 else 0,
                                     disk=disk,network=None,gpu=None,
                                     status_sampled_at=status_at,
                                     status_age_s=max(0,time.monotonic()-status_monotonic)))
                    seen.add(key)
                    statuses[key] = state, status_monotonic, status_at
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        # Only current accessible identities survive; exited and denied processes
        # cannot accumulate indefinitely or transfer state to a reused PID.
        self._seen = seen
        self._io = {key:value for key,value in io_samples.items() if key in seen}
        self._status = statuses
        return rows

    def invalidate_status(self, pid: int | None = None) -> None:
        """Refresh changed processes on the next read; never performs a mutation."""
        if pid is None:
            self._status.clear()
        else:
            self._status = {key:value for key,value in self._status.items() if key[0] != pid}

    def control(self, pid: int, created: float, action: str, *, authorized: bool = False) -> None:
        if not authorized:
            raise PermissionError("É necessária autorização explícita.")
        if pid in (0, 1, os.getpid()):
            raise ValueError("Processo protegido pela aplicação.")
        if action not in ("suspend", "resume", "terminate"):
            raise ValueError("Operação inválida.")
        process = psutil.Process(pid)
        if process.create_time() != created:
            raise psutil.NoSuchProcess(pid, msg="O PID foi reutilizado.")
        getattr(process, action)()
        self.invalidate_status(pid)
