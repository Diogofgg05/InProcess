"""Gravitational laboratory. Numeric work and file operations run in Tasks."""
from dataclasses import asdict
import csv
import json
import os
from pathlib import Path
import tempfile
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLineEdit,
                              QDoubleSpinBox,QComboBox,QPushButton,QLabel,QGridLayout,
                              QFileDialog,QScrollArea,QPlainTextEdit)
from PySide6.QtGui import QPen,QColor
from PySide6.QtCore import Signal
from .workers import Tasks
from .charts import Plot
from .gravity_visuals import OrbitPlot,prepare_gravity
from ..physics.gravity import GravityConfig,run_gravity


_UNITS={'time':'s','position':'m','velocity':'m/s','mass':'kg','energy':'J','angular_momentum':'kg m²/s'}
_LABELS={'Euler explícito':'Euler explícito','Euler simplético':'Euler simplético','Velocity Verlet':'Velocity Verlet'}


def _calculate(config,token):
    experiment=run_gravity(config,token)
    presentation=prepare_gravity(experiment,token)
    return experiment,presentation


def _save_config(path,config,token):
    token.check()
    target=Path(path)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=target.parent,delete=False) as stream:
            temporary=stream.name
            json.dump({'schema':'expecto-gravity-1','units':_UNITS,'provenance':'simulado',
                       'model':'massa central fixa, gravitação Newtoniana 2D',
                       'config':asdict(config)},stream,ensure_ascii=False,allow_nan=False,indent=2)
        token.check()
        os.replace(temporary,target)
    finally:
        if temporary and os.path.exists(temporary): os.unlink(temporary)


def _open_config(path,token):
    token.check()
    if Path(path).stat().st_size>64*1024:
        raise ValueError('Configuração gravitacional demasiado grande (máximo 64 KiB).')
    with open(path,encoding='utf-8') as stream: payload=json.load(stream)
    if not isinstance(payload,dict) or payload.get('schema')!='expecto-gravity-1' or payload.get('units')!=_UNITS:
        raise ValueError('Versão/unidades da configuração gravitacional inválidas.')
    try:
        config=GravityConfig(**payload['config'])
    except (KeyError,TypeError) as error:
        raise ValueError('Configuração gravitacional inválida.') from error
    return _calculate(config,token)


def _export(path,experiment,token):
    token.check()
    temporary=None
    try:
        with tempfile.NamedTemporaryFile('w',encoding='utf-8-sig',newline='',dir=Path(path).parent,delete=False) as stream:
            temporary=stream.name
            writer=csv.DictWriter(stream,fieldnames=['method','time_s','x_m','y_m','vx_m_s','vy_m_s',
                                                    'energy_j','angular_momentum_kg_m2_s','position_error_m','provenance'])
            writer.writeheader()
            for method,trajectory in experiment.trajectories.items():
                for i,t in enumerate(experiment.times):
                    if i%256==0: token.check()
                    writer.writerow(dict(method=method,time_s=t,x_m=trajectory.x[i],y_m=trajectory.y[i],
                                         vx_m_s=trajectory.vx[i],vy_m_s=trajectory.vy[i],
                                         energy_j=trajectory.energy[i],angular_momentum_kg_m2_s=trajectory.angular_momentum[i],
                                         position_error_m=trajectory.position_error[i] if trajectory.position_error is not None else None,
                                         provenance='simulado'))
        token.check()
        os.replace(temporary,path)
    finally:
        if temporary and os.path.exists(temporary): os.unlink(temporary)


