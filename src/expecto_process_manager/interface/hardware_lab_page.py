"""Physical-system experiments; all calculations and I/O run in workers."""
from dataclasses import asdict
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QComboBox,
    QDoubleSpinBox,QLineEdit,QPushButton,QLabel,QPlainTextEdit,QFileDialog,QScrollArea)

from .charts import Plot
from .workers import Tasks
from .responsive_lab import ResponsiveLab
from PySide6.QtCore import Qt
from ..simulation.hardware_experiments import (SPECS,PARAMETERS,HardwareConfig,run_hardware,
    import_observations,validate_observations,export_hardware)

CHANNEL_NAMES = {'voltage_v':'Tensão do capacitor','current_a':'Corrente','stored_j':'Energia armazenada',
    'input_w':'Potência de entrada','joule_w':'Perdas por efeito Joule','drag_w':'Perdas mecânicas',
    'mechanical_w':'Potência mecânica','damping_w':'Dissipação por amortecimento',
    'omega_rad_s':'Velocidade angular','rpm':'Rotação','acceleration_rad_s2':'Aceleração angular',
    'angular_momentum_kg_m2_s':'Momento angular','temperature_c':'Temperatura',
    'conductance_w_k':'Condutância térmica','displacement_m':'Deslocamento',
    'velocity_m_s':'Velocidade de vibração','control':'Comando de arrefecimento',
    'cpu_temp_c':'Temperatura CPU','sink_temp_c':'Temperatura dissipador',
    'interface_w':'Transferência CPU-dissipador','cooling_w':'Potência de arrefecimento',
    'soc':'Estado de carga (SOC)','polarization_v':'Tensão de polarização',
    'terminal_voltage_v':'Tensão terminal','chemical_j':'Energia química idealizada',
    'capacitor_j':'Energia do ramo RC','thermal_relative_j':'Energia térmica relativa',
    'load_w':'Potência fornecida à carga','loss_joule_w':'Perdas na resistência interna',
    'loss_polarization_w':'Perdas na polarização'}


