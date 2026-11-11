"""Automatic visible-page refresh and history continuity across samples."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from unittest.mock import Mock
from dataclasses import replace
import pytest
from PySide6.QtWidgets import QApplication,QPushButton
from PySide6.QtCore import QPersistentModelIndex
from expecto_process_manager.core.monitoring import Snapshot
from expecto_process_manager.interface.history_page import HistoryPage,HistoryModel
from expecto_process_manager.interface.inventory_page import InventoryPage
from expecto_process_manager.interface.performance_page import PerformancePage


@pytest.fixture(scope='module')
def app(): return QApplication.instance() or QApplication([])


def snapshot(t,cpu=25):
    return Snapshot(timestamp=t,cpu=cpu,cores=[25],memory_used=100,memory_available=200,
                    memory_percent=33,swap_used=None,disk_bytes_s=None,network_bytes_s=None,temperature_c=None)


def test_history_inserts_without_resetting_selection_and_retains_newest_limit(app):
    model=HistoryModel()
    a,b,c=snapshot(1),snapshot(2),snapshot(3)
    model.update([a,b])
    selected=QPersistentModelIndex(model.index(0,0))
    reset=Mock(); model.modelReset.connect(reset)
    model.update([b,c])
    assert not reset.called
    assert selected.isValid() and selected.row()==1
    assert selected.data(256)==2
    assert [row.timestamp for row in model.rows]==[3,2]
    model.update([replace(b,cpu=80),c])
    assert model.rows[1].cpu==80


def test_history_period_metrics_exclude_missing_cpu_and_export_remains_available(app):
    page=HistoryPage()
    try:
        page.refresh([snapshot(0,None),snapshot(100,10),snapshot(500,30),snapshot(600,50)])
        assert page.metrics['count'].text()=='4'
        assert page.metrics['average'].text()=='30,0 %'
        page.period.setCurrentIndex(1)
        assert page.model.rowCount()==2
        assert page.metrics['average'].text()=='40,0 %'
        assert page.metrics['peak'].text()=='50,0 %'
        exported=Mock(); page.export_requested.connect(exported)
        page.export_button.click(); exported.assert_called_once()
    finally: page.close(); page.deleteLater(); app.processEvents()


@pytest.mark.parametrize('kind',['startup','users','services'])
def test_inventory_polls_only_while_visible_without_overlapping_jobs(app,kind):
    tasks=Mock()
    page=InventoryPage('Inventário',kind,tasks)
    try:
        page.show(); app.processEvents()
        assert page.timer.isActive()
        assert tasks.start.call_count==1
        page.timer.timeout.emit()
        assert tasks.start.call_count==1
        page.display((['Nome','Estado'],[['example','running']],'Leitura'))
        page.search.setText('missing'); assert page.proxy.rowCount()==0
        page.search.setText('example'); assert page.proxy.rowCount()==1
        page.timer.timeout.emit(); assert tasks.start.call_count==2
        page.hide(); assert not page.timer.isActive()
        assert not any('Atualizar' in button.text() for button in page.findChildren(QPushButton))
        page.failed('private platform error')
        assert 'indisponível' in page.note.text()
        assert 'private platform error' not in page.note.text()
    finally: page.close(); page.deleteLater(); app.processEvents()


def test_monitoring_shows_graphs_without_the_old_technical_text(app):
    page=PerformancePage()
    try:
        page.show(); page.refresh([snapshot(0),snapshot(1)])
        assert page.summary.isHidden() and page.cores.isHidden()
        assert 'Núcleos' in page.plots[0].toolTip()
        assert len(page.plots[0].lines)==1
    finally: page.close(); page.deleteLater(); app.processEvents()
