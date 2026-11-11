import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from expecto_process_manager.interface.processes_page import ProcessesPage


@pytest.fixture(scope='module')
def app(): return QApplication.instance() or QApplication([])


def records():
    return [dict(name=name,pid=pid,created=100+pid,user=user,status='running',elapsed=1,
                 cpu=cpu,memory=1000000,disk=10,network=None,gpu=None)
            for name,pid,user,cpu in [('browser.exe',1,'one',10),('browser.exe',2,'one',20),
                ('browser.exe',3,'two',5),('editor.exe',4,'one',None)]]


def test_folders_use_executable_and_user_with_real_resource_totals(app):
    page=ProcessesPage()
    try:
        page.update_rows(records())
        assert page.groups.rowCount()==3
        root=page.groups.find(('group',('browser.exe','one')))
        assert page.groups.rowCount(root)==2
        assert root.data()=='browser (2)'
        assert page.groups.index(root.row(),2).data(Qt.UserRole)==30
        assert page.groups.index(root.row(),3).data(Qt.UserRole)==2000000
        assert page.groups.index(root.row(),5).data()=='—'
        child=page.groups.index(0,0,root)
        assert child.parent()==root
        page.tree.setCurrentIndex(root)
        assert page.selected() is None
        requested=[]; page.action.connect(lambda *args:requested.append(args))
        page.request('terminate'); assert requested==[]
        page.tree.setCurrentIndex(child)
        page.request('suspend')
        assert requested[0][0]['pid'] in (1,2)
        assert requested[0][1]=='suspend'
    finally: page.close(); page.deleteLater(); app.processEvents()


def test_folder_expansion_selection_search_and_pid_reuse(app):
    page=ProcessesPage()
    try:
        rows=records(); page.update_rows(rows)
        root=page.groups.find(('group',('browser.exe','one')))
        page.tree.setExpanded(root,True)
        child=page.groups.find(('process',2,102)); page.tree.setCurrentIndex(child)
        updated=records()+[dict(rows[0],pid=5,created=105)]
        page.update_rows(updated)
        assert page.selected()['pid']==2
        root=page.groups.find(('group',('browser.exe','one')))
        assert page.tree.isExpanded(root)
        page.search.setText('2')
        assert page.groups.rowCount()==1 and page.groups.rowCount(page.groups.index(0,0))==1
        page.search.clear()
        page.tree.setCurrentIndex(page.groups.find(('process',2,102)))
        page.update_rows([dict(row,created=999) if row['pid']==2 else row for row in updated])
        assert page.selected() is None
    finally: page.close(); page.deleteLater(); app.processEvents()


def test_group_numeric_sort_keeps_unknown_aggregates_unknown(app):
    page=ProcessesPage()
    try:
        rows=records(); rows[0]['cpu']=None
        page.update_rows(rows); page.tree.sortByColumn(2,Qt.DescendingOrder)
        assert page.groups.index(0,2).data(Qt.UserRole)==5
        root=page.groups.find(('group',('browser.exe','one')))
        assert page.groups.index(root.row(),2).data()=='—'
        page.grouping.setCurrentIndex(1)
        assert page.proxy.rowCount()==4
    finally: page.close(); page.deleteLater(); app.processEvents()


def test_group_uses_real_application_icon_and_updates_when_cache_arrives(app):
    from PySide6.QtGui import QIcon,QPixmap,QColor
    page=ProcessesPage()
    try:
        page.update_rows(records())
        root=page.groups.find(('group',('browser.exe','one')))
        assert root.data(Qt.DecorationRole).cacheKey()==page.model.process_icon.cacheKey()
        pixmap=QPixmap(24,24); pixmap.fill(QColor('#e1477c'))
        native=QIcon(pixmap)
        page.model.icons['browser.exe']=native
        page.model.dataChanged.emit(page.model.index(0,0),page.model.index(3,0),[Qt.DecorationRole])
        root=page.groups.find(('group',('browser.exe','one')))
        assert root.data(Qt.DecorationRole).cacheKey()==native.cacheKey()
        assert page.groups.index(0,0,root).data(Qt.DecorationRole).cacheKey()==native.cacheKey()
    finally: page.close(); page.deleteLater(); app.processEvents()


