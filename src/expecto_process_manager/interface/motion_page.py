"""Compact AGV laboratory: calculations and bounded previews stay off the UI."""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
                              QDoubleSpinBox, QPushButton, QLabel, QGridLayout,
                              QScrollArea, QFileDialog)

from .charts import Plot
from .workers import Tasks
from ..core.metrics import export_csv
from ..physics.motion import MotionConfig, run_motion


def _calculate(config, token):
    experiment = run_motion(config, token)
    count = len(experiment.times)
    indices = sorted({int(i*(count-1)/min(1499, count-1)) for i in range(min(1500, count))})
    preview = {"times": [experiment.times[i] for i in indices]}
    for field in ("positions", "velocities", "accelerations"):
        preview[field] = {method: [getattr(trajectory, field)[i] for i in indices]
                          for method, trajectory in experiment.trajectories.items()}
        preview[field]["Analítica"] = [getattr(experiment.reference, field)[i] for i in indices]
    token.check()
    return experiment, preview


def _export(path, experiment, token):
    rows = []
    for method, trajectory in experiment.trajectories.items():
        for i, time in enumerate(experiment.times):
            if i % 256 == 0:
                token.check()
            rows.append({"method": method, "time_s": time,
                         "position_m": trajectory.positions[i], "velocity_m_s": trajectory.velocities[i],
                         "acceleration_m_s2": trajectory.accelerations[i], "provenance": "simulado"})
    export_csv(path, rows, token)


class MotionPage(QWidget):
    def __init__(self, tasks=None):
        super().__init__()
        self.tasks = tasks or Tasks(self)
        self.job = self.experiment = self.result = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        title = QLabel("Movimento e travagem · AGV")
        title.setObjectName("title")
        layout.addWidget(title)
        note = QLabel("Simulação independente · Euler, Heun e RK4 · sem deslocamento após a paragem")
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        body = QHBoxLayout(content)
        controls = QWidget()
        controls.setMaximumWidth(340)
        form = QFormLayout(controls)
        self.fields = {}
        for name, label, value, low, high, decimals in [
                ("position", "Posição inicial (m)", 0, -1e7, 1e7, 3),
                ("velocity", "Velocidade inicial (m/s)", 10, 0, 1e4, 3),
                ("acceleration", "Aceleração (m/s²)", 0, 0, 1e4, 3),
                ("deceleration", "Desaceleração (m/s²)", 2, 0, 1e4, 3),
                ("friction", "Atrito linear (s⁻¹)", 0, 0, 1e3, 5),
                ("duration", "Duração (s)", 10, .001, 1e6, 3),
                ("dt", "Passo Δt (s)", .1, .000001, 1e4, 6)]:
            field = QDoubleSpinBox()
            field.setDecimals(decimals)
            field.setRange(low, high)
            field.setValue(value)
            self.fields[name] = field
            form.addRow(label, field)
        self.fields["friction"].setToolTip("Aceleração de arrasto = −c·v. Coeficiente linear em s⁻¹; exige Δt·c ≤ 1.")
        self.run = QPushButton("Comparar métodos")
        self.run.setObjectName("primary")
        self.run.clicked.connect(self.execute)
        form.addRow(self.run)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.cancel)
        form.addRow(cancel)
        export = QPushButton("Exportar CSV")
        export.clicked.connect(self.export)
        form.addRow(export)
        explanation = QLabel("Modelo retilíneo com aceleração e travagem constantes. O atrito reduz a velocidade proporcionalmente ao seu valor.")
        explanation.setWordWrap(True)
        explanation.setObjectName("muted")
        form.addRow(explanation)
        self.results = QLabel("Execute uma comparação para obter a distância e o tempo de paragem.")
        self.results.setWordWrap(True)
        form.addRow(self.results)
        body.addWidget(controls)
        charts = QGridLayout()
        self.position_plot = Plot("Posição", "m")
        self.velocity_plot = Plot("Velocidade", "m/s")
        self.acceleration_plot = Plot("Aceleração", "m/s²")
        self.plots = [self.position_plot, self.velocity_plot, self.acceleration_plot]
        for i, plot in enumerate(self.plots):
            charts.addWidget(plot, i//2, i%2)
        body.addLayout(charts, 1)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        self.summary = QLabel("Parâmetros e resultados em unidades SI · dados simulados")
        self.summary.setObjectName("muted")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

    def config(self):
        return MotionConfig(**{name: field.value() for name, field in self.fields.items()})

    def execute(self):
        if not self.run.isEnabled():
            return
        try:
            config = self.config()
        except (ValueError, TypeError) as error:
            self.failed(str(error))
            return
        self.run.setEnabled(False)
        self.summary.setText("A calcular movimento e localizar a paragem…")
        self.job = self.tasks.start(lambda token: _calculate(config, token), self.display, self.calculation_failed)

    def cancel(self):
        if self.job:
            self.job.token.cancel()

    def failed(self, message):
        self.summary.setText(message)

    def calculation_failed(self, message):
        self.job = None
        self.run.setEnabled(True)
        self.failed(message)

    def display(self, payload):
        self.experiment, preview = payload
        self.result = self.experiment
        self.run.setEnabled(True)
        self.job = None
        for plot, field in zip(self.plots, ("positions", "velocities", "accelerations")):
            plot.update_series(preview["times"], preview[field])
        reference = self.experiment.reference
        if reference.stopping_time is not None:
            text = f"Referência: {reference.stopping_time:.4g} s · {reference.stopping_distance:.5g} m"
            for method, trajectory in self.experiment.trajectories.items():
                if trajectory.stopping_distance is not None:
                    text += f"\n{method}: {trajectory.stopping_distance:.5g} m"
            self.results.setText(text)
        else:
            self.results.setText("Não ocorre uma paragem finita durante a duração escolhida.")
        self.summary.setText(f"Simulado · {len(self.experiment.times)-1} intervalos · Δt = {self.experiment.config.dt:g} s · referência analítica independente")

    def export(self):
        if self.experiment is None:
            self.failed("Execute primeiro uma simulação.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exportar movimento", "agv.csv", "CSV (*.csv)")
        if path:
            experiment = self.experiment
            self.tasks.start(lambda token: _export(path, experiment, token),
                             lambda _: self.summary.setText("Trajetórias completas exportadas em SI."), self.failed)

    def theme(self):
        for plot in self.plots:
            plot.theme()
