"""Synthetic page updates and icon delivery, without OS queries or extraction."""
import argparse
import json
from pathlib import Path
import statistics
import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage,QColor
from PySide6.QtWidgets import QApplication

from expecto_process_manager.main import configure_app
from expecto_process_manager.interface.processes_page import ProcessesPage
from expecto_process_manager.interface.process_icons import ProcessIcons
from benchmark_ui_updates import rows


def benchmark(updates):
    app=QApplication([]); configure_app(app)
    results={}
    for case in ('visible','hidden','icons'):
        page=ProcessesPage(); page.resize(1200,800); page.show()
        page.update_rows(rows(600,0)); app.processEvents()
        page.tree.sortByColumn(2,Qt.DescendingOrder)
        for i in range(10): page.tree.expand(page.groups.index(i,0))
        images=[]
        for color in ('#157aff','#8754da'):
            image=QImage(28,28,QImage.Format_ARGB32); image.fill(QColor(color)); images.append(image)
        icons=ProcessIcons(page.model,None)
        for tick in range(1,4): page.update_rows(rows(600,tick)); app.processEvents()
        if case=='hidden':
            page.hide(); app.processEvents()
            if hasattr(page,'set_display_active'): page.set_display_active(False)
        values=[]
        for tick in range(4,updates+4):
            data=rows(600,tick)
            delivery={f'Application {i:02d}.exe':images[tick%2] for i in range(16)}
            start=time.perf_counter()
            if case=='icons': icons.loaded(delivery)
            else: page.update_rows(data)
            app.processEvents()
            values.append((time.perf_counter()-start)*1000)
        restored=None
        if case=='hidden':
            start=time.perf_counter()
            if hasattr(page,'set_display_active'): page.set_display_active(True)
            page.show(); app.processEvents()
            restored=(time.perf_counter()-start)*1000
            assert page.model.rows==data
        ordered=sorted(values)
        results[case]=dict(median_ms=statistics.median(values),
            p95_ms=ordered[min(len(values)-1,int(len(values)*.95))],maximum_ms=max(values),
            restore_and_show_ms=restored,samples_ms=values)
        page.close(); page.deleteLater(); app.processEvents()
    return dict(origin='SIMULATED',qt_platform=app.platformName(),rows=600,updates=updates,cases=results,
        scope='Process page and Qt events; ten expanded groups sorted by CPU. '
              'Hidden updates retain latest snapshot, return cost measured separately. '
              'Icons: delivery of sixteen generated images per batch, no native extraction. '
              'Not click latency, system CPU or a maximum-latency guarantee.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--updates',type=int,default=40)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not 10<=args.updates<=200: parser.error('Updates 10..200.')
    result=benchmark(args.updates)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:{a:b for a,b in v.items() if a!='samples_ms'} for k,v in result['cases'].items()},indent=2))
