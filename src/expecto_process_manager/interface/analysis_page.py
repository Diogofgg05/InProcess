from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QPlainTextEdit,QHBoxLayout,QPushButton,QTableWidget,QTableWidgetItem,QHeaderView
from .charts import Plot


class AnalysisPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        title = QLabel('Análise científica')
        title.setObjectName('title')
        layout.addWidget(title)
        row = QHBoxLayout()
        self.plot = Plot('Derivadas dos sinais sintéticos','°C/s')
        self.convergence = Plot('Convergência · potência constante','RMSE (°C)',logarithmic=True)
        row.addWidget(self.plot)
        row.addWidget(self.convergence)
        layout.addLayout(row)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.hide()
        self.table=QTableWidget(0,3)
        self.table.setHorizontalHeaderLabels(['Método','RMSE (°C)','Erro máximo (°C)'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setMaximumHeight(170)
        layout.addWidget(self.table)
        self.report_button=QPushButton('Abrir relatório térmico completo')
        self.report_button.setEnabled(False)
        layout.addWidget(self.report_button)
        note=QLabel('Comparação numérica com dados sintéticos. Fórmulas, hipóteses, custos e interpretação estão no relatório gerado.')
        note.setWordWrap(True)
        note.setObjectName('muted')
        layout.addWidget(note)

    def display(self,experiment):
        r = experiment.simulation
        self.plot.update_series(r.times,dict(zip(['Sem ruído','Com ruído','Filtrado'],experiment.derivatives)))
        study=getattr(experiment,'method_convergence',{})
        if study:
            first=next(iter(study.values()))
            self.convergence.update_series([row['dt'] for row in first],
                {name:[row['rmse'] if row['rmse'] is not None and row['rmse']>1e-12 else None for row in rows] for name,rows in study.items()})
        else:
            valid = [(h,e) for h,e in experiment.convergence if e is not None and e > 1e-12]
            self.convergence.update_series([h for h,e in valid],{'Euler':[e for h,e in valid]})
        self.text.setPlainText(experiment.report)
        errors=getattr(experiment,'method_errors',{}) or {'Euler':experiment.error}
        self.table.setRowCount(len(errors))
        for i,(name,error) in enumerate(errors.items()):
            for j,value in enumerate((name,f"{error['rmse']:.6g}",f"{error['maximum']:.6g}")):
                self.table.setItem(i,j,QTableWidgetItem(value))
