import json
import logging
import sys
import os
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase,QFont
from .interface.main_window import MainWindow
from .interface.theme import apply_theme
from .interface.branding import application_icon,set_windows_app_id


class JsonFormatter(logging.Formatter):
    def format(self,record):
        return json.dumps({'time':self.formatTime(record),'level':record.levelname,
                           'event':record.getMessage(),'exception':self.formatException(record.exc_info) if record.exc_info else None},ensure_ascii=False)


def configure_app(app: QApplication) -> None:
    font_path = Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/'segoeui.ttf'
    for filename in ('SegUIVar.ttf','segoeui.ttf','seguisb.ttf','segoeuib.ttf'):
        candidate=font_path.parent/filename
        if candidate.exists(): QFontDatabase.addApplicationFont(str(candidate))
    families=set(QFontDatabase.families())
    family=next((name for name in ('Segoe UI Variable Text','Segoe UI Variable','Inter','Segoe UI','Noto Sans') if name in families),'sans-serif')
    heading=next((name for name in ('Segoe UI Variable Display',family) if name in families),family)
    app.setProperty('bodyFont',family)
    app.setProperty('headingFont',heading)
    font=QFont(family,10)
    font.setHintingPreference(QFont.PreferNoHinting)
    app.setFont(font)
    app.setApplicationName('InProcess')
    app.setApplicationDisplayName('InProcess')
    apply_theme(app,False)
    app.setWindowIcon(application_icon())


def main() -> int:
    set_windows_app_id()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO,handlers=[handler])
    app = QApplication(sys.argv)
    configure_app(app)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
