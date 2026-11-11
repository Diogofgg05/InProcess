"""Derive a compact evidence index from raw acquisition/soak/JUnit artifacts."""
import argparse
import json
from pathlib import Path
import statistics
import xml.etree.ElementTree as ET

from expecto_process_manager.physics.experimental_validation import load_session


def summarize(directory):
    directory=Path(directory)
    result=dict(schema=1,sensor_sessions=[],soaks=[],tests=[],
                interpretation='Descriptive local evidence; no physical certification or causal attribution.')
    for path in sorted(directory.glob('gpu-*/manifest.json')):
        manifest,series=load_session(path)
        result['sensor_sessions'].append(dict(manifest=str(path),run_id=manifest['run_id'],
            samples=len(series.times),duration_s=manifest['actual_duration_s'],
            device=manifest['selected_device'],temperature_min_c=min(series.temperatures),
            temperature_max_c=max(series.temperatures),power_min_w=min(series.powers),
            power_max_w=max(series.powers),errors=manifest['errors'],sha256_verified=True))
    for path in sorted(directory.glob('soak-*/soak.json')):
        raw=json.loads(path.read_text(encoding='utf-8'))
        trace=raw['trace']; phases={}
        for event in trace['events']: phases.setdefault(event['name'],[]).append(event['duration_ms'])
        callbacks={name:dict(count=len(values),median_ms=statistics.median(values),maximum_ms=max(values))
                   for name,values in phases.items()}
        gaps=trace['spikes']
        result['soaks'].append(dict(path=str(path),configured=raw['configured'],elapsed_s=raw['elapsed_s'],
            heartbeat_steady=raw['heartbeat_steady'],cpu_percent_one_core=raw['cpu_percent_one_core'],
            rss_growth_after_warmup_bytes=raw['rss_growth_after_warmup_bytes'],
            helper_count=len(raw['helpers']),helpers_exited_successfully=all(r['exit_code']==0 for r in raw['helpers']),
            owned_workers_observed=raw.get('owned_workers_observed'),collection_failures=raw['collection_failures'],
            collection_count=len(raw['history']),callbacks=callbacks,
            internal_timer_spikes_80ms=len(gaps),
            spikes_without_recorded_callbacks=sum(not s['overlapping_callbacks'] for s in gaps),
            worst_internal_spikes=sorted(gaps,key=lambda s:s['gap_ms'],reverse=True)[:10]))
    for path in sorted(directory.glob('*-tests.xml')):
        suites=ET.parse(path).getroot()
        records=list(suites.iter('testcase'))
        result['tests'].append(dict(path=str(path),tests=len(records),
            failures=sum(r.find('failure') is not None for r in records),
            errors=sum(r.find('error') is not None for r in records),
            skipped=sum(r.find('skipped') is not None for r in records),
            testcase_duration_s=sum(float(r.attrib.get('time',0)) for r in records),
            suite_duration_s=sum(float(s.attrib.get('time',0)) for s in suites.iter('testsuite'))))
    path=directory/'summary.json'
    path.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=Path('data/validation'))
    print(summarize(parser.parse_args().directory))
