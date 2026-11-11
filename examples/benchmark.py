"""Repeated real API collections. Run separately from tests/GUI benchmarks."""
import argparse
import json
import statistics
import time
import platform
from pathlib import Path
import psutil
from expecto_process_manager.core.providers import PsutilProvider


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--samples',type=int,default=5)
    parser.add_argument('--repetitions',type=int,default=3)
    parser.add_argument('--output',default='benchmark-results.json')
    args = parser.parse_args()
    if args.samples<1 or args.repetitions<1: parser.error('Valores devem ser positivos')
    provider = PsutilProvider()
    process = psutil.Process()
    measurements = []
    provider.list_processes()
    for repetition in range(args.repetitions):
        cpu_start = process.cpu_times()
        start = time.perf_counter()
        durations = []
        for _ in range(args.samples):
            tick = time.perf_counter()
            provider.sample()
            provider.list_processes()
            durations.append(time.perf_counter()-tick)
        elapsed = time.perf_counter()-start
        cpu_end = process.cpu_times()
        cpu = cpu_end.user+cpu_end.system-cpu_start.user-cpu_start.system
        measurements.append(dict(repetition=repetition+1,samples=args.samples,wall_s=elapsed,cpu_s=cpu,
                                 cpu_percent_one_core=100*cpu/elapsed,rss_bytes=process.memory_info().rss,
                                 collection_mean_s=statistics.mean(durations),collection_max_s=max(durations)))
    result = dict(scope='API: system + process collections, consecutive samples, no GUI',
                  platform=platform.platform(),python=platform.python_version(),measurements=measurements,
                  mean_collection_s=statistics.mean(m['collection_mean_s'] for m in measurements),
                  between_repetitions_stdev_s=statistics.stdev(m['collection_mean_s'] for m in measurements) if len(measurements)>1 else 0)
    Path(args.output).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
