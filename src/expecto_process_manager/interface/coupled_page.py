"""Optional two-node thermal experiment; all numerical work runs in Tasks."""
from dataclasses import asdict

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from .charts import Plot
from .workers import Tasks
from ..core.metrics import export_csv
from ..physics.coupled_thermal import CoupledThermalConfig, simulate_coupled


class CoupledThermalPage(QWidget):
    result_ready = Signal(object)

    def __init__(self, tasks=None):
        super().__init__()
        self.tasks = tasks or Tasks(self)
        self.job = None
        self.result = self.experiment = None
        self.result_context = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        title = QLabel("CPU/GPU · acoplamento térmico")
        title.setObjectName("title")
        layout.addWidget(title)
        note = QLabel("SIMULATED · dois nós térmicos com potências independentes. O acoplamento transfere energia entre CPU e GPU.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        body = QHBoxLayout(content)
        controls = QWidget()
        controls.setMinimumWidth(270)
        controls.setMaximumWidth(360)
        form = QFormLayout(controls)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.fields = {}
        for name, label, value, low, high, decimals in [
            ("ambient", "Ambiente Ta (°C)", 22, -50, 100, 2),
            ("initial_cpu", "T inicial CPU (°C)", 40, -50, 200, 2),
            ("initial_gpu", "T inicial GPU (°C)", 35, -50, 200, 2),
            ("cpu_power", "Potência CPU (W)", 45, 0, 3000, 2),
            ("gpu_power", "Potência GPU (W)", 60, 0, 3000, 2),
            ("cpu_capacity", "Capacidade CPU (J/K)", 100, .01, 100000, 3),
            ("gpu_capacity", "Capacidade GPU (J/K)", 150, .01, 100000, 3),
            ("cpu_dissipation", "Dissipação CPU (W/K)", 2, 0, 1000, 4),
            ("gpu_dissipation", "Dissipação GPU (W/K)", 3, 0, 1000, 4),
            ("coupling", "Acoplamento (W/K)", .5, 0, 1000, 4),
            ("duration", "Duração (s)", 120, .001, 100000, 3),
            ("dt", "Passo interno Δt (s)", .1, .0001, 10000, 4),
        ]:
            field = QDoubleSpinBox()
            field.setDecimals(decimals)
            field.setRange(low, high)
            field.setValue(value)
            self.fields[name] = field
            form.addRow(label, field)
        self.fields["coupling"].setToolTip("kcg=0 separa os modelos. Um valor positivo transfere calor do nó mais quente para o mais frio.")
        self.fields["dt"].setToolTip("Passo da simulação, independente da frequência de recolha de sensores.")
        self.method = QComboBox()
        for text, name in (("Euler explícito", "euler"), ("Euler melhorado · Heun", "heun"), ("Runge–Kutta de 4.ª ordem", "rk4")):
            self.method.addItem(text, name)
        self.method.setCurrentIndex(2)
        form.addRow("Método", self.method)
        self.run = QPushButton("Simular CPU e GPU")
        self.run.setObjectName("primary")
        self.run.clicked.connect(self.execute)
        form.addRow(self.run)
        self.cancel_button = QPushButton("Cancelar cálculo")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel)
        form.addRow(self.cancel_button)
        self.export_button = QPushButton("Exportar resultados CSV")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export)
        form.addRow(self.export_button)
        body.addWidget(controls, 1)
        self.plots = [Plot("Temperatura CPU · efeito do acoplamento", "Temperatura (°C)"),
                      Plot("Temperatura GPU · efeito do acoplamento", "Temperatura (°C)"),
                      Plot("Balanço energético do sistema", "Energia (J)"),
                      Plot("Resíduo do balanço · entrada − perdas − ΔU", "Resíduo energético (J)")]
        self.plots[3].y_axis.setLabelFormat("%.2e")
        grid = QGridLayout()
        for index, plot in enumerate(self.plots):
            grid.addWidget(plot, index // 2, index % 2)
        body.addLayout(grid, 3)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        self.summary = QLabel("Parâmetros ilustrativos. As curvas independentes são referências analíticas apenas quando kcg=0.")
        self.summary.setObjectName("muted")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

    def execute(self):
        if not self.run.isEnabled():
            return
        parameters = {name: field.value() for name, field in self.fields.items()}
        model_names = ("ambient", "cpu_capacity", "gpu_capacity", "cpu_dissipation", "gpu_dissipation", "coupling")
        config = CoupledThermalConfig(**{name: parameters[name] for name in model_names})
        arguments = {name: parameters[name] for name in ("initial_cpu", "initial_gpu", "cpu_power", "gpu_power", "duration", "dt")}
        arguments["method"] = self.method.currentData()
        context = {"provenance": "SIMULATED", "model": asdict(config), "parameters": dict(arguments),
                   "units": {"time": "s", "temperature": "°C", "power": "W", "energy": "J", "capacity": "J/K", "dissipation": "W/K"}}
        self.run.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.summary.setText("A resolver as temperaturas e o balanço energético em segundo plano…")
        self.job = self.tasks.start(lambda token: (simulate_coupled(config, **arguments, token=token), context), self.display, self.failed)

    def display(self, payload):
        self.run.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.job = None
        self.result, self.result_context = payload
        self.experiment = self.result
        r = self.result
        self.plots[0].update_series(r.times, {"CPU · modelo acoplado": r.cpu_temperatures, "CPU · modelo independente analítico": r.independent_cpu})
        self.plots[1].update_series(r.times, {"GPU · modelo acoplado": r.gpu_temperatures, "GPU · modelo independente analítico": r.independent_gpu})
        self.plots[2].update_series(r.times, {"Energia térmica recebida": r.input_energy, "Transferência líquida ao ambiente": r.dissipated_energy,
                                           "Variação da energia armazenada": r.stored_energy})
        self.plots[3].update_series(r.times, {"Resíduo energético do sistema": r.balance_residual})
        self.summary.setText(f"SIMULATED · {r.method.upper()} · CPU final {r.cpu_temperatures[-1]:.3f} °C · GPU final {r.gpu_temperatures[-1]:.3f} °C\n"
                             f"Energia recebida {r.input_energy[-1]:.5g} J · resíduo máximo {max(abs(value) for value in r.balance_residual):.3g} J.")
        self.export_button.setEnabled(True)
        self.result_ready.emit(r)

    def cancel(self):
        if self.job is not None:
            self.job.token.cancel()

    def failed(self, message):
        self.run.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.job = None
        self.summary.setText(message)

    def export(self):
        if self.result is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exportar CPU/GPU", "coupled-thermal.csv", "CSV (*.csv)")
        if path:
            r, context = self.result, self.result_context
            def write(token):
                rows = []
                for index, time in enumerate(r.times):
                    if index % 256 == 0:
                        token.check()
                    rows.append(dict(time_s=time, cpu_temperature_c=r.cpu_temperatures[index], gpu_temperature_c=r.gpu_temperatures[index],
                                     independent_cpu_c=r.independent_cpu[index], independent_gpu_c=r.independent_gpu[index],
                                     cpu_power_w=r.cpu_powers[index], gpu_power_w=r.gpu_powers[index], input_energy_j=r.input_energy[index],
                                     ambient_energy_j=r.dissipated_energy[index], stored_energy_j=r.stored_energy[index],
                                     balance_residual_j=r.balance_residual[index], method=r.method, provenance="SIMULATED", **context["model"]))
                export_csv(path, rows, token)
            self.tasks.start(write, lambda _: self.summary.setText("CSV exportado com temperaturas, energias, parâmetros e origem simulada."),
                             lambda message: self.summary.setText(message))


# Concise alias for integrations that name the extension by the tab label.
CoupledPage = CoupledThermalPage
