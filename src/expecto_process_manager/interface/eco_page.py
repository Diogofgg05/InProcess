"""Task-energy comparison UI; it never applies operating-system policies."""
from bisect import bisect_right
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QLabel,
    QLineEdit, QDoubleSpinBox, QComboBox, QCheckBox, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QFileDialog, QScrollArea,
)

from .charts import Plot
from .workers import Tasks
from ..optimization.eco import (POLICIES, compare_policies, load_policy_csv,
                                 synthetic_policy_runs)
from ..optimization.advisor import energy_advice


def _preview(comparison, token):
    """Interpolate only the presentation; full samples determine all metrics."""
    available = [run for run in comparison.runs if run.powers is not None]
    if not available:
        return [], {}, {}
    end = max(run.times[-1]-run.times[0] for run in available)
    if sum(len(run.times) for run in available) <= 1496:
        times = sorted({time-run.times[0] for run in available for time in run.times})
    else:
        # Keep transient peaks instead of hiding them behind uniform subsampling.
        # 201 grid points + 2 extrema × 200 bins × 3 profiles + 3 endpoints ≤ 1404.
        selected = {end*i/200 for i in range(201)}
        for run in available:
            extrema = {}
            for i, (time, power) in enumerate(zip(run.times, run.powers)):
                if i % 256 == 0:
                    token.check()
                elapsed = time-run.times[0]
                bucket = min(199, int(200*elapsed/end))
                previous = extrema.get(bucket)
                if previous is None:
                    extrema[bucket] = ((power, elapsed), (power, elapsed))
                else:
                    extrema[bucket] = (min(previous[0], (power, elapsed)), max(previous[1], (power, elapsed)))
            selected.update(time for pair in extrema.values() for _, time in pair)
            selected.add(run.times[-1]-run.times[0])
        times = sorted(selected)
    powers, energies = {}, {}
    for run in available:
        token.check()
        local_times = [time-run.times[0] for time in run.times]
        accumulated = [0.0]
        total = 0.0
        for i in range(len(local_times)-1):
            if i % 256 == 0:
                token.check()
            total += (run.powers[i]/2+run.powers[i+1]/2)*(local_times[i+1]-local_times[i])
            accumulated.append(total)
        p_values, e_values = [], []
        for time in times:
            if time > local_times[-1]:
                p_values.append(None)
                e_values.append(None)
                continue
            i = min(bisect_right(local_times, time)-1, len(local_times)-2)
            elapsed = time-local_times[i]
            interval = local_times[i+1]-local_times[i]
            slope = (run.powers[i+1]-run.powers[i])/interval
            p_values.append(run.powers[i]+slope*elapsed)
            e_values.append(accumulated[i]+run.powers[i]*elapsed+slope*elapsed*elapsed/2)
        powers[run.policy], energies[run.policy] = p_values, e_values
    token.check()
    return times, powers, energies


def _calculate(runs, constraints, token, advisory_limits=None):
    comparison = compare_policies(runs, token=token, **constraints)
    advice = energy_advice(comparison, **(advisory_limits or {}))
    comparison.report += "\n\n" + advice.report
    return comparison, _preview(comparison, token), advice


