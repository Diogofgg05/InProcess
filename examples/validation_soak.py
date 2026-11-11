"""Sustained real monitoring, bounded owned-process load/churn, raw spike logs."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import time
import psutil
from PySide6.QtCore import QTimer,Qt
from PySide6.QtWidgets import QApplication
from expecto_process_manager.main import configure_app
from expecto_process_manager.interface.main_window import MainWindow


def statistics_ms(values):
    ordered=sorted(values)
    return dict(count=len(values),median_ms=statistics.median(values) if values else None,
        p95_ms=ordered[min(len(values)-1,int(len(values)*.95))] if values else None,
        p99_ms=ordered[min(len(values)-1,int(len(values)*.99))] if values else None,
        maximum_ms=max(values,default=None))


def run(args):
    if not 10<=args.duration<=3600 or not 0<=args.workers<=2: raise ValueError('Duração 10..3600 s; até dois trabalhadores.')
    if not 0<=args.duty<=.5: raise ValueError('Duty entre 0 e 50% de um núcleo por trabalhador.')
    output=args.output.resolve(); output.mkdir(parents=True,exist_ok=True)
    if (output/'soak.json').exists() or any(output.glob('worker-*.json')):
        raise ValueError('A pasta já contém um ensaio; escolhe outra pasta para preservar os dados.')
    app=QApplication([]); configure_app(app)
    helpers=[]; failures=[]; telemetry=[]; heartbeats=[]; row_metrics=[]; seen=set(); previous=set()
    start=time.perf_counter(); main_process=psutil.Process(); base_cpu=main_process.cpu_times()
    def spawn(duration,duty,kind):
        target=output/f'worker-{len(helpers)}.json'
        process=subprocess.Popen([sys.executable,'-m','expecto_process_manager.core.validation_worker',
            '--duration',str(duration),'--duty',str(duty),'--output',str(target)],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        helpers.append(dict(process=process,path=target,kind=kind,launched_s=time.perf_counter()-start))
    with tempfile.TemporaryDirectory() as directory:
        window=MainWindow(settings_path=Path(directory)/'settings.ini',report_directory=Path(directory)/'reports')
        window.set_interval(1000); window.set_history_limit(600); window.show()
        window.collector.failed.connect(failures.append)
        for _ in range(args.workers): spawn(max(1,args.duration-1),args.duty,'sustained')
        last=[time.perf_counter()]
        def beat():
            now=time.perf_counter(); heartbeats.append(dict(time_s=now-start,gap_ms=(now-last[0])*1000)); last[0]=now
        heartbeat=QTimer(); heartbeat.setTimerType(Qt.PreciseTimer); heartbeat.setInterval(25); heartbeat.timeout.connect(beat); heartbeat.start()
        def observe():
            nonlocal previous
            now=time.perf_counter()-start
            ids={(row['pid'],row['created']) for row in window.processes.rows}
            row_metrics.append(dict(time_s=now,visible_processes=len(ids),arrivals=len(ids-previous),departures=len(previous-ids)))
            seen.update(pid for pid,created in ids); previous=ids
            cpu=main_process.cpu_times()
            telemetry.append(dict(time_s=now,rss_bytes=main_process.memory_info().rss,
                                   cpu_s=cpu.user+cpu.system-base_cpu.user-base_cpu.system))
        observer=QTimer(); observer.setInterval(1000); observer.timeout.connect(observe); observer.start()
        def churn():
            if time.perf_counter()-start<args.duration-4:
                for _ in range(2): spawn(2.,.10,'churn')
        churn_timer=QTimer(); churn_timer.setInterval(5000); churn_timer.timeout.connect(churn); churn_timer.start()
        pages=[0,1,2,8]; phase=[0]
        def navigate():
            phase[0]+=1; window.nav.setCurrentRow(pages[phase[0]%len(pages)])
            if window.nav.currentRow()==0:
                window.processes.tree.sortByColumn(2,Qt.DescendingOrder)
                for i in range(min(5,window.processes.groups.rowCount())): window.processes.tree.expand(window.processes.groups.index(i,0))
        navigation=QTimer(); navigation.setInterval(20000); navigation.timeout.connect(navigate); navigation.start()
        ended={}
        def finish():
            for timer in (heartbeat,observer,churn_timer,navigation): timer.stop()
            observe(); ended['trace']=window.latency_trace.as_dict()
            ended['history']=[dict(timestamp=s.timestamp,collection_ms=s.collection_s*1000,interval_s=s.interval_s) for s in window.history_rows]
            window.close()
        deadline=QTimer(); deadline.setTimerType(Qt.PreciseTimer); deadline.setSingleShot(True)
        deadline.timeout.connect(finish); deadline.start(round(args.duration*1000))
        try: app.exec()
        finally:
            for helper in helpers:
                p=helper['process']
                if p.poll() is None:
                    try: p.wait(timeout=2)
                    except subprocess.TimeoutExpired: p.terminate(); p.wait(timeout=3)
        records=[]
        for helper in helpers:
            p=helper['process']; entry=dict(kind=helper['kind'],launcher_pid=p.pid,exit_code=p.returncode,launched_s=helper['launched_s'])
            if helper['path'].exists(): entry.update(json.loads(helper['path'].read_text(encoding='utf-8')))
            records.append(entry)
        warmup=min(20,args.duration/4)
        steady=[h['gap_ms'] for h in heartbeats if h['time_s']>=warmup]
        stable_memory=[t['rss_bytes'] for t in telemetry if t['time_s']>=warmup]
        end_cpu=main_process.cpu_times(); elapsed=time.perf_counter()-start
        cpu_s=end_cpu.user+end_cpu.system-base_cpu.user-base_cpu.system
        report=dict(schema=1,origin='MEASURED_OS',platform=platform.platform(),python=platform.python_version(),
            qt_platform=app.platformName(),finished_at=datetime.now(timezone.utc).isoformat(),
            configured=dict(duration_s=args.duration,workers=args.workers,duty_per_worker=args.duty,sampling_ms=1000,churn_every_s=5),
            elapsed_s=elapsed,warmup_excluded_s=warmup,heartbeat_all=statistics_ms([h['gap_ms'] for h in heartbeats]),
            heartbeat_steady=statistics_ms(steady),cpu_percent_one_core=100*cpu_s/elapsed,
            rss_growth_after_warmup_bytes=statistics.median(stable_memory[-10:])-statistics.median(stable_memory[:10]) if stable_memory else None,
            helpers=records,owned_launchers_observed=sum(r['launcher_pid'] in seen for r in records),
            owned_workers_observed=sum(r.get('pid') in seen for r in records),
            collection_failures=failures,heartbeat_samples=heartbeats,resources=telemetry,process_churn=row_metrics,
            **ended,limitations=['Single machine, local OS measurements, external load uncontrolled.',
                'Two workers at 50% duty target at most one effective core, not maximum system stress.',
                'Temporal callback overlap is not causal attribution; heartbeat is not click latency.',
                'WSL/Linux runs, when present, are a different OS on the same hardware, not another computer.'])
        path=output/'soak.json'; path.write_text(json.dumps(report,indent=2),encoding='utf-8'); return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration',type=float,default=180)
    parser.add_argument('--workers',type=int,default=2)
    parser.add_argument('--duty',type=float,default=.5)
    parser.add_argument('--output',type=Path,default=Path('data/validation/soak'))
    print(run(parser.parse_args()))
