"""Own a monitoring subprocess; termination never targets user processes."""
from collections import deque
import json
import os
import subprocess
import sys
import psutil
from threading import Event,Lock
from PySide6.QtCore import QThread,Signal
from ..core.monitoring import Snapshot
from ..core.sampling_process import PROTOCOL_VERSION


class ProcessSamplingThread(QThread):
    collected = Signal(object)
    failed = Signal(str)
    backend = 'Processo isolado (psutil)'

    def __init__(self,interval_ms=1000,history_limit=3600,parent=None):
        super().__init__(parent)
        self.interval_ms = interval_ms
        self.history_limit = history_limit
        self.stop_event = Event()
        self._process = None
        self._worker_pid = None
        self._worker_created = None
        self._refresh = set()
        self._refresh_lock = Lock()

    def invalidate_status(self,pid):
        with self._refresh_lock:
            self._refresh.add(pid)

    @property
    def child_pid(self):
        # Windows venv python.exe may be a small redirector whose child actually
        # performs sampling. The worker reports its real PID on the private pipe.
        return self._worker_pid or (self._process.pid if self._process else None)

    @property
    def owned_pids(self):
        return tuple(dict.fromkeys(pid for pid in
                                   (self._process.pid if self._process else None,self._worker_pid) if pid))

    def _terminate_worker(self):
        if self._worker_pid and self._process and self._worker_pid!=self._process.pid:
            try:
                worker=psutil.Process(self._worker_pid)
                if worker.create_time()==self._worker_created:
                    worker.terminate()
            except psutil.Error:
                pass

    def stop(self):
        self.stop_event.set()
        self._terminate_worker()
        process = self._process
        if process and process.poll() is None:
            # Only our read-only helper; it never performs user mutations/writes.
            try: process.terminate()
            except OSError: pass

    def run(self):
        history = deque(maxlen=self.history_limit)
        try:
            if self.stop_event.is_set(): return
            flags = subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
            process = subprocess.Popen([sys.executable,'-u','-m','expecto_process_manager.core.sampling_process'],
                                       stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                                       text=True,encoding='utf-8',bufsize=1,creationflags=flags)
            self._process = process
            if self.stop_event.is_set():
                process.terminate()
                return
            while not self.stop_event.is_set():
                with self._refresh_lock:
                    refresh = list(self._refresh)
                    self._refresh.clear()
                request = json.dumps(dict(version=PROTOCOL_VERSION,op='sample',refresh_pids=refresh))+'\n'
                process.stdin.write(request)
                process.stdin.flush()
                line = process.stdout.readline(16*1024*1024)
                if self.stop_event.is_set(): break
                if not line or not line.endswith('\n'):
                    raise RuntimeError('O processo de recolha terminou ou excedeu o limite de resposta.')
                payload = json.loads(line)
                if payload.get('version') != PROTOCOL_VERSION:
                    raise ValueError('Versão do fornecedor incompatível.')
                if not payload.get('ok'):
                    self.failed.emit(payload.get('error','Recolha indisponível.'))
                else:
                    self._worker_pid = payload['worker_pid']
                    self._worker_created = payload['worker_created']
                    snapshot = Snapshot(**payload['snapshot'])
                    if history.maxlen != self.history_limit:
                        history = deque(history,maxlen=self.history_limit)
                    history.append(snapshot)
                    self.collected.emit((snapshot,payload['rows'],list(history)))
                # Use the actual collection cost, not the time spent waiting for
                # the GUI. Long calls skip missed deadlines instead of piling up.
                elapsed = payload.get('snapshot',{}).get('collection_s',0)
                self.stop_event.wait(max(.02,self.interval_ms/1000-elapsed))
        except Exception as error:
            if not self.stop_event.is_set():
                self.failed.emit(f'Fornecedor isolado: {error}')
        finally:
            process = self._process
            if process:
                self._terminate_worker()
                if process.poll() is None:
                    try: process.terminate()
                    except OSError: pass
                # This wait runs in the reader thread, never the GUI thread.
                try: process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
                for stream in (process.stdin,process.stdout):
                    if stream:
                        try: stream.close()
                        except OSError: pass