class EcoPage(QWidget):
    result_ready = Signal(object)

    def __init__(self, tasks=None):
        super().__init__()
        self.tasks = tasks or Tasks(self)
        self.job = self.result = self.experiment = None
        self.advice = None
        self._runs = {}
        self.policy_rows = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        title = QLabel("Energia por tarefa · NORMAL / ECO / ULTRA ECO")
        title.setObjectName("title")
        layout.addWidget(title)
        self.notice = QLabel("SIMULAÇÃO disponível · nenhuma configuração do SO é alterada")
        self.notice.setObjectName("muted")
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        body = QVBoxLayout(content)
        metadata = QHBoxLayout()
        self.task_id = QLineEdit("exemplo-mesma-tarefa-1")
        self.task_id.setPlaceholderText("Identificador da mesma tarefa")
        self.work_label = QLineEdit("tarefa sintética")
        self.work_label.setPlaceholderText("Unidade de trabalho útil concluído")
        self.work_label.setToolTip("Ex.: imagens processadas, ficheiros renderizados. CPU% não é uma unidade de trabalho.")
        task_form = QFormLayout()
        task_form.addRow("Mesma tarefa", self.task_id)
        task_form.addRow("Unidade de trabalho", self.work_label)
        metadata.addLayout(task_form, 1)
        constraint_form = QFormLayout()
        deadline_row = QHBoxLayout()
        self.limit_duration = QCheckBox("Prazo (s)")
        self.limit_duration.setChecked(True)
        self.max_duration = QDoubleSpinBox()
        self.max_duration.setRange(.001, 1e9)
        self.max_duration.setDecimals(3)
        self.max_duration.setValue(18)
        self.limit_duration.toggled.connect(self.max_duration.setEnabled)
        deadline_row.addWidget(self.limit_duration)
        deadline_row.addWidget(self.max_duration)
        constraint_form.addRow(deadline_row)
        thermal_row = QHBoxLayout()
        self.limit_temperature = QCheckBox("Temperatura da série (°C)")
        self.limit_temperature.setChecked(False)
        self.max_temperature = QDoubleSpinBox()
        self.max_temperature.setRange(-273.15, 1000)
        self.max_temperature.setValue(80)
        self.max_temperature.setEnabled(False)
        self.limit_temperature.toggled.connect(self.max_temperature.setEnabled)
        self.limit_temperature.setToolTip("Se ativa, exige temperatura em todos os instantes do perfil. A origem térmica permanece independente da potência.")
        thermal_row.addWidget(self.limit_temperature)
        thermal_row.addWidget(self.max_temperature)
        constraint_form.addRow(thermal_row)
        self.minimum_savings = QDoubleSpinBox()
        self.minimum_savings.setRange(0, 100)
        self.minimum_savings.setDecimals(1)
        self.minimum_savings.setSuffix(" %")
        self.minimum_savings.setValue(5)
        self.minimum_savings.setToolTip("Redução energética mínima face ao perfil NORMAL.")
        constraint_form.addRow("Poupança mínima", self.minimum_savings)
        self.maximum_slowdown = QDoubleSpinBox()
        self.maximum_slowdown.setRange(0, 1000)
        self.maximum_slowdown.setDecimals(1)
        self.maximum_slowdown.setSuffix(" %")
        self.maximum_slowdown.setValue(25)
        self.maximum_slowdown.setToolTip("Tempo adicional máximo permitido face ao perfil NORMAL.")
        constraint_form.addRow("Atraso máximo", self.maximum_slowdown)
        metadata.addLayout(constraint_form, 1)
        body.addLayout(metadata)

        inputs = QGridLayout()
        for column, text in enumerate(("Perfil", "Origem da potência no CSV", "Trabalho útil", "Concluído", "Dados", "Série carregada")):
            label = QLabel(text)
            label.setObjectName("muted")
            label.setWordWrap(True)
            inputs.addWidget(label, 0, column)
        for row, policy in enumerate(POLICIES, start=1):
            source = QComboBox()
            for text, code in (("Simulada", "SIMULATED"), ("Medida (declarada)", "MEASURED"),
                               ("Estimada", "ESTIMATED")):
                source.addItem(text, code)
            source.setToolTip("Etiqueta explícita aplicada ao próximo CSV. O ficheiro sozinho não confirma sensores nem calibração.")
            work = QDoubleSpinBox()
            work.setRange(.000001, 1e12)
            work.setDecimals(6)
            work.setValue(1)
            completed = QCheckBox()
            completed.setChecked(True)
            load = QPushButton("Importar CSV")
            load.clicked.connect(lambda checked=False, name=policy: self.open(name))
            origin = QLabel("SIMULATED · exemplo")
            origin.setWordWrap(True)
            origin.setObjectName("muted")
            self.policy_rows[policy] = {"source": source, "work": work, "completed": completed,
                                        "load": load, "origin": origin}
            for column, widget in enumerate((QLabel(policy), source, work, completed, load, origin)):
                inputs.addWidget(widget, row, column)
        inputs.setColumnStretch(5, 1)
        body.addLayout(inputs)
        note = QLabel("CSV: time_s,power_w[,temperature_c] · declare a mesma tarefa, fronteira de potência e quantidade de trabalho concluído.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        body.addWidget(note)

        actions = QHBoxLayout()
        self.run = QPushButton("Comparar energia")
        self.run.setObjectName("primary")
        self.run.clicked.connect(self.execute)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.cancel)
        self.preset_button = QPushButton("Repor exemplo simulado")
        self.preset_button.clicked.connect(self.set_preset)
        for button in (self.run, self.cancel_button, self.preset_button):
            actions.addWidget(button)
        actions.addStretch()
        body.addLayout(actions)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["Perfil", "Tempo (s)", "Energia (J)", "Energia (Wh)",
                                               "T máxima (°C)", "Trabalho/J", "Admissível", "Motivo"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.Stretch)
        self.table.setMinimumHeight(155)
        self.table.setMaximumHeight(220)
        body.addWidget(self.table)
        charts = QHBoxLayout()
        self.power_plot = Plot("Potência por perfil", "Potência (W)", x_title="Tempo decorrido (s)")
        self.energy_plot = Plot("Energia acumulada por tarefa", "Energia (J)", x_title="Tempo decorrido (s)")
        self.plots = [self.power_plot, self.energy_plot]
        for plot in self.plots:
            charts.addWidget(plot, 1)
        body.addLayout(charts, 1)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        self.advice_note = QLabel("PARECER · A aguardar comparação. Nenhuma política será alterada.")
        self.advice_note.setObjectName("muted")
        self.advice_note.setWordWrap(True)
        layout.addWidget(self.advice_note)
        self.summary = QLabel()
        self.summary.setObjectName("muted")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.set_preset()

    def set_preset(self):
        if self.job:
            return
        self._runs = {run.policy: run for run in synthetic_policy_runs()}
        self.task_id.setText("exemplo-mesma-tarefa-1")
        self.work_label.setText("tarefa sintética")
        for policy, row in self.policy_rows.items():
            row["source"].setCurrentIndex(0)
            row["work"].setValue(1)
            row["completed"].setChecked(True)
            row["origin"].setText("SIMULATED · exemplo")
        self.result = self.experiment = None
        self.advice = None
        self.advice_note.setText("PARECER · A aguardar comparação. Nenhuma política será alterada.")
        self.table.setRowCount(0)
        for plot in self.plots:
            plot.update_series([], {})
        self.summary.setText("Exemplo sintético: ECO usa menos W durante mais tempo; compare os J para avaliar o efeito total.")

    def config(self):
        return {"max_duration": self.max_duration.value() if self.limit_duration.isChecked() else None,
                "max_temperature": self.max_temperature.value() if self.limit_temperature.isChecked() else None}

    def advisory_limits(self):
        return {"min_savings_percent": self.minimum_savings.value(),
                "max_slowdown_percent": self.maximum_slowdown.value()}

    def _busy(self, active):
        self.run.setEnabled(not active)
        self.preset_button.setEnabled(not active)
        for row in self.policy_rows.values():
            row["load"].setEnabled(not active)

    def execute(self):
        if self.job:
            return
        try:
            runs = [replace(self._runs[policy], task_id=self.task_id.text(), work_label=self.work_label.text(),
                            work_units=self.policy_rows[policy]["work"].value(),
                            work_completed=self.policy_rows[policy]["completed"].isChecked())
                    for policy in POLICIES]
            constraints = self.config()
        except (ValueError, KeyError, TypeError) as error:
            self.failed(str(error))
            return
        self._busy(True)
        self.summary.setText("A comparar o trabalho concluído e integrar as séries em segundo plano…")
        limits = self.advisory_limits()
        self.job = self.tasks.start(lambda token: _calculate(runs, constraints, token, limits),
                                    self.display, self.calculation_failed)

    def open(self, policy):
        if self.job:
            return
        path, _ = QFileDialog.getOpenFileName(self, f"Importar potência · {policy}", "", "CSV (*.csv)")
        if not path:
            return
        row = self.policy_rows[policy]
        metadata = {"policy": policy, "work_units": row["work"].value(), "work_label": self.work_label.text(),
                    "provenance": row["source"].currentData(), "task_id": self.task_id.text(),
                    "work_completed": row["completed"].isChecked()}
        self._busy(True)
        self.summary.setText(f"A validar o CSV de {policy}; nenhuma proveniência é inferida automaticamente…")
        self.job = self.tasks.start(lambda token: load_policy_csv(path, token=token, **metadata),
                                    lambda run: self.loaded(run, Path(path).name), self.calculation_failed)

    def loaded(self, run, filename):
        self.job = None
        self._busy(False)
        self._runs[run.policy] = run
        self.policy_rows[run.policy]["origin"].setText(f"{run.provenance} · {filename}")
        self.result = self.experiment = None
        self.advice = None
        self.advice_note.setText("PARECER · A aguardar comparação. Nenhuma política será alterada.")
        self.table.setRowCount(0)
        for plot in self.plots:
            plot.update_series([], {})
        self.summary.setText(f"{run.policy}: {len(run.times)} amostras carregadas; confirme a equivalência da tarefa antes de comparar.")

    def display(self, payload):
        self.result, preview, self.advice = payload
        self.experiment = self.result
        self.job = None
        self._busy(False)
        times, powers, energies = preview
        self.power_plot.update_series(times, powers)
        self.energy_plot.update_series(times, energies)
        self.table.setRowCount(len(self.result.rows))
        for index, row in enumerate(self.result.rows):
            formatted = lambda value: f"{value:.7g}" if value is not None else "Indisponível"
            values = [row.policy, formatted(row.duration), formatted(row.energy_j), formatted(row.energy_wh),
                      formatted(row.max_temperature), formatted(row.efficiency),
                      "Sim" if row.feasible else "Não", " · ".join(row.reasons) or "Condições satisfeitas"]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.table.setItem(index, column, item)
        self.table.resizeRowsToContents()
        if self.result.recommendation:
            source = self.result.runs[0].provenance
            label = "no cenário simulado" if source == "SIMULATED" else "nos dados fornecidos"
            self.summary.setText(f"Menor energia admissível {label}: {self.result.recommendation}. O relatório explica os pressupostos e limites.")
        else:
            text = " ".join(self.result.reasons) or "Nenhum perfil satisfaz todas as restrições."
            self.summary.setText("Sem recomendação. "+text)
        if self.advice.candidate:
            self.advice_note.setText(
                f"DRY RUN · {self.advice.candidate}: {self.advice.savings_percent:.1f}% menos energia, "
                f"{self.advice.slowdown_percent:+.1f}% de tempo face a NORMAL. "
                "Cenário dos dados fornecidos, não uma poupança real comprovada."
            )
        elif self.advice.status == "KEEP_NORMAL":
            self.advice_note.setText(
                "DRY RUN · Manter NORMAL: nenhuma alternativa respeita a poupança mínima "
                "e o atraso máximo."
            )
        else:
            self.advice_note.setText("DRY RUN · Parecer inconclusivo: " + " ".join(self.advice.reasons))
        self.result_ready.emit(self.result)

    def cancel(self):
        if self.job:
            self.job.token.cancel()

    def failed(self, message):
        self.summary.setText(message)

    def calculation_failed(self, message):
        self.job = None
        self._busy(False)
        self.failed(message)

    def theme(self):
        for plot in self.plots:
            plot.theme()
