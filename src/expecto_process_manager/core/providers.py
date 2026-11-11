from typing import Protocol
from .monitoring import Monitor, Snapshot
from .processes import ProcessService
from .models import ProcessRecord
import platform
import time
from ..platforms.catalog import windows_groups,linux_group


class MonitoringProvider(Protocol):
    def sample(self) -> Snapshot: ...
    def list_processes(self) -> list[ProcessRecord]: ...


class PsutilProvider:
    def __init__(self) -> None:
        self.monitor = Monitor()
        self.processes = ProcessService()
        self._groups = None
        self._groups_time = 0
        self._groups_at = None

    def sample(self) -> Snapshot:
        return self.monitor.sample()

    def list_processes(self) -> list[ProcessRecord]:
        rows = self.processes.list_processes()
        system = platform.system()
        if system == 'Windows' and time.monotonic()-self._groups_time > 10:
            try:
                self._groups = windows_groups()
            except (OSError,AttributeError):
                self._groups = None
            self._groups_time = time.monotonic()
            self._groups_at = time.time() if self._groups is not None else None
        for row in rows:
            pid = row['pid']
            if system == 'Linux':
                row['kind'] = linux_group(pid)
                row['kind_sampled_at'] = time.time() if row['kind'] != 'unknown' else None
                row['kind_age_s'] = 0.0 if row['kind'] != 'unknown' else None
            elif system == 'Windows' and self._groups is not None:
                if row['created'] > self._groups_at:
                    # Cached PID membership cannot classify a process created
                    # after the catalog snapshot (including PID reuse).
                    row['kind'] = 'unknown'
                    row['kind_sampled_at'] = None
                    row['kind_age_s'] = None
                else:
                    apps,services = self._groups
                    row['kind'] = 'application' if pid in apps else 'service' if pid in services else 'process'
                    row['kind_sampled_at'] = self._groups_at
                    row['kind_age_s'] = max(0,time.monotonic()-self._groups_time)
            else:
                row['kind'] = 'unknown'
                row['kind_sampled_at'] = None
                row['kind_age_s'] = None
        return rows