class GravityPage(QWidget):
    result_ready=Signal(object)
    def __init__(self,tasks=None):
        super().__init__()
        self.tasks=tasks or Tasks(self)
        self.job=None
        self.experiment=None
        self.presentation=None
        self.result=None
        layout=QVBoxLayout(self)
        layout.setContentsMargins(8,8,8,8)
        title=QLabel('Laboratório gravitacional')
        title.setObjectName('title')
        layout.addWidget(title)
        note=QLabel('Simulação Newtoniana com massa central fixa. Modelos, métodos e limitações no relatório.')
        note.setObjectName('muted')
        note.setWordWrap(True)
        layout.addWidget(note)
        scroll=QScrollArea()
        scroll.setWidgetResizable(True)
        content=QWidget()
        body=QHBoxLayout(content)
        body.setContentsMargins(4,8,4,4)
        form=QFormLayout()
        form.setHorizontalSpacing(10)
        self.central_mass=QLineEdit('5.972e24')
        self.body_mass=QLineEdit('1000')
        self.central_mass.setToolTip('Massa pontual central em kg. Aceita notação científica, por exemplo 5.972e24.')
        self.body_mass.setToolTip('Massa de teste em kg; não altera a aceleração no modelo de massa central fixa.')
        form.addRow('Massa central M (kg)',self.central_mass)
        form.addRow('Massa de teste m (kg)',self.body_mass)
        self.fields={}
        for name,label,value,low,high,decimals in [
                ('radius','Raio inicial (km)',7000,.001,1e12,3),
                ('velocity_factor','Velocidade (× circular)',1,0,10,4),
                ('duration','Duração (s)',10800,.001,1e9,3),
                ('dt','Passo Δt (s)',10,.000001,1e8,6)]:
            spin=QDoubleSpinBox()
            spin.setDecimals(decimals)
            spin.setRange(low,high)
            spin.setValue(value)
            self.fields[name]=spin
            form.addRow(label,spin)
        self.fields['velocity_factor'].setToolTip('Velocidade tangencial inicial não negativa relativa a √(GM/r). Fator 1 dá órbita circular; fator 0 dá queda radial idealizada.')
        self.preset=QComboBox()
        self.preset.addItems(['Circular sintética','Elíptica sintética','Escape sintético'])
        self.preset.currentIndexChanged.connect(self.set_preset)
        form.addRow('Cenário ilustrativo',self.preset)
        self.run=QPushButton('Comparar os três métodos')
        self.run.setObjectName('primary')
        self.run.clicked.connect(self.execute)
        form.addRow(self.run)
        self.cancel_button=QPushButton('Cancelar cálculo')
        self.cancel_button.clicked.connect(self.cancel)
        form.addRow(self.cancel_button)
        row=QHBoxLayout()
        for text,callback in [('Guardar configuração',self.save),('Reabrir',self.open)]:
            button=QPushButton(text)
            button.clicked.connect(callback)
            row.addWidget(button)
        form.addRow(row)
        export=QPushButton('Exportar resultados CSV')
        export.clicked.connect(self.export)
        form.addRow(export)
        physical=QLabel('v circular = √(GM/r)\nEstado inicial: (x,y) = (r,0),\n(vx,vy) = (0, fator · v circular).\n\nComparação: Euler explícito,\nEuler simplético e Velocity Verlet.\n\nΔE/|E₀| e ΔL/|L₀| são diagnósticos\nnuméricos, não medições reais.')
        physical.setWordWrap(True)
        physical.setObjectName('muted')
        explanation=QPlainTextEdit(physical.text())
        explanation.setReadOnly(True)
        explanation.setFixedHeight(120)
        physical.deleteLater()
        explanation.hide()
        body.addLayout(form,1)
        graphics=QVBoxLayout()
        grid=QGridLayout()
        self.orbit=OrbitPlot()
        self.energy=Plot('Deriva relativa de energia','(E − E₀) / |E₀|')
        self.error=Plot('Erro de posição · referência circular','km')
        self.momentum=Plot('Deriva relativa de momento angular','(L − L₀) / |L₀|')
        self.plots=[self.orbit,self.energy,self.error,self.momentum]
        for i,plot in enumerate(self.plots): grid.addWidget(plot,i//2,i%2)
        graphics.addLayout(grid,3)
        self.report=QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setMinimumHeight(120)
        self.report.hide()
        body.addLayout(graphics,3)
        scroll.setWidget(content)
        layout.addWidget(scroll,1)
        self.summary=QLabel('Configure a experiência e compare Euler com métodos que preservam melhor a dinâmica orbital.')
        self.summary.setWordWrap(True)
        self.summary.setObjectName('muted')
        layout.addWidget(self.summary)

    def set_preset(self,index):
        self.fields['velocity_factor'].setValue([1,.75,1.5][index])

    def config(self):
        try:
            central=float(self.central_mass.text().replace(',','.'))
            body=float(self.body_mass.text().replace(',','.'))
        except ValueError as error:
            raise ValueError('As massas devem ser números finitos em kg; pode usar notação científica.') from error
        return GravityConfig(central_mass=central,body_mass=body,
                             radius=self.fields['radius'].value()*1000,
                             velocity_factor=self.fields['velocity_factor'].value(),
                             duration=self.fields['duration'].value(),dt=self.fields['dt'].value())

    def execute(self):
        if not self.run.isEnabled(): return
        try: config=self.config()
        except (ValueError,TypeError,OverflowError) as error:
            self.failed(str(error))
            return
        self.run.setEnabled(False)
        self.summary.setText('A calcular trajetórias e diagnósticos em segundo plano…')
        self.job=self.tasks.start(lambda token:_calculate(config,token),self.display,self.calculation_failed)

    def cancel(self):
        if self.job: self.job.token.cancel()

    def failed(self,message):
        self.summary.setText(message)

    def calculation_failed(self,message):
        self.run.setEnabled(True)
        self.job=None
        self.failed(message)

    def display(self,payload):
        self.run.setEnabled(True)
        self.job=None
        self.experiment,self.presentation=payload
        self.result=self.experiment
        p=self.presentation
        self.orbit.set_orbits(p.orbits)
        for chart,series in [(self.energy,p.energy_drift),(self.error,p.errors),(self.momentum,p.momentum_drift)]:
            chart.update_series(p.times,{_LABELS.get(name,name):values for name,values in series.items()})
            colors={'Euler explícito':'#21b9ff','Euler simplético':'#b366ff','Velocity Verlet':'#28d58b'}
            for name,line in chart.lines.items():
                line.setPen(QPen(QColor(colors.get(name,'#e6b454')),1.4))
        if p.errors: self.error.y_axis.setMin(0)
        text=self.experiment.report
        if p.note: text+='\n\n'+p.note
        self.report.setPlainText(text)
        c=self.experiment.config
        self.summary.setText(f'Simulado · {len(self.experiment.times)-1} passos · Δt = {c.dt:g} s · r₀ = {c.radius/1000:g} km · fator de velocidade = {c.velocity_factor:g}')
        self.result_ready.emit(self.experiment)

    def save(self):
        if self.experiment is None:
            self.failed('Execute uma simulação antes de guardar a configuração.')
            return
        path,_=QFileDialog.getSaveFileName(self,'Guardar configuração gravitacional','gravity.json','JSON (*.json)')
        if path:
            config=self.experiment.config
            self.tasks.start(lambda token:_save_config(path,config,token),
                             lambda _:self.summary.setText('Configuração guardada. Ao reabrir, as trajetórias são recalculadas.'),self.failed)

    def open(self):
        if not self.run.isEnabled(): return
        path,_=QFileDialog.getOpenFileName(self,'Reabrir configuração gravitacional','','JSON (*.json)')
        if path:
            self.run.setEnabled(False)
            self.summary.setText('A validar a configuração e reproduzir a experiência…')
            self.job=self.tasks.start(lambda token:_open_config(path,token),self.loaded,self.calculation_failed)

    def loaded(self,payload):
        experiment,_=payload
        c=experiment.config
        self.central_mass.setText(f'{c.central_mass:.17g}')
        self.body_mass.setText(f'{c.body_mass:.17g}')
        values={'radius':c.radius/1000,'velocity_factor':c.velocity_factor,'duration':c.duration,'dt':c.dt}
        for name,value in values.items():
            spin=self.fields[name]
            spin.setRange(min(spin.minimum(),value),max(spin.maximum(),value))
            spin.setValue(value)
        self.display(payload)

    def export(self):
        if self.experiment is None: return
        path,_=QFileDialog.getSaveFileName(self,'Exportar trajetórias gravitacionais','gravity.csv','CSV (*.csv)')
        if path:
            experiment=self.experiment
            self.tasks.start(lambda token:_export(path,experiment,token),
                             lambda _:self.summary.setText('Resultados completos exportados em SI; guarde a configuração JSON para reproduzir.'),self.failed)

    def theme(self):
        self.orbit.theme()
