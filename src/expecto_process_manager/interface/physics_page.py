from dataclasses import replace
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QDoubleSpinBox,QSpinBox,
                              QComboBox,QPushButton,QLabel,QGridLayout,QFileDialog,QScrollArea,
                              QFrame,QToolButton,QButtonGroup,QTableWidget,QTableWidgetItem,QHeaderView,QMenu)
from .charts import Plot
from PySide6.QtCore import Signal
from .workers import Tasks
from ..simulation.experiments import ExperimentConfig,run_experiment,save_experiment,load_experiment
from ..simulation.scenarios import SCENARIOS
from ..core.metrics import export_csv,import_power
from .theme import icon
from PySide6.QtCore import Qt


class PhysicsPage(QWidget):
    result_ready=Signal(object)
    def __init__(self,analysis,tasks=None):
        super().__init__()
        self.analysis = analysis
        self.tasks = tasks or Tasks(self)
        self.result = None
        self.experiment = None
        self.result_context = {}
        self.imported = None
        self.job = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(12)
        heading = QHBoxLayout()
        label = QLabel('Modelo Térmico do CPU')
        label.setObjectName('title')
        heading.addWidget(label,1)
        self.modes = QButtonGroup(self)
        for i,(name,tip) in enumerate([('Simulação','Temperatura e comparação de métodos'),
                                      ('Validação','Erros, convergência e referência analítica'),
                                      ('Experiência','Potência, energia e dados importados')]):
            button = QPushButton(name)
            button.setObjectName('segment'); button.setCheckable(True)
            button.setToolTip(tip); button.setCursor(Qt.PointingHandCursor)
            self.modes.addButton(button,i); heading.addWidget(button)
        self.modes.button(0).setChecked(True)
        self.modes.idClicked.connect(self.set_mode)
        layout.addLayout(heading)
        provenance = QLabel('C dT/dt = P(t) − k(T − Ta) · Comparação de métodos numéricos e validação.')
        provenance.setObjectName('muted')
        provenance.setWordWrap(True)
        layout.addWidget(provenance)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        body = QHBoxLayout(content)
        body.setContentsMargins(0,0,0,0); body.setSpacing(14)
        self.parameter_card = QFrame()
        self.parameter_card.setObjectName('parameterCard')
        self.parameter_card.setMinimumWidth(270)
        parameter_box = QVBoxLayout(self.parameter_card)
        parameter_box.setContentsMargins(16,14,16,14); parameter_box.setSpacing(9)
        parameter_title = QLabel('Parâmetros do modelo')
        parameter_title.setObjectName('sectionTitle')
        parameter_box.addWidget(parameter_title)
        form = QFormLayout()
        form.setVerticalSpacing(7); form.setHorizontalSpacing(10)
        parameter_box.addLayout(form)
        self.fields = {}
        for name,title,value,low,high in [
            ('power','Potência P (W)',45,0,2000),('capacity','Capacidade C (J/K)',180,.01,100000),
            ('dissipation','Dissipação k (W/K)',1.2,.001,1000),('ambient','T ambiente (°C)',25,-100,100),
            ('initial','T inicial (°C)',30,-100,300),('duration','Duração (s)',120,.01,3600)]:
            spin = QDoubleSpinBox()
            spin.setRange(low,high)
            spin.setDecimals(2)
            spin.setValue(value)
            spin.setMinimumWidth(94)
            spin.setFixedHeight(34)
            self.fields[name] = spin
            form.addRow(title,spin)
        self.step = QComboBox()
        self.step.addItems(['0.01','0.05','0.1','0.5','1'])
        self.step.setCurrentText('0.5')
        self.step.setFixedHeight(34)
        form.addRow('Passo Δt (s)',self.step)
        advanced_toggle = QToolButton()
        advanced_toggle.setText('Opções da experiência')
        advanced_toggle.setCheckable(True)
        advanced_toggle.setToolButtonStyle(Qt.ToolButtonTextOnly)
        parameter_box.addWidget(advanced_toggle)
        self.advanced = QWidget()
        advanced_form = QFormLayout(self.advanced)
        advanced_form.setContentsMargins(0,0,0,0)
        self.scenario = QComboBox()
        self.scenario.addItems(SCENARIOS)
        advanced_form.addRow('Cenário',self.scenario)
        noise = QDoubleSpinBox(); noise.setRange(0,30); noise.setDecimals(3); noise.setValue(.2)
        self.fields['noise'] = noise
        advanced_form.addRow('Ruído σ (°C)',noise)
        self.seed = QSpinBox(); self.seed.setRange(0,2147483647); self.seed.setValue(42)
        advanced_form.addRow('Semente',self.seed)
        parameter_box.addWidget(self.advanced)
        self.advanced.hide(); advanced_toggle.toggled.connect(self.advanced.setVisible)
        self.run = QPushButton('Simular')
        self.run.setIcon(icon('play','#ffffff'))
        self.run.setObjectName('primary')
        self.run.clicked.connect(self.execute)
        cancel = QPushButton('Cancelar')
        self.cancel_button = cancel
        cancel.clicked.connect(self.cancel)
        actions = QHBoxLayout()
        actions.addWidget(self.run)
        actions.addWidget(cancel)
        parameter_box.addLayout(actions)
        files = QToolButton()
        files.setText('Dados e exportação')
        files.setToolButtonStyle(Qt.ToolButtonTextOnly)
        files.setPopupMode(QToolButton.InstantPopup)
        files_menu = QMenu(files)
        self.files_menu = files_menu
        for text,callback in [('Importar potência CSV',self.import_power),('Usar cenário simulado',self.clear_import),
                              ('Guardar experiência',self.save),('Reabrir experiência',self.open),
                              ('Exportar resultados CSV',self.export)]:
            files_menu.addAction(text,callback)
        files.setMenu(files_menu)
        parameter_box.addWidget(files)
        parameter_box.addStretch()
        body.addWidget(self.parameter_card,1)
        right = QVBoxLayout(); right.setSpacing(14)
        self.chart_grid = QGridLayout(); self.chart_grid.setSpacing(14)
        self.plots = [Plot('Temperatura do CPU — comparação de métodos','°C'),Plot('Potência de entrada','W'),
                      Plot('Energia — comparação de quadraturas','J'),Plot('Erro absoluto |Tn − T(tn)|','°C',log_y=True)]
        self.plots[3].setToolTip('Escala logarítmica no erro; valores exatamente zero não são representáveis.')
        self.chart_grid.addWidget(self.plots[0],0,0)
        self.chart_grid.addWidget(self.plots[3],0,1)
        self.chart_grid.addWidget(self.plots[1],1,0)
        self.chart_grid.addWidget(self.plots[2],1,1)
        self.plots[1].hide(); self.plots[2].hide()
        for plot in self.plots: plot.setMinimumHeight(260)
        right.addLayout(self.chart_grid,3)
        results = QHBoxLayout(); results.setSpacing(12)
        self.results_card = QFrame(); self.results_card.setObjectName('resultCard')
        results_box = QVBoxLayout(self.results_card)
        results_box.setContentsMargins(12,12,12,12); results_box.setSpacing(10)
        results_title = QLabel('Resultados principais'); results_title.setObjectName('sectionTitle')
        results_title.setMaximumHeight(25)
        results_box.addWidget(results_title)
        tiles = QHBoxLayout(); self.metrics = {}
        for key,title in [('final','T final · RK4'),('equilibrium','Equilíbrio Teq'),('tau','Constante τ')]:
            tile = QFrame(); tile.setObjectName('metricTile')
            tile_box = QVBoxLayout(tile)
            caption = QLabel(title); caption.setObjectName('muted')
            value = QLabel('—'); value.setObjectName('metric')
            tile_box.addWidget(caption); tile_box.addWidget(value)
            self.metrics[key] = value; tiles.addWidget(tile)
        results_box.addLayout(tiles)
        results.addWidget(self.results_card,4)
        errors_card = QFrame(); errors_card.setObjectName('resultCard')
        errors_box = QVBoxLayout(errors_card)
        errors_title = QLabel('Erros dos métodos'); errors_title.setObjectName('sectionTitle')
        errors_box.addWidget(errors_title)
        self.error_table = QTableWidget(3,2)
        self.error_table.setHorizontalHeaderLabels(['Método','Erro final (°C)'])
        self.error_table.verticalHeader().hide(); self.error_table.setShowGrid(False)
        self.error_table.verticalHeader().setDefaultSectionSize(28)
        self.error_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.error_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.error_table.setMaximumHeight(144)
        self.error_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        for i,name in enumerate(('Euler','Heun','RK4')):
            self.error_table.setItem(i,0,QTableWidgetItem(name))
            self.error_table.setItem(i,1,QTableWidgetItem('—'))
        errors_box.addWidget(self.error_table)
        results.addWidget(errors_card,3)
        interpretation_card = QFrame(); interpretation_card.setObjectName('resultCard')
        interpretation_box = QVBoxLayout(interpretation_card)
        interpretation_title = QLabel('Interpretação'); interpretation_title.setObjectName('sectionTitle')
        interpretation_box.addWidget(interpretation_title)
        self.interpretation = QLabel('Execute uma simulação para interpretar a evolução térmica e comparar os métodos.')
        self.interpretation.setWordWrap(True); self.interpretation.setObjectName('muted')
        interpretation_box.addWidget(self.interpretation,1)
        results.addWidget(interpretation_card,3)
        right.addLayout(results,2)
        body.addLayout(right,4)
        scroll.setWidget(content)
        layout.addWidget(scroll,1)
        self.summary = QLabel('Referência analítica por intervalo para potência retida à esquerda. Dados sintéticos.')
        self.summary.setWordWrap(True)
        self.summary.setObjectName('muted')
        layout.addWidget(self.summary)

    def install_report_actions(self,actions):
        actions.hide()
        self.files_menu.addSeparator()
        menu_actions = [self.files_menu.addAction(text,callback) for text,callback in
                        [('Ver relatório científico',actions.open),('Guardar relatório HTML',actions.save),
                         ('Exportar gráficos PNG',actions.export_png)]]
        for action in menu_actions: action.setEnabled(False)
        actions.generated_ready.connect(lambda _: [action.setEnabled(True) for action in menu_actions])

    def set_mode(self,mode):
        self.plots[1].setVisible(mode==2)
        self.plots[2].setVisible(mode==2)
        if self.experiment:
            series = dict(self.temperature_series)
            if mode==2: series['Observação sintética com ruído']=self.experiment.noisy
            self.plots[0].update_series(self.result.times,series)
        if mode==1:
            self.summary.setText('Validação numérica perante a solução analítica ZOH. Os erros não certificam o comportamento de hardware real.')
        elif mode==2:
            self.summary.setText('Importe potência CSV ou escolha um cenário. Temperaturas calculadas continuam a ser simulações.')

    def config(self):
        params = {k:v.value() for k,v in self.fields.items()}
        config = ExperimentConfig(**params,dt=float(self.step.currentText()),seed=self.seed.value(),scenario=self.scenario.currentText())
        if self.imported:
            times,powers,origin = self.imported
            config = replace(config,source_times=times,source_powers=powers,provenance=origin)
        return config

    def execute(self):
        if not self.run.isEnabled(): return
        try: config = self.config()
        except ValueError as error:
            self.failed(str(error))
            return
        self.run.setEnabled(False)
        self.summary.setText('A calcular… Pode cancelar ou continuar a navegar.')
        self.job = self.tasks.start(lambda token:run_experiment(config,token),self.display,self.calculation_failed)

    def cancel(self):
        if self.job: self.job.token.cancel()

    def clear_import(self):
        self.imported = None
        self.summary.setText('Potência sintética do cenário selecionado.')

    def failed(self,message):
        self.summary.setText(message)

    def calculation_failed(self,message):
        self.run.setEnabled(True)
        self.job = None
        self.failed(message)

    def display(self,experiment):
        self.run.setEnabled(True)
        self.job = None
        self.experiment = experiment
        self.result = experiment.simulation
        r,e = self.result,experiment
        methods = e.method_solutions or {'Euler':r.temperatures}
        labels = {'Euler':'Euler','Heun':'Heun','RK4':'RK4'}
        temperatures = {labels[name]:values for name,values in methods.items()}
        temperatures.update({'Analítica (ZOH)':r.reference})
        self.temperature_series = dict(temperatures)
        if self.modes.checkedId()==2: temperatures['Observação sintética com ruído']=e.noisy
        self.plots[0].update_series(r.times,temperatures)
        self.plots[1].update_series(r.times,{'Potência de entrada · amostras':r.powers})
        energy = {'Trapézios · potência amostrada':e.energy}
        if e.energy_zoh: energy['Retenção à esquerda · ZOH'] = e.energy_zoh
        self.plots[2].update_series(r.times,energy)
        method_errors = e.method_errors or {'Euler':e.error}
        self.plots[3].update_series(r.times,{f'Erro absoluto · {name}':error['absolute'] for name,error in method_errors.items()})
        rmse = ' · '.join(f"{name} {error['rmse']:.4g}" for name,error in method_errors.items())
        input_energy = e.energy_zoh[-1] if e.energy_zoh else e.energy[-1]
        self.summary.setText(f'Simulação concluída · temperatura simulada · potência {e.config.provenance} · Δt = {e.config.dt:g} s')
        self.summary.setToolTip(f'RMSE (°C): {rmse}\nEntrada ZOH {input_energy:.5g} J · trapézios {e.energy[-1]:.5g} J.')
        c = e.config
        final_temperature = methods.get('RK4',r.temperatures)[-1]
        equilibrium = c.ambient+r.powers[-1]/c.dissipation
        self.metrics['final'].setText(f'{final_temperature:.1f} °C'.replace('.',','))
        self.metrics['equilibrium'].setText(f'{equilibrium:.1f} °C'.replace('.',','))
        self.metrics['tau'].setText(f'{c.capacity/c.dissipation:.1f} s'.replace('.',','))
        self.metrics['equilibrium'].setToolTip('Equilíbrio associado à potência final, se mantida constante.')
        for row,name in enumerate(('Euler','Heun','RK4')):
            error = method_errors.get(name)
            if error: self.error_table.item(row,1).setText(f'{error["absolute"][-1]:.3g}'.replace('.',','))
        self.interpretation.setText(f'• Sob potência final constante, o equilíbrio é {equilibrium:.1f} °C.\n\n'
                                    f'• A constante τ = C/k é {c.capacity/c.dissipation:.1f} s.\n\n'
                                    '• Os erros comparam métodos e referência; os parâmetros não estão calibrados ao PC.')
        self.result_context = {'provenance':'SIMULATED','power_provenance':e.config.provenance,
                               'method_timings_s':dict(e.method_timings),'timing_scope':'temperature loops only',
                               'energy_input_zoh_j':input_energy}
        self.analysis.display(e)
        self.result_ready.emit(e)

    def import_power(self):
        path,_ = QFileDialog.getOpenFileName(self,'Importar potência','','CSV (*.csv)')
        if path:
            self.tasks.start(lambda token:import_power(path,token),self.power_loaded,self.failed)

    def power_loaded(self,payload):
        self.imported = payload
        self.fields['duration'].setValue(payload[0][-1]-payload[0][0])
        self.summary.setText(f'{len(payload[0])} amostras · origem não verificada · retenção à esquerda · duração limitada à cobertura CSV')

    def save(self):
        if not self.experiment:
            self.summary.setText('Execute uma experiência antes de guardar.')
            return
        path,_ = QFileDialog.getSaveFileName(self,'Guardar experiência','experiment.json','JSON (*.json)')
        if path:
            experiment = self.experiment
            self.tasks.start(lambda token:save_experiment(path,experiment,token),lambda _:self.summary.setText('Experiência guardada com configuração e resultados.'),self.failed)

    def open(self):
        if not self.run.isEnabled(): return
        path,_ = QFileDialog.getOpenFileName(self,'Reabrir experiência','','JSON (*.json)')
        if path:
            self.run.setEnabled(False)
            self.job = self.tasks.start(lambda token:load_experiment(path,token),self.loaded,self.calculation_failed)

    def loaded(self,experiment):
        c = experiment.config
        for name,spin in self.fields.items():
            value = getattr(c,name)
            spin.setRange(min(spin.minimum(),value),max(spin.maximum(),value))
            spin.setValue(value)
        self.seed.setValue(c.seed)
        if self.step.findText(str(c.dt)) < 0: self.step.addItem(str(c.dt))
        self.step.setCurrentText(str(c.dt))
        self.scenario.setCurrentText(c.scenario)
        self.imported = (c.source_times,c.source_powers,c.provenance) if c.source_times else None
        self.display(experiment)

    def export(self):
        if not self.experiment: return
        path,_ = QFileDialog.getSaveFileName(self,'Exportar resultados','simulation.csv','CSV (*.csv)')
        if path:
            experiment = self.experiment
            def write(token):
                r = experiment.simulation
                heun = experiment.method_solutions.get('Heun')
                rk4 = experiment.method_solutions.get('RK4')
                rows = []
                for i,(t,v,p,ref) in enumerate(zip(r.times,r.temperatures,r.powers,r.reference)):
                    if i % 256 == 0: token.check()
                    rows.append(dict(time_s=t,temperature_c=v,power_w=p,reference_c=ref,
                                     heun_temperature_c=heun[i] if heun else None,
                                     rk4_temperature_c=rk4[i] if rk4 else None,
                                     euler_error_c=experiment.error['absolute'][i],
                                     energy_trapezoid_j=experiment.energy[i],
                                     energy_zoh_j=experiment.energy_zoh[i] if experiment.energy_zoh else None,
                                     temperature_origin='simulado',power_origin=experiment.config.provenance))
                export_csv(path,rows,token)
            self.tasks.start(write,lambda _:self.summary.setText('CSV exportado. Guarde também a experiência JSON para reproduzir.'),self.failed)
