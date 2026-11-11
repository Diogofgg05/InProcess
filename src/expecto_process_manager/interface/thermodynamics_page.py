"""Pressure-volume analysis with explicit SI input and honest provenance."""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
                              QDoubleSpinBox, QSpinBox, QPushButton, QLabel,
                              QScrollArea, QFileDialog)

from .charts import Plot
from .workers import Tasks
from ..core.metrics import export_csv
from ..physics.thermodynamics import import_compression_csv, synthetic_compression


def _prepare(experiment, token):
    count = len(experiment.volumes)
    indices = sorted({int(i*(count-1)/min(1499, count-1)) for i in range(min(1500, count))})
    series = {"Dados": [experiment.pressures[i]/1000 for i in indices]}
    for name, values in (("Politrópica", experiment.fitted_pressures),
                         ("Isotérmica", experiment.isothermal_pressures),
                         ("Adiabática", experiment.adiabatic_pressures)):
        if values is not None:
            series[name] = [values[i]/1000 for i in indices]
    token.check()
    return experiment, ([experiment.volumes[i] for i in indices], series)


def _export(path, experiment, token):
    rows = []
    for i, (volume, pressure) in enumerate(zip(experiment.volumes, experiment.pressures)):
        if i % 256 == 0:
            token.check()
        rows.append({"volume_m3": volume, "pressure_pa": pressure,
                     "fit_pressure_pa": experiment.fitted_pressures[i] if experiment.fitted_pressures else "",
                     "provenance": experiment.provenance})
    export_csv(path, rows, token)


class ThermodynamicsPage(QWidget):
    def __init__(self, tasks=None):
        super().__init__()
        self.tasks = tasks or Tasks(self)
        self.job = self.experiment = self.result = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        title = QLabel("Termodinâmica · compressor")
        title.setObjectName("title")
        layout.addWidget(title)
        note = QLabel("Trabalho pressão-volume · ajuste politrópico · amostras preservadas na ordem original")
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
        self.samples = QSpinBox()
        self.samples.setRange(3, 100001)
        self.samples.setValue(101)
        form.addRow("Amostras sintéticas", self.samples)
        self.exponent = QDoubleSpinBox()
        self.exponent.setRange(.01, 3)
        self.exponent.setDecimals(3)
        self.exponent.setValue(1.3)
        form.addRow("Expoente sintético n", self.exponent)
        self.run = QPushButton("Gerar cenário simulado")
        self.run.setObjectName("primary")
        self.run.clicked.connect(self.execute)
        form.addRow(self.run)
        self.import_button = QPushButton("Importar CSV em SI")
        self.import_button.clicked.connect(self.open)
        form.addRow(self.import_button)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.cancel)
        form.addRow(cancel)
        export = QPushButton("Exportar resultados CSV")
        export.clicked.connect(self.export)
        form.addRow(export)
        explanation = QLabel("CSV: volume_m3,pressure_pa\nPressão absoluta em Pa; volume em m³. O gráfico usa kPa. A origem dos dados importados não é verificada.")
        explanation.setWordWrap(True)
        explanation.setObjectName("muted")
        form.addRow(explanation)
        self.results = QLabel("Gere um cenário sintético ou importe as suas amostras.")
        self.results.setWordWrap(True)
        form.addRow(self.results)
        body.addWidget(controls)
        self.pv = Plot("Diagrama pressão-volume", "Pressão (kPa)")
        self.pv.x_axis.setTitleText("Volume (m³)")
        self.plots = [self.pv]
        body.addWidget(self.pv, 1)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        self.summary = QLabel("W pelo gás = ∫p dV · W sobre o gás = −W pelo gás")
        self.summary.setWordWrap(True)
        self.summary.setObjectName("muted")
        layout.addWidget(self.summary)

    def config(self):
        return {"samples": self.samples.value(), "exponent": self.exponent.value()}

    def _start(self, function):
        if not self.run.isEnabled():
            return
        self.run.setEnabled(False)
        self.import_button.setEnabled(False)
        self.summary.setText("A validar amostras, calcular trabalho e ajustar referências…")
        self.job = self.tasks.start(lambda token: _prepare(function(token), token), self.display, self.calculation_failed)

    def execute(self):
        config = self.config()
        self._start(lambda token: synthetic_compression(**config, token=token))

    def open(self):
        if not self.run.isEnabled():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Importar pressão-volume", "", "CSV (*.csv)")
        if path:
            self._start(lambda token: import_compression_csv(path, token))

    def cancel(self):
        if self.job:
            self.job.token.cancel()

    def failed(self, message):
        self.summary.setText(message)

    def calculation_failed(self, message):
        self.job = None
        self.run.setEnabled(True)
        self.import_button.setEnabled(True)
        self.failed(message)

    def display(self, payload):
        self.experiment, preview = payload
        self.result = self.experiment
        self.job = None
        self.run.setEnabled(True)
        self.import_button.setEnabled(True)
        self.pv.update_series(*preview)
        experiment = self.experiment
        text = f"Pelo gás: {experiment.work_by_gas:.6g} J\nSobre o gás: {experiment.work_on_gas:.6g} J"
        text += f"\nSimpson: {experiment.simpson_work:.6g} J" if experiment.simpson_work is not None else "\nSimpson: condições não satisfeitas"
        if experiment.polytropic_index is not None:
            text += f"\nn ajustado: {experiment.polytropic_index:.5g}\nRMSE: {experiment.fit_rmse:.5g} Pa"
        else:
            text += "\nSem ajuste global para estes dados"
        self.results.setText(text)
        self.summary.setText(f"{experiment.provenance} · {len(experiment.volumes)} amostras · referências ideais com γ = {experiment.gamma:g}")

    def export(self):
        if self.experiment is None:
            self.failed("Gere ou importe primeiro uma experiência.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exportar análise de compressor", "compressor.csv", "CSV (*.csv)")
        if path:
            experiment = self.experiment
            self.tasks.start(lambda token: _export(path, experiment, token),
                             lambda _: self.summary.setText("Amostras e ajuste exportados em SI."), self.failed)

    def theme(self):
        self.pv.theme()
