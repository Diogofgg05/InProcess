"""Small conduction/acoustic extensions with explicit units and local imports."""
import csv
import json
import math
from html import escape
from pathlib import Path
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QFormLayout,QHBoxLayout,QLineEdit,
                              QPushButton,QPlainTextEdit,QLabel,QFileDialog,QComboBox)
from .charts import Plot
from .workers import Tasks
from ..physics.acoustics import spectrum,wave_field,tonal_frequencies
from ..physics.hardware_models import heat_path,parallel_plates
from ..simulation.hardware_experiments import import_observations


class FieldLabPage(QWidget):
    def __init__(self,kind,tasks=None):
        super().__init__()
        self.kind,self.tasks = kind,tasks or Tasks(self)
        self.job,self.result = None,None
        layout = QVBoxLayout(self)
        self.note = QLabel('Extensão didática · hipóteses explícitas · dados simulados ou importados localmente')
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.mode = QComboBox()
        self.mode.addItems(['Simulação','Experiência · importar sinal','Validação']) if kind=='acoustic' else self.mode.addItems(['Simulação','Validação por leis de Fourier e Newton'])
        layout.addWidget(self.mode)
        form = QFormLayout()
        self.fields = {}
        definitions = [('rpm','Rotação (RPM)',1200),('blades','Número de pás',7),('speed','Velocidade do som (m/s)',343),
                       ('length','Comprimento (m)',1),('reflection','Reflexão de pressão (−1 a 1)',.5),
                       ('attenuation','Atenuação fenomenológica (1/m)',0),('amplitude','Amplitude simulada (Pa)',1),
                       ('sample_rate','Amostragem (Hz)',4096),('count','Amostras FFT (potência de 2)',4096)] if kind=='acoustic' else [
                       ('hot','Chip (°C)',60),('cold','Ambiente (°C)',25),('conductivity','Condutividade (W/(m·K))',200),
                       ('area','Área (m²)',.001),('thickness','Espessura (m)',.005),('h','Convecção (W/(m²·K))',25)]
        for name,title,value in definitions:
            field = QLineEdit(str(value)); self.fields[name]=field; form.addRow(title,field)
        layout.addLayout(form)
        buttons = QHBoxLayout()
        self.run = QPushButton('Simular e verificar')
        self.run.clicked.connect(self.execute); buttons.addWidget(self.run)
        if kind=='acoustic':
            button = QPushButton('Importar sinal CSV (Pa)')
            button.clicked.connect(self.import_signal); buttons.addWidget(button)
        cancel = QPushButton('Cancelar'); cancel.clicked.connect(self.cancel); buttons.addWidget(cancel)
        export = QPushButton('Exportar CSV + relatório'); export.clicked.connect(self.export); buttons.addWidget(export)
        layout.addLayout(buttons)
        self.plot = Plot('Campo físico','Pa' if kind=='acoustic' else '°C',x_title='Posição (m)')
        layout.addWidget(self.plot,2)
        self.spectral = Plot('Espectro unilateral','Pa',x_title='Frequência (Hz)')
        self.spectral.setVisible(kind=='acoustic'); layout.addWidget(self.spectral,2)
        self.report = QPlainTextEdit(); self.report.setReadOnly(True); layout.addWidget(self.report,1)

    def parameters(self):
        p = {k:float(v.text()) for k,v in self.fields.items()}
        if not all(math.isfinite(v) for v in p.values()): raise ValueError('Valores finitos obrigatórios.')
        return p

    def cancel(self):
        if self.job: self.job.token.cancel()

    def execute(self):
        if self.job: return
        try: p=self.parameters()
        except ValueError as error: self.note.setText(str(error)); return
        kind=self.kind
        def calculate(token):
            token.check()
            if kind=='conduction':
                result=heat_path(**p)
                x=[p['thickness']*i/100 for i in range(101)]
                y=[p['hot']+result['gradient_k_m']*v for v in x]
                fourier=-p['conductivity']*p['area']*result['gradient_k_m']
                convection=p['h']*p['area']*(result['surface_c']-p['cold'])
                text=('Condução 1D estacionária e convecção em série · SIMULATED\n'
                      'Fourier: Q=−kt A dT/dx; Rcond=d/(kt A). Newton: Q=hA(Ts−Ta); Rconv=1/(hA).\n'
                      'Conservação em regime estacionário: Q=(Tchip−Ta)/(Rcond+Rconv); T(x)=Tchip−Qx/(kt A).\n'
                      'Hipóteses: parede plana homogénea, temperatura linear, sem geração volumétrica, sem radiação, área constante.\n'
                      f'Verificação independente das duas leis: QFourier={fourier:g} W; Qconvecção={convection:g} W; resíduo={fourier-convection:.8g} W.\n'
                      'A temperatura da superfície difere da temperatura ambiente. Não somar Qcond e Qconv: é a mesma transferência.\n'
                      'Limitações: geometria real do dissipador e resistência de contacto não incluídas; h não é inferido de RPM.\n'+json.dumps(result,indent=2))
                return dict(x=x,y=y,parameters=p,origin='SIMULATED',report=text,x_unit='m',value_unit='°C',spectrum=None)
            frequencies=tonal_frequencies(p['rpm'],int(p['blades']))
            if p['blades']!=int(p['blades']): raise ValueError('Número de pás deve ser inteiro.')
            fs,n=p['sample_rate'],int(p['count'])
            if fs<=0 or p['count']!=n or not 8<=n<=65536 or n&(n-1): raise ValueError('Amostragem positiva e 8..65536 amostras em potência de dois.')
            f=frequencies['blade_passage_hz']
            x=[p['length']*i/400 for i in range(401)]
            args=dict(frequency=f,speed=p['speed'],amplitude=p['amplitude'],reflection=p['reflection'],length=p['length'],attenuation=p['attenuation'])
            y=[wave_field(v,0,**args) for v in x]
            t=[i/fs for i in range(n)]
            signal=[wave_field(p['length']/2,v,**args) for v in t]
            spec=spectrum(t,signal,expected_frequencies=list(frequencies.values()),token=token)
            text=('Onda acústica plana incidente + refletida · SIMULATED\n'
                  'p_tt=c² p_xx para α=0; p=A cos(ω(t−x/c))+rA cos(ω(t−(2L−x)/c)).\n'
                  'Hipóteses: propagação 1D linear em ar homogéneo, reflexão especificada em x=L. Interferência por sobreposição.\n'
                  'α>0 introduz fatores exp(−α distância): extensão fenomenológica com perdas, não solução da equação sem perdas.\n'
                  f'frot={frequencies["rotation_hz"]:g} Hz; fpassagem={f:g} Hz; λ={p["speed"]/f if f else "infinito"} m.\n'+spec.report+
                  '\nSem utilização do microfone. O sinal simulado usa apenas a componente de passagem de pás. Não é uma previsão calibrada do ruído do PC.')
            return dict(x=x,y=y,parameters=p,origin='SIMULATED',report=text,x_unit='m',value_unit='Pa',spectrum=spec.__dict__,time_s=t,signal_pa=signal)
        self.run.setEnabled(False)
        self.job=self.tasks.start(calculate,self.display,self.failed)

    def failed(self,error):
        self.job=None; self.run.setEnabled(True); self.note.setText(error)

    def display(self,result):
        self.job=None; self.run.setEnabled(True); self.result=result
        self.plot.x_axis.setTitleText('Tempo (s)' if result['x_unit']=='s' else 'Posição (m)')
        self.plot.update_series(result['x'],{result['origin']:result['y']})
        if result['spectrum']:
            spec=result['spectrum']; self.spectral.update_series(spec['frequencies'],{'Amplitude · Pa':spec['amplitudes']})
        self.report.setPlainText(result['report'])
        self.note.setText(result['origin'])

    def import_signal(self):
        if self.job: return
        path,_=QFileDialog.getOpenFileName(self,'Sinal local: time_s,value,unit (Pa)','','CSV (*.csv)')
        if not path: return
        def calculate(token):
            t,y=import_observations(path,'Pa',token)
            spec=spectrum(t,y,token=token)
            return dict(x=t,y=y,parameters={},origin='IMPORTED_UNVERIFIED',x_unit='s',value_unit='Pa',
                        spectrum=spec.__dict__,report='Sinal importado de origem não verificada; unidade declarada Pa, calibração não certificada.\n'+spec.report)
        self.run.setEnabled(False); self.job=self.tasks.start(calculate,self.display,self.failed)

    def export(self):
        if self.job or self.result is None: return
        directory=QFileDialog.getExistingDirectory(self,'Exportar campo físico')
        if not directory: return
        result,kind=self.result,self.kind
        def write(token):
            target=Path(directory)/kind
            target.with_suffix('.json').write_text(json.dumps(result,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
            target.with_suffix('.html').write_text('<!doctype html><meta charset="utf-8"><title>InProcess</title><pre style="white-space:pre-wrap">'+escape(result['report'])+'</pre>',encoding='utf-8')
            with open(target.with_suffix('.csv'),'w',encoding='utf-8',newline='') as stream:
                writer=csv.writer(stream); writer.writerow(['position_'+result['x_unit'],'value','unit','origin'])
                for x,y in zip(result['x'],result['y']): token.check(); writer.writerow([x,y,result['value_unit'],result['origin']])
            if result['spectrum']:
                with open(target.parent/(kind+'-spectrum.csv'),'w',encoding='utf-8',newline='') as stream:
                    writer=csv.writer(stream); writer.writerow(['frequency_hz','amplitude_pa'])
                    writer.writerows(zip(result['spectrum']['frequencies'],result['spectrum']['amplitudes']))
            return str(target)
        self.run.setEnabled(False); self.job=self.tasks.start(write,lambda path:self.failed('Exportado: '+path),self.failed)
