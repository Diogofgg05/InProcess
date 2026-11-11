"""GUI heartbeat, GUI resources, and aggregate resources of owned workers."""
import argparse
import json
import platform
import statistics
import time
from pathlib import Path
import tempfile
import psutil
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from expecto_process_manager.main import configure_app
from expecto_process_manager.interface.main_window import MainWindow
from expecto_process_manager.core.providers import PsutilProvider


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--duration',type=float,default=10)
    parser.add_argument('--interval',type=int,default=1000)
    parser.add_argument('--backend',choices=['process','thread'],default='process')
    parser.add_argument('--output',default='benchmark-gui-results.json')
    args=parser.parse_args()
    if args.duration<1 or not 250<=args.interval<=10000: parser.error('Duração >=1 s; intervalo 250–10000 ms')
    app=QApplication([])
    configure_app(app)
    with tempfile.TemporaryDirectory() as directory:
        window=MainWindow(provider=PsutilProvider() if args.backend=='thread' else None,
                          settings_path=Path(directory)/'preferences.ini')
        window.set_interval(args.interval)
        window.show()
        process=psutil.Process()
        cpu_start=process.cpu_times()
        start=time.perf_counter()
        last=[start]
        gaps,rss,tree_rss=[],[],[]
        child_cpu={}
        child_baselines={}
        owned={}
        for initial_pid in getattr(window.collector,'owned_pids',()):
            try:
                owned[initial_pid]=psutil.Process(initial_pid)
                times=owned[initial_pid].cpu_times()
                child_baselines[initial_pid]=times.user+times.system
            except psutil.Error: pass
        def resources():
            parent_rss=process.memory_info().rss
            total_rss=parent_rss
            # Never enumerate the whole OS process tree every 25 ms: that
            # monitoring overhead would dominate the latency being measured.
            for pid in getattr(window.collector,'owned_pids',()):
                if pid not in owned:
                    try: owned[pid]=psutil.Process(pid)
                    except psutil.Error: continue
                child=owned[pid]
                try:
                    times=child.cpu_times()
                    child_cpu[child.pid]=max(child_cpu.get(child.pid,0),times.user+times.system)
                    total_rss+=child.memory_info().rss
                except psutil.Error: pass
            rss.append(parent_rss)
            tree_rss.append(total_rss)
        def heartbeat():
            now=time.perf_counter()
            gaps.append(now-last[0])
            last[0]=now
            resources()
        timer=QTimer()
        timer.setInterval(25)
        timer.timeout.connect(heartbeat)
        timer.start()
        capture={}
        def finish():
            timer.stop()
            resources()
            elapsed=time.perf_counter()-start
            cpu_end=process.cpu_times()
            cpu=cpu_end.user+cpu_end.system-cpu_start.user-cpu_start.system
            workers_cpu=sum(max(0,value-child_baselines.get(pid,0)) for pid,value in child_cpu.items())
            ordered=sorted(gaps)
            capture.update(scope='Including startup; GUI + actual collector + Windows venv launcher; cached process handles; heartbeat is not input latency',
                           backend=args.backend,platform=platform.platform(),qt_platform=app.platformName(),interval_ms=args.interval,
                           actual_duration_s=elapsed,cpu_s=cpu,cpu_percent_one_core=100*cpu/elapsed,
                           worker_cpu_s=workers_cpu,tree_cpu_s=cpu+workers_cpu,
                           tree_cpu_percent_one_core=100*(cpu+workers_cpu)/elapsed,
                           rss_peak_sampled_bytes=max(rss,default=0),tree_rss_peak_sampled_bytes=max(tree_rss,default=0),
                           heartbeat_count=len(gaps),heartbeat_max_gap_ms=max(gaps,default=0)*1000,
                           heartbeat_p95_gap_ms=ordered[min(len(ordered)-1,int(len(ordered)*.95))]*1000 if ordered else None,
                           collection_count=len(window.history_rows),
                           collection_mean_ms=statistics.mean(s.collection_s*1000 for s in window.history_rows) if window.history_rows else None)
            window.grab().save('data/dashboard-preview.png')
            window.close()
        QTimer.singleShot(int(args.duration*1000),finish)
        app.exec()
        Path(args.output).write_text(json.dumps(capture,indent=2),encoding='utf-8')
        print(json.dumps(capture,indent=2))


if __name__=='__main__': main()
