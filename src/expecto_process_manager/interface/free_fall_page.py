"""Uniform-gravity Euler experiment, independent of physical sensors."""
from dataclasses import dataclass
import csv
import math
import os
from pathlib import Path
import tempfile
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QDoubleSpinBox,
                              QPushButton,QLabel,QGridLayout,QFileDialog,QScrollArea)
from .workers import Tasks
from PySide6.QtCore import Signal
from .charts import Plot
from ..physics.gravity import free_fall_euler,FreeFallResult


@dataclass(frozen=True)
class FreeFallPresentation:
    result: FreeFallResult
    parameters: dict[str,float]
    times: list[float]
    heights: dict[str,list[float]]
    velocities: dict[str,list[float]]
    errors: dict[str,list[float]]
    energy: dict[str,list[float]]
    max_error: float
    rmse: float
    max_energy_drift: float


def calculate_free_fall(parameters,token) -> FreeFallPresentation:
    result=free_fall_euler(**parameters,token=token)
    token.check()
    n=len(result.times)
    stride=max(1,math.ceil((n-1)/1499))
    indices=list(range(0,n,stride))
    if indices[-1]!=n-1: indices.append(n-1)
    errors=[abs(y-ref) for y,ref in zip(result.heights,result.reference_heights)]
    g=parameters['gravity']
    energy=[.5*v*v+g*y for y,v in zip(result.heights,result.velocities)]
    reference_energy=.5*parameters['initial_velocity']**2+g*parameters['height']
    if not all(math.isfinite(value) for value in errors+energy+[reference_energy]):
        raise ValueError('Energia ou erro excederam o domínio numérico.')
    token.check()
    return FreeFallPresentation(result,dict(parameters),[result.times[i] for i in indices],
                                {'Euler':[result.heights[i] for i in indices],
                                 'Analítica':[result.reference_heights[i] for i in indices]},
                                {'Euler':[result.velocities[i] for i in indices],
                                 'Analítica':[result.reference_velocities[i] for i in indices]},
                                {'Erro absoluto':[errors[i] for i in indices]},
                                {'Euler':[energy[i] for i in indices],
                                 'Referência constante':[reference_energy]*len(indices)},
                                max(errors),math.hypot(*errors)/math.sqrt(n),
                                max(abs(e-reference_energy) for e in energy))


def export_free_fall(path,presentation,token):
    token.check()
    temporary=None
    p=presentation.parameters
    r=presentation.result
    try:
        with tempfile.NamedTemporaryFile('w',encoding='utf-8-sig',newline='',dir=Path(path).parent,delete=False) as stream:
            temporary=stream.name
            writer=csv.DictWriter(stream,fieldnames=['time_s','height_m','velocity_m_s','reference_height_m',
                                                    'reference_velocity_m_s','specific_energy_j_kg','reference_energy_j_kg',
                                                    'height_error_m','initial_height_m','initial_velocity_m_s',
                                                    'gravity_m_s2','nominal_dt_s','provenance'])
            writer.writeheader()
            for i,t in enumerate(r.times):
                if i%256==0: token.check()
                writer.writerow(dict(time_s=t,height_m=r.heights[i],velocity_m_s=r.velocities[i],
                                     reference_height_m=r.reference_heights[i],reference_velocity_m_s=r.reference_velocities[i],
                                     specific_energy_j_kg=.5*r.velocities[i]**2+p['gravity']*r.heights[i],
                                     reference_energy_j_kg=.5*p['initial_velocity']**2+p['gravity']*p['height'],
                                     height_error_m=abs(r.heights[i]-r.reference_heights[i]),initial_height_m=p['height'],
                                     initial_velocity_m_s=p['initial_velocity'],gravity_m_s2=p['gravity'],
                                     nominal_dt_s=p['dt'],provenance='simulado'))
        token.check()
        os.replace(temporary,path)
    finally:
        if temporary and os.path.exists(temporary): os.unlink(temporary)


