"""Behavioral checks for card navigation, quiet focus and scientific axes."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import Qt,QEvent
from PySide6.QtGui import QFocusEvent,QImage,QPainter
from PySide6.QtWidgets import QApplication,QWidget,QLineEdit,QStyle,QStyleOptionFocusRect
from expecto_process_manager.main import configure_app
from expecto_process_manager.interface.laboratory_workspace import LaboratoryWorkspace,GROUPS
from expecto_process_manager.interface.charts import Plot


@pytest.fixture(scope='module')
def app():
    app=QApplication.instance() or QApplication([])
    configure_app(app)
    return app


def test_cards_keep_every_model_accessible_and_legacy_pages_hidden(app):
    lab=LaboratoryWorkspace()
    try:
        for i in range(19): lab.add_lazy(f'Setor · Modelo {i}',lambda:QWidget())
        lab.setTabVisible(1,False); lab.setTabVisible(2,False)
        lab.resize(1250,750); lab.show(); app.processEvents()
        assert len(lab.cards)==5
        assert lab.secondary.count()==8  # seven thermal models and trailing space
        for i,group in enumerate(GROUPS):
            lab.cards[i].click(); app.processEvents()
            assert lab.currentIndex()==group[3][0]
            assert lab.cards[i].isChecked()
            lab.setCurrentIndex(group[3][-1])
            assert lab.currentIndex()==group[3][-1]
        lab.ensure(1)
        assert not lab.isTabVisible(1)
        assert lab.search('calibração') and lab.currentIndex()==4
        assert lab.search('acústica') and lab.currentIndex()==12
        assert not lab.search('unknown process.exe')
    finally:
        lab.close(); lab.deleteLater(); app.processEvents()


def test_pointer_and_keyboard_focus_are_distinguished_without_native_frame(app):
    field=QLineEdit()
    try:
        QApplication.sendEvent(field,QFocusEvent(QEvent.FocusIn,Qt.MouseFocusReason))
        assert field.property('keyboardFocus') is False
        QApplication.sendEvent(field,QFocusEvent(QEvent.FocusIn,Qt.TabFocusReason))
        assert field.property('keyboardFocus') is True
        image=QImage(40,40,QImage.Format_ARGB32); image.fill(Qt.transparent)
        painter=QPainter(image)
        option=QStyleOptionFocusRect(); option.rect=image.rect()
        app.style().drawPrimitive(QStyle.PE_FrameFocusRect,option,painter,field)
        painter.end()
        assert all(image.pixelColor(x,y).alpha()==0 for x in range(40) for y in range(40))
    finally:
        field.deleteLater(); app.processEvents()


def test_error_plot_keeps_linear_time_origin_and_filters_zero_only_on_log_y(app):
    plot=Plot('Erro','°C',log_y=True)
    try:
        plot.update_series([0,.5,1],{'Euler':[0,.01,.02],'RK4':[0,1e-12,2e-12]})
        assert plot.x_axis.min()==0
        assert plot.x_axis.max()==1
        assert plot.y_axis.min()>0
        assert plot.lines['Euler'].count()==2
        assert plot.lines['RK4'].count()==2
        assert plot.y_axis.base()==100
    finally:
        plot.deleteLater(); app.processEvents()
