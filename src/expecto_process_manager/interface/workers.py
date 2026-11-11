import logging
import time
from collections import deque
from threading import Event
from PySide6.QtCore import QObject, Signal, Slot, QRunnable, QThreadPool, QThread
from ..core.cancellation import Cancellation, Cancelled
from ..core.providers import MonitoringProvider


class Signals(QObject):
    done = Signal(object)
    failed = Signal(str)
    finished = Signal()


class Job(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = Signals()
        self.token = Cancellation()

    @Slot()
    def run(self):
        try:
            self.token.check()
            result = self.function(self.token)
            self.token.check()
            self.signals.done.emit(result)
        except Cancelled:
            self.signals.failed.emit("Operação cancelada.")
        except Exception as error:
            logging.getLogger("expecto").exception("worker_failed")
            self.signals.failed.emit(str(error))
        finally:
            self.signals.finished.emit()


class Tasks(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self.jobs: list[Job] = []

    def start(self, function, done, failed):
        job = Job(function)
        self.jobs.append(job)
        job.signals.done.connect(done)
        job.signals.failed.connect(failed)
        job.signals.finished.connect(lambda:self.jobs.remove(job) if job in self.jobs else None)
        self.pool.start(job)
        return job

    def cancel(self):
        for job in self.jobs:
            job.token.cancel()

    def active(self):
        return bool(self.jobs) or self.pool.activeThreadCount() > 0


class SamplingThread(QThread):
    collected = Signal(object)
    failed = Signal(str)

    def __init__(self, provider: MonitoringProvider, interval_ms=1000, history_limit=3600, parent=None):
        super().__init__(parent)
        self.provider = provider
        self.interval_ms = interval_ms
        self.history_limit = history_limit
        self.stop_event = Event()

    def stop(self):
        self.stop_event.set()

    def run(self):
        history = deque(maxlen=self.history_limit)
        while not self.stop_event.is_set():
            start = time.monotonic()
            try:
                snapshot = self.provider.sample()
                rows = self.provider.list_processes()
                snapshot.collection_s = time.monotonic()-start
                if history.maxlen != self.history_limit:
                    history = deque(history,maxlen=self.history_limit)
                history.append(snapshot)
                self.collected.emit((snapshot,rows,list(history)))
            except Exception as error:
                logging.getLogger("expecto").exception("collection_failed")
                self.failed.emit(str(error))
            self.stop_event.wait(max(.05,self.interval_ms/1000-(time.monotonic()-start)))
