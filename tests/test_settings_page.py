import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from types import SimpleNamespace
from unittest.mock import Mock
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication,QPushButton
from expecto_process_manager.interface.settings_page import SettingsPage


def test_reorganized_settings_keep_actions_and_current_theme_selected(tmp_path):
    app=QApplication.instance() or QApplication([])
    window=SimpleNamespace(settings_store=QSettings(str(tmp_path/'settings.ini'),QSettings.IniFormat),
        report_directory=tmp_path,nav=Mock(),laboratory=Mock())
    for name in ('set_theme','set_interval','set_history_limit','export_history','export_processes',
                 'import_csv','generate_academic','open_academic','open_hardware'):
        setattr(window,name,Mock())
    page=SettingsPage(window)
    try:
        page.resize(1100,750); page.show(); app.processEvents()
        assert page.tabs.count()==3
        light=next(button for i,button in page.theme_buttons if i==1)
        assert light.isChecked()
        light.click(); assert light.isChecked()
        dark=next(button for i,button in page.theme_buttons if i==0)
        dark.click(); window.set_theme.assert_called_once_with(0)
        assert dark.isChecked() and not light.isChecked()
        page.interval.setValue(500); window.set_interval.assert_called_with(500)
        assert '30 minutos' in page.history_hint.text()
        page.tabs.setCurrentIndex(1)
        export=next(button for button in page.findChildren(QPushButton) if button.property('settingsAction')=='exportProcesses')
        export.click(); window.export_processes.assert_called_once()
        assert not page.academic_open.isEnabled()
        page.resize(600,600); app.processEvents()
        assert page.grids[0][0].getItemPosition(1)[:2]==(1,0)
    finally: page.close(); page.deleteLater(); app.processEvents()
