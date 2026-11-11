import os
import time
from unittest.mock import Mock
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import Qt
from expecto_process_manager.interface.main_window import MainWindow
from expecto_process_manager.interface.processes_page import ProcessesPage
from expecto_process_manager.main import configure_app


@pytest.fixture(scope='module')
def app():
    app = QApplication.instance() or QApplication([])
    configure_app(app)
    return app


def wait(app,predicate,timeout=15):
    end = time.monotonic()+timeout
    while not predicate() and time.monotonic()<end:
        app.processEvents()
        time.sleep(.005)
    app.processEvents()
    assert predicate()
    from PySide6.QtCore import QCoreApplication,QEvent
    QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)


def test_window_and_simulation(app,tmp_path):
    window = MainWindow(settings_path=tmp_path/'settings.ini',report_directory=tmp_path/'reports')
    worker_pid=None
    try:
        window.show()
        window.physics.fields['duration'].setValue(1)
        window.physics.execute()
        wait(app,lambda:window.physics.result is not None and len(window.history_rows)>=2)
        assert window.pages.count()==9
        assert window.windowFlags() & Qt.FramelessWindowHint
        assert window.size().width()==1536 and window.size().height()==1024
        assert window.sidebar.width()==206
        assert window.titlebar.height()==60
        assert window.resources.width()==381
        assert window.footer.height()==103
        assert window.processes.table.verticalHeader().defaultSectionSize()==49
        assert [i for i in range(10) if not window.processes.table.isColumnHidden(i)]==list(range(6))
        assert window.processes.rows
        worker_pid=window.collector.child_pid
        assert worker_pid and worker_pid!=os.getpid()
        assert 'RMSE' in window.analysis.text.toPlainText()
        wait(app,lambda:window.physics.report_actions.generated is not None)
        assert os.path.isfile(window.physics.report_actions.generated.path)
        power_axes = window.physics.plots[1].chart.axes(Qt.Vertical)
        assert power_axes[0].min() < 45 < power_axes[0].max()
        assert window.history_rows[0].cpu is None
        window.grab().save('data/interface-preview.png')
        window.nav.setCurrentRow(6)
        app.processEvents()
        window.grab().save('data/laboratory-preview.png')
        window.resize(900,650)
        app.processEvents()
        assert not window.resources.isVisible()
        window.set_theme(1)
        assert app.property('dark') is False
        window.set_theme(0)
    finally:
        window.close()
        wait(app,lambda:window.closed_ready)
        import psutil
        if worker_pid: assert not psutil.pid_exists(worker_pid)


def test_numeric_sort_search_and_selection(app):
    page = ProcessesPage()
    page.grouping.setCurrentIndex(1)
    rows = [dict(pid=i,name=name,user='test',created=1,status='running',cpu=cpu,memory=200*1024**2,elapsed=1)
            for i,name,cpu in [(1,'alpha',2),(2,'beta',10),(3,'gamma',None)]]
    page.update_rows(rows)
    page.table.sortByColumn(2,Qt.DescendingOrder)
    assert page.proxy.index(0,1).data()=='2'
    page.table.selectRow(0)
    page.update_rows(rows)
    assert page.selected()['pid']==2
    page.search.setText('ALPHA')
    assert page.proxy.rowCount()==1
    assert page.proxy.index(0,0).data()=='alpha'
    page.search.clear()
    page.filter.setCurrentIndex(1)
    assert page.proxy.rowCount()==2
    rows[0]['kind'] = 'application'
    rows[1]['kind'] = 'service'
    rows[2]['kind'] = 'process'
    page.update_rows(rows)
    for mode,name in [(3,'alpha'),(4,'beta'),(5,'gamma')]:
        page.filter.setCurrentIndex(mode)
        assert page.proxy.rowCount()==1
        assert page.proxy.index(0,0).data()==name
    page.close()
    page.deleteLater()


def test_navigation_defers_process_models_and_icon_requests_without_losing_latest_data(app,tmp_path,monkeypatch):
    from expecto_process_manager.core.monitoring import Snapshot
    window=MainWindow(settings_path=tmp_path/'settings.ini',report_directory=tmp_path/'reports')
    try:
        request=Mock()
        monkeypatch.setattr(window.process_icons,'request',request)
        snapshot=Snapshot(100,25,[25],100,200,33,None,None,None,None)
        first=[dict(pid=123,name='example.exe',created=100,user='test',status='running',
                    elapsed=1,cpu=1,memory=2000,disk=0,network=None,gpu=None)]
        window.collected((snapshot,first,[snapshot]))
        assert request.call_count==1
        window.nav.setCurrentRow(2)
        latest=[dict(first[0],cpu=50)]
        window.collected((snapshot,latest,[snapshot]))
        assert window.processes.rows==latest
        assert window.processes.model.rows==first and request.call_count==1
        window.nav.setCurrentRow(0)
        assert window.processes.model.rows==latest and request.call_count==2
    finally:
        window.close(); wait(app,lambda:window.closed_ready)


