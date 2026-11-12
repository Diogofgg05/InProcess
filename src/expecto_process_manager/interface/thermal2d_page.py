"""Interactive read-only thermal field viewer and Physics Lab 6.2 controls."""
import csv
import json
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QImage
from PySide6.QtWidgets import (
    QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLineEdit,QComboBox,
    QCheckBox,QLabel,QPushButton,QPlainTextEdit,QFileDialog,QSlider,
)
from .workers import Tasks
from ..physics.heat_2d import HeatPlate2D, solve_heat_2d, heat_2d_grid_study


class HeatMap2D(QWidget):
    """Paint simulation cell temperatures as a compact, resizeable color map.

    The QImage is generated in memory from SIMULATED numeric data only.
    81x81 cells maximum, nearest-neighbour scale, with no remote assets.
    """
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setMinimumSize(280,210)
        self.frame = ()
        self.min_temperature = 0.0
        self.max_temperature = 1.0
        self._image = QImage()

    def update_frame(self, frame, minimum, maximum):
        self.frame = tuple(tuple(row) for row in frame)
        self.min_temperature = float(minimum)
        self.max_temperature = float(maximum)
        if not self.frame:
            self._image=QImage()
            self.update()
            return
        nx=len(self.frame[0]); ny=len(self.frame)
        if any(len(row)!=nx for row in self.frame):
            raise ValueError("Mapa térmico irregular.")
        img=QImage(nx,ny,QImage.Format_RGB32)
        span=max(1e-12,self.max_temperature-self.min_temperature)
        for j,row in enumerate(self.frame):
            for i,temp in enumerate(row):
                ratio=max(0.0,min(1.0,(temp-self.min_temperature)/span))
                # Continuous perceptual-ish cold blue -> aqua -> gold -> orange.
                if ratio < .5:
                    t=ratio*2
                    rgb=(int(21+20*t),int(95+125*t),int(190-38*t))
                else:
                    t=(ratio-.5)*2
                    rgb=(int(41+210*t),int(220-104*t),int(152-108*t))
                img.setPixelColor(i,j,QColor(*rgb))
        self._image=img
        self.update()

    def paintEvent(self,event):
        super().paintEvent(event)
        painter=QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform,False)
        painter.fillRect(self.rect(),self.palette().base())
        if not self._image.isNull():
            size=self.size()
            margin=16
            w=max(1,size.width()-2*margin)
            h=max(1,size.height()-2*margin-20)
            scale=min(w/self._image.width(),h/self._image.height())
            draw_w=self._image.width()*scale
            draw_h=self._image.height()*scale
            target=QRectF((size.width()-draw_w)/2,
                          (size.height()-draw_h)/2-8,draw_w,draw_h)
            painter.drawImage(target,self._image)
        painter.end()


