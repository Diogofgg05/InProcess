"""InProcess 7.5/7.6/8.0 — opt-in native experiments and evidence-only advice.

Does not optimize arbitrary active processes or claim sensor calibration.
"""
import json
import sys
from dataclasses import asdict
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,QPushButton,
    QPlainTextEdit,QCheckBox,QMessageBox,QFileDialog,
)
from .workers import Tasks
from ..optimization.native75 import native_capability,native_workload_trial
from ..optimization.energy76 import load_energy_trace_csv,integrate_energy,compare_energy_traces
from ..optimization.recommendations80 import recommend_energy,combine_recommendations


class EvidenceLab80Page(QWidget):
    def __init__(self,tasks=None):
        super().__init__()
        self.tasks=tasks or Tasks(self)
        self.job=None
        self.last_report=None
        layout=QVBoxLayout(self)
        title=QLabel("InProcess 7.5 / 7.6 / 8.0 · Eficiência e evidência")
        title.setObjectName("title")
        layout.addWidget(title)
        self.note=QLabel(
            "READ-ONLY por defeito. Medir watts exige sensor e unidades reais; "
            "o modo nativo só se aplica a uma tarefa de teste criada nesta página."
        )
        self.note.setObjectName("muted")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)

        layout.addWidget(QLabel("7.5 · Ensaio isolado com política nativa"))
        capability=native_capability()
        self.capability=QLabel(
            f"{capability.system} — {capability.mechanism} · suportado={capability.supported}. "
            +"; ".join(capability.limitations)
        )
        self.capability.setWordWrap(True)
        layout.addWidget(self.capability)
        row=QHBoxLayout()
        self.authorize=QCheckBox("Autorizo aplicar eficiência nativa apenas à tarefa de referência criada agora.")
        self.run_native=QPushButton("Executar ensaio nativo")
        self.run_native.clicked.connect(self.execute_native)
        row.addWidget(self.authorize)
        row.addWidget(self.run_native)
        layout.addLayout(row)

        layout.addWidget(QLabel("7.6 · Medições de potência elétrica com proveniência"))
        form=QFormLayout()
        self.csv_a=QLineEdit()
        self.csv_b=QLineEdit()
        self.csv_a.setPlaceholderText("CSV A: time_s,power_w[,temperature_c]")
        self.csv_b.setPlaceholderText("CSV B: time_s,power_w[,temperature_c]")
        self.device=QLineEdit("computer")
        self.sensor=QLineEdit("external-power-meter")
        self.scope=QLineEdit("system-wall")
        form.addRow("CSV cenário A",self.csv_a)
        form.addRow("CSV cenário B (opcional)",self.csv_b)
        form.addRow("Equipamento",self.device)
        form.addRow("Sensor / instrumento",self.sensor)
        form.addRow("Domínio de potência",self.scope)
        layout.addLayout(form)
        self.work_check=QCheckBox(
            "Confirmo que os cenários usam exatamente a mesma tarefa e fronteira de medição."
        )
        self.work_check.setChecked(False)
        layout.addWidget(self.work_check)
        actions=QHBoxLayout()
        self.analyse=QPushButton("Analisar dados e recomendar (sem alterar o SO)")
        self.analyse.setObjectName("primary")
        self.analyse.clicked.connect(self.evaluate)
        self.export_button=QPushButton("Guardar relatório JSON")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export)
        actions.addWidget(self.analyse)
        actions.addWidget(self.export_button)
        layout.addLayout(actions)
        self.results=QPlainTextEdit()
        self.results.setReadOnly(True)
        layout.addWidget(self.results,1)

    def execute_native(self):
        if self.job:
            return
        if not self.authorize.isChecked():
            self.results.setPlainText("O ensaio nativo só ocorre após autorização explícita.")
            return
        if QMessageBox.question(
            self,"Confirmar experiência isolada",
            "Executar apenas uma tarefa de referência, com política nativa temporária?\n"
            "Não serão alterados outros processos nem planos globais.",
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No
        )!=QMessageBox.Yes:
            return
        self.run_native.setEnabled(False)
        self.results.setPlainText("A executar ensaio nativo com a tarefa de referência...")
        command=[sys.executable,"-m",
                 "expecto_process_manager.optimization.benchmark_workload71",
                 "--iterations","300000"]
        self.job=self.tasks.start(
            lambda token:native_workload_trial(command,authorized=True,
                                               timeout_s=20),
            self.native_done,self.failed,
        )

    def native_done(self,data):
        self.job=None
        self.run_native.setEnabled(True)
        self.authorize.setChecked(False)
        self.results.setPlainText(
            f"7.5: {data.mechanism}, estado={data.status}, "
            f"duração={data.elapsed_s:.4f}s, código={data.return_code}.\n"
            f"{data.warning}\nNão é prova de poupança de energia."
        )

    def evaluate(self):
        if self.job:
            return
        path_a=self.csv_a.text().strip()
        path_b=self.csv_b.text().strip()
        device=self.device.text().strip()
        sensor=self.sensor.text().strip()
        scope=self.scope.text().strip()
        comparable=self.work_check.isChecked()
        if not path_a:
            self.results.setPlainText("Escolha um ficheiro de medição CSV A.")
            return
        self.analyse.setEnabled(False)
        self.results.setPlainText("A integrar potência em joules...")
        def calculate(token):
            token.check()
            traces={"A":load_energy_trace_csv(
                path_a,device=device,sensor=sensor,power_scope=scope
            )}
            if path_b:
                traces["B"]=load_energy_trace_csv(
                    path_b,device=device,sensor=sensor,power_scope=scope
                )
            if len(traces)>1:
                comparison=compare_energy_traces(traces,comparable_work=comparable)
                advice=recommend_energy(comparison)
            else:
                comparison={"comparable":False,
                            "reasons":["Só existe um cenário; não há comparação."],
                            "results":{"A":asdict(integrate_energy(traces["A"]))},
                            "best_energy":None}
                advice=recommend_energy(comparison)
            return comparison,advice
        self.job=self.tasks.start(calculate,self.analysis_done,self.failed)

    def analysis_done(self,payload):
        self.job=None
        self.analyse.setEnabled(True)
        comparison,advice=payload
        self.last_report=combine_recommendations(energy=comparison)
        self.export_button.setEnabled(True)
        lines=[
            "7.6 ENERGIA: séries importadas são MEASURED_UNVERIFIED, não certificadas.",
            f"Cenários comparáveis: {comparison['comparable']}",
            *[f"{key}: {value['joules']:.5g} J, "
              f"{value['watt_hours']:.6g} Wh, "
              f"{value['mean_power_w']:.5g} W médio"
              for key,value in comparison["results"].items()],
            "Impedimentos: "+"; ".join(comparison["reasons"]),
            f"8.0 — {advice.status}: {advice.explanation}",
            "Nenhum processo ou política do SO foi modificado.",
        ]
        self.results.setPlainText("\n".join(lines))

    def failed(self,message):
        self.job=None
        self.run_native.setEnabled(True)
        self.analyse.setEnabled(True)
        self.results.setPlainText("Operação interrompida/recusada: "+str(message))

    def export(self):
        if self.last_report is None:
            return
        path,_=QFileDialog.getSaveFileName(
            self,"Guardar análise energética", "inprocess-evidence80.json","JSON (*.json)"
        )
        if path:
            Path(path).write_text(
                json.dumps(self.last_report,ensure_ascii=False,indent=2,
                           allow_nan=False),encoding="utf-8"
            )