def test_confirmation_and_async_close(app,tmp_path,monkeypatch):
    window = MainWindow(settings_path=tmp_path/'settings.ini')
    # Native shell icon extraction is covered separately and may outlast a
    # control operation under system load; this test exercises confirmation
    # and cancellation, without waiting for unrelated shell calls.
    monkeypatch.setattr(window.process_icons,'request',lambda _:None)
    service = Mock()
    window.service = service
    row = dict(pid=123,name='mock',created=1)
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.No)
    window.control(row,'terminate')
    service.control.assert_not_called()
    monkeypatch.setattr(QMessageBox,'question',lambda *args:QMessageBox.Yes)
    window.control(row,'terminate')
    wait(app,lambda:not window.tasks.active())
    service.control.assert_called_once_with(123,1,'terminate',authorized=True)
    window.physics.fields['duration'].setValue(1900)
    window.physics.step.setCurrentText('0.01')
    window.physics.execute()
    start = time.monotonic()
    window.close()
    assert time.monotonic()-start<.5
    wait(app,lambda:window.closed_ready)
    from shiboken6 import isValid
    assert not isValid(window.collector) or not window.collector.isRunning()


def test_preferences_and_inventory_error(app,tmp_path):
    path = tmp_path/'settings.ini'
    window = MainWindow(settings_path=path)
    window.set_interval(5000)
    window.set_history_limit(120)
    window.set_theme(1)
    page = window.inventory_pages[0]
    page.failed('erro de teste')
    assert 'indisponível' in page.note.text()
    window.close()
    wait(app,lambda:window.closed_ready)
    reopened = MainWindow(settings_path=path)
    try:
        assert reopened.settings_page.interval.value()==5000
        assert reopened.settings_page.limit.value()==120
        assert app.property('dark') is False
    finally:
        reopened.close()
        wait(app,lambda:reopened.closed_ready)
        configure_app(app)


def test_native_executable_icon(app):
    import platform
    import psutil
    from expecto_process_manager.core.cancellation import Cancellation
    from expecto_process_manager.interface.process_icons import extract_icons
    if platform.system()!='Windows':
        pytest.skip('Extração HICON específica de Windows.')
    process=psutil.Process()
    result=extract_icons([dict(pid=process.pid,created=process.create_time(),name=process.name())],Cancellation())
    assert process.name() in result
    assert not result[process.name()].isNull()


def test_custom_window_controls(app,tmp_path):
    from PySide6.QtTest import QTest
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QToolButton
    window=MainWindow(settings_path=tmp_path/'chrome.ini')
    try:
        window.show()
        app.processEvents()
        window.titlebar.toggle_maximize()
        app.processEvents()
        assert window.isMaximized()
        window.titlebar.toggle_maximize()
        app.processEvents()
        assert not window.isMaximized()
        QTest.mousePress(window,Qt.LeftButton,Qt.NoModifier,QPoint(3,3))
        QTest.mouseRelease(window,Qt.LeftButton,Qt.NoModifier,QPoint(3,3))
        close=window.titlebar.findChild(QToolButton,'closeControl')
        close.click()
        wait(app,lambda:window.closed_ready)
    finally:
        if not window.closed_ready:
            window.close()
            wait(app,lambda:window.closed_ready)


def test_gravity_and_free_fall_integrated(app,tmp_path):
    window=MainWindow(settings_path=tmp_path/'physics.ini')
    try:
        window.show()
        window.open_gravity()
        assert window.laboratory.currentIndex()==1
        window.gravity.execute()
        wait(app,lambda:window.gravity.result is not None and len(window.history_rows)>=2)
        assert len(window.gravity.result.trajectories)==3
        assert 'Euler explícito' in window.gravity.report.toPlainText()
        assert window.gravity.result.provenance=='simulado'
        app.processEvents()
        window.grab().save('data/gravity-integrated-preview.png')
        window.laboratory.setCurrentIndex(2)
        window.free_fall.execute()
        wait(app,lambda:window.free_fall.result is not None)
        result=window.free_fall.result
        assert result.times[-1]==4
        assert result.heights[-1]>result.reference_heights[-1]
        app.processEvents()
        window.grab().save('data/free-fall-integrated-preview.png')
    finally:
        window.close()
        wait(app,lambda:window.closed_ready)


def test_plot_reuses_scene_objects(app):
    from expecto_process_manager.interface.charts import Plot
    plot=Plot('Teste de atualização','W')
    plot.update_series([0,1],{'Entrada':[10,20]})
    x,y,line=plot.x_axis,plot.y_axis,plot.lines['Entrada']
    for i in range(10):
        plot.update_series([0,1],{'Entrada':[10+i,20+i]})
    assert plot.x_axis is x and plot.y_axis is y
    assert plot.lines['Entrada'] is line
    assert y.min()<19<29<y.max()
    plot.close()
    plot.deleteLater()


def test_lazy_scientific_pages_and_reports(app,tmp_path):
    window=MainWindow(settings_path=tmp_path/'lazy.ini',report_directory=tmp_path/'reports')
    try:
        window.show()
        app.processEvents()
        assert not window.laboratory.created
        window.nav.setCurrentRow(6)
        window.laboratory.setCurrentIndex(4)
        calibration=window.laboratory.ensure(4)
        calibration.execute()
        wait(app,lambda:calibration.report_actions.generated is not None,timeout=25)
        assert calibration.result.capacity>0
        path=calibration.report_actions.generated.path
        assert 'ESTIMATED' in open(path,encoding='utf-8').read()
        calibration.report_actions.open()
        app.processEvents()
        calibration.report_actions.dialog.grab().save('data/report-preview.png')
        calibration.report_actions.dialog.close()
        window.grab().save('data/calibration-integrated-preview.png')
        window.laboratory.setCurrentIndex(6)
        eco=window.laboratory.ensure(6)
        eco.execute()
        wait(app,lambda:eco.report_actions.generated is not None)
        assert eco.result.comparable
        window.grab().save('data/energy-integrated-preview.png')
    finally:
        window.close()
        wait(app,lambda:window.closed_ready)