def test_collapsed_groups_notify_once_and_expanded_children_stay_fresh(app):
    from PySide6.QtTest import QSignalSpy
    page=ProcessesPage()
    try:
        page.update_rows(records())
        signals=QSignalSpy(page.groups.dataChanged)
        updated=[dict(row,cpu=15) for row in records()]
        page.update_rows(updated)
        assert signals.count()==1
        root=page.groups.find(('group',('browser.exe','one')))
        assert page.groups.index(root.row(),2).data(Qt.UserRole)==30
        page.tree.expand(root)
        assert page.groups.index(0,2,root).data(Qt.UserRole)==15
        previous=signals.count()
        page.update_rows([dict(row,cpu=16) for row in updated])
        assert signals.count()-previous==2  # one root range, one expanded child range
        root=page.groups.find(('group',('browser.exe','one')))
        assert page.groups.index(0,2,root).data(Qt.UserRole)==16
    finally: page.close(); page.deleteLater(); app.processEvents()


def test_group_filter_follows_new_measurements_even_when_flat_proxy_is_empty(app):
    page=ProcessesPage()
    try:
        page.update_rows([dict(row,cpu=None) for row in records()])
        page.filter.setCurrentIndex(1)
        assert page.groups.rowCount()==0
        page.update_rows([dict(row,cpu=1) for row in records()])
        assert page.groups.rowCount()==3
        page.grouping.setCurrentIndex(1)
        assert page.proxy.rowCount()==4
        page.update_rows([dict(row,cpu=0) for row in records()])
        assert page.proxy.rowCount()==0
        page.grouping.setCurrentIndex(0)
        assert page.groups.rowCount()==0
    finally: page.close(); page.deleteLater(); app.processEvents()


def test_hidden_group_view_defers_work_and_recovers_latest_snapshot(app):
    from PySide6.QtTest import QSignalSpy
    page=ProcessesPage()
    try:
        page.update_rows(records())
        page.grouping.setCurrentIndex(1)
        signals=QSignalSpy(page.groups.dataChanged)
        updated=[dict(records()[0],pid=99,created=199,cpu=42)]
        page.update_rows(updated)
        assert signals.count()==0
        assert page.proxy.rowCount()==1
        page.grouping.setCurrentIndex(0)
        assert page.groups.rowCount()==1
        child=page.groups.find(('process',99,199))
        assert child.isValid() and page.groups.record(child)['cpu']==42
    finally: page.close(); page.deleteLater(); app.processEvents()


def test_repeated_churn_cpu_reordering_and_pid_reuse_preserve_totals_and_selection(app):
    """600 changing records, including removals and new identities under old PIDs."""
    import random
    rng=random.Random(7021)
    page=ProcessesPage()
    try:
        for generation in range(30):
            rows=[]
            for pid in range(600):
                if pid!=42 and (pid+generation)%5==0: continue
                rows.append(dict(name=f'app-{pid%30}.exe',pid=pid,
                    created=10042 if pid==42 else generation*10000+pid,
                    user='one',status='running',elapsed=1,cpu=rng.randrange(100),
                    memory=pid*1000,disk=0,network=None,gpu=None))
            page.update_rows(rows)
            page.tree.sortByColumn(2,Qt.DescendingOrder)
            if generation==0:
                page.tree.setCurrentIndex(page.groups.find(('process',42,10042)))
            assert page.selected()['pid']==42 and page.selected()['created']==10042
            expected={}
            for row in rows: expected[row['name']]=expected.get(row['name'],0)+row['cpu']
            displayed=[]
            for index in range(page.groups.rowCount()):
                root=page.groups.index(index,0)
                total=page.groups.index(index,2).data(Qt.UserRole)
                members=[page.groups.record(page.groups.index(i,0,root))
                         for i in range(page.groups.rowCount(root))]
                assert len({(r['pid'],r['created']) for r in members})==len(members)
                assert total==expected[members[0]['name']]
                displayed.append(total)
            assert displayed==sorted(expected.values(),reverse=True)
    finally: page.close(); page.deleteLater(); app.processEvents()


