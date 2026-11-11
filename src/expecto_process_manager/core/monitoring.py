from collections import deque
from dataclasses import asdict, dataclass
import time
import psutil
import threading
import math
from ..platforms import temperatures


@dataclass
class Snapshot:
    timestamp: float
    cpu: float | None
    cores: list[float]
    memory_used: int
    memory_available: int
    memory_percent: float
    swap_used: int | None
    disk_bytes_s: float | None
    network_bytes_s: float | None
    temperature_c: float | None
    provenance: str = "medido"
    interval_s: float | None = None
    collection_s: float = 0
    memory_total: int = 0
    cpu_frequency_mhz: float | None = None
    network_received_s: float | None = None
    network_sent_s: float | None = None
    swap_sampled_at: float | None = None
    swap_age_s: float | None = None
    temperature_sampled_at: float | None = None
    temperature_age_s: float | None = None
    frequency_sampled_at: float | None = None
    frequency_age_s: float | None = None


class Monitor:
    def __init__(self, history_limit: int = 3600, *, auxiliary_interval_s: float = 2.0) -> None:
        if not math.isfinite(auxiliary_interval_s) or auxiliary_interval_s < 0:
            raise ValueError("Cadência de sensores inválida.")
        self.history: deque[Snapshot] = deque(maxlen=history_limit)
        self.previous = None
        self._thread = None
        self.auxiliary_interval_s = auxiliary_interval_s
        self._auxiliary = {}

    def _cached_auxiliary(self, name, getter, monotonic):
        cached = self._auxiliary.get(name)
        if cached is None or monotonic-cached[1] >= self.auxiliary_interval_s:
            try:
                value = getter()
                if value is not None and not math.isfinite(value):
                    value = None
            except (psutil.Error,OSError,NotImplementedError,AttributeError):
                value = None
            sampled_monotonic = time.monotonic()
            sampled_at = time.time() if value is not None else None
            cached = value,sampled_monotonic,sampled_at
            self._auxiliary[name] = cached
        value,sampled_monotonic,sampled_at = cached
        age = max(0,time.monotonic()-sampled_monotonic) if value is not None else None
        return value,sampled_at,age

    @staticmethod
    def _frequency():
        frequency = psutil.cpu_freq()
        return frequency.current if frequency and frequency.current > 0 else None

    def sample(self) -> Snapshot:
        now, monotonic = time.time(), time.monotonic()
        thread = threading.get_ident()
        warmed = self._thread == thread
        self._thread = thread
        cores = psutil.cpu_percent(percpu=True)
        memory = psutil.virtual_memory()
        swap_used,swap_at,swap_age = self._cached_auxiliary('swap',lambda:psutil.swap_memory().used,monotonic)
        temperature,temperature_at,temperature_age = self._cached_auxiliary('temperature',temperatures,monotonic)
        frequency,frequency_at,frequency_age = self._cached_auxiliary('frequency',self._frequency,monotonic)
        disk, net = psutil.disk_io_counters(), psutil.net_io_counters()
        d = disk.read_bytes+disk.write_bytes if disk else None
        n = net.bytes_sent+net.bytes_recv if net else None
        rates = [None, None]
        if self.previous:
            old_time, old_d, old_n, old_sent, old_received = self.previous
            for i,(value,old) in enumerate(((d,old_d),(n,old_n))):
                if value is not None and old is not None and value >= old:
                    rates[i] = (value-old)/(monotonic-old_time)
        interval = monotonic-self.previous[0] if self.previous else None
        received,sent=None,None
        if self.previous and net:
            if old_received is not None and net.bytes_recv>=old_received:
                received=(net.bytes_recv-old_received)/interval
            if old_sent is not None and net.bytes_sent>=old_sent:
                sent=(net.bytes_sent-old_sent)/interval
        self.previous = monotonic,d,n,net.bytes_sent if net else None,net.bytes_recv if net else None
        snapshot = Snapshot(now,sum(cores)/len(cores) if cores and warmed else None,
                            cores if warmed else [],memory.used,
                            memory.available,memory.percent,swap_used,*rates,temperature,
                            interval_s=interval,collection_s=time.monotonic()-monotonic,
                            memory_total=memory.total,cpu_frequency_mhz=frequency,
                            network_received_s=received,network_sent_s=sent,
                            swap_sampled_at=swap_at,swap_age_s=swap_age,
                            temperature_sampled_at=temperature_at,temperature_age_s=temperature_age,
                            frequency_sampled_at=frequency_at,frequency_age_s=frequency_age)
        self.history.append(snapshot)
        return snapshot

    def records(self) -> list[dict]:
        return [asdict(s) for s in self.history]
