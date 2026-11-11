"""Read-only JSON-lines worker. No Qt imports and no process-control commands.

Native monitoring calls may hold Python's GIL. Keeping them in this owned helper
lets the desktop event loop run independently, even during slow OS calls.
"""
from collections import deque
from dataclasses import asdict
import json
import os
import sys
import time
import psutil
from .providers import PsutilProvider

PROTOCOL_VERSION = 1


def serve(input_stream, output_stream) -> None:
    provider = PsutilProvider()
    worker_pid = os.getpid()
    worker_created = psutil.Process(worker_pid).create_time()
    # The desktop owns history; do not retain a second full history in the child.
    provider.monitor.history = deque(maxlen=1)
    for line in input_stream:
        try:
            request = json.loads(line)
            if request.get('version') != PROTOCOL_VERSION or request.get('op') != 'sample':
                raise ValueError('Comando de recolha inválido.')
            for pid in request.get('refresh_pids',[])[:2048]:
                if isinstance(pid,int) and pid>0:
                    provider.processes.invalidate_status(pid)
            start = time.monotonic()
            snapshot = provider.sample()
            rows = provider.list_processes()
            snapshot.collection_s = time.monotonic()-start
            published = time.time()
            for stem in ('swap','temperature','frequency'):
                at = getattr(snapshot,stem+'_sampled_at',None)
                setattr(snapshot,stem+'_age_s',max(0,published-at) if at is not None else None)
            for row in rows:
                for stem in ('status','kind'):
                    at = row.get(stem+'_sampled_at')
                    row[stem+'_age_s'] = max(0,published-at) if at is not None else None
            response = dict(version=PROTOCOL_VERSION,ok=True,snapshot=asdict(snapshot),rows=rows,
                            worker_pid=worker_pid,worker_created=worker_created)
            encoded = json.dumps(response,ensure_ascii=True,allow_nan=False)
        except Exception as error:
            encoded = json.dumps(dict(version=PROTOCOL_VERSION,ok=False,error=str(error)),ensure_ascii=True)
        output_stream.write(encoded+'\n')
        output_stream.flush()


def main() -> None:
    serve(sys.stdin,sys.stdout)


if __name__=='__main__':
    main()