@pytest.mark.parametrize('flat',[False,True])
def test_inactive_page_coalesces_snapshots_and_preserves_live_process_selection(app,flat):
    from PySide6.QtTest import QSignalSpy
    page=ProcessesPage()
    try:
        page.update_rows(records())
        if flat:
            page.grouping.setCurrentIndex(1)
            source=page.model.index(1,0)
            page.table.selectRow(page.proxy.mapFromSource(source).row())
        else:
            root=page.groups.find(('group',('browser.exe','one')))
            page.tree.expand(root)
            page.tree.setCurrentIndex(page.groups.find(('process',2,102)))
        assert page.selected()['pid']==2
        page.set_display_active(False)
        resets=QSignalSpy(page.model.modelReset)
        changed=QSignalSpy(page.model.dataChanged)
        for tick in range(10):
            latest=[dict(row,cpu=41+tick) for row in records()]+[dict(records()[0],pid=50+tick,created=500+tick)]
            page.update_rows(latest)
        assert page.rows==latest  # exports/diagnostics retain all latest records
        assert resets.count()==0 and changed.count()==0
        assert page.selected() is None  # no action can target a stale hidden row
        page.set_display_active(True)
        assert resets.count()==1 and page.model.rows==latest
        assert page.selected()['pid']==2 and page.selected()['cpu']==50
        if not flat:
            root=page.groups.find(('group',('browser.exe','one')))
            assert page.tree.isExpanded(root)
    finally: page.close(); page.deleteLater(); app.processEvents()


@pytest.mark.parametrize('flat',[False,True])
def test_resuming_page_clears_selection_when_pid_was_reused(app,flat):
    page=ProcessesPage()
    try:
        page.update_rows(records())
        if flat:
            page.grouping.setCurrentIndex(1)
            page.table.selectRow(page.proxy.mapFromSource(page.model.index(1,0)).row())
        else: page.tree.setCurrentIndex(page.groups.find(('process',2,102)))
        page.set_display_active(False)
        page.update_rows([dict(row,created=999) if row['pid']==2 else row for row in records()])
        page.set_display_active(True)
        assert page.selected() is None
    finally: page.close(); page.deleteLater(); app.processEvents()


def test_icon_delivery_updates_only_decoration_without_regrouping(app,monkeypatch):
    from PySide6.QtGui import QImage,QColor
    from PySide6.QtTest import QSignalSpy
    from expecto_process_manager.interface.process_icons import ProcessIcons
    page=ProcessesPage()
    try:
        page.update_rows(records())
        root=page.groups.find(('group',('browser.exe','one')))
        page.tree.expand(root)
        page.tree.setCurrentIndex(page.groups.find(('process',2,102)))
        signature=page.groups._signature
        signals=QSignalSpy(page.groups.dataChanged)
        resets=QSignalSpy(page.groups.modelReset)
        def forbidden(_): raise AssertionError('Decoration changes must not recompute filters/totals.')
        monkeypatch.setattr(page.proxy,'accepts_record',forbidden)
        image=QImage(24,24,QImage.Format_ARGB32); image.fill(QColor('#2d79ff'))
        delivery=ProcessIcons(page.model,None)
        delivery.loaded({'browser.exe':image})
        assert signals.count()==2 and resets.count()==0
        for i in range(signals.count()):
            first,last,roles=signals.at(i)
            assert first.column()==last.column()==0 and roles==[Qt.DecorationRole]
        assert page.groups._signature==signature
        assert root.data(Qt.DecorationRole).cacheKey()==page.model.icons['browser.exe'].cacheKey()
        assert page.selected()['pid']==2
        previous=signals.count()
        delivery.loaded({})
        assert signals.count()==previous
    finally: page.close(); page.deleteLater(); app.processEvents()
