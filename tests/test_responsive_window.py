import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import time
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from expecto_process_manager.main import configure_app
from expecto_process_manager.interface.main_window import MainWindow
from expecto_process_manager.interface.branding import application_icon,ASSETS


@pytest.fixture(scope='module')
def app():
    app=QApplication.instance() or QApplication([])
    configure_app(app)
    return app


def settle(app,predicate,timeout=15):
    deadline=time.monotonic()+timeout
    while not predicate() and time.monotonic()<deadline:
        app.processEvents(); time.sleep(.01)
    app.processEvents()
    assert predicate()


def test_width_and_height_control_density_without_losing_navigation(app,tmp_path):
    window=MainWindow(settings_path=tmp_path/'responsive.ini',report_directory=tmp_path/'reports')
    try:
        window.show(); app.processEvents()
        window.adaptive.apply()
        assert window.adaptive.scale==1
        large_row=window.processes.table.verticalHeader().defaultSectionSize()
        window.resize(950,600)
        settle(app,lambda:window.adaptive.scale<1)
        assert window.titlebar.height()<60
        assert window.sidebar.width()<206
        assert window.processes.table.verticalHeader().defaultSectionSize()<large_row
        assert not window.resources.isVisible()
        assert window.titlebar.isVisible()
        assert window.titlebar.menu_button.isVisible()
        assert window.titlebar.search.isVisible()
        assert window.sidebar_brand.isVisible()
        assert not window.footer.isVisible()
        assert not window.findChildren(type(window.sidebar),'trafficLights')
        assert not hasattr(window.titlebar,'gap')
        window.nav.setCurrentRow(6); window.adaptive.apply(); app.processEvents()
        assert window.laboratory.category_picker.isVisible()
        assert not window.laboratory.cards_widget.isVisible()
        window.laboratory.category_picker.setCurrentIndex(3)
        assert window.laboratory.currentIndex()==4
        window.resize(1536,1024)
        settle(app,lambda:window.adaptive.scale==1)
        assert window.titlebar.height()==60
        assert window.laboratory.cards_widget.isVisible()
        assert not window.laboratory.category_picker.isVisible()
    finally:
        window.close(); settle(app,lambda:window.closed_ready)


def test_supplied_icon_has_windows_sizes_and_is_packaged():
    assert (ASSETS/'expecto.png').is_file()
    assert (ASSETS/'expecto.ico').is_file()
    actual=application_icon()
    assert not actual.isNull()
    assert {size.width() for size in actual.availableSizes()}>={16,32,48,128,256}
