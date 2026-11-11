"""The user's supplied artwork, shared by the window, taskbar and launcher."""
from pathlib import Path
from PySide6.QtGui import QIcon

ASSETS=Path(__file__).parent/'assets'


def application_icon():
    path=ASSETS/'expecto.ico'
    return QIcon(str(path if path.is_file() else ASSETS/'expecto.png'))


def set_windows_app_id():
    import sys
    if sys.platform=='win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('InProcess.PhysicalSystemsLab.Desktop')
