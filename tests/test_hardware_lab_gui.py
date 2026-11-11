"""Exercise real worker-backed laboratory pages without acquiring sensors."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import time
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from expecto_process_manager.interface.hardware_lab_page import HardwareLabPage
from expecto_process_manager.interface.field_lab_page import FieldLabPage
from expecto_process_manager.simulation.hardware_experiments import SPECS
from expecto_process_manager.reporting.physical_suite import generate_physical_suite


@pytest.fixture(scope='module')
def app(): return QApplication.instance() or QApplication([])


def wait(app,page):
    deadline=time.monotonic()+20
    while (page.job or page.tasks.active()) and time.monotonic()<deadline:
        app.processEvents(); time.sleep(.002)
    app.processEvents()
    assert not page.job and not page.tasks.active()


@pytest.mark.parametrize('key',list(SPECS))
def test_model_page_executes_worker_and_draws_real_results(app,key):
    page=HardwareLabPage((key,))
    try:
        page.resize(1400,1000); page.show()
        page.duration.setText('.1'); page.dt.setText('.001')
        page.execute(); wait(app,page)
        assert page.result is not None,page.note.text()
        assert 'rk4' in page.plot.lines
        assert page.plot.y_axis.titleText()==page.result.metadata['primary_unit']
        assert 'Limitações:' in page.report.toPlainText()
        page.mode.setCurrentIndex(1)
        assert not page.import_button.isHidden()
        page.mode.setCurrentIndex(2)
        assert page.import_button.isHidden()
    finally:
        page.close(); page.deleteLater(); app.processEvents()


@pytest.mark.parametrize('kind',['conduction','acoustic'])
def test_field_page_computes_actual_field_and_spectrum(app,kind):
    page=FieldLabPage(kind)
    try:
        page.show(); page.execute(); wait(app,page)
        assert page.result is not None,page.note.text()
        assert page.result['origin']=='SIMULATED'
        assert len(page.plot.lines)==1
        if kind=='acoustic': assert page.result['spectrum']['peak_frequency']==140
        else: assert 'resíduo=' in page.report.toPlainText()
    finally:
        page.close(); page.deleteLater(); app.processEvents()


def test_ui_timer_progresses_and_cancel_preserves_editing(app):
    page=HardwareLabPage(('rc',))
    ticks=[]
    timer=QTimer(); timer.setInterval(1); timer.timeout.connect(lambda:ticks.append(1))
    try:
        timer.start()
        page.duration.setText('50'); page.dt.setText('.001')
        page.execute(); page.cancel(); wait(app,page)
        assert page.run.isEnabled()
        assert 'cancelada' in page.note.text()
        assert ticks
    finally:
        timer.stop(); page.close(); page.deleteLater(); app.processEvents()


def test_ten_priority_experiments_run_with_quantitative_checks(tmp_path):
    import json
    path=generate_physical_suite(tmp_path)
    payload=json.loads((tmp_path/'physical-suite.json').read_text(encoding='utf-8'))
    assert len(payload['experiments'])==10
    assert all(all(row['checks'].values()) for row in payload['experiments'])
    assert len(payload['benchmark'])==3
    assert '<svg' in path.read_text(encoding='utf-8')
    assert (tmp_path/'motor.csv').exists()