class HardwareLabPage(QWidget):
    def __init__(self,models,tasks=None):
        super().__init__()
        self.tasks = tasks or Tasks(self)
        self.result = None
        self.validation = None
        self.job = None
        layout = QVBoxLayout(self)
        self.model = QComboBox()
        for key in models: self.model.addItem(SPECS[key].title,key)
        layout.addWidget(self.model)
        self.mode = QComboBox()
        self.mode.addItems(['Simulação','Experiência · importar observações','Validação · referência e erros'])
        layout.addWidget(self.mode)
        self.note = QLabel('SIMULATED · parâmetros ilustrativos · sem controlo de hardware')
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        row = QHBoxLayout(content)
        self.form_widget = QWidget()
        self.form_widget.setObjectName('parameterCard')
        self.form_widget.setAttribute(Qt.WA_StyledBackground,True)
        self.form_widget.setMinimumWidth(280)
        self.form = QFormLayout(self.form_widget)
        row.addWidget(self.form_widget,1)
        charts = QVBoxLayout()
        self.plot = Plot('Resposta física','SI')
        self.energy = Plot('Energia armazenada','J')
        self.frequency = Plot('Amplitude estacionária','m',x_title='Frequência (Hz)')
        self.channel = QComboBox()
        self.channel.currentTextChanged.connect(self.update_plot)
        charts.addWidget(self.channel)
        for plot in (self.plot,self.energy,self.frequency): charts.addWidget(plot)
        row.addLayout(charts,2)
        scroll.setWidget(content)
        layout.addWidget(scroll,3)
        buttons = QHBoxLayout()
        self.run = QPushButton('Executar')
        self.run.setObjectName('primary')
        self.run.clicked.connect(self.execute)
        buttons.addWidget(self.run)
        cancel = QPushButton('Cancelar')
        cancel.clicked.connect(self.cancel)
        buttons.addWidget(cancel)
        self.import_button = QPushButton('Importar e comparar CSV')
        self.import_button.clicked.connect(self.import_csv)
        buttons.addWidget(self.import_button)
        self.export_button = QPushButton('Exportar CSV + JSON + relatório')
        self.export_button.clicked.connect(self.export)
        buttons.addWidget(self.export_button)
        suite = QPushButton('10 experiências')
        suite.clicked.connect(self.suite)
        buttons.addWidget(suite)
        layout.addLayout(buttons)
        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        layout.addWidget(self.report,1)
        self.model.currentIndexChanged.connect(self.configure)
        self.mode.currentIndexChanged.connect(self.mode_changed)
        self.configure()
        self.responsive_lab = ResponsiveLab(self)

    def configure(self):
        while self.form.rowCount(): self.form.removeRow(0)
        self.fields = {}
        spec = SPECS[self.model.currentData()]
        for name,value in asdict(spec.factory()).items():
            title,unit,low,high = PARAMETERS[name]
            if name=='damping': unit = 'kg/s' if self.model.currentData() in ('vibration','forced') else 'N·m·s/rad'
            field = QLineEdit(f'{value:g}')
            self.fields[name] = field
            self.form.addRow(f'{title} ({unit})',field)
        self.initial = QLineEdit(', '.join(str(v) for v in spec.initial))
        from ..simulation.hardware_experiments import STATE_UNITS
        initial_units = ', '.join(STATE_UNITS[self.model.currentData()])
        self.form.addRow('Estado inicial ('+initial_units+')',self.initial)
        self.duration = QLineEdit(str(spec.duration))
        self.dt = QLineEdit(str(spec.dt))
        self.form.addRow('Duração (s)',self.duration)
        self.form.addRow('Passo Δt (s)',self.dt)
        self.result = None
        self.validation = None
        self.report.setPlainText(spec.equations+'\n\nHipóteses: '+spec.assumptions+'\n\n'+spec.interpretation+'\n\nLimitações: '+spec.limitations)
        self.channel.clear()
        for plot in (self.plot,self.energy,self.frequency): plot.update_series([],{})
        self.frequency.setVisible(self.model.currentData() in ('forced','vibration'))
        self.mode_changed()

    def mode_changed(self):
        self.import_button.setVisible(self.mode.currentIndex()==1)
        self.note.setText(['SIMULATED · parâmetros ilustrativos; nunca inferidos do hardware.',
            'CSV: time_s,value,unit · tempos relativos à condição inicial · origem não verificada · sem aquisição automática.',
            'Referências analíticas quando disponíveis; balanços incluem quadratura. Dados sintéticos validam algoritmos.'][self.mode.currentIndex()])
        self.update_plot()

    def execute(self):
        if self.job: return
        try:
            config = HardwareConfig(self.model.currentData(),{k:float(v.text()) for k,v in self.fields.items()},
                                    tuple(float(v.strip()) for v in self.initial.text().split(',')),float(self.duration.text()),float(self.dt.text()))
        except ValueError:
            self.note.setText('Introduza números com ponto decimal; condições iniciais separadas por vírgulas.')
            return
        self.busy(True)
        self.job = self.tasks.start(lambda token:run_hardware(config,token),self.display,self.failed)

    def busy(self,value):
        for widget in (self.run,self.model,self.form_widget,self.import_button,self.export_button): widget.setEnabled(not value)

    def cancel(self):
        if self.job: self.job.token.cancel()

    def failed(self,message):
        self.job = None
        self.busy(False)
        self.note.setText(message)

    def display(self,result):
        self.job = None
        self.busy(False)
        self.result = result
        self.validation = None
        self.report.setPlainText(result.report)
        self.channel.blockSignals(True)
        self.channel.clear()
        for key in result.observables['rk4'][0]:
            self.channel.addItem(CHANNEL_NAMES[key]+' ('+result.metadata['observable_units'][key]+')',key)
        self.channel.setCurrentIndex(self.channel.findData(result.metadata['primary']))
        self.channel.blockSignals(False)
        self.update_plot()
        self.energy.setVisible('stored_j' in result.observables['rk4'][0])
        if self.energy.isVisibleTo(self):
            self.energy.update_series(result.times,{m:[o['stored_j'] for o in obs] for m,obs in result.observables.items()})
        response = result.frequency_response
        if response:
            self.frequency.update_series(response['frequency_hz'],{'Amplitude estacionária · não transiente':response['amplitude_m']})
        self.note.setText('Concluído · SIMULATED · relatório inclui equações, parâmetros, erros e limitações.')

    def update_plot(self,*_):
        if self.result is None: return
        key = self.channel.currentData()
        if not key: return
        result = self.result
        unit = result.metadata['observable_units'][key]
        self.plot.y_axis.setTitleText(unit)
        if self.mode.currentIndex()==2 and key==result.metadata['primary']:
            if self.validation:
                v=self.validation
                residual=[p-o for p,o in zip(v['predicted'],v['observed'])]
                self.plot.title_label.setText('Resíduo: previsto − observado')
                self.plot.update_series(v['times_s'],{'Resíduo RK4 · origem não verificada':residual})
            elif result.errors:
                self.plot.title_label.setText('Erro absoluto perante a referência analítica')
                self.plot.update_series(result.times,{m:e['absolute'] for m,e in result.errors.items()})
            else:
                self.plot.title_label.setText('Diferença numérica perante RK4 · não validação independente')
                self.plot.update_series(result.times,{m:[abs(a[key]-b[key]) for a,b in zip(obs,result.observables['rk4'])]
                    for m,obs in result.observables.items() if m!='rk4'})
            return
        self.plot.title_label.setText('Resposta física')
        series = {m:[o[key] for o in obs] for m,obs in result.observables.items()}
        if result.reference is not None and key==result.metadata['primary']: series['Analítica independente']=result.reference
        self.plot.update_series(result.times,series)

    def import_csv(self):
        if self.result is None:
            self.note.setText('Execute primeiro o modelo a comparar.')
            return
        path,_ = QFileDialog.getOpenFileName(self,'Observações: time_s,value,unit','','CSV (*.csv)')
        if not path: return
        result = self.result
        def calculate(token):
            t,y = import_observations(path,result.metadata['primary_unit'],token)
            return validate_observations(result,t,y,token)
        self.busy(True)
        self.job = self.tasks.start(calculate,self.validated,self.failed)

    def validated(self,validation):
        self.job = None
        self.busy(False)
        self.validation = validation
        e = validation['errors']
        self.report.appendPlainText(f'\nIMPORTED_UNVERIFIED: MAE={e["mae"]:.8g}; RMSE={e["rmse"]:.8g}; máximo={e["maximum"]:.8g} {validation["unit"]}.\n'+validation['limitation'])
        self.plot.y_axis.setTitleText(validation['unit'])
        self.plot.update_series(validation['times_s'],{'Observações · origem não verificada':validation['observed'],
                                                       'RK4 nos tempos observados':validation['predicted']})

    def export(self):
        if self.result is None: return
        directory = QFileDialog.getExistingDirectory(self,'Exportar experiência científica')
        if not directory: return
        result,validation = self.result,self.validation
        self.busy(True)
        self.job = self.tasks.start(lambda token:export_hardware(result,directory,token,validation),self.exported,self.failed)

    def exported(self,path):
        self.job = None
        self.busy(False)
        self.note.setText('CSV, JSON e relatório HTML guardados em '+str(path.parent))

    def suite(self):
        if self.job: return
        directory = QFileDialog.getExistingDirectory(self,'Relatório das dez experiências físicas')
        if not directory: return
        from ..reporting.physical_suite import generate_physical_suite
        self.busy(True)
        self.job = self.tasks.start(lambda token:generate_physical_suite(directory,token),self.exported,self.failed)
