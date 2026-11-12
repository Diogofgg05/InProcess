"""Physical Systems Lab 6: heat PDE, convergence, sensitivity and fan control."""
from dataclasses import asdict
import csv
import json
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QPlainTextEdit, QFileDialog,
)
from .charts import Plot
from .workers import Tasks
from ..physics.heat_implicit import (solve_heat_61, temporal_order_study, spatial_order_study)
from ..physics.physical_lab6 import (
    HeatSlab, solve_heat, heat_convergence, heat_sensitivity,
    FanControl, fan_comparison, simulate_fan_control,
)


class PhysicalLab6Page(QWidget):
    def __init__(self, tasks=None):
        super().__init__()
        self.tasks = tasks or Tasks(self)
        self.job = None
        self.result = None
        layout = QVBoxLayout(self)
        title = QLabel("Physical Systems Lab 6 · Modelos e validação")
        title.setObjectName("title")
        layout.addWidget(title)
        self.note = QLabel(
            "SIMULATED · Não utiliza sensores reais, não controla ventoinhas nem processos. "
            "Resultados de modelos didáticos, sem calibração."
        )
        self.note.setObjectName("muted")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.mode = QComboBox()
        self.mode.addItem("Condução térmica 1D · equação do calor", "heat")
        self.mode.addItem("Convergência e sensibilidade · Fourier", "validation")
        self.mode.addItem("Arrefecimento: PI adaptativo vs fixo", "fan")
        self.mode.addItem("6.1 · Métodos numéricos implícitos e convergência", "implicit")
        layout.addWidget(self.mode)
        self.method = QComboBox()
        self.method.addItem("Euler explícito (Fo ≤ 0,5)", "explicit")
        self.method.addItem("Euler implícito (Backward Euler)", "backward_euler")
        self.method.addItem("Crank–Nicolson", "crank_nicolson")
        self.method.setCurrentIndex(2)
        layout.addWidget(self.method)
        self.mode.currentIndexChanged.connect(self._update_mode)

        self.heat_form = QFormLayout()
        form = self.heat_form
        self.length = QLineEdit("0.04")
        self.alpha = QLineEdit("0.00001")
        self.nodes = QLineEdit("21")
        self.duration = QLineEdit("4")
        form.addRow("Comprimento (m)", self.length)
        form.addRow("Difusividade (m²/s)", self.alpha)
        form.addRow("Nós espaciais", self.nodes)
        form.addRow("Duração (s)", self.duration)
        self.heat_form_widget = QWidget()
        self.heat_form_widget.setLayout(form)
        layout.addWidget(self.heat_form_widget)
        self.fan_form_widget = QWidget()
        fan_form = QFormLayout(self.fan_form_widget)
        self.target = QLineEdit("47")
        self.proportional = QLineEdit("0.025")
        self.integral = QLineEdit("0.0008")
        self.thermal_power = QLineEdit("70")
        self.fan_duration = QLineEdit("180")
        fan_form.addRow("Temperatura alvo (°C)", self.target)
        fan_form.addRow("Ganho proporcional (1/°C)", self.proportional)
        fan_form.addRow("Ganho integral (1/(°C·s))", self.integral)
        fan_form.addRow("Potência térmica simulada (W)", self.thermal_power)
        fan_form.addRow("Duração (s)", self.fan_duration)
        layout.addWidget(self.fan_form_widget)
        self._update_mode()
        buttons = QHBoxLayout()
        self.run = QPushButton("Executar e verificar")
        self.run.setObjectName("primary")
        self.run.clicked.connect(self.execute)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.cancel)
        self.export_button = QPushButton("Exportar resultados JSON + CSV")
        self.export_button.clicked.connect(self.export)
        self.export_button.setEnabled(False)
        for item in (self.run, self.cancel_button, self.export_button):
            buttons.addWidget(item)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.plot = Plot("Temperaturas e estados simulados", "°C", x_title="Tempo (s)")
        layout.addWidget(self.plot, 2)
        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        layout.addWidget(self.report, 1)

    def _update_mode(self, *_):
        mode = self.mode.currentData()
        self.heat_form_widget.setVisible(mode != "fan")
        self.fan_form_widget.setVisible(mode == "fan")
        self.method.setVisible(mode == "implicit")

    def _read_fan(self):
        try:
            parameters = FanControl(
                target_c=float(self.target.text()),
                proportional=float(self.proportional.text()),
                integral=float(self.integral.text()),
                thermal_power_w=float(self.thermal_power.text())
            )
            duration = float(self.fan_duration.text())
        except ValueError as exc:
            raise ValueError("Parâmetros do controlador inválidos.") from exc
        if not 0 < duration <= 3600:
            raise ValueError("Duração do controlo entre 0 e 3600 s.")
        return parameters, duration

    def _read(self):
        try:
            length = float(self.length.text())
            alpha = float(self.alpha.text())
            nodes = int(self.nodes.text())
            duration = float(self.duration.text())
        except ValueError as exc:
            raise ValueError("Introduza parâmetros numéricos válidos.") from exc
        if self.nodes.text().strip() != str(nodes):
            raise ValueError("Número de nós deve ser inteiro.")
        return HeatSlab(length_m=length, diffusivity_m2_s=alpha, nodes=nodes), duration

    def execute(self):
        if self.job: return
        try:
            mode = self.mode.currentData()
            if mode == "fan":
                fan_settings, duration = self._read_fan()
                model = None
            else:
                model, duration = self._read()
                fan_settings = None
        except ValueError as exc:
            self.note.setText(str(exc))
            return
        numerical_method = self.method.currentData()
        self.run.setEnabled(False)
        self.export_button.setEnabled(False)
        self.note.setText("A calcular no trabalhador, sem bloquear a interface...")
        def calculate(token):
            if mode == "heat":
                out = solve_heat(model, duration_s=duration, token=token)
                return {
                    "mode": mode, "origin": "SIMULATED",
                    "times_s": list(out.times_s),
                    "series": {"Centro (°C)": [profile[model.nodes // 2] for profile in out.profiles_c],
                               "Referência analítica (°C)": [
                                   model.exact(model.length_m / 2, t) for t in out.times_s]},
                    "parameters": asdict(model), "metadata": asdict(out),
                    "report": ("Equação: T_t = alpha*T_xx; fronteiras Dirichlet constantes no ambiente.\n"
                               f"Fourier={out.fourier:.6g} (limite de estabilidade <= 0.5).\n"
                               f"RMSE contra solução analítica contínua = {out.rmse_c:.6g} °C.\n"
                               f"Resíduo discreto de energia = {out.balance_error_j:.6g} J.\n"
                               "O erro inclui discretização espacial e temporal.")}
            if mode == "validation":
                convergence = heat_convergence(model, duration_s=duration,token=token)
                sensitivity = heat_sensitivity(model, duration_s=duration,token=token)
                return {
                    "mode": mode, "origin": "SIMULATED",
                    "times_s": [row["actual_fourier"] for row in convergence],
                    "series": {"RMSE (°C)": [row["rmse_c"] for row in convergence]},
                    "parameters": asdict(model),
                    "metadata": {"convergence": convergence, "sensitivity": sensitivity,
                                 "note": "Estudo com grelha e material selecionados pelo utilizador."},
                    "report": ("Comparação do esquema explícito, malha fixa de 21 nós.\n"
                               "Os erros incluem erro espacial de ordem 2; não inferir ordem temporal "
                               "diretamente da solução contínua.\n"
                               +json.dumps({"convergencia":convergence,"sensibilidade":sensitivity},
                                           ensure_ascii=False,indent=2))}
            if mode == "implicit":
                out = solve_heat_61(model, duration_s=duration, method=numerical_method, token=token)
                time_rows = temporal_order_study(model, duration_s=duration,
                                                 method=numerical_method, token=token)
                space_rows = spatial_order_study(model, duration_s=duration, token=token)
                return {
                    "mode": mode, "origin": "SIMULATED",
                    "times_s": list(out.times_s),
                    "series": {
                        "Centro numérico (°C)": [profile[model.nodes//2] for profile in out.profiles_c],
                        "Referência contínua (°C)": [
                            model.exact(model.length_m/2, t) for t in out.times_s
                        ]
                    },
                    "parameters": asdict(model),
                    "metadata": {"solver": numerical_method, "rmse_c": out.rmse_c,
                                 "max_error_c": out.max_error_c, "fourier": out.fourier,
                                 "energy_balance_j": out.balance_error_j,
                                 "temporal_order": time_rows, "spatial_order": space_rows},
                    "report": (
                        "Métodos 6.1 · Difusão térmica 1D (simulação)\n"
                        f"Esquema: {numerical_method}; Fo efetivo = {out.fourier:.6g}\n"
                        f"RMSE vs EDP contínua = {out.rmse_c:.8g} °C\n"
                        f"Resíduo discreto de energia = {out.balance_error_j:.8g} J\n"
                        "Ordem temporal calculada face à solução SEMIDISCRETA exata; "
                        "ordem espacial analisada separadamente sem erro de integração temporal.\n"
                        "Crank–Nicolson é A-estável, mas pode apresentar oscilações com passos elevados.\n"
                        + json.dumps({"temporal": time_rows, "spatial": space_rows},
                                     ensure_ascii=False,indent=2)
                    ),
                }
            result = {
                "fixed": simulate_fan_control(fan_settings, adaptive=False,
                                              duration_s=duration, token=token),
                "adaptive": simulate_fan_control(fan_settings, adaptive=True,
                                                 duration_s=duration, token=token),
            }
            return {
                "mode": mode, "origin": "SIMULATED",
                "times_s": list(result["fixed"].times_s),
                "series": {"CPU · ventilação fixa": list(result["fixed"].die_c),
                           "CPU · controlo PI": list(result["adaptive"].die_c)},
                "parameters": asdict(fan_settings),
                "metadata": {name: {"max_cpu_c":r.max_die_c,
                                    "last_cpu_c":r.last_die_c,
                                    "mean_fan_fraction":r.mean_fan_fraction}
                             for name,r in result.items()},
                "report": ("Dois nós térmicos + atuador de 1.ª ordem + PI anti-windup.\n"
                           "Potência da ventoinha não inferida da velocidade; não se mede energia elétrica.\n"
                           +json.dumps({name: {"max_c":r.max_die_c, "final_c":r.last_die_c,
                                                "fan_mean":r.mean_fan_fraction}
                                        for name,r in result.items()},ensure_ascii=False,indent=2))
            }
        self.job = self.tasks.start(calculate, self.display, self.failed)

    def display(self, result):
        self.job = None
        self.result = result
        self.run.setEnabled(True)
        self.export_button.setEnabled(True)
        self.note.setText("SIMULATED · resultados reproduzíveis · sem atuação no hardware")
        self.plot.x_axis.setTitleText("Número de Fourier" if result["mode"] == "validation" else "Tempo (s)")
        self.plot.y_axis.setTitleText("RMSE (°C)" if result["mode"] == "validation" else "Temperatura (°C)")
        self.plot.update_series(result["times_s"], result["series"])
        self.report.setPlainText(result["report"])

    def failed(self, message):
        self.job = None
        self.run.setEnabled(True)
        self.note.setText(str(message))

    def cancel(self):
        if self.job:
            self.job.token.cancel()

    def export(self):
        if self.job or self.result is None: return
        directory = QFileDialog.getExistingDirectory(self, "Exportar experiência 6.0")
        if not directory: return
        output = Path(directory)
        result = self.result
        def write(token):
            token.check()
            stem = "inprocess_lab6_" + result["mode"]
            (output/(stem+".json")).write_text(
                json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8"
            )
            with (output/(stem+".csv")).open("w",newline="",encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow(["x","origin",*result["series"]])
                for index, x in enumerate(result["times_s"]):
                    token.check()
                    writer.writerow([x, result["origin"],
                                     *(values[index] for values in result["series"].values())])
            return stem
        self.job = self.tasks.start(write,self._exported,self.failed)

    def _exported(self, name):
        self.job = None
        self.note.setText(f"Exportação {name}: JSON e CSV guardados.")
