"""Settings grouped into responsive, readable sections with immediate saving."""
from importlib.metadata import version,PackageNotFoundError
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget,QFormLayout,QSpinBox,QComboBox,QPushButton,QLabel,
    QVBoxLayout,QHBoxLayout,QGridLayout,QScrollArea,QFrame,QTabWidget,QToolButton)
from .theme import icon
from .branding import application_icon


class SettingsPage(QWidget):
    def __init__(self,window):
        super().__init__()
        self.window=window
        self.grids=[]
        outer=QVBoxLayout(self)
        outer.setContentsMargins(8,24,8,8); outer.setSpacing(16)
        header=QHBoxLayout()
        heading=QVBoxLayout(); heading.setSpacing(5)
        title=QLabel('Definições'); title.setObjectName('title')
        subtitle=QLabel('Personaliza o InProcess à tua forma de trabalhar.')
        subtitle.setObjectName('settingsDescription')
        heading.addWidget(title); heading.addWidget(subtitle); header.addLayout(heading,1)
        self.saved=QLabel('Guardado automaticamente'); self.saved.setObjectName('badge')
        header.addWidget(self.saved); outer.addLayout(header)
        self.tabs=QTabWidget(); self.tabs.setObjectName('settingsTabs')
        outer.addWidget(self.tabs,1)

        preferences=self.new_tab('Preferências')
        appearance,box=self.card('Aparência','Um espaço claro e confortável para trabalhar.','settings')
        options=QHBoxLayout(); options.setSpacing(10)
        self.theme=QComboBox(self)
        self.theme.addItems(['Escuro','Claro · azul InProcess'])
        self.theme.setCurrentIndex(window.settings_store.value('theme',1,type=int)); self.theme.hide()
        self.theme_buttons=[]
        for index,text in ((1,'Claro\nSuperfícies luminosas'),(0,'Escuro\nMenos brilho')):
            button=QPushButton(text); button.setObjectName('themeOption'); button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setChecked(self.theme.currentIndex()==index)
            button.clicked.connect(lambda checked=False,i=index:self.choose_theme(i))
            self.theme_buttons.append((index,button)); options.addWidget(button,1)
        box.addLayout(options)
        self.theme.currentIndexChanged.connect(window.set_theme)
        self.theme.currentIndexChanged.connect(self.theme_changed)

        sampling,box=self.card('Monitorização','Define a cadência das novas amostras.','performance')
        self.interval=QSpinBox(); self.interval.setRange(250,10000)
        self.interval.setValue(window.settings_store.value('interval',1000,type=int)); self.interval.setSuffix(' ms')
        self.interval.valueChanged.connect(window.set_interval)
        self.setting_row(box,'Intervalo entre recolhas','CPU, memória e contadores de I/O.',self.interval)
        self.caption(box,'Um intervalo maior reduz a frequência das consultas. O tempo real depende do sistema.')

        history,box=self.card('Histórico da sessão','Escolhe quantas amostras conservar em memória.','history')
        self.limit=QSpinBox(); self.limit.setRange(60,10000)
        self.limit.setValue(window.settings_store.value('history',3600,type=int)); self.limit.setSuffix(' amostras')
        self.limit.valueChanged.connect(window.set_history_limit)
        self.setting_row(box,'Limite de amostras','As mais antigas dão lugar às novas.',self.limit)
        self.history_hint=self.caption(box,'')
        self.interval.valueChanged.connect(self.retention_hint)
        self.limit.valueChanged.connect(self.retention_hint)
        self.retention_hint()

        session,box=self.card('Preferências e dados','Cada alteração é aplicada e guardada no momento.','info')
        self.caption(box,'Tema, cadência e limite do histórico persistem entre sessões. As medições ficam em memória; exporta-as antes de fechar.')
        self.action(box,'Exportar histórico da sessão',window.export_history,'exportHistory')
        self.add_cards(preferences,[appearance,sampling,history,session])

        data=self.new_tab('Dados e relatórios')
        exports,box=self.card('Exportar dados','Ficheiros CSV para analisar ou guardar as medições.','disk')
        self.action(box,'Histórico de desempenho',window.export_history,'exportHistoryData')
        self.action(box,'Lista de processos',window.export_processes,'exportProcesses')
        lab,box=self.card('Laboratório físico','Importação, simulações e validação numérica.','lab')
        self.action(box,'Importar potência CSV',window.import_csv,'importPower')
        self.action(box,'Abrir modelo térmico',lambda:(window.nav.setCurrentRow(6),window.laboratory.setCurrentIndex(0)),'openThermal')
        self.action(box,'Explorar o laboratório',lambda:window.nav.setCurrentRow(6),'openLaboratory')
        academic,box=self.card('Relatório académico','Oito experiências executadas com dados sintéticos identificados.','analysis')
        self.academic_generate=self.action(box,'Gerar relatório académico',window.generate_academic,'generateAcademic')
        self.academic_generate.setObjectName('primary')
        self.academic_open=self.action(box,'Abrir relatório completo',window.open_academic,'openAcademic')
        self.academic_open.setEnabled((window.report_directory/'academic-final.html').is_file())
        self.academic_status=self.caption(box,'HTML offline com gráficos, métodos, resultados e limitações.')
        self.add_cards(data,[exports,lab,academic])

        system=self.new_tab('Sistema')
        diagnostics,box=self.card('Estado da monitorização','Tempos observados nesta sessão.','performance')
        self.diagnostics=self.caption(box,'A aguardar as primeiras medições…')
        self.diagnostics.setTextInteractionFlags(Qt.TextSelectableByMouse)
        sensors,box=self.card('Hardware e sensores','Consulta as fontes e a disponibilidade dos dados.','cpu')
        self.caption(box,'As leituras disponíveis dependem do sistema e das permissões. GPU e rede por processo não estão expostas pelo fornecedor atual.')
        self.action(box,'Ver hardware detetado e fontes',window.open_hardware,'openHardware')
        cadence,box=self.card('Como são recolhidos os dados','A monitorização e os modelos físicos têm origens distintas.','info')
        self.caption(box,'CPU, RAM e I/O: cada recolha. Estado dos processos: até 5 s. Swap, temperatura e frequência: 2 s. A idade dos dados consta dos detalhes e exportações.')
        details=QLabel('CPU por processo: 100% corresponde a um núcleo. Disco/rede globais são taxas medidas, não percentagens. A primeira amostra pode estar em aquecimento. Arranque e serviços são consultas de leitura. Parâmetros simulados do laboratório não são medições do hardware.')
        details.setObjectName('settingsDescription'); details.setWordWrap(True); details.hide()
        toggle=QToolButton(); toggle.setText('Ver detalhes e limitações'); toggle.setCheckable(True)
        toggle.setArrowType(Qt.RightArrow); toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        toggle.toggled.connect(details.setVisible)
        toggle.toggled.connect(lambda checked:toggle.setArrowType(Qt.DownArrow if checked else Qt.RightArrow))
        box.addWidget(toggle); box.addWidget(details)
        about,box=self.card('InProcess','Gestão de processos e laboratório de sistemas físicos.','process')
        identity=QHBoxLayout()
        mark=QLabel(); mark.setPixmap(application_icon().pixmap(56,56)); identity.addWidget(mark)
        try: software_version=version('expecto-process-manager')
        except PackageNotFoundError: software_version='desenvolvimento'
        identity.addWidget(QLabel('InProcess\nVersão '+software_version),1); box.addLayout(identity)
        self.caption(box,'Preferências locais · sem alterações automáticas a ventoinhas ou perfis do sistema.')
        self.add_cards(system,[diagnostics,sensors,cadence,about])
        self.arrange()

    def new_tab(self,title):
        scroll=QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content=QWidget(); layout=QVBoxLayout(content)
        layout.setContentsMargins(0,8,8,8); layout.setSpacing(16)
        grid=QGridLayout(); grid.setSpacing(16); layout.addLayout(grid); layout.addStretch()
        scroll.setWidget(content); self.tabs.addTab(scroll,title)
        return grid

    def card(self,title,subtitle,kind):
        card=QFrame(); card.setObjectName('settingsCard')
        box=QVBoxLayout(card); box.setContentsMargins(20,20,20,20); box.setSpacing(16)
        header=QHBoxLayout(); header.setSpacing(12)
        symbol=QLabel(); symbol.setObjectName('settingsIcon'); symbol.setPixmap(icon(kind,'#2378eb').pixmap(23,23))
        symbol.setFixedSize(40,40); symbol.setAlignment(Qt.AlignCenter); header.addWidget(symbol,0,Qt.AlignTop)
        labels=QVBoxLayout(); labels.setSpacing(4)
        heading=QLabel(title); heading.setObjectName('settingsCardTitle'); heading.setWordWrap(True)
        description=QLabel(subtitle); description.setObjectName('settingsDescription'); description.setWordWrap(True)
        labels.addWidget(heading); labels.addWidget(description); header.addLayout(labels,1)
        box.addLayout(header)
        return card,box

    def caption(self,layout,text):
        label=QLabel(text); label.setWordWrap(True); label.setObjectName('settingsDescription')
        layout.addWidget(label); return label

    def setting_row(self,layout,title,description,control):
        row=QHBoxLayout(); row.setSpacing(12)
        labels=QVBoxLayout(); labels.setSpacing(4)
        labels.addWidget(QLabel(title))
        detail=QLabel(description); detail.setObjectName('settingsDescription'); detail.setWordWrap(True)
        labels.addWidget(detail); row.addLayout(labels,1)
        control.setMinimumWidth(125); control.setMaximumWidth(195)
        row.addWidget(control); layout.addLayout(row)

    def action(self,layout,text,callback,name):
        button=QPushButton(text); button.setObjectName('settingAction')
        button.setProperty('settingsAction',name); button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(callback); layout.addWidget(button); return button

    def add_cards(self,grid,cards): self.grids.append((grid,cards))

    def arrange(self):
        columns=2 if self.width()>=840 else 1
        for grid,cards in self.grids:
            for card in cards: grid.removeWidget(card)
            grid.setColumnStretch(1,0)
            for i,card in enumerate(cards): grid.addWidget(card,i//columns,i%columns,Qt.AlignTop)
            for column in range(columns): grid.setColumnStretch(column,1)

    def resizeEvent(self,event):
        super().resizeEvent(event); self.arrange()

    def theme_changed(self,index):
        for value,button in self.theme_buttons: button.setChecked(index==value)

    def choose_theme(self,index):
        self.theme.setCurrentIndex(index)
        self.theme_changed(index)

    def retention_hint(self,*_):
        minutes=self.interval.value()*self.limit.value()/60000
        self.history_hint.setText(f'Até cerca de {minutes:g} minutos à cadência configurada. O intervalo real pode variar.')