class FreeFallPage(QWidget):
    result_ready=Signal(object)
    def __init__(self,tasks=None):
        super().__init__()
        self.tasks=tasks or Tasks(self)
        self.job=None
        self.result=None
        self.presentation=None
        layout=QVBoxLayout(self)
        layout.setContentsMargins(8,8,8,8)
        title=QLabel('Queda livre · Euler e referência analítica')
        title.setObjectName('title')
        layout.addWidget(title)
        note=QLabel('Dados simulados · g uniforme, sem arrasto · eixo positivo para cima · y < 0 significa abaixo da origem; sem impacto/chão modelado')
        note.setObjectName('muted')
        note.setWordWrap(True)
        layout.addWidget(note)
        scroll=QScrollArea()
        scroll.setWidgetResizable(True)
        content=QWidget()
        body=QHBoxLayout(content)
        form=QFormLayout()
        self.fields={}
        for name,label,value,low,high,decimals in [
                ('height','Altura inicial (m)',100,0,1e12,3),
                ('initial_velocity','Velocidade inicial (m/s)',0,-1e9,1e9,4),
                ('gravity','g (m/s²)',9.80665,0,1e6,5),
                ('duration','Duração (s)',4,.000001,1e6,6),
                ('dt','Passo Δt (s)',.01,.000001,1e6,6)]:
            spin=QDoubleSpinBox()
            spin.setDecimals(decimals)
            spin.setRange(low,high)
            spin.setValue(value)
            self.fields[name]=spin
            form.addRow(label,spin)
        self.run=QPushButton('Executar Euler')
        self.run.setObjectName('primary')
        self.run.clicked.connect(self.execute)
        form.addRow(self.run)
        cancel=QPushButton('Cancelar cálculo')
        cancel.clicked.connect(self.cancel)
        form.addRow(cancel)
        export=QPushButton('Exportar resultados CSV')
        export.clicked.connect(self.export)
        form.addRow(export)
        formulas=QLabel('Equações:\ny′ = v; v′ = −g\n\nEuler explícito:\nyₙ₊₁ = yₙ + Δt vₙ\nvₙ₊₁ = vₙ − Δt g\n\nReferência analítica:\ny(t) = y₀ + v₀t − gt²/2\nv(t) = v₀ − gt\n\nEnergia específica:\ne = v²/2 + gy (J/kg)\n\nErro global esperado em altura: O(Δt).\nCom g constante, Euler reproduz\na velocidade até arredondamento.')
        formulas.setWordWrap(True)
        formulas.setObjectName('muted')
        from PySide6.QtWidgets import QPlainTextEdit
        explanation=QPlainTextEdit(formulas.text())
        explanation.setReadOnly(True)
        explanation.setFixedHeight(170)
        formulas.deleteLater()
        explanation.hide()
        body.addLayout(form,1)
        grid=QGridLayout()
        self.plots=[Plot('Altura simulada e referência','m'),Plot('Velocidade simulada e referência','m/s'),
                    Plot('Erro absoluto da altura','m'),Plot('Energia específica · sem dissipação','J/kg')]
        for i,plot in enumerate(self.plots): grid.addWidget(plot,i//2,i%2)
        body.addLayout(grid,3)
        scroll.setWidget(content)
        layout.addWidget(scroll,1)
        self.summary=QLabel('Configure os parâmetros para comparar a aproximação de Euler com a solução analítica independente.')
        self.summary.setObjectName('muted')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

    def execute(self):
        if not self.run.isEnabled(): return
        parameters={name:spin.value() for name,spin in self.fields.items()}
        self.run.setEnabled(False)
        self.summary.setText('A calcular em segundo plano…')
        self.job=self.tasks.start(lambda token:calculate_free_fall(parameters,token),self.display,self.calculation_failed)

    def cancel(self):
        if self.job: self.job.token.cancel()

    def calculation_failed(self,message):
        self.run.setEnabled(True)
        self.job=None
        self.summary.setText(message)

    def display(self,presentation):
        self.run.setEnabled(True)
        self.job=None
        self.presentation=presentation
        self.result=presentation.result
        for plot,series in zip(self.plots,[presentation.heights,presentation.velocities,presentation.errors,presentation.energy]):
            plot.update_series(presentation.times,series)
        if presentation.max_error>0: self.plots[2].y_axis.setMin(0)
        self.summary.setText(f'Simulado · {len(self.result.times)-1} passos · RMSE altura {presentation.rmse:.6g} m · erro máximo {presentation.max_error:.6g} m · deriva máxima de energia {presentation.max_energy_drift:.6g} J/kg. Sem chão: a integração continua abaixo de y = 0.')
        self.result_ready.emit(presentation)

    def export(self):
        if self.presentation is None: return
        path,_=QFileDialog.getSaveFileName(self,'Exportar queda livre','free-fall.csv','CSV (*.csv)')
        if path:
            presentation=self.presentation
            self.tasks.start(lambda token:export_free_fall(path,presentation,token),
                             lambda _:self.summary.setText('Resultados completos e parâmetros exportados em SI; proveniência simulada.'),
                             lambda message:self.summary.setText(message))
