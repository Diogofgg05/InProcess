"""Summarize retained before/after runs without rerunning or cherry-picking."""
import argparse
import json
import platform
import statistics
from pathlib import Path


def summarize(directory):
    directory=Path(directory)
    result={'environment':platform.platform(),'ui':{},'real_gui':{},
            'limitations':'UI workload is synthetic (600 rows, 30 timed updates per view). Real GUI trials: three sequential 8 s trials before and after, startup included, 1000 ms sampling, Qt offscreen. External load is not controlled. Heartbeat gaps are not click latency, power or frame rate.'}
    before=json.loads((directory/'ui-before.json').read_text(encoding='utf-8'))
    after=json.loads((directory/'ui-after.json').read_text(encoding='utf-8'))
    if before['profiled'] or after['profiled'] or (before['rows'],before['updates'])!=(after['rows'],after['updates']):
        raise ValueError('Os ensaios não têm a mesma carga, ou incluem overhead de profiling.')
    result['workload']={k:before[k] for k in ('rows','updates','scope')}
    for name,old in before['cases'].items():
        new=after['cases'][name]
        result['ui'][name]=dict(before_median_ms=old['median_ms'],after_median_ms=new['median_ms'],
            reduction_percent=100*(1-new['median_ms']/old['median_ms']),
            before_p95_ms=old['p95_ms'],after_p95_ms=new['p95_ms'])
    for phase in ('before','after'):
        trials=[json.loads((directory/f'{phase}-{i}.json').read_text(encoding='utf-8')) for i in range(1,4)]
        if not all(trial['backend']=='process' and trial['interval_ms']==1000 and 'actual collector' in trial['scope'] for trial in trials):
            raise ValueError('Os ensaios reais usam fornecedores ou cadências incompatíveis.')
        result['real_gui'][phase]={key:statistics.mean(trial[key] for trial in trials) for key in
            ('cpu_percent_one_core','tree_cpu_percent_one_core','collection_mean_ms',
             'heartbeat_p95_gap_ms','heartbeat_max_gap_ms')}
        result['real_gui'][phase]['worst_gap_ms']=max(trial['heartbeat_max_gap_ms'] for trial in trials)
        result['real_gui'][phase]['aggregate_peak_rss_mean_mib']=statistics.mean(trial['tree_rss_peak_sampled_bytes'] for trial in trials)/1024**2
    result['gui_cpu_reduction_percent']=100*(1-result['real_gui']['after']['cpu_percent_one_core']/result['real_gui']['before']['cpu_percent_one_core'])
    target=directory/'summary.json'
    target.write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',default='data/sidebar-optimization')
    print(json.dumps(summarize(parser.parse_args().directory),indent=2))
