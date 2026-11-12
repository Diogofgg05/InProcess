"""InProcess 6.3 Advanced Control Laboratory — read-only P/PI/PID comparison."""
import csv
import json
from dataclasses import asdict
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,QPushButton,
    QPlainTextEdit,QFileDialog,
)
from .workers import Tasks
from .charts import Plot
from ..physics.control_lab63 import ControlScenario,compare_controllers,gain_sensitivity


class ControlLab63Page(QWidget):
    def __init__(self,tasks=None):
        super().__init__()
        self.tasks=tasks or Tasks(self)
        self.job=None
        self.results=None
        self.scenario=None
        self.sensitivity=None
        layout=QVBoxLayout(self)
        header=QLabel("InProcess 6.3 · Advanced Control Laboratory")
        header.setObjectName("title")
        layout.addWidget(header)
        self.note=QLabel("SIMULATED · PID com derivada filtrada, anti-windup e perturbações. "
                         "Sem atuação em ventoinhas reais.")
        self.note.setWordWrap(True)
        self.note.setObjectName("muted")
        layout.addWidget(self.note)
        form=QFormLayout()
        self.target=QLineEdit("47")
        self.base_power=QLineEdit("55")
        self.disturbance=QLineEdit("35")
        self.start=QLineEdit("100")
        self.end=QLineEdit("180")
        self.duration=QLineEdit("300")
        self.kp=QLineEdit("0.06")
        self.ki=QLineEdit("0.0015")
        self.kd=QLineEdit("0.15")
        self.noise=QLineEdit("0")
        for text,widget in [
            ("Temperatura alvo (°C)",self.target),
            ("Potência de base (W)",self.base_power),
            ("Perturbação térmica (W)",self.disturbance),
            ("Início da perturbação (s)",self.start),
            ("Fim da perturbação (s)",self.end),
            ("Duração (s)",self.duration),
            ("Ganho P (1/°C)",self.kp),
            ("Ganho I (1/(°C·s))",self.ki),
            ("Ganho D (s/°C)",self.kd),
            ("Ruído determinístico (°C)",self.noise),
        ]:
            form.addRow(text,widget)
        layout.addLayout(form)
        controls=QHBoxLayout()
        self.run=QPushButton("Comparar P / PI / PID")
        self.run.setObjectName("primary")
        self.run.clicked.connect(self.execute)
        self.cancel_button=QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.cancel)
        self.export_button=QPushButton("Exportar JSON + CSV")
        self.export_button.clicked.connect(self.export)
        self.export_button.setEnabled(False)
        for widget in (self.run,self.cancel_button,self.export_button):
            controls.addWidget(widget)
        controls.addStretch()
        layout.addLayout(controls)
        self.plot=Plot("Resposta térmica CPU", "Temperatura (°C)",x_title="Tempo (s)")
        layout.addWidget(self.plot,2)
        self.report=QPlainTextEdit()
        self.report.setReadOnly(True)
        layout.addWidget(self.report,1)

    def read_scenario(self):
        try:
            return ControlScenario(
                target_c=float(self.target.text()),
                base_power_w=float(self.base_power.text()),
                disturbance_w=float(self.disturbance.text()),
                disturbance_at_s=float(self.start.text()),
                disturbance_end_s=float(self.end.text()),
                duration_s=float(self.duration.text()),
                proportional_per_k=float(self.kp.text()),
                integral_per_k_s=float(self.ki.text()),
                derivative_s_per_k=float(self.kd.text()),
                sensor_noise_amplitude_c=float(self.noise.text()),
            )
        except (ValueError,OverflowError) as error:
            raise ValueError(f"Parâmetros de controlo inválidos: {error}") from error

    def execute(self):
        if self.job:return
        try:
            scenario=self.read_scenario()
        except ValueError as error:
            self.note.setText(str(error))
            return
        self.run.setEnabled(False)
        self.export_button.setEnabled(False)
        self.note.setText("A calcular as três respostas no trabalhador...")
        def calculate(token):
            outputs=compare_controllers(scenario,token)
            sensitivity=gain_sensitivity(scenario,token)
            return (scenario,outputs,sensitivity)
        self.job=self.tasks.start(calculate,self.display,self.failed)

    def display(self,payload):
        self.job=None
        self.scenario,self.results,self.sensitivity=payload
        self.run.setEnabled(True)
        self.export_button.setEnabled(True)
        self.note.setText("SIMULATED · comportamento observado numa janela finita; "
                          "não constitui prova de estabilidade.")
        times=self.results["P"].times_s
        self.plot.update_series(times,{name:list(data.die_c) for name,data in self.results.items()})
        lines=[
            "INPROCESS 6.3 · COMPARAÇÃO DE CONTROLORES",
            "Fonte: SIMULATED; nenhuma potência de ventoinha foi medida.",
            f"Perturbação: +{self.scenario.disturbance_w:g} W entre "
            f"{self.scenario.disturbance_at_s:g} e {self.scenario.disturbance_end_s:g} s",
            "Método: P, PI, PID (derivada na medição filtrada) + anti-windup.",
            "A estabilidade é avaliada só em janela finita, não por autovalores.",
        ]
        for name,trace in self.results.items():
            m=trace.metrics
            settle=("não observado" if m.observed_settling_s is None
                    else f"{m.observed_settling_s:.2f} s")
            lines.append(f"{name}: pico={m.peak_die_c:.3f} °C; erro final="
                         f"{m.final_abs_error_c:.3f} °C; IAE={m.iae_c_s:.3f} °C·s; "
                         f"ITAE={m.itae_c_s2:.3f} °C·s²; fan médio={m.fan_mean_fraction:.3f}; "
                         f"saturação={100*m.saturated_fraction:.1f}%; "
                         f"acomodação observada={settle}; "
                         f"resíduo energético={m.energy_balance_residual_j:.5g} J")
        lines.append("Sensibilidade dos ganhos PID:")
        lines.extend(f"×{r['gain_factor']:.2f}: IAE={r['iae_c_s']:.3f}, "
                     f"pico={r['peak_c']:.3f} °C" for r in self.sensitivity)
        lines.append("Uma fração da ventoinha não é uma medição de potência elétrica.")
        self.report.setPlainText("\n".join(lines))

    def failed(self,message):
        self.job=None
        self.run.setEnabled(True)
        self.note.setText(str(message))

    def cancel(self):
        if self.job:self.job.token.cancel()

    def export(self):
        if self.job or self.results is None:return
        folder=QFileDialog.getExistingDirectory(self,"Exportar estudo PID 6.3")
        if not folder:return
        path=Path(folder)
        scenario=self.scenario
        results=self.results
        sensitivity=self.sensitivity
        def write(token):
            token.check()
            (path/"inprocess_control63.json").write_text(
                json.dumps({"origin":"SIMULATED","scenario":asdict(scenario),
                            "metrics":{name:asdict(trace.metrics) for name,trace in results.items()},
                            "gain_sensitivity":sensitivity},ensure_ascii=False,allow_nan=False,indent=2),
                encoding="utf-8"
            )
            with (path/"inprocess_control63.csv").open("w",newline="",encoding="utf-8") as stream:
                writer=csv.writer(stream)
                writer.writerow(["time_s","cpu_P_c","cpu_PI_c","cpu_PID_c",
                                 "fan_P","fan_PI","fan_PID","heat_input_w","origin"])
                for index,time in enumerate(results["P"].times_s):
                    token.check()
                    writer.writerow([time,*[results[name].die_c[index] for name in ("P","PI","PID")],
                                     *[results[name].fan_fraction[index] for name in ("P","PI","PID")],
                                     results["P"].power_w[index],"SIMULATED"])
            return True
        self.job=self.tasks.start(write,self._exported,self.failed)

    def _exported(self,*_):
        self.job=None
        self.note.setText("Exportação concluída: inprocess_control63.csv e .json")
