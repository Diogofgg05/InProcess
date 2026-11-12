import platform
from pathlib import Path
import time
from collections import deque
from dataclasses import asdict
from PySide6.QtWidgets import (QMainWindow,QWidget,QFrame,QHBoxLayout,QVBoxLayout,QListWidget,
                              QListWidgetItem,QStackedWidget,QLabel,QLineEdit,QPushButton,
                              QFileDialog,QMessageBox,QApplication,QScrollArea,QTabWidget)
from PySide6.QtCore import QTimer,QSettings,QSize,Qt,QEvent
from PySide6.QtGui import QShortcut,QKeySequence,QDesktopServices
from PySide6.QtCore import QUrl
from .workers import Tasks,SamplingThread
from .process_collector import ProcessSamplingThread
from .processes_page import ProcessesPage
from .performance_page import PerformancePage
from .physics_page import PhysicsPage
from .gravity_page import GravityPage
from .free_fall_page import FreeFallPage
from .lazy_tabs import LazyTabs
from .laboratory_workspace import LaboratoryWorkspace
from .report_actions import ReportActions
from .hardware_page import HardwarePage
from .responsive_lab import ResponsiveLab
from ..reporting.service import generate_university_report
from .analysis_page import AnalysisPage
from .history_page import HistoryPage
from .inventory_page import InventoryPage
from .settings_page import SettingsPage
from .dashboard import ResourcePanel,SummaryBar
from .theme import icon,apply_theme
from .charts import Plot
from .window_chrome import TitleBar
from .adaptive_layout import AdaptiveLayout
from .branding import application_icon
from ..core.latency import LatencyTrace
from .delegates import NavigationDelegate
from .process_icons import ProcessIcons
from ..core.processes import ProcessService
from ..core.insights import ProcessInsights
from ..core.sampling_policy import effective_interval_ms
from ..core.providers import PsutilProvider
from ..core.metrics import export_csv,import_power
from ..physics.integration import integrate


