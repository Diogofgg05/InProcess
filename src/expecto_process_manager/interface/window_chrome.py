"""Functional custom window chrome matching the supplied desktop reference."""
from PySide6.QtWidgets import QFrame,QHBoxLayout,QToolButton,QLabel,QMenu,QLineEdit,QWidget,QSizePolicy
from PySide6.QtCore import Qt,QSize
from PySide6.QtGui import QPainter,QPen,QColor,QIcon,QPixmap
from .theme import icon
from .branding import application_icon


def control_icon(kind):
    pix = QPixmap(24,24)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    from PySide6.QtWidgets import QApplication
    p.setPen(QPen(QColor('#b3c5e1' if QApplication.instance().property('dark') else '#182b52'),1.7))
    if kind=='close':
        p.drawLine(6,6,18,18); p.drawLine(18,6,6,18)
    elif kind=='maximize':
        p.drawRect(5,6,14,13); p.drawLine(6,8,18,8)
    else: p.drawLine(5,12,19,12)
    p.end()
    return QIcon(pix)


class TitleBar(QFrame):
    def __init__(self,window):
        super().__init__()
        self.window = window
        self.setObjectName('toolbar')
        self.setFixedHeight(60)
        row = QHBoxLayout(self)
        row.setContentsMargins(28,8,8,8)
        row.setSpacing(0)
        self.menu_button = QToolButton()
        self.menu_button.setObjectName('appMark')
        self.menu_button.setIcon(application_icon())
        self.menu_button.setIconSize(QSize(38,38))
        self.menu_button.setFixedSize(38,38)
        self.menu_button.setToolTip('Ferramentas científicas e definições')
        menu = QMenu(self.menu_button)
        for title,index in [('Laboratório',6),('Modelo Térmico',6),('Validação Científica',6)]:
            if title == 'Laboratório':
                menu.addAction(title,lambda checked=False,i=index:window.nav.setCurrentRow(i))
            else:
                menu.addAction(title,lambda checked=False,t=title: (window.nav.setCurrentRow(6), window.laboratory.setCurrentIndex(0 if t == 'Modelo Térmico' else 3)))
        self.menu_button.setMenu(menu)
        self.menu_button.setPopupMode(QToolButton.InstantPopup)
        row.addWidget(self.menu_button)
        row.addSpacing(16)
        self.title = QLabel('InProcess')
        self.title.setObjectName('brand')
        row.addWidget(self.title)
        row.addStretch(1)
        self.search = QLineEdit()
        self.search.setObjectName('globalSearch')
        self.search.setPlaceholderText('Procurar processos, modelos ou experiências…')
        self.search.addAction(icon('search'),QLineEdit.LeadingPosition)
        for button in self.search.findChildren(QToolButton): button.setIconSize(QSize(24,24))
        self.search.setFixedHeight(41)
        self.search.setMinimumWidth(130)
        self.search.setMaximumWidth(560)
        row.addWidget(self.search,2)
        row.addStretch(1)
        row.addSpacing(12)
        settings = QToolButton()
        settings.setProperty('controlKind','settings')
        settings.setObjectName('windowControl')
        settings.setIcon(icon('settings'))
        settings.setIconSize(QSize(23,23))
        settings.setFixedSize(42,42)
        settings.setToolTip('Definições · menu com botão direito')
        settings.clicked.connect(lambda:window.nav.setCurrentRow(8))
        settings.setContextMenuPolicy(Qt.CustomContextMenu)
        settings.customContextMenuRequested.connect(lambda point:menu.exec(settings.mapToGlobal(point)))
        row.addWidget(settings)
        for kind,title,callback in [('minimize','Minimizar',window.showMinimized),
                                    ('maximize','Maximizar/restaurar',self.toggle_maximize),('close','Fechar',window.close)]:
            button = QToolButton()
            button.setProperty('controlKind',kind)
            button.setObjectName('closeControl' if kind=='close' else 'windowControl')
            button.setIcon(control_icon(kind))
            button.setFixedSize(42,42)
            button.setToolTip(title)
            button.clicked.connect(callback)
            row.addWidget(button)

    def refresh_theme(self):
        for button in self.findChildren(QToolButton):
            kind=button.property('controlKind')
            if kind: button.setIcon(icon('settings') if kind=='settings' else control_icon(kind))

    def toggle_maximize(self):
        self.window.showNormal() if self.window.isMaximized() else self.window.showMaximized()

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton and self.window.windowHandle():
            self.window.windowHandle().startSystemMove()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.LeftButton: self.toggle_maximize()

    def adapt(self,width):
        self.title.setVisible(width>=1100)
        self.search.setPlaceholderText('Procurar…' if width<1000 else 'Procurar processos, modelos ou experiências…')


class TrafficLights(QFrame):
    def __init__(self,window):
        super().__init__()
        self.setFixedHeight(58)
        self.setObjectName('trafficLights')
        row = QHBoxLayout(self)
        row.setContentsMargins(22,21,0,21)
        row.setSpacing(12)
        for color,title,callback in [('#ff514f','Fechar',window.close),('#ffb526','Minimizar',window.showMinimized),
                                     ('#00be56','Maximizar/restaurar',lambda:window.titlebar.toggle_maximize())]:
            button = QToolButton()
            button.setFixedSize(17,17)
            button.setToolTip(title)
            button.setStyleSheet(f'QToolButton {{ background: {color}; border: none; border-radius: 8px; }} QToolButton:hover {{ border: 1px solid #e3eafa; }}')
            button.clicked.connect(callback)
            row.addWidget(button)
        row.addStretch()
