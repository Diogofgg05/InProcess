"""Thermal parameter identification with short results and asynchronous work."""
import csv
import math
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from .charts import Plot
from .workers import Tasks
from ..core.metrics import export_csv
from ..physics.calibration import MAX_SAMPLES, ThermalSeries, fit_thermal, predict_zoh
from ..physics.numerical.signals import add_gaussian_noise


def import_thermal_csv(path, token) -> ThermalSeries:
    """Only units declared by this schema; the origin is not sensor-verified."""
    if Path(path).stat().st_size > 10 * 1024 * 1024:
        raise ValueError("CSV demasiado grande: máximo 10 MiB.")
    times, temperatures, powers = [], [], []
    with open(path, encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        required = {"time_s", "temperature_c", "power_w"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames) or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError("CSV requer colunas time_s, temperature_c e power_w, sem nomes repetidos.")
        try:
            for index, row in enumerate(reader):
                if index % 256 == 0:
                    token.check()
                if index >= MAX_SAMPLES or None in row:
                    raise ValueError("CSV excede 20000 amostras ou contém colunas sem cabeçalho.")
                if row.get("time_unit", "s") != "s" or row.get("temperature_unit", "°C") not in ("°C", "C") or row.get("power_unit", "W") != "W":
                    raise ValueError("Unidades suportadas: tempo s, temperatura °C e potência W.")
                try:
                    t, temperature, power = (float(row[name]) for name in ("time_s", "temperature_c", "power_w"))
                except (ValueError, TypeError) as error:
                    raise ValueError(f"Valores numéricos inválidos na linha {index + 2}.") from error
                if not all(math.isfinite(value) for value in (t, temperature, power)) or power < 0:
                    raise ValueError(f"A linha {index + 2} requer valores finitos e potência não negativa.")
                if times and (t <= times[-1] or not math.isfinite(t - times[-1])):
                    raise ValueError("Os tempos do CSV devem ser estritamente crescentes, em segundos.")
                times.append(t)
                temperatures.append(temperature)
                powers.append(power)
        except csv.Error as error:
            raise ValueError(f"CSV malformado: {error}") from error
    if len(times) < 12:
        raise ValueError("A calibração requer pelo menos 12 amostras para treino e validação disjuntos.")
    token.check()
    return ThermalSeries(times, temperatures, powers)


def calculate_calibration(parameters, imported, token):
    """Capture all metadata with the result, independent of subsequent UI edits."""
    if imported is None:
        duration, step = parameters["duration"], parameters["dt"]
        count = math.ceil(duration / step)
        if count + 1 > MAX_SAMPLES:
            raise ValueError("A demonstração excede o limite de 20000 amostras; aumente o passo.")
        times = [min(index * step, duration) for index in range(count + 1)]
        # Four known plateaux supply heating/cooling excitation, not CPU load.
        powers = [[15., 70., 30., 60.][min(3, int(4 * time / duration))] for time in times]
        clean = predict_zoh(times, powers, parameters["initial"], parameters["ambient"], parameters["capacity"], parameters["dissipation"])
        observations = add_gaussian_noise(clean, parameters["noise"], parameters["seed"])
        source = ThermalSeries(times, observations, powers)
        provenance = "SIMULATED"
        declaration = "Dados sintéticos com parâmetros e semente conhecidos."
    else:
        source, filename, declaration = imported
        provenance = "CSV · origem declarada, não verificada"
        clean = None
    token.check()
    result = fit_thermal(source.times, source.temperatures, source.powers, parameters["ambient"], method=parameters["method"], token=token)
    context = {
        "provenance": provenance,
        "origin_declaration": declaration,
        "parameters": dict(parameters),
        "ambient_c": parameters["ambient"],
        "times": list(source.times),
        "powers": list(source.powers),
        "observed_temperatures": list(source.temperatures),
        "units": {"time": "s", "temperature": "°C", "power": "W", "capacity": "J/K", "dissipation": "W/K"},
        "power_interpolation": "zero-order hold (left sample)",
        "initial_condition_supplied": True,
    }
    if imported is None:
        context["synthetic_reference"] = clean
        context["known_capacity"] = parameters["capacity"]
        context["known_dissipation"] = parameters["dissipation"]
    else:
        context["filename"] = filename
    return result, context


class CalibrationPage(QWidget):
    result_ready = Signal(object)

    def __init__(self, tasks=None):
        super().__init__()
        self.tasks = tasks or Tasks(self)
        self.job = None
        self.result = self.experiment = None
        self.result_context = {}
        self.imported = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        title = QLabel("Calibração térmica · ajuste e validação")
        title.setObjectName("title")
        layout.addWidget(title)
        note = QLabel("Estime C e k com dados excitados e validação temporal separada. A origem de CSV é declarada pelo utilizador.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        layout.addWidget(note)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        body = QHBoxLayout(content)
        controls = QWidget()
        controls.setMaximumWidth(360)
        controls.setMinimumWidth(270)
        form = QFormLayout(controls)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.source = QComboBox()
        self.source.addItems(["SIMULATED · demonstração", "CSV · dados importados"])
        self.source.currentIndexChanged.connect(self.source_changed)
        form.addRow("Origem", self.source)
        self.import_button = QPushButton("Importar CSV térmico")
        self.import_button.setToolTip("Colunas obrigatórias: time_s, temperature_c, power_w. A importação não verifica sensores.")
        self.import_button.clicked.connect(self.import_data)
        form.addRow(self.import_button)
        self.declaration = QComboBox()
        self.declaration.addItems(["Origem não verificada", "MEASURED · declarado", "SIMULATED · declarado", "ESTIMATED · declarado"])
        self.declaration.setToolTip("A declaração não certifica instrumentação, calibração ou origem do ficheiro.")
        form.addRow("Declaração CSV", self.declaration)
        self.fields = {}
        for name, label, value, low, high, decimals in [
            ("ambient", "Ambiente Ta (°C)", 22, -50, 100, 2),
            ("initial", "T inicial sintética (°C)", 35, -50, 200, 2),
            ("capacity", "C sintética (J/K)", 100, .01, 100000, 3),
            ("dissipation", "k sintético (W/K)", 2, .001, 1000, 4),
            ("duration", "Duração sintética (s)", 120, 1, 100000, 2),
            ("dt", "Amostragem sintética (s)", .5, .001, 1000, 3),
            ("noise", "Ruído sintético σ (°C)", .05, 0, 10, 3),
        ]:
            field = QDoubleSpinBox()
            field.setDecimals(decimals)
            field.setRange(low, high)
            field.setValue(value)
            self.fields[name] = field
            form.addRow(label, field)
        self.seed = QSpinBox()
        self.seed.setRange(0, 2147483647)
        self.seed.setValue(42)
        form.addRow("Semente sintética", self.seed)
        self.method = QComboBox()
        self.method.addItem("Exato por intervalo · ZOH", "integral_zoh")
        self.method.addItem("Regressão da derivada", "derivative")
        self.method.setToolTip("ZOH assume potência constante entre amostras. A regressão da derivada amplifica ruído e pode ter viés.")
        form.addRow("Ajuste", self.method)
        self.run = QPushButton("Ajustar e validar")
        self.run.setObjectName("primary")
        self.run.clicked.connect(self.execute)
        form.addRow(self.run)
        self.cancel_button = QPushButton("Cancelar cálculo")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel)
        form.addRow(self.cancel_button)
        self.export_button = QPushButton("Exportar previsões CSV")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export)
        form.addRow(self.export_button)
        body.addWidget(controls, 1)
        grid = QGridLayout()
        self.plots = [Plot("Treino · observado e previsão", "Temperatura (°C)"),
                      Plot("Validação · dados reservados", "Temperatura (°C)"),
                      Plot("Resíduos · observado menos previsto", "Resíduo (°C)"),
                      Plot("Potência de entrada · amostras", "Potência térmica (W)")]
        for index, plot in enumerate(self.plots):
            grid.addWidget(plot, index // 2, index % 2)
        body.addLayout(grid, 3)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        self.summary = QLabel("Demonstração: quatro níveis de potência térmica, 120 s, semente 42. Os últimos 30% ficam reservados para validação.")
        self.summary.setWordWrap(True)
        self.summary.setObjectName("muted")
        layout.addWidget(self.summary)
        self.source_changed()

    def source_changed(self, _index=None):
        synthetic = self.source.currentIndex() == 0
        for name, field in self.fields.items():
            if name != "ambient":
                field.setEnabled(synthetic)
        self.seed.setEnabled(synthetic)
        self.declaration.setEnabled(not synthetic)

    def _busy(self, busy):
        self.run.setEnabled(not busy)
        self.import_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)

    def execute(self):
        if not self.run.isEnabled():
            return
        if self.source.currentIndex() == 1 and self.imported is None:
            self.summary.setText("Importe um CSV com time_s, temperature_c e power_w para continuar.")
            return
        parameters = {name: field.value() for name, field in self.fields.items()}
        parameters.update(seed=self.seed.value(), method=self.method.currentData())
        imported = None
        if self.source.currentIndex() == 1:
            data, filename = self.imported
            imported = data, filename, self.declaration.currentText() + "; origem não verificada"
        self._busy(True)
        self.summary.setText("A ajustar parâmetros e avaliar dados reservados em segundo plano…")
        self.job = self.tasks.start(lambda token: calculate_calibration(parameters, imported, token), self.display, self.failed)

    def display(self, payload):
        self._busy(False)
        self.job = None
        self.result, self.result_context = payload
        self.experiment = self.result
        train, holdout = self.result.training, self.result.validation
        self.plots[0].update_series(train.times, {"Temperatura observada · treino": train.observed, "Previsão ajustada · treino": train.predicted})
        self.plots[1].update_series(holdout.times, {"Temperatura observada · validação": holdout.observed, "Previsão sem reajuste · validação": holdout.predicted})
        times = train.times + holdout.times
        self.plots[2].update_series(times, {"Resíduo no treino": train.residuals + [None] * len(holdout.times),
                                          "Resíduo na validação": [None] * len(train.times) + holdout.residuals})
        self.plots[3].update_series(self.result_context["times"], {"Potência térmica declarada": self.result_context["powers"]})
        r = self.result
        self.summary.setText(f"ESTIMATED · C={r.capacity:.4g} J/K · k={r.dissipation:.4g} W/K · τ={r.time_constant:.4g} s\n"
                             f"RMSE treino {train.errors['rmse']:.4g} °C · validação {holdout.errors['rmse']:.4g} °C · origem {self.result_context['provenance']}.")
        self.export_button.setEnabled(True)
        self.result_ready.emit(self.result)

    def failed(self, message):
        self._busy(False)
        self.job = None
        self.summary.setText(message)

    def cancel(self):
        if self.job is not None:
            self.job.token.cancel()

    def import_data(self):
        path, _ = QFileDialog.getOpenFileName(self, "Importar dados térmicos", "", "CSV (*.csv)")
        if path:
            self._busy(True)
            self.summary.setText("A validar unidades, tempos e amostras do CSV…")
            self.job = self.tasks.start(lambda token: (import_thermal_csv(path, token), Path(path).name), self.csv_loaded, self.failed)

    def csv_loaded(self, payload):
        self._busy(False)
        self.job = None
        self.imported = payload
        self.source.setCurrentIndex(1)
        self.summary.setText(f"{len(payload[0].times)} amostras importadas · origem não verificada · Ta deve corresponder à experiência.")

    def export(self):
        if self.result is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exportar calibração", "thermal-calibration.csv", "CSV (*.csv)")
        if path:
            result, context = self.result, self.result_context
            def write(token):
                powers = dict(zip(context["times"], context["powers"]))
                rows = []
                for partition, data in (("training", result.training), ("validation", result.validation)):
                    for index, time in enumerate(data.times):
                        if index % 256 == 0:
                            token.check()
                        rows.append(dict(partition=partition, time_s=time, observed_c=data.observed[index], predicted_c=data.predicted[index],
                                         residual_c=data.residuals[index], power_w=powers[time], capacity_j_k=result.capacity,
                                         dissipation_w_k=result.dissipation, ambient_c=context["ambient_c"],
                                         parameter_origin="ESTIMATED", data_origin=context["provenance"], method=result.method))
                export_csv(path, rows, token)
            self.tasks.start(write, lambda _: self.summary.setText("Previsões, resíduos, parâmetros e origem exportados; treino e validação identificados."),
                             lambda message: self.summary.setText(message))
