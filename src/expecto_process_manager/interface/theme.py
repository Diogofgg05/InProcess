from PySide6.QtGui import QColor,QPainter,QPen,QIcon,QPixmap,QPolygonF,QBrush
from PySide6.QtCore import Qt,QPointF,QRectF
from pathlib import Path

DARK = dict(bg='#0c1117',surface='#11171f',raised='#1c2430',border='#252f3d',text='#eef2fa',muted='#b0c1dc',selected='#273550')
LIGHT = dict(bg='#fbfcff',surface='#ffffff',raised='#f1f6ff',border='#dce7f6',text='#101d40',muted='#607295',selected='#e8f1ff')


def density_styles(scale):
    from PySide6.QtWidgets import QApplication
    dark=QApplication.instance() and QApplication.instance().property('dark')
    body=max(11,round(14*scale)); control=max(11,round(13*scale))
    return f'''
    QWidget {{ font-size: {body}px; }}
    QLabel#title {{ font-size: {max(18,round(23*scale))}px; }}
    QLabel#labTitle {{ font-size: {max(18,round(25*scale))}px; }}
    QLabel#sectionTitle {{ font-size: {max(13,round(16*scale))}px; }}
    QLabel#metric, QLabel#value {{ font-size: {max(18,round(23*scale))}px; }}
    QLabel#brand {{ font-size: {max(14,round(18*scale))}px; }}
    QLineEdit, QComboBox {{ font-size: {control}px; }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ min-height: {round(20*scale)}px; padding: {round(7*scale)}px {round(10*scale)}px; }}
    QSpinBox, QDoubleSpinBox {{ padding-right: 22px; }}
    QPushButton, QToolButton {{ padding: {round(9*scale)}px {round(14*scale)}px; }}
    QPushButton#segment {{ padding: {round(9*scale)}px {round(17*scale)}px; }}
    QPushButton#primary {{ padding: {round(11*scale)}px {round(18*scale)}px; }}
    QToolButton#sectorCard {{ font-size: {control}px; padding: {round(14*scale)}px {round(10*scale)}px; }}
    QHeaderView::section {{ font-size: {max(11,round(14*scale))}px; padding: {round(10*scale)}px {round(12*scale)}px; }}
    QLabel#settingsDescription {{ font-size: {max(11,round(13*scale))}px; }}
    QLabel#settingsCardTitle {{ font-size: {max(14,round(17*scale))}px; font-weight: 600; }}
    QLabel#settingsIcon {{ padding: {round(8*scale)}px; }}
    QTableView, QTreeView {{ font-size: {body}px; }}
    QTreeView {{ background: transparent; border: none; outline: 0; alternate-background-color: {'#16202b' if dark else '#f5f8fd'}; }}
    QTreeView::item {{ padding: 5px 9px; border-bottom: 1px solid transparent; }}
    QTreeView::item:hover {{ background: {'#273550' if dark else '#e8f1ff'}; }}
    QTreeView::item:selected {{ background: {'#273550' if dark else '#dceaff'}; }}
    QLabel#badge {{ padding: {round(9*scale)}px {round(14*scale)}px; }}
    '''


def apply_density(app,scale):
    scale=max(.75,min(1.,scale))
    if app.property('densityScale')==scale: return
    app.setProperty('densityScale',scale)
    base=app.property('expectoBaseStyle')
    if base: app.setStyleSheet(base+density_styles(scale))