class MainWindow(QMainWindow):
    def __init__(self,provider=None,settings_path=None,report_directory=None):
        super().__init__()
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle('InProcess · Gestão de processos')
        self.setWindowIcon(application_icon())
        self.resize(1536,1024)
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.setMinimumSize(720,500)
        self.closing = False
        self.closed_ready = False
        self.history_rows = []
        self.latency_trace=LatencyTrace()
        self.report_directory=Path(report_directory or Path.cwd()/'reports')
        self.tasks = Tasks(self)
        self.provider = provider or PsutilProvider()
        self.service = ProcessService()
        self.process_insights = ProcessInsights()
        self.latest_insights = ()
        self.settings_store = QSettings(str(settings_path or Path.cwd()/'data/preferences.ini'),QSettings.IniFormat)
        if self.settings_store.value('appearanceVersion','')!='6':
            self.settings_store.setValue('theme',1)
            self.settings_store.setValue('appearanceVersion','6')
        apply_theme(QApplication.instance(),self.settings_store.value('theme',1,type=int)==0)
        root = QWidget()
        root.setObjectName('outer')
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0,0,0,0)
        self.shell = QFrame()
        self.shell.setObjectName('shell')
        outer.addWidget(self.shell)
        horizontal = QHBoxLayout(self.shell)
        horizontal.setContentsMargins(0,0,0,0)
        horizontal.setSpacing(0)
        self.sidebar = QFrame()
        self.sidebar.setObjectName('sidebar')
        self.sidebar.setFixedWidth(206)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(0,0,0,0)
        side.setSpacing(0)
        self.sidebar_brand=QLabel('InProcess')
        self.sidebar_brand.setObjectName('brand')
        self.sidebar_brand.setFixedHeight(60)
        self.sidebar_brand.setAlignment(Qt.AlignCenter)
        side.addWidget(self.sidebar_brand)
        line = QFrame()
        line.setFixedSize(0,0)
        line.setStyleSheet('background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #00c4aa,stop:0.75 #00c4aa,stop:0.76 #344152,stop:1 #344152); border: none;')
        accent = QHBoxLayout()
        accent.setContentsMargins(22,0,0,0)
        accent.addWidget(line)
        accent.addStretch()
        side.addLayout(accent)
        navigation = QVBoxLayout()
        navigation.setContentsMargins(13,18,14,0)
        self.nav = QListWidget()
        self.nav.setObjectName('navigation')
        self.nav.setIconSize(QSize(24,24))
        self.navigation_delegate=NavigationDelegate(self.nav)
        self.nav.setItemDelegate(self.navigation_delegate)
        self.nav.setMouseTracking(True)
        for title,kind in [('Processos','process'),('Desempenho','performance'),('Histórico','history'),
                           ('Aplicações','startup'),('Utilizadores','users'),('Serviços','services'),
                           ('Laboratório','lab'),('Análise científica','analysis'),('Definições','settings')]:
            item=QListWidgetItem(icon(kind),title)
            item.setSizeHint(QSize(180,51))
            self.nav.addItem(item)
        self.nav.item(7).setHidden(True)
        for index in range(self.nav.count()): self.nav.item(index).setToolTip(self.nav.item(index).text())
        navigation.addWidget(self.nav)
        side.addLayout(navigation,1)
        system_box = QHBoxLayout()
        system_box.setContentsMargins(22,18,14,28)
        system_icon = QLabel()
        self.system_icon=system_icon
        system_icon.setPixmap(icon('windows' if platform.system()=='Windows' else 'cpu').pixmap(34,34))
        system_box.addWidget(system_icon)
        system = QLabel(f'{platform.system()}\nKernel {platform.release()}')
        system.setObjectName('muted')
        self.system_label=system
        system.setWordWrap(True)
        system_box.addWidget(system,1)
        separator = QFrame()
        self.system_divider=separator
        separator.setFixedHeight(1)
        separator.setObjectName('divider')
        side.addWidget(separator)
        side.addLayout(system_box)
        horizontal.addWidget(self.sidebar)
        workspace = QVBoxLayout()
        workspace.setContentsMargins(0,0,0,0)
        workspace.setSpacing(0)
        self.titlebar = TitleBar(self)
        self.global_search = self.titlebar.search
        workspace.addWidget(self.titlebar)
        body = QHBoxLayout()
        body.setSpacing(0)
        center = QVBoxLayout()
        center.setSpacing(24)
        self.pages = QStackedWidget()
        self.processes = ProcessesPage()
        self.process_icons=ProcessIcons(self.processes.model,self.tasks,self,trace=self.latency_trace)
        self.performance = PerformancePage()
        self.hardware = HardwarePage(self.tasks)
        self.performance_tabs=QTabWidget()
        self.performance_tabs.addTab(self.performance,'Monitorização')
        self.performance_tabs.addTab(self.hardware,'Hardware detetado')
        self.performance_tabs.currentChanged.connect(self.performance_tab_changed)
        self.history = HistoryPage()
        self.history.export_requested.connect(self.export_history)
        self.analysis = AnalysisPage()
        self.analysis.report_button.clicked.connect(lambda:self.physics.report_actions.open())
        self.laboratory = LaboratoryWorkspace()
        self.laboratory.add_lazy('A · Termodinâmica',lambda:self.prepare_science_page(PhysicsPage(self.analysis,self.tasks),'thermal'))
        self.laboratory.add_lazy('Gravitação',lambda:self.prepare_science_page(GravityPage(self.tasks),'gravity'))
        self.laboratory.add_lazy('Queda livre',lambda:self.prepare_science_page(FreeFallPage(self.tasks),'free-fall'))
        self.laboratory.add_lazy('F · Métodos e validação',lambda:self.create_extra_page('numerical'))
        self.laboratory.add_lazy('A · Calibração',lambda:self.create_extra_page('calibration'))
        self.laboratory.add_lazy('A · CPU / GPU',lambda:self.create_extra_page('coupled'))
        self.laboratory.add_lazy('G · Energia / ULTRA ECO',lambda:self.create_extra_page('energy'))
        # Preserve legacy indices/APIs and data, but remove unrelated models from navigation.
        self.laboratory.setTabVisible(1,False)
        self.laboratory.setTabVisible(2,False)
        from .hardware_lab_page import HardwareLabPage
        self.laboratory.add_lazy('B · Circuitos',lambda:HardwareLabPage(('rc','rl'),self.tasks))
        self.laboratory.add_lazy('C · Arrefecimento',lambda:HardwareLabPage(('rotor','motor'),self.tasks))
        self.laboratory.add_lazy('D · Vibrações',lambda:HardwareLabPage(('vibration','forced'),self.tasks))
        self.laboratory.add_lazy('E · Dinâmica não linear',lambda:HardwareLabPage(('feedback',),self.tasks))
        from .field_lab_page import FieldLabPage
        self.laboratory.add_lazy('A · Condução e convecção',lambda:FieldLabPage('conduction',self.tasks))
        self.laboratory.add_lazy('D · Acústica',lambda:FieldLabPage('acoustic',self.tasks))
        self.inventory_pages = [InventoryPage('Aplicações de arranque','startup',self.tasks),
                                InventoryPage('Utilizadores','users',self.tasks),InventoryPage('Serviços','services',self.tasks)]
        self.settings_page = SettingsPage(self)
        for page in [self.processes,self.performance_tabs,self.history,*self.inventory_pages,self.laboratory,self.analysis,self.settings_page]:
            self.pages.addWidget(page)
        center.addWidget(self.pages,1)
        self.footer = SummaryBar()
        center.addWidget(self.footer)
        center.setContentsMargins(20,0,20,18)
        body.addLayout(center,1)
        self.resources = ResourcePanel()
        self.hardware.inventory_ready.connect(self.resources.set_inventory)
        body.addWidget(self.resources)
        workspace.addLayout(body,1)
        horizontal.addLayout(workspace,1)
        self.nav.currentRowChanged.connect(self.navigate)
        self.nav.setCurrentRow(0)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.global_search.textChanged.connect(self.search)
        self.processes.search.textChanged.connect(self.sync_search)
        self.processes.action.connect(self.control)
        if provider is None:
            self.collector = ProcessSamplingThread(self.settings_page.interval.value(),self.settings_page.limit.value(),self)
        else:
            self.collector = SamplingThread(self.provider,self.settings_page.interval.value(),self.settings_page.limit.value(),self)
        self.collector.collected.connect(self.collected)
        self.collector.failed.connect(self.collection_error)
        self.shutdown_timer = QTimer(self)
        self.shutdown_timer.setInterval(30)
        self.shutdown_timer.timeout.connect(self.finish_close)
        self.collector.start()
        self.ui_gaps = deque(maxlen=120)
        self._last_pulse = time.perf_counter()
        self.pulse_timer = QTimer(self)
        self.pulse_timer.setInterval(16)
        self.pulse_timer.timeout.connect(self.record_pulse)
        self.pulse_timer.start()
        self.statusBar().hide()
        for key,index in [('Ctrl+L',6),('Ctrl+J',7),('Ctrl+,',8)]:
            shortcut = QShortcut(QKeySequence(key),self)
            shortcut.activated.connect(lambda i=index:self.nav.setCurrentRow(i))
        gravity_shortcut = QShortcut(QKeySequence('Ctrl+G'),self)
        gravity_shortcut.activated.connect(self.open_gravity)
        search_shortcut=QShortcut(QKeySequence('Ctrl+K'),self)
        search_shortcut.activated.connect(lambda:(self.global_search.setFocus(Qt.ShortcutFocusReason),self.global_search.selectAll()))
        self.adaptive=AdaptiveLayout(self)

    def open_gravity(self):
        self.nav.setCurrentRow(6)
        self.laboratory.setCurrentIndex(1)

    @property
    def physics(self): return self.laboratory.ensure(0)

    @property
    def gravity(self): return self.laboratory.ensure(1)

    @property
    def free_fall(self): return self.laboratory.ensure(2)

    def prepare_science_page(self,page,kind):
        def context():
            return {'metadata':{'Intervalo configurado dos sensores (ms)':self.settings_page.interval.value(),
                                'Modo de aquisição':'Separado do passo interno da simulação'}}
        actions=ReportActions(page,kind,self.tasks,self.report_directory,context)
        if hasattr(page,'install_report_actions'): page.install_report_actions(actions)
        else: page.layout().addWidget(actions)
        page.result_ready.connect(actions.publish)
        page.report_actions=actions
        if kind=='thermal': actions.generated_ready.connect(lambda _:self.analysis.report_button.setEnabled(True))
        page.responsive_lab=ResponsiveLab(page)
        return page

    def create_extra_page(self,kind):
        if kind=='numerical':
            from .numerical_page import NumericalPage
            page=NumericalPage(self.tasks)
        elif kind=='calibration':
            from .calibration_page import CalibrationPage
            page=CalibrationPage(self.tasks)
        elif kind=='coupled':
            from .coupled_page import CoupledThermalPage
            page=CoupledThermalPage(self.tasks)
        else:
            from .eco_page import EcoPage
            page=EcoPage(self.tasks)
        return self.prepare_science_page(page,kind)

    def open_hardware(self):
        self.nav.setCurrentRow(1)
        self.performance_tabs.setCurrentIndex(1)

    def generate_academic(self):
        button=self.settings_page.academic_generate
        if not button.isEnabled(): return
        button.setEnabled(False)
        self.settings_page.academic_status.setText('A executar oito experiências e gerar o relatório académico…')
        def finished(path):
            button.setEnabled(True)
            self.settings_page.academic_open.setEnabled(True)
            self.settings_page.academic_status.setText('Relatório académico pronto · '+str(path))
        def failed(error):
            button.setEnabled(True)
            self.settings_page.academic_status.setText(error)
        self.tasks.start(lambda token:generate_university_report(self.report_directory,token),finished,failed)

    def open_academic(self):
        path=self.report_directory/'academic-final.html'
        if path.is_file(): QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def performance_tab_changed(self,index):
        self.update_resource_visibility()

    def update_resource_visibility(self):
        if hasattr(self,'resources'):
            monitoring=self.nav.currentRow()==0 or self.nav.currentRow()==1 and self.performance_tabs.currentIndex()==0
            self.resources.setVisible(self.width()>=1350 and self.height()>=800 and monitoring)

    def navigate(self,index):
        with self.latency_trace.measure('page_navigation'):
            self.processes.set_display_active(index==0)
            self.pages.setCurrentIndex(index)
            if index == 0:
                self.processes.show_insights(self.latest_insights)
            if index==0: self.process_icons.request(self.processes.rows)
            self.footer.setVisible(index in (0,1) and self.height()>=650)
            self.update_resource_visibility()
            if index == 2 and self.history_rows: self.history.refresh(self.history_rows)
            if index == 1 and self.performance_tabs.currentIndex()==0 and self.history_rows: self.performance.refresh(self.history_rows)

    def _apply_sampling_policy(self):
        """Keep full sampling while visible, but reduce overhead minimized."""
        if hasattr(self, 'collector'):
            self.collector.interval_ms = effective_interval_ms(
                self.settings_page.interval.value(), minimized=self.isMinimized()
            )

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange and hasattr(self, 'collector'):
            self._apply_sampling_policy()
            if hasattr(self, 'pulse_timer'):
                if self.isMinimized():
                    self.pulse_timer.stop()
                elif not self.closing:
                    self._last_pulse = time.perf_counter()
                    self.pulse_timer.start()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.update_resource_visibility()
        if hasattr(self,'titlebar'): self.titlebar.adapt(self.width())

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton and self.windowHandle() and not self.isMaximized():
            pos=event.position()
            edges=Qt.Edges()
            if pos.x()<14: edges|=Qt.LeftEdge
            if pos.x()>self.width()-14: edges|=Qt.RightEdge
            if pos.y()<12: edges|=Qt.TopEdge
            if pos.y()>self.height()-30: edges|=Qt.BottomEdge
            if edges: self.windowHandle().startSystemResize(edges)
        super().mousePressEvent(event)

    def search(self,text):
        if self.laboratory.search(text):
            self.nav.setCurrentRow(6)
            return
        if self.nav.currentRow()==6 and text: return
        if self.nav.currentRow()!=0: self.nav.setCurrentRow(0)
        self.processes.search.setText(text)

    def sync_search(self,text):
        self.global_search.blockSignals(True)
        self.global_search.setText(text)
        self.global_search.blockSignals(False)

    def collected(self,payload):
        if self.closing: return
        snapshot,rows,history = payload
        self.history_rows = history
        # The read-only detector uses already-collected data and never probes
        # processes again. Exclude our dedicated sampler/launcher identities.
        self.latest_insights = self.process_insights.observe(
            rows,
            memory_total=snapshot.memory_total,
            excluded_pids=getattr(self.collector, 'owned_pids', ()),
        )
        # History continues to collect; hidden Qt views do not need re-rendering.
        if self.isMinimized():
            return
        phase='process_view' if self.pages.currentIndex()==0 else 'process_snapshot'
        with self.latency_trace.measure(phase):
            self.processes.update_rows(rows)
        if self.pages.currentIndex()==0:
            self.processes.show_insights(self.latest_insights)
            with self.latency_trace.measure('icon_dispatch'):
                self.process_icons.request(rows)
        if self.pages.currentIndex()==1 and self.performance_tabs.currentIndex()==0:
            with self.latency_trace.measure('performance_charts'): self.performance.refresh(history)
        if self.pages.currentIndex()==2:
            with self.latency_trace.measure('history_view'): self.history.refresh(history)
        if self.resources.isVisible():
            with self.latency_trace.measure('resource_cards'): self.resources.refresh(history)
        self.footer.refresh(snapshot,len(rows))
        gaps = sorted(self.ui_gaps)
        p95 = gaps[min(len(gaps)-1,int(len(gaps)*.95))] if gaps else 0
        backend = getattr(self.collector,'backend','Thread dedicada (fornecedor externo)')
        diagnostic = f'{backend} · recolha {snapshot.collection_s*1000:.1f} ms · intervalo do timer GUI P95 {p95:.1f} ms (alvo 16 ms)'
        self.settings_page.diagnostics.setText(diagnostic)
        self.footer.setToolTip(diagnostic)
        interval = '—' if snapshot.interval_s is None else f'{snapshot.interval_s:.2f} s'
        self.statusBar().showMessage(f'{len(rows)} processos acessíveis · intervalo real {interval} · recolha {snapshot.collection_s*1000:.0f} ms · dados medidos')

    def record_pulse(self):
        now = time.perf_counter()
        self.latency_trace.pulse(now,now-self._last_pulse)
        self.ui_gaps.append((now-self._last_pulse)*1000)
        self._last_pulse = now

    def collection_error(self,message):
        self.statusBar().show()
        self.statusBar().showMessage(message,12000)

    def set_interval(self,value):
        self.settings_store.setValue('interval',value)
        if hasattr(self,'collector'): self._apply_sampling_policy()

    def set_history_limit(self,value):
        self.settings_store.setValue('history',value)
        if hasattr(self,'collector'): self.collector.history_limit = value

    def set_theme(self,index):
        self.settings_store.setValue('theme',index)
        apply_theme(QApplication.instance(),index==0)
        if hasattr(self,'titlebar'): self.titlebar.refresh_theme()
        for plot in self.findChildren(Plot): plot.theme()
        for page in self.laboratory.created.values():
            if hasattr(page,'theme'): page.theme()
        if hasattr(self,'adaptive'): self.adaptive.timer.start()

    def control(self,row,action):
        verbs = {'suspend':'suspender','resume':'continuar','terminate':'terminar'}
        if QMessageBox.question(self,'Confirmar operação',f"Autoriza {verbs[action]} {row['name']} (PID {row['pid']})?",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes: return
        self.tasks.start(lambda token:self.service.control(row['pid'],row['created'],action,authorized=True),
                         lambda _:self.control_completed(row['pid']),self.collection_error)

    def control_completed(self,pid):
        if hasattr(self.collector,'invalidate_status'):
            self.collector.invalidate_status(pid)
        elif hasattr(self.provider,'processes'):
            self.provider.processes.invalidate_status(pid)
        self.statusBar().showMessage('Operação executada.',5000)

    def save(self,prepare):
        path,_ = QFileDialog.getSaveFileName(self,'Exportar CSV','inprocess.csv','CSV (*.csv)')
        if path:
            def write(token):
                rows = prepare(token)
                export_csv(path,rows,token)
            self.tasks.start(write,lambda _:self.statusBar().showMessage('CSV exportado.',5000),self.collection_error)

    def export_history(self):
        history = list(self.history_rows)
        def prepare(token):
            rows = []
            for s in history:
                token.check()
                rows.append(asdict(s))
            return rows
        self.save(prepare)

    def export_processes(self):
        rows = list(self.processes.rows)
        self.save(lambda token:[dict(row,provenance='medido') for row in rows])

    def import_csv(self):
        self.nav.setCurrentRow(6)
        self.laboratory.setCurrentIndex(0)
        self.physics.import_power()

    def closeEvent(self,event):
        if self.closed_ready:
            self.settings_store.sync()
            event.accept()
            return
        event.ignore()
        if not self.closing:
            self.closing = True
            self.collector.stop()
            self.pulse_timer.stop()
            self.tasks.cancel()
            self.centralWidget().setEnabled(False)
            self.statusBar().showMessage('A cancelar tarefas e encerrar…')
            self.shutdown_timer.start()

    def finish_close(self):
        if not self.collector.isRunning() and not self.tasks.active():
            self.shutdown_timer.stop()
            self.closed_ready = True
            self.close()