class Thermal2DPage(QWidget):
    def __init__(self,tasks=None):
        super().__init__()
        self.tasks=tasks or Tasks(self)
        self.job=None
        self.result=None
        self._model=None
        layout=QVBoxLayout(self)
        title=QLabel("Thermal Field 2D · InProcess 6.2")
        title.setObjectName("title")
        layout.addWidget(title)
        self.note=QLabel("SIMULATED · difusão 2D, dois materiais e fronteiras físicas. Sem sensores ou atuação no hardware.")
        self.note.setObjectName("muted")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        config=QFormLayout()
        self.width_m=QLineEdit("0.10")
        self.height_m=QLineEdit("0.08")
        self.nx=QLineEdit("25")
        self.ny=QLineEdit("21")
        self.matrix_k=QLineEdit("160")
        self.inclusion_k=QLineEdit("18")
        self.power=QLineEdit("6")
        self.duration=QLineEdit("6")
        self.convection=QLineEdit("25")
        self.boundary=QComboBox()
        self.boundary.addItem("Convecção (Robin)","convection")
        self.boundary.addItem("Temperatura fixa (Dirichlet)","dirichlet")
        self.boundary.addItem("Isolada (Neumann)","insulated")
        self.inclusion=QCheckBox("Incluir material central com condutividade diferente")
        self.inclusion.setChecked(True)
        for name,widget in [
            ("Comprimento X (m)",self.width_m),("Comprimento Y (m)",self.height_m),
            ("Células X",self.nx),("Células Y",self.ny),
            ("Condutividade da matriz (W/m·K)",self.matrix_k),
            ("Condutividade central (W/m·K)",self.inclusion_k),
            ("Fonte térmica total (W)",self.power),
            ("Convecção h (W/m²·K)",self.convection),
            ("Duração (s)",self.duration),
            ("Fronteira",self.boundary),("Materiais",self.inclusion)
        ]:
            config.addRow(name,widget)
        layout.addLayout(config)
        actions=QHBoxLayout()
        self.run=QPushButton("Simular campo térmico")
        self.run.setObjectName("primary")
        self.run.clicked.connect(self.execute)
        self.cancel_button=QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.cancel)
        self.export_button=QPushButton("Exportar JSON + CSV")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export)
        for widget in (self.run,self.cancel_button,self.export_button):
            actions.addWidget(widget)
        actions.addStretch()
        layout.addLayout(actions)
        self.heatmap=HeatMap2D()
        layout.addWidget(self.heatmap,2)
        time_controls=QHBoxLayout()
        self.frame_slider=QSlider(Qt.Horizontal)
        self.frame_slider.setRange(0,0)
        self.frame_slider.valueChanged.connect(self.update_display_frame)
        self.frame_label=QLabel("Sem resultados")
        time_controls.addWidget(self.frame_slider,1)
        time_controls.addWidget(self.frame_label)
        layout.addLayout(time_controls)
        self.report=QPlainTextEdit()
        self.report.setReadOnly(True)
        layout.addWidget(self.report,1)

    def parameters(self):
        try:
            nx=int(self.nx.text())
            ny=int(self.ny.text())
            if str(nx)!=self.nx.text().strip() or str(ny)!=self.ny.text().strip():
                raise ValueError("Os números de células devem ser inteiros.")
            model=HeatPlate2D(
                length_x_m=float(self.width_m.text()),
                length_y_m=float(self.height_m.text()),
                nx=nx,ny=ny,
                matrix_k_w_m_k=float(self.matrix_k.text()),
                inclusion_k_w_m_k=float(self.inclusion_k.text()),
                inclusion=self.inclusion.isChecked(),
                boundary=self.boundary.currentData(),
                convection_h_w_m2_k=float(self.convection.text()),
                source_w=float(self.power.text()),
            )
            duration=float(self.duration.text())
            if not 0 < duration <= 600:
                raise ValueError("Duração entre 0 e 600 segundos.")
            return model,duration
        except (ValueError,OverflowError) as exc:
            raise ValueError(f"Parâmetros térmicos 2D inválidos: {exc}") from exc

    def execute(self):
        if self.job:
            return
        try:
            model,duration=self.parameters()
        except ValueError as error:
            self.note.setText(str(error))
            return
        self.run.setEnabled(False)
        self.export_button.setEnabled(False)
        self.note.setText("A simular campo térmico 2D no trabalhador...")
        self._model=model
        def calculate(token):
            result=solve_heat_2d(model,duration_s=duration,token=token)
            return result
        self.job=self.tasks.start(calculate,self.display,self.failed)

    def display(self,result):
        self.job=None
        self.run.setEnabled(True)
        self.export_button.setEnabled(True)
        self.result=result
        self.frame_slider.setMaximum(len(result.times_s)-1)
        self.frame_slider.setValue(len(result.times_s)-1)
        self.update_display_frame(self.frame_slider.value())
        text=(
            "MODELO 2D · SIMULATED\n"
            f"Fronteira: {self._model.boundary}; material central: {self._model.inclusion}\n"
            f"Malha: {self._model.nx} × {self._model.ny}, dx={result.dx_m:.6g} m, dy={result.dy_m:.6g} m\n"
            f"Passo efetivo: {result.dt_s:.6g} s; limite conservativo: {result.conservative_limit_s:.6g} s\n"
            f"Fo_x={result.fourier_x:.6g}; Fo_y={result.fourier_y:.6g} (matriz homogénea como referência).\n"
            f"Temperaturas simuladas: mínimo {result.min_c:.4f} °C; máximo {result.max_c:.4f} °C\n"
            f"Energia interna: inicial {result.initial_j:.6g} J; final {result.final_j:.6g} J\n"
            f"Fonte total integrada {result.heat_input_j:.6g} J; perdas nas fronteiras {result.boundary_loss_j:.6g} J\n"
            f"Resíduo conservativo: {result.balance_residual_j:.6g} J\n"
            f"RMSE vs solução analítica: {result.rmse_exact_c if result.rmse_exact_c is not None else 'não aplicável à heterogeneidade/fonte/fronteira'}\n"
            "Estas grandezas não são medições reais do computador."
        )
        self.report.setPlainText(text)
        self.note.setText("SIMULATED · resultados verificados numericamente")

    def update_display_frame(self,index):
        if self.result is None:
            return
        idx=max(0,min(index,len(self.result.times_s)-1))
        frame=self.result.frames_c[idx]
        self.heatmap.update_frame(frame,self.result.min_c,self.result.max_c)
        self.frame_label.setText(f"t={self.result.times_s[idx]:.3f} s")

    def failed(self,message):
        self.job=None
        self.run.setEnabled(True)
        self.note.setText(str(message))

    def cancel(self):
        if self.job:
            self.job.token.cancel()

    def export(self):
        if self.job or self.result is None:
            return
        folder=QFileDialog.getExistingDirectory(self,"Exportar campo térmico 2D")
        if not folder:
            return
        path=Path(folder)
        result=self.result
        model=self._model
        def write(token):
            token.check()
            name="inprocess_thermal2d"
            (path/(name+".json")).write_text(
                json.dumps({"origin":"SIMULATED","model":asdict(model),"result":asdict(result)},
                           ensure_ascii=False,allow_nan=False,indent=2),encoding="utf-8"
            )
            with (path/(name+".csv")).open("w",encoding="utf-8",newline="") as f:
                writer=csv.writer(f)
                writer.writerow(["time_s","x_center_m","y_center_m","temperature_c","origin"])
                for t,frame in zip(result.times_s,result.frames_c):
                    token.check()
                    for j,row in enumerate(frame):
                        for i,temp in enumerate(row):
                            writer.writerow([t,(i+.5)*result.dx_m,(j+.5)*result.dy_m,temp,"SIMULATED"])
            return name
        self.job=self.tasks.start(write,self._exported,self.failed)

    def _exported(self,name):
        self.job=None
        self.note.setText(f"Exportação {name}: JSON e CSV guardados.")