def apply_theme(app,dark=False):
    from .interaction import install_interaction
    install_interaction(app)
    signature=f'inprocess-design-7:{bool(dark)}:{app.property("bodyFont")}'
    if app.property('expectoThemeSignature')==signature: return
    c = DARK if dark else LIGHT
    app.setProperty('expectoThemeSignature',signature)
    app.setProperty('dark',dark)
    sidebar = 'qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #202731,stop:0.5 #171e28,stop:1 #131b24)' if dark else c['surface']
    arrow=(Path(__file__).parent/'assets'/'chevron-down.svg').as_posix()
    style=f'''
    QWidget {{ background: {c['bg']}; color: {c['text']}; font-family: '{app.property('bodyFont') or 'Segoe UI'}'; font-size: 14px; outline: 0; }}
    QLabel#title, QLabel#labTitle, QLabel#sectionTitle, QLabel#brand, QLabel#metric, QLabel#settingsCardTitle {{ font-family: '{app.property('headingFont') or app.property('bodyFont') or 'Segoe UI'}'; }}
    QMainWindow, QWidget#outer {{ background: {c['bg']}; }}
    QFrame#shell {{ border: none; background: {c['bg']}; }}
    QFrame#sidebar {{ background: {sidebar}; border-right: 1px solid {c['border']}; border-top-left-radius: 14px; border-bottom-left-radius: 14px; }}
    QFrame#trafficLights {{ background: transparent; }}
    QFrame#toolbar {{ background: {c['surface']}; border-bottom: 1px solid {c['border']}; }}
    QWidget#resources {{ border-left: 1px solid {c['border']}; background: {'#0f151c' if dark else c['bg']}; }}
    QFrame#resourceCard, QFrame#systemCard, QFrame#footer, QFrame#parameterCard, QFrame#resultCard {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 14px; }}
    QWidget#parameterCard {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 14px; }}
    QLabel {{ background: transparent; border: none; }}
    QWidget#plotCard {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 14px; }}
    QLabel#title {{ font-size: 23px; font-weight: 600; padding: 0; }}
    QLabel#sectionTitle {{ font-size: 16px; font-weight: 600; }}
    QLabel#labTitle {{ font-size: 25px; font-weight: 700; }}
    QLabel#badge {{ color: #1267da; background: {c['raised']}; border: 1px solid {c['border']}; border-radius: 10px; padding: 9px 14px; }}
    QLabel#metric {{ font-size: 23px; font-weight: 700; }}
    QFrame#divider {{ background: {c['border']}; border: none; }}
    QFrame#metricTile {{ background: {c['raised']}; border: none; border-radius: 12px; }}
    QLabel#brand {{ font-size: 18px; font-weight: 600; }}
    QLabel#settingsDescription {{ color: {c['muted']}; font-size: 13px; }}
    QLabel#settingsCardTitle {{ font-size: 17px; font-weight: 600; }}
    QLabel#settingsEyebrow {{ color: #367ce2; font-size: 11px; font-weight: 600; letter-spacing: 1px; }}
    QFrame#settingsCard {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 16px; }}
    QLabel#settingsIcon {{ background: {c['raised']}; border-radius: 10px; padding: 8px; }}
    QFrame#settingsRow {{ background: transparent; border: none; }}
    QFrame#settingsAbout {{ background: {c['raised']}; border: none; border-radius: 14px; }}
    QPushButton#themeOption {{ background: {c['raised']}; color: {c['muted']}; padding: 16px 24px; text-align: left; }}
    QPushButton#themeOption:checked {{ background: {c['selected']}; color: #0673ff; font-weight: 600; }}
    QPushButton#settingAction {{ background: {c['raised']}; padding: 10px 16px; text-align: left; }}
    QPushButton#settingAction:hover {{ background: {c['selected']}; }}
    QTabWidget#settingsTabs::pane {{ border: none; }}
    QTabWidget#settingsTabs QTabBar::tab {{ padding: 10px 20px; margin: 0 5px 8px 0; font-weight: 600; }}
    QLabel#muted {{ color: {c['muted']}; }}
    QLabel#value {{ font-size: 27px; font-weight: 600; }}
    QTableView, QPlainTextEdit, QTextEdit, QTextBrowser, QListWidget {{ background: {c['surface']}; border: none; outline: 0; selection-background-color: {c['selected']}; selection-color: {c['text']}; }}
    QPlainTextEdit, QTextEdit, QTextBrowser {{ border: 1px solid {c['border']}; border-radius: 12px; padding: 10px; }}
    QTableView {{ gridline-color: {c['border']}; font-size: 14px; alternate-background-color: {c['bg']}; }}
    QTableView::item:hover {{ background: {c['raised']}; }}
    QTableView::item {{ padding: 8px 12px; border-bottom: 1px solid {'#1a232e' if dark else c['border']}; }}
    QTableView::item:selected {{ background: {'#1a2330' if dark else c['selected']}; }}
    QHeaderView::section {{ background: {c['bg']}; color: {c['muted']}; border: none; border-bottom: 1px solid {c['border']}; padding: 10px 12px; font-size: 14px; font-weight: normal; }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 9px; padding: 7px 10px; color: {c['text']}; selection-background-color: #dceaff; selection-color: #101d40; min-height: 20px; }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border: 1px solid {c['border']}; background: {c['surface']}; outline: 0; }}
    QLineEdit[keyboardFocus="true"], QComboBox[keyboardFocus="true"], QAbstractSpinBox[keyboardFocus="true"] {{ background: {c['raised']}; }}
    QLineEdit, QComboBox {{ font-size: 13px; }}
    QLineEdit#globalSearch {{ background: {'#1c2431' if dark else c['raised']}; }}
    QComboBox::drop-down {{ border: none; width: 30px; }}
    QComboBox::down-arrow {{ image: url("{arrow}"); width: 16px; height: 16px; }}
    QSpinBox, QDoubleSpinBox {{ padding-right: 24px; }}
    QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: 20px; border: none; border-top-right-radius: 8px; background: transparent; }}
    QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: 20px; border: none; border-bottom-right-radius: 8px; background: transparent; }}
    QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover, QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{ background: {c['selected']}; }}
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url("{(Path(__file__).parent/'assets'/'chevron-up.svg').as_posix()}"); width: 12px; height: 10px; }}
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url("{arrow}"); width: 12px; height: 10px; }}
    QComboBox QAbstractItemView {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 5px; selection-background-color: {c['selected']}; outline: 0; }}
    QPushButton, QToolButton {{ background: {c['raised']}; border: none; border-radius: 10px; padding: 9px 14px; outline: 0; }}
    QPushButton:hover {{ background: {c['selected']}; }}
    QPushButton:pressed, QToolButton:pressed {{ background: {'#254875' if dark else '#d8e8ff'}; }}
    QPushButton:focus, QToolButton:focus {{ outline: 0; border: none; }}
    QPushButton[keyboardFocus="true"], QToolButton[keyboardFocus="true"] {{ background: {c['selected']}; color: #0671f9; }}
    QPushButton:disabled {{ color: {c['muted']}; }}
    QPushButton#primary {{ background: #0673ff; color: white; border: none; font-weight: 600; padding: 11px 18px; }}
    QPushButton#primary:hover {{ background: #0062e5; }}
    QPushButton#primary:pressed {{ background: #0056cf; }}
    QPushButton#segment {{ background: {c['surface']}; color: {c['muted']}; padding: 9px 17px; }}
    QPushButton#segment:hover {{ background: {c['raised']}; }}
    QPushButton#segment:checked {{ background: #0673ff; color: white; }}
    QToolButton#sectorCard {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 13px; padding: 14px 10px; text-align: left; font-size: 14px; font-weight: 600; }}
    QToolButton#sectorCard:hover {{ background: {c['raised']}; border-color: #b6d2fa; }}
    QToolButton#sectorCard:checked {{ background: #0673ff; border-color: #0673ff; color: white; }}
    QToolButton#sectorCard:focus {{ outline: 0; }}
    QPushButton#danger {{ color: #f07d89; }}
    QToolButton#windowControl, QToolButton#closeControl {{ background: transparent; border: none; border-radius: 5px; padding: 0; }}
    QToolButton#windowControl:hover {{ background: {c['selected']}; }}
    QToolButton#closeControl:hover {{ background: #ac3b49; }}
    QToolButton#appMark {{ background: transparent; border: none; border-radius: 9px; padding: 0; }}
    QToolButton#appMark::menu-indicator {{ image: none; }}
    QListWidget#navigation {{ background: transparent; font-size: 14px; }}
    QListWidget#navigation::item {{ padding: 12px 10px; margin: 1px 0; border-radius: 10px; color: {c['muted']}; }}
    QListWidget#navigation::item:selected {{ background: {c['selected']}; color: {c['text']}; }}
    QListWidget#navigation::item:hover:!selected {{ background: {'#202b3a' if dark else c['raised']}; }}
    QMenu {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 12px; padding: 6px; }}
    QMenu::item {{ padding: 8px 20px; }}
    QMenu::item:selected {{ background: {c['selected']}; border-radius: 4px; }}
    QTabWidget::pane {{ border: none; }}
    QTabBar::tab {{ background: transparent; color: {c['muted']}; padding: 9px 16px; margin: 4px 3px; border: none; border-radius: 9px; }}
    QTabBar::tab:hover {{ background: {c['raised']}; }}
    QTabBar::tab:selected {{ background: {c['selected']}; color: #0673ff; }}
    QScrollArea {{ border: none; }}
    QScrollBar:vertical {{ background: transparent; width: 5px; }}
    QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 2px; min-height: 25px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 5px; }}
    QScrollBar::handle:horizontal {{ background: {c['border']}; border-radius: 2px; min-width: 25px; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    QStatusBar {{ color: {c['muted']}; font-size: 11px; }}
    QToolTip {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 7px; }}
    '''
    app.setProperty('expectoBaseStyle',style)
    app.setStyleSheet(style+density_styles(app.property('densityScale') or 1.))


