"""Deterministic UI update workload; synthetic data, no OS process queries.

Run the same script before/after changes. The regular result excludes profiling;
--profile is a separate diagnostic run and includes profiler overhead.
"""
import argparse
import cProfile
import io
import json
import pstats
import statistics
import time
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from expecto_process_manager.main import configure_app
from expecto_process_manager.interface.processes_page import ProcessesPage


def rows(count,tick):
    return [dict(pid=i+100,created=1700000000+i,name=f'Application {i%60:02d}.exe',user='benchmark',
        status='running',cpu=(i%17+tick*.1)%100,memory=20000000+i*1024+tick*4096,
        disk=1000.+i+tick,network=None,gpu=None,elapsed=100.+tick,
        status_sampled_at=1700001000.,status_age_s=float(tick%5)) for i in range(count)]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rows',type=int,default=600)
    parser.add_argument('--updates',type=int,default=40)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--profile',action='store_true')
    args=parser.parse_args()
    if not 60<=args.rows<=10000 or not 10<=args.updates<=200: parser.error('Rows 60..10000; updates 10..200.')
    app=QApplication([]); configure_app(app)
    result=dict(origin='SIMULATED',rows=args.rows,updates=args.updates,profiled=args.profile,
                scope='Process page update and Qt event processing; no sampling, native icon extraction or input latency',cases={})
    profiler=cProfile.Profile() if args.profile else None
    for name,expanded,sort,flat in [('grouped',False,0,False),('expanded',True,0,False),
                                     ('cpu_sorted',True,2,False),('flat',False,2,True)]:
        page=ProcessesPage(); page.resize(1200,800); page.show()
        page.update_rows(rows(args.rows,0)); app.processEvents()
        page.grouping.setCurrentIndex(1 if flat else 0)
        view=page.table if flat else page.tree
        view.sortByColumn(sort,Qt.DescendingOrder if sort else Qt.AscendingOrder)
        if expanded:
            for i in range(min(10,page.groups.rowCount())): page.tree.expand(page.groups.index(i,0))
        for tick in range(1,4): page.update_rows(rows(args.rows,tick)); app.processEvents()
        timings=[]
        if profiler: profiler.enable()
        for tick in range(4,args.updates+4):
            data=rows(args.rows,tick)
            start=time.perf_counter()
            page.update_rows(data); app.processEvents()
            timings.append((time.perf_counter()-start)*1000)
        if profiler: profiler.disable()
        ordered=sorted(timings)
        result['cases'][name]=dict(median_ms=statistics.median(timings),mean_ms=statistics.mean(timings),
                                   p95_ms=ordered[min(len(ordered)-1,int(len(ordered)*.95))],
                                   maximum_ms=max(timings),samples_ms=timings)
        page.close(); page.deleteLater(); app.processEvents()
    if profiler:
        output=io.StringIO(); pstats.Stats(profiler,stream=output).strip_dirs().sort_stats('cumulative').print_stats(25)
        result['profile']=output.getvalue()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({name:{k:v for k,v in case.items() if k!='samples_ms'} for name,case in result['cases'].items()},indent=2))
    if profiler: print(result['profile'])


if __name__=='__main__': main()
