"""InProcess 7.0 — Scientific thermal twin, with cautious provenance.

The app never claims that CSV values are calibrated physical measurements.
The baseline, holdout, uncertainty proxy and extrapolation boundaries are
visible and exported with every result. No OS or device is controlled.
"""
import csv
import json
from dataclasses import asdict
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,QPushButton,
    QPlainTextEdit,QFileDialog,QComboBox,
)
from .workers import Tasks
from .charts import Plot
from ..physics.digital_twin7 import (
    load_thermal_csv,synthetic_thermal_series,calibrate_twin,forecast_scenario
)


class ThermalTwin7Page(QWidget):
    def __init__(self,tasks=None):
        super().__init__()
        self.tasks=tasks or Tasks(self)
        self.job=None
        self.series=None
        self.analysis=None
        self.future=None
        layout=QVBoxLayout(self)
        title=QLabel("InProcess 7.0 · Thermal Digital Twin")
        title.setObjectName("title")
        layout.addWidget(title)
        self.note=QLabel(
            "SIMULATED por defeito · os CSV são MEASURED_UNVERIFIED. "
            "Nenhuma potência, temperatura ou ventilação é inferida de CPU%."
        )
        self.note.setObjectName("muted")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.source=QComboBox()
        self.source.addItem("Experiência sintética reproduzível","synthetic")
        self.source.addItem("Carregar CSV com dados declarados como medidos","csv")
        layout.addWidget(self.source)
        self.csv_path=QLineEdit()
        self.csv_path.setPlaceholderText("CSV: time_s,cpu_temp_c,ambient_c,power_w")
        self.choose=QPushButton("Selecionar CSV")
        self.choose.clicked.connect(self.choose_csv)
        row=QHBoxLayout()
        row.addWidget(self.csv_path,1)
        row.addWidget(self.choose)
        layout.addLayout(row)
        form=QFormLayout()
        self.train_fraction=QLineEdit("0.70")
        self.prediction_power=QLineEdit("60")
        self.prediction_ambient=QLineEdit("24")
        self.horizon=QLineEdit("120")
        form.addRow("Fração de treino temporal (0,55–0,85)",self.train_fraction)
        form.addRow("Potência térmica hipotética (W)",self.prediction_power)
        form.addRow("Ambiente hipotético (°C)",self.prediction_ambient)
        form.addRow("Horizonte de previsão (s)",self.horizon)
        layout.addLayout(form)
        actions=QHBoxLayout()
        self.run=QPushButton("Calibrar e validar")
        self.run.setObjectName("primary")
        self.run.clicked.connect(self.execute)
        self.cancel_button=QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.cancel)
        self.export_button=QPushButton("Exportar JSON + CSV")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export)
        actions.addWidget(self.run)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.export_button)
        actions.addStretch()
        layout.addLayout(actions)
        self.plot=Plot("Treino separado · validação temporal", "Temperatura (°C)",x_title="Tempo (s)")
        layout.addWidget(self.plot,2)
        self.report=QPlainTextEdit()
        self.report.setReadOnly(True)
        layout.addWidget(self.report,1)

    def choose_csv(self):
        filename,_=QFileDialog.getOpenFileName(self,"Dados experimentais CSV","","CSV (*.csv)")
        if filename:
            self.csv_path.setText(filename)
            self.source.setCurrentIndex(self.source.findData("csv"))

    def _inputs(self):
        try:
            fraction=float(self.train_fraction.text())
            power=float(self.prediction_power.text())
            ambient=float(self.prediction_ambient.text())
            horizon=float(self.horizon.text())
        except ValueError as exc:
            raise ValueError("Parâmetros de calibração/previsão inválidos.") from exc
        return fraction,power,ambient,horizon

    def execute(self):
        if self.job:
            return
        try:
            inputs=self._inputs()
            source=self.source.currentData()
            path=self.csv_path.text().strip()
            if source=="csv" and not path:
                raise ValueError("Selecione um CSV com unidades explícitas.")
        except ValueError as error:
            self.note.setText(str(error))
            return
        self.run.setEnabled(False)
        self.export_button.setEnabled(False)
        self.note.setText("A identificar parâmetros e testar as previsões no trabalhador...")
        def calculate(token):
            series=(load_thermal_csv(path) if source=="csv" else synthetic_thermal_series())
            result=calibrate_twin(series,train_fraction=inputs[0],token=token)
            future=None
            warning=None
            try:
                future=forecast_scenario(series,result,power_w=inputs[1],
                                         ambient_c=inputs[2],horizon_s=inputs[3])
            except ValueError as exc:
                warning=f"Previsão hipotética não disponível: {exc}"
            return series,result,future,warning
        self.job=self.tasks.start(calculate,self.display,self.failed)

    def display(self,payload):
        self.job=None
        self.series,self.analysis,self.future,warning=payload
        self.run.setEnabled(True)
        self.export_button.setEnabled(True)
        m=self.analysis.model
        v=self.analysis.validation
        self.plot.update_series(self.analysis.validation_times_s,{
            "Temperatura observada (°C)":list(self.analysis.validation_measured_c),
            "Previsão sem correção (°C)":list(self.analysis.validation_predicted_c),
        })
        self.note.setText(
            f"Origem: {self.analysis.origin} · previsão em holdout; "
            "não equivale a validação física de sensores."
        )
        lines=[
            "INPROCESS 7.0 · CALIBRAÇÃO DO GÉMEO DIGITAL TÉRMICO",
            f"Origem de dados: {self.analysis.origin}",
            f"Treino (amostras): {self.analysis.train_points}; validação (previsões): {v.points}",
            f"Resistência térmica estimada: {m.resistance_k_w:.6g} K/W",
            f"Capacidade térmica estimada: {m.capacity_j_k:.6g} J/K",
            f"Constante de tempo: {m.tau_s:.6g} s",
            f"RMSE validação: {v.rmse_c:.6g} °C",
            f"MAE validação: {v.mae_c:.6g} °C; viés: {v.bias_c:.6g} °C",
            f"RMSE persistência: {v.persistence_rmse_c:.6g} °C",
            f"Skill relativa à persistência: {v.skill_vs_persistence}",
            f"R² no holdout: {v.r_squared}",
            f"P90 EMPÍRICO de |erro|: {v.observed_abs_error_p90_c:.6g} °C",
            "Este quantil não é um intervalo de confiança/predição calibrado.",
        ]
        if self.future is not None:
            lines.append(
                f"Cenário constante: {len(self.future[0])-1} passos; "
                f"temperatura final hipotética {self.future[1][-1]:.4f} °C."
            )
        if warning:
            lines.append(warning)
        lines.extend(self.analysis.interpretation)
        self.report.setPlainText("\n".join(lines))

    def failed(self,message):
        self.job=None
        self.run.setEnabled(True)
        self.note.setText(str(message))

    def cancel(self):
        if self.job:
            self.job.token.cancel()

    def export(self):
        if self.job or self.analysis is None:
            return
        target=QFileDialog.getExistingDirectory(self,"Exportar validação do Digital Twin")
        if not target:
            return
        out=Path(target)
        analysis=self.analysis
        future=self.future
        def save(token):
            token.check()
            (out/"inprocess_twin7.json").write_text(
                json.dumps({"report":asdict(analysis),
                            "future_scenario":future,
                            "note":"A origem do CSV não demonstra calibração dos sensores."},
                           ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8"
            )
            with (out/"inprocess_twin7_validation.csv").open("w",newline="",encoding="utf-8") as f:
                writer=csv.writer(f)
                writer.writerow(["time_s","measured_c","predicted_c","origin"])
                for t,actual,pred in zip(analysis.validation_times_s,
                                         analysis.validation_measured_c,
                                         analysis.validation_predicted_c):
                    token.check()
                    writer.writerow([t,actual,pred,analysis.origin])
            return True
        self.job=self.tasks.start(save,self._exported,self.failed)

    def _exported(self,*_):
        self.job=None
        self.note.setText("Exportação concluída: validação CSV + modelo JSON.")
