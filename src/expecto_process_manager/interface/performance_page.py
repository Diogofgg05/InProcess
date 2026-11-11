from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QGridLayout
from .charts import Plot


class PerformancePage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.summary = QLabel("A aguardar a primeira amostra…")
        self.summary.setWordWrap(True)
        self.summary.hide()
        self.cores = QLabel()
        self.cores.setWordWrap(True)
        self.cores.hide()
        grid = QGridLayout()
        self.plots = [Plot("CPU medida","%"),Plot("Memória medida","%"),
                      Plot("Disco · leitura + escrita","MiB/s"),Plot("Rede · envio + receção","MiB/s")]
        for i,plot in enumerate(self.plots):
            grid.addWidget(plot,i//2,i%2)
        layout.addLayout(grid)

    def refresh(self,history):
        s = history[-1]
        sensor = f"{s.temperature_c:.1f} °C" if s.temperature_c is not None else "indisponível"
        cpu = 'aquecimento' if s.cpu is None else f'{s.cpu:.1f}%'
        swap = 'indisponível' if s.swap_used is None else f'{s.swap_used/1024**3:.2f} GiB'
        self.summary.setText(f"CPU {cpu}  |  RAM {s.memory_used/1024**3:.2f} GiB  |  Disponível {s.memory_available/1024**3:.2f} GiB  |  Swap {swap}  |  Sensor CPU: {sensor} | GPU: indisponível")
        ages = []
        for label,key in [('Swap','swap_age_s'),('Temperatura','temperature_age_s'),('Frequência','frequency_age_s')]:
            age = getattr(s,key,None)
            ages.append(f'{label}: indisponível' if age is None else f'{label}: medido há {age:.2f} s')
        self.summary.setToolTip('\n'.join(ages)+'\nSensores auxiliares são atualizados a cada 2 s.')
        self.cores.setText("Núcleos lógicos: " + " · ".join(f"{i}: {v:.0f}%" for i,v in enumerate(s.cores)))
        self.plots[0].setToolTip(self.cores.text())
        self.plots[1].setToolTip(self.summary.text()+'\n'+self.summary.toolTip())
        times = [r.timestamp-history[0].timestamp for r in history]
        for plot,key,scale in zip(self.plots,["cpu","memory_percent","disk_bytes_s","network_bytes_s"],[1,1,1024**2,1024**2]):
            valid = [(t,getattr(r,key)/scale) for t,r in zip(times,history) if getattr(r,key) is not None]
            plot.update_series([t for t,v in valid],{"Medido":[v for t,v in valid]})
