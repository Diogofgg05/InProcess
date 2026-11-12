"""InProcess 7.1 and 7.2 — benchmark results and authorized priority session.

UI is intentionally conservative: no automatic privileged operation, no
task termination, no system services manipulation and no invented latency.
"""
import json
import os
import sys
from dataclasses import asdict

import psutil
from PySide6.QtWidgets import (
    QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,QPushButton,
    QPlainTextEdit,QComboBox,QCheckBox,QMessageBox,QFileDialog,
)
from .workers import Tasks
from ..optimization.benchmarks71 import (
    benchmark_trial,validate_comparison,write_benchmark_json,
)
from ..optimization.priority72 import preview_priority,run_temporary_priority


class ResourceLab71Page(QWidget):
    def __init__(self,tasks=None):
        super().__init__()
        self.tasks=tasks or Tasks(self)
        self.job=None
        self.trials=[]
        self.approved_preview=None
        layout=QVBoxLayout(self)
        header=QLabel("InProcess 7.1 + 7.2 · Performance & Adaptive Resources")
        header.setObjectName("title")
        layout.addWidget(header)
        note=QLabel(
            "7.1: comparação A/B controlada sem medir diretamente latência de clique "
            "ou potência elétrica. 7.2: prioridade apenas com autorização e "
            "restauro na saída normal; falhas de hardware/crash não garantem reversão."
        )
        note.setWordWrap(True)
        note.setObjectName("muted")
        layout.addWidget(note)

        layout.addWidget(QLabel("7.1 · Performance Benchmark Laboratory"))
        bform=QFormLayout()
        self.benchmark_label=QComboBox()
        self.benchmark_label.addItem("Sem monitor / baseline","BASELINE")
        self.benchmark_label.addItem("InProcess","INPROCESS")
        self.benchmark_label.addItem("Gestor de Tarefas do Windows 11","WINDOWS_TASK_MANAGER")
        self.benchmark_label.addItem("GNOME System Monitor","GNOME_SYSTEM_MONITOR")
        self.observer_pid=QLineEdit(str(os.getpid()))
        self.iterations=QLineEdit("3000000")
        self.repetitions=QLineEdit("3")
        bform.addRow("Cenário",self.benchmark_label)
        bform.addRow("PID real da aplicação monitor (exceto baseline)",self.observer_pid)
        bform.addRow("Iterações da tarefa idêntica",self.iterations)
        bform.addRow("Repetições",self.repetitions)
        layout.addLayout(bform)
        brow=QHBoxLayout()
        self.run_benchmark=QPushButton("Executar ensaios")
        self.run_benchmark.clicked.connect(self.execute_benchmark)
        self.export_benchmark=QPushButton("Exportar resultados JSON")
        self.export_benchmark.setEnabled(False)
        self.export_benchmark.clicked.connect(self.export_trials)
        brow.addWidget(self.run_benchmark)
        brow.addWidget(self.export_benchmark)
        layout.addLayout(brow)
        self.benchmark_text=QPlainTextEdit()
        self.benchmark_text.setReadOnly(True)
        self.benchmark_text.setMaximumHeight(175)
        layout.addWidget(self.benchmark_text)

        layout.addWidget(QLabel("7.2 · Controlo temporário e reversível de prioridade"))
        pform=QFormLayout()
        self.target_pid=QLineEdit()
        self.target_pid.setPlaceholderText("PID de processo do próprio utilizador")
        self.priority_duration=QLineEdit("5")
        pform.addRow("PID a inspecionar",self.target_pid)
        pform.addRow("Duração (1–15 segundos)",self.priority_duration)
        layout.addLayout(pform)
        self.permission=QCheckBox("Autorizo explicitamente a redução temporária de prioridade deste processo.")
        self.permission.setChecked(False)
        layout.addWidget(self.permission)
        prow=QHBoxLayout()
        self.preview_button=QPushButton("Verificar identidade e permissões")
        self.preview_button.clicked.connect(self.preview)
        self.apply_button=QPushButton("Aplicar temporariamente e repor")
        self.apply_button.clicked.connect(self.apply)
        self.apply_button.setEnabled(False)
        self.cancel_button=QPushButton("Cancelar sessão")
        self.cancel_button.clicked.connect(self.cancel)
        prow.addWidget(self.preview_button)
        prow.addWidget(self.apply_button)
        prow.addWidget(self.cancel_button)
        layout.addLayout(prow)
        self.priority_text=QPlainTextEdit()
        self.priority_text.setReadOnly(True)
        self.priority_text.setMaximumHeight(130)
        layout.addWidget(self.priority_text)
        self.target_pid.textChanged.connect(self.invalidate_preview)

    def invalidate_preview(self,*_):
        self.approved_preview=None
        self.apply_button.setEnabled(False)

    def execute_benchmark(self):
        if self.job:
            return
        try:
            label=self.benchmark_label.currentData()
            if label=="BASELINE":
                raise ValueError(
                    "Para medir BASELINE sem observador, feche o InProcess e use "
                    "examples/benchmark_observers71.py --label BASELINE no terminal."
                )
            pid=int(self.observer_pid.text())
            iterations=int(self.iterations.text())
            repetitions=int(self.repetitions.text())
            if not 1000<=iterations<=100_000_000 or not 1<=repetitions<=10:
                raise ValueError("Use 1000–100000000 iterações e 1–10 repetições.")
        except (ValueError,OverflowError) as error:
            self.benchmark_text.setPlainText(f"Parâmetros inválidos: {error}")
            return
        task=[sys.executable,"-m",
              "expecto_process_manager.optimization.benchmark_workload71",
              "--iterations",str(iterations)]
        self.run_benchmark.setEnabled(False)
        self.benchmark_text.setPlainText("A executar a mesma tarefa em ensaios repetidos...")
        def measure(token):
            collected=[]
            for _ in range(repetitions):
                token.check()
                outcome=benchmark_trial(task,label=label,observer_pid=pid,
                                        timeout_s=30,sample_interval_s=.15)
                collected.append(outcome)
                if outcome.status!="SUCCESS":
                    break
            return collected
        self.job=self.tasks.start(measure,self.benchmark_done,self.benchmark_failed)

    def benchmark_done(self,new_trials):
        self.job=None
        self.run_benchmark.setEnabled(True)
        self.trials.extend(new_trials)
        self.export_benchmark.setEnabled(True)
        comparison=validate_comparison(self.trials)
        last=new_trials[-1]
        self.benchmark_text.setPlainText(
            f"Último cenário: {last.label}; estado={last.status}\n"
            f"Duração={last.task_duration_s:.3f}s; CPU observador="
            f"{last.observer_cpu_core_percent} % de um núcleo; "
            f"RSS pico amostrado={last.observer_peak_rss_mib} MiB; "
            f"amostras={last.observer_samples}\n"
            f"Protocolo comparável: {comparison['comparable']}; "
            f"razões: {'; '.join(comparison['reasons']) or 'dados disponíveis'}\n"
            "Latência de clique: NÃO MEDIDA. Frequência mostrada: "
            "regularidade do amostrador do benchmark, não frequência da GUI.\n"
            "Executar os diferentes monitores isoladamente no mesmo computador "
            "e repetir em ordem alternada."
        )

    def benchmark_failed(self,error):
        self.job=None
        self.run_benchmark.setEnabled(True)
        self.benchmark_text.setPlainText(str(error))

    def export_trials(self):
        if not self.trials:
            return
        path,_=QFileDialog.getSaveFileName(self,"Guardar ensaios de desempenho",
                                          "inprocess-benchmark-71.json","JSON (*.json)")
        if path:
            write_benchmark_json(path,self.trials)

    def preview(self):
        if self.job:
            return
        self.invalidate_preview()
        try:
            pid=int(self.target_pid.text())
            p=psutil.Process(pid)
            created=p.create_time()
            plan=preview_priority(pid,created)
            self.approved_preview=plan if plan.reversible else None
            self.apply_button.setEnabled(plan.reversible)
            self.priority_text.setPlainText(
                f"{plan.name} · PID {plan.pid} · utilizador {plan.user}\n"
                f"Prioridade original: {plan.original_priority}; "
                f"temporária: {plan.temporary_priority} · SO: {plan.platform_name}\n"
                f"Reversível nesta sessão: {plan.reversible}. "
                f"{'; '.join(plan.reasons)}"
            )
        except (ValueError,OverflowError,psutil.Error,PermissionError) as error:
            self.priority_text.setPlainText(f"Não autorizado: {error}")

    def apply(self):
        if self.job or self.approved_preview is None:
            return
        if not self.permission.isChecked():
            self.priority_text.setPlainText("Marque a autorização explícita.")
            return
        try:
            duration=float(self.priority_duration.text())
            if not 1<=duration<=15:
                raise ValueError("Duração deve estar entre 1–15 s.")
            plan=self.approved_preview
            # Identity and priority are rechecked immediately before writing.
            current=preview_priority(plan.pid,plan.created)
            if current!=plan:
                raise PermissionError("O processo mudou após a verificação. Verifique novamente.")
        except (ValueError,PermissionError,psutil.Error) as error:
            self.priority_text.setPlainText(str(error))
            self.invalidate_preview()
            return
        confirmation=QMessageBox.question(
            self,"Confirmar alteração temporária de prioridade",
            f"Reduzir a prioridade de {plan.name} (PID {plan.pid}) durante "
            f"{duration:g} s e tentar repor a prioridade original?\n"
            "A reposição não é garantida se o sistema ou aplicação falhar.",
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No
        )
        if confirmation!=QMessageBox.Yes:
            return
        self.apply_button.setEnabled(False)
        self.preview_button.setEnabled(False)
        self.priority_text.setPlainText("Sessão temporária em curso; reposição ao sair...")
        def run(token):
            return run_temporary_priority(
                plan.pid,plan.created,authorized=True,duration_s=duration,token=token
            )
        self.job=self.tasks.start(run,self.priority_done,self.priority_failed)

    def priority_done(self,outcome):
        self.job=None
        self.preview_button.setEnabled(True)
        self.permission.setChecked(False)
        self.invalidate_preview()
        self.priority_text.setPlainText(
            f"Reposição confirmada: {outcome.restoration_confirmed}\n"
            f"PID={outcome.pid}; antes={outcome.before}; temporária="
            f"{outcome.temporary}; reposta={outcome.restored}\n"
            f"{outcome.details}"
        )

    def priority_failed(self,error):
        self.job=None
        self.preview_button.setEnabled(True)
        self.permission.setChecked(False)
        self.invalidate_preview()
        self.priority_text.setPlainText(
            f"ERRO/REPOSIÇÃO NÃO CONFIRMADA: {error}\n"
            "Verifique imediatamente a prioridade atual no gestor nativo."
        )

    def cancel(self):
        if self.job:
            self.job.token.cancel()
