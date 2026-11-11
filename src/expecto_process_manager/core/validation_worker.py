"""Bounded load helper used only by the explicit validation harness."""
import argparse
import json
import math
import os
from pathlib import Path
import time


def run(duration,duty,output):
    if not 0<duration<=3600 or not 0<=duty<=.75: raise ValueError('Carga limitada a 75% de um núcleo por trabalhador.')
    start=time.perf_counter(); cpu=time.process_time(); value=1.
    while time.perf_counter()-start<duration:
        cycle=time.perf_counter(); busy=min(start+duration,cycle+.05*duty)
        while time.perf_counter()<busy:
            for _ in range(300): value=math.sin(value)+1.1
        time.sleep(max(0,min(start+duration,cycle+.05)-time.perf_counter()))
    Path(output).write_text(json.dumps(dict(pid=os.getpid(),duration_s=time.perf_counter()-start,
        cpu_s=time.process_time()-cpu,configured_duty=duty)),encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--duration',type=float,required=True)
    parser.add_argument('--duty',type=float,required=True); parser.add_argument('--output',required=True)
    args=parser.parse_args(); run(args.duration,args.duty,args.output)