def icon(kind: str,color=None) -> QIcon:
    if color is None:
        from PySide6.QtWidgets import QApplication
        color='#afc2df' if QApplication.instance() and QApplication.instance().property('dark') else '#20355c'
    pix = QPixmap(28,28)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(color),1.8,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
    if kind=='process':
        p.drawPolyline([QPointF(x,y) for x,y in [(2,15),(7,15),(10,7),(14,22),(17,11),(20,15),(26,15)]])
    elif kind=='cpu':
        p.drawRoundedRect(6,6,16,16,2,2)
        p.drawRect(9,9,10,10)
        for i in [8,12,16,20]:
            p.drawLine(i,3,i,6); p.drawLine(i,22,i,25)
            p.drawLine(3,i,6,i); p.drawLine(22,i,25,i)
    elif kind=='memory':
        p.drawRoundedRect(3,7,22,15,2,2)
        p.drawLine(6,11,22,11)
        for x in [7,12,18]: p.drawRect(x,16,2,3)
    elif kind=='disk':
        p.drawPolygon(QPolygonF([QPointF(7,5),QPointF(21,5),QPointF(25,23),QPointF(3,23)]))
        p.drawLine(4,18,24,18); p.drawLine(18,21,21,21)
    elif kind=='gpu':
        p.drawRect(3,4,22,16); p.drawLine(14,20,14,25); p.drawLine(9,25,19,25)
    elif kind=='network':
        p.drawLine(8,23,8,5); p.drawLine(4,10,8,5); p.drawLine(8,5,12,10)
        p.drawLine(20,5,20,23); p.drawLine(16,18,20,23); p.drawLine(20,23,24,18)
    elif kind=='users':
        p.drawEllipse(5,4,6,6); p.drawEllipse(17,5,5,5)
        p.drawArc(3,13,13,13,0,180*16); p.drawArc(15,14,10,10,0,180*16)
        p.drawLine(3,20,3,23); p.drawLine(15,20,15,23); p.drawLine(3,23,15,23)
    elif kind=='performance':
        p.setBrush(QColor(color)); p.setPen(Qt.NoPen)
        for x,h in [(4,10),(11,22),(19,16)]: p.drawRoundedRect(x,26-h,4,h,0.5,0.5)
    elif kind in ('history','analysis'):
        p.drawEllipse(4,4,20,20); p.drawLine(14,8,14,15); p.drawLine(14,15,20,17)
    elif kind=='search':
        p.drawEllipse(4,3,14,14); p.drawLine(16,15,24,23)
    elif kind=='startup':
        p.drawEllipse(QRectF(11,6,6,6))
        p.drawPath(_rocket_path())
        p.drawLine(7,20,4,25); p.drawLine(10,22,8,26)
    elif kind=='info':
        p.drawEllipse(4,4,20,20); p.drawLine(14,12,14,20); p.drawPoint(14,8)
    elif kind=='windows':
        p.setBrush(QColor('#25afea')); p.setPen(Qt.NoPen)
        for x,y in [(3,3),(15,3),(3,15),(15,15)]: p.drawRect(x,y,10,10)
    elif kind=='play':
        p.drawPolygon(QPolygonF([QPointF(8,4),QPointF(23,14),QPointF(8,24)]))
    elif kind=='thermal':
        p.drawRoundedRect(10,3,8,16,4,4)
        p.drawEllipse(8,16,12,10); p.drawLine(14,8,14,21)
        for y in (7,11,15): p.drawLine(21,y,24,y)
    elif kind=='energy':
        p.drawPolygon(QPolygonF([QPointF(16,2),QPointF(4,16),QPointF(12,16),QPointF(10,26),QPointF(25,11),QPointF(16,11)]))
    elif kind=='signal':
        p.drawPolyline([QPointF(3,23),QPointF(10,15),QPointF(15,18),QPointF(24,5)])
        p.drawLine(17,5,24,5); p.drawLine(24,5,24,12)
    elif kind=='sliders':
        for y,x in ((6,10),(14,20),(22,8)):
            p.drawLine(3,y,25,y); p.setBrush(QColor('#ffffff')); p.drawEllipse(x-3,y-3,6,6); p.setBrush(Qt.NoBrush)
    elif kind=='cube':
        p.drawPolygon(QPolygonF([QPointF(14,2),QPointF(25,8),QPointF(25,21),QPointF(14,27),QPointF(3,21),QPointF(3,8)]))
        p.drawPolyline([QPointF(3,8),QPointF(14,15),QPointF(25,8)])
        p.drawLine(14,15,14,27)
    elif kind=='folder':
        p.setBrush(QColor('#e8f2ff'))
        p.drawPath(_folder_path())
    elif kind=='lab':
        p.drawLine(10,4,18,4); p.drawLine(11,4,11,12); p.drawLine(17,4,17,12)
        p.drawPolyline([QPointF(11,12),QPointF(5,24),QPointF(23,24),QPointF(17,12)])
        p.drawLine(9,18,19,18)
    else:
        from math import sin,cos,pi
        points=[]
        for i in range(32):
            angle=2*pi*i/32
            radius=11 if i%4 in (1,2) else 8.5
            points.append(QPointF(14+radius*cos(angle),14+radius*sin(angle)))
        p.drawPolygon(QPolygonF(points)); p.drawEllipse(10,10,8,8)
    p.end()
    return QIcon(pix)


def _rocket_path():
    from PySide6.QtGui import QPainterPath
    path=QPainterPath(QPointF(9,18))
    path.cubicTo(7,10,16,3,24,3)
    path.cubicTo(25,13,17,21,11,20)
    path.lineTo(9,18); path.lineTo(4,16); path.lineTo(8,12)
    path.moveTo(14,21); path.lineTo(13,26); path.lineTo(19,21)
    return path


def _folder_path():
    from PySide6.QtGui import QPainterPath
    path=QPainterPath(QPointF(3,9))
    path.lineTo(3,6); path.quadTo(3,4,5,4)
    path.lineTo(11,4); path.lineTo(14,8); path.lineTo(24,8)
    path.quadTo(26,8,26,10); path.lineTo(25,23)
    path.lineTo(3,23); path.closeSubpath()
    return path
