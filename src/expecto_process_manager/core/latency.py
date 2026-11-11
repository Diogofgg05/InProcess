"""Bounded callback timing and spike correlation; never claims causality."""
from collections import deque
from contextlib import contextmanager
import time


class LatencyTrace:
    def __init__(self,limit=2000):
        self.events=deque(maxlen=limit)
        self.spikes=deque(maxlen=limit)
        self.started=time.perf_counter()

    @contextmanager
    def measure(self,name):
        start=time.perf_counter()
        try: yield
        finally:
            end=time.perf_counter()
            self.events.append(dict(name=name,start_s=start-self.started,end_s=end-self.started,duration_ms=(end-start)*1000))

    def pulse(self,now,gap_s,threshold_ms=80):
        if gap_s*1000>=threshold_ms:
            end=now-self.started; start=end-gap_s
            overlap=[dict(event) for event in self.events if event['end_s']>=start and event['start_s']<=end]
            self.spikes.append(dict(at_s=end,gap_ms=gap_s*1000,overlapping_callbacks=overlap))

    def as_dict(self):
        return dict(events=list(self.events),spikes=list(self.spikes),
                    interpretation='Temporal overlap is correlation, not proof of the cause. Scheduler/GIL/OS delays may occur outside recorded callbacks.')
