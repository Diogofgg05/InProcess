"""Card navigation over the existing lazy scientific pages and stable indices."""
from PySide6.QtCore import Qt,QSize,Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QToolButton,QPushButton,QSizePolicy,QComboBox
from .lazy_tabs import LazyTabs
from .theme import icon


GROUPS = (
    ('Modelo térmico','CPU / GPU','thermal',(0,5,11,13)),
    ('Energia e potência','Circuitos e arrefecimento','energy',(7,8,14)),
    ('Derivadas e sinais','Vibrações e dinâmica','signal',(3,9,12,10)),
    ('Calibração','Estimação de parâmetros','sliders',(4,)),
    ('Otimização (ULTRA ECO)','Eficiência energética','cube',(6,)),
)


class LaboratoryWorkspace(QWidget):
    currentChanged=Signal(int)

    def __init__(self,parent=None):
        super().__init__(parent)
        self._group=None
        self._columns=0
        layout=QVBoxLayout(self)
        layout.setContentsMargins(0,20,0,0)
        layout.setSpacing(16)
        header=QHBoxLayout()
        symbol=QLabel(); self.header_icon=symbol; symbol.setPixmap(icon('lab','#0673ff').pixmap(38,38))
        symbol.setFixedSize(58,58)
        symbol.setAlignment(Qt.AlignCenter)
        symbol.setStyleSheet('background: #edf5ff; border-radius: 14px;')
        header.addWidget(symbol)
        text=QVBoxLayout()
        title=QLabel('Laboratório de Modelação de Sistemas Físicos')
        title.setObjectName('labTitle'); title.setWordWrap(True)
        subtitle=QLabel('Modelos, simulações e validação numérica aplicados ao hardware do computador.')
        self.subtitle=subtitle
        subtitle.setObjectName('muted'); subtitle.setWordWrap(True)
        text.addWidget(title); text.addWidget(subtitle)
        header.addLayout(text,1)
        self.badge=QLabel('InProcess · Modelação Computacional')
        self.badge.setObjectName('badge'); header.addWidget(self.badge)
        layout.addLayout(header)
        self.cards_widget=QWidget()
        self.cards_grid=QGridLayout(self.cards_widget)
        self.cards_grid.setContentsMargins(0,0,0,0); self.cards_grid.setSpacing(10)
        self.cards=[]
        for group,(name,subtitle,kind,indices) in enumerate(GROUPS):
            card=QToolButton()
            card.setObjectName('sectorCard')
            card.setText(name+'\n'+subtitle)
            card.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            symbol=icon(kind,'#0673ff')
            symbol.addPixmap(icon(kind,'#ffffff').pixmap(34,34),QIcon.Normal,QIcon.On)
            card.setIcon(symbol); card.setIconSize(QSize(32,32))
            card.setCheckable(True); card.setMinimumWidth(0); card.setFixedHeight(84)
            card.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
            card.setCursor(Qt.PointingHandCursor)
            card.clicked.connect(lambda checked=False,i=group:self.select_group(i))
            self.cards.append(card)
        layout.addWidget(self.cards_widget)
        self.category_picker=QComboBox()
        self.category_picker.addItems([group[0] for group in GROUPS])
        self.category_picker.currentIndexChanged.connect(self.select_group)
        self.category_picker.hide(); layout.addWidget(self.category_picker)
        self.secondary=QHBoxLayout(); self.secondary.setSpacing(5)
        self.secondary.setContentsMargins(0,0,0,0)
        layout.addLayout(self.secondary)
        self.tabs=LazyTabs()
        self.tabs.tabBar().hide()
        self.tabs.currentChanged.connect(self.selected)
        layout.addWidget(self.tabs,1)
        self.arrange_cards(1200)

    @property
    def created(self): return self.tabs.created
    @property
    def factories(self): return self.tabs.factories
    def add_lazy(self,title,factory):
        self.tabs.add_lazy(title,factory)
        self._group=None
    def ensure(self,index): return self.tabs.ensure(index)
    def currentIndex(self): return self.tabs.currentIndex()
    def setCurrentIndex(self,index):
        self.tabs.setCurrentIndex(index)
        self.selected(index)
    def setTabVisible(self,index,visible): self.tabs.setTabVisible(index,visible)
    def isTabVisible(self,index): return self.tabs.isTabVisible(index)
    def count(self): return self.tabs.count()
    def tabText(self,index): return self.tabs.tabText(index)
    def widget(self,index): return self.tabs.widget(index)

    def select_group(self,group):
        indices=GROUPS[group][3]
        if self.currentIndex() not in indices: self.setCurrentIndex(indices[0])
        else: self.selected(self.currentIndex())

    def selected(self,index):
        group=next((i for i,g in enumerate(GROUPS) if index in g[3]),None)
        for i,card in enumerate(self.cards): card.setChecked(group==i)
        self.category_picker.blockSignals(True)
        self.category_picker.setCurrentIndex(group if group is not None else -1)
        self.category_picker.blockSignals(False)
        if group!=self._group or not self.secondary.count():
            self._group=group
            while self.secondary.count():
                item=self.secondary.takeAt(0)
                if item.widget(): item.widget().deleteLater()
            if group is not None:
                for page_index in GROUPS[group][3]:
                    if page_index>=self.tabs.count(): continue
                    title=self.tabs.tabText(page_index).split(' · ',1)[-1]
                    button=QPushButton(title)
                    button.setObjectName('segment'); button.setCheckable(True)
                    button.setProperty('pageIndex',page_index)
                    button.setCursor(Qt.PointingHandCursor)
                    button.clicked.connect(lambda checked=False,i=page_index:self.setCurrentIndex(i))
                    self.secondary.addWidget(button)
                self.secondary.addStretch()
        for i in range(self.secondary.count()):
            button=self.secondary.itemAt(i).widget()
            if button: button.setChecked(button.property('pageIndex')==index)
        self.currentChanged.emit(index)

    def arrange_cards(self,width):
        columns=5 if width>=1100 else 3 if width>=720 else 2
        if columns==self._columns: return
        self._columns=columns
        for card in self.cards: self.cards_grid.removeWidget(card)
        for column in range(5): self.cards_grid.setColumnStretch(column,0)
        for i,card in enumerate(self.cards): self.cards_grid.addWidget(card,i//columns,i%columns)
        for column in range(columns): self.cards_grid.setColumnStretch(column,1)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.arrange_cards(self.width())
        self.badge.setVisible(self.width()>=1150)
        self.adapt_density(self.window().property('densityScale') or 1.)

    def adapt_density(self,scale):
        short=self.window().height()<720
        compact=short or self.width()<650
        self.cards_widget.setVisible(not compact)
        self.category_picker.setVisible(compact)
        self.subtitle.setVisible(not short)
        self.header_icon.setVisible(not short)
        self.badge.setVisible(not short and self.width()>=1150)

    def showEvent(self,event):
        super().showEvent(event)
        self.selected(self.currentIndex())
        self.adapt_density(1.)

    def search(self,text):
        import unicodedata
        query=''.join(c for c in unicodedata.normalize('NFKD',text.casefold()) if not unicodedata.combining(c)).strip()
        aliases={'termico':0,'modelo termico':0,'temperatura':0,'cpu gpu':5,'conducao':11,
                 'circuitos':7,'rc':7,'rl':7,'energia':7,'ventoinha':8,'motor':8,
                 'vibracao':9,'ressonancia':9,'acustica':12,'sinais':3,'derivadas':3,
                 'calibracao':4,'bateria':14,'eletrotermica':14,'dissipador':13,'dois nos':13,'eco':6,'ultra eco':6,'otimizacao':6,'nao linear':10}
        if query in aliases:
            self.setCurrentIndex(aliases[query]); return True
        return False
