"""Repeatable A/B comparison. Retain every raw run and report real tradeoffs."""
import argparse
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--duration',type=float,default=8)
    parser.add_argument('--repetitions',type=int,default=3)
    parser.add_argument('--directory',default='data')
    parser.add_argument('--reuse',action='store_true',help='Summarize existing perf-thread/process-N.json files')
    args=parser.parse_args()
    if args.repetitions<1 or args.duration<1: parser.error('Valores devem ser positivos.')
    directory=Path(args.directory)
    directory.mkdir(parents=True,exist_ok=True)
    if not args.reuse:
        env=dict(os.environ,QT_QPA_PLATFORM='offscreen')
        flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
        # Alternate modes to reduce systematic effects from the run order.
        for repetition in range(1,args.repetitions+1):
            for backend in ('thread','process'):
                subprocess.run([sys.executable,str(Path(__file__).with_name('benchmark_gui.py')),
                                '--duration',str(args.duration),'--backend',backend,'--interval','1000',
                                '--output',str(directory/f'perf-{backend}-{repetition}.json')],
                               env=env,creationflags=flags,check=True)
    result={'method':'Mean of per-trial statistics; 25 ms heartbeat; startup included; not pooled latency or input latency',
            'order':'Existing files; execution order not inferred' if args.reuse else 'Alternating thread/process',
            'repetitions':args.repetitions,'results':{}}
    for backend in ('thread','process'):
        rows=[json.loads((directory/f'perf-{backend}-{i}.json').read_text(encoding='utf-8'))
              for i in range(1,args.repetitions+1)]
        if not all('actual collector' in r['scope'] for r in rows):
            raise ValueError('Raw runs do not include the real worker/launcher resource accounting.')
        mean=lambda key:statistics.mean(r[key] for r in rows)
        result['results'][backend]={
            'collection_mean_ms':mean('collection_mean_ms'),
            'heartbeat_p95_trial_mean_ms':mean('heartbeat_p95_gap_ms'),
            'heartbeat_max_trial_mean_ms':mean('heartbeat_max_gap_ms'),
            'heartbeat_worst_gap_ms':max(r['heartbeat_max_gap_ms'] for r in rows),
            'aggregate_cpu_percent_one_core_mean':mean('tree_cpu_percent_one_core'),
            'aggregate_peak_rss_trial_mean_mib':mean('tree_rss_peak_sampled_bytes')/1024**2,
            'gui_cpu_percent_one_core_mean':mean('cpu_percent_one_core')}
    before,after=result['results']['thread'],result['results']['process']
    result['mean_max_gap_reduction_percent']=100*(1-after['heartbeat_max_trial_mean_ms']/before['heartbeat_max_trial_mean_ms'])
    result['aggregate_memory_delta_mib']=after['aggregate_peak_rss_trial_mean_mib']-before['aggregate_peak_rss_trial_mean_mib']
    result['limitations']='Short offscreen local trials; external load not controlled. Isolating native calls trades memory/CPU for fewer GUI stalls. Linux unverified.'
    path=directory/'performance-comparison.json'
    path.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
