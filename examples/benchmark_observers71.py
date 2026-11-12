"""Capture comparable, *observed* trial data (not fabricated comparison).

Examples (run on same machine, under similar load, observers started by user):
  python examples/benchmark_observers71.py --label BASELINE --output bench/base.json
  python examples/benchmark_observers71.py --label INPROCESS --observer-pid 12345 --output bench/inprocess.json
  python examples/benchmark_observers71.py --label WINDOWS_TASK_MANAGER --observer-pid 2222 --output bench/windows.json
  python examples/benchmark_observers71.py --label GNOME_SYSTEM_MONITOR --observer-pid 3333 --output bench/gnome.json
  python examples/benchmark_observers71.py --compare bench/base.json bench/inprocess.json

Do not run Task Manager and InProcess simultaneously unless intentionally
measuring that combined overhead. UI latency must be measured separately.
"""
import argparse
import json
from pathlib import Path
import sys

from expecto_process_manager.optimization.benchmarks71 import (
    LABELS,benchmark_trial,validate_comparison,write_benchmark_json,
    BenchmarkTrial,
)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--label",choices=LABELS,default="BASELINE")
    parser.add_argument("--observer-pid",type=int)
    parser.add_argument("--iterations",type=int,default=3_000_000)
    parser.add_argument("--repetitions",type=int,default=3)
    parser.add_argument("--timeout",type=float,default=30)
    parser.add_argument("--output",type=Path,default=Path("benchmarks/observer-trials.json"))
    parser.add_argument("--compare",nargs="+",type=Path,
                        help="Validate and summarize trial JSON files from other executions")
    args=parser.parse_args()
    if args.compare:
        trials=[]
        for path in args.compare:
            content=json.loads(path.read_text(encoding="utf-8"))
            trials.extend(BenchmarkTrial(**row) for row in content["trials"])
        report=validate_comparison(trials)
        print(json.dumps(report,indent=2,ensure_ascii=False))
        return 0 if report["comparable"] else 2
    if not 1<=args.repetitions<=10 or not 1000<=args.iterations<=100_000_000:
        parser.error("Limites: 1–10 repetições e 1000–100000000 iterações.")
    workload=[sys.executable,"-m",
              "expecto_process_manager.optimization.benchmark_workload71",
              "--iterations",str(args.iterations)]
    trials=[]
    for iteration in range(args.repetitions):
        trial=benchmark_trial(workload,label=args.label,
                              observer_pid=args.observer_pid,
                              timeout_s=args.timeout)
        trials.append(trial)
        print(f"{args.label}: repetição {iteration+1}/{args.repetitions} — "
              f"{trial.status}; duração={trial.task_duration_s:.3f}s")
    args.output.parent.mkdir(parents=True,exist_ok=True)
    report=write_benchmark_json(args.output,trials)
    print(json.dumps({"output":str(args.output),"analysis":report},
                     indent=2,ensure_ascii=False))
    return 0 if all(t.status=="SUCCESS" for t in trials) else 2


if __name__=="__main__":
    sys.exit(main())
