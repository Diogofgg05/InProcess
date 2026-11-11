from datetime import datetime,timezone
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QTableView,QHeaderView,
                              QFrame,QComboBox,QPushButton,QAbstractItemView)
from PySide6.QtCore import QAbstractTableModel,Qt,QModelIndex,QSortFilterProxyModel,Signal
from PySide6.QtGui import QColor


class HistoryModel(QAbstractTableModel):
    columns = [('timestamp','Hora'),('cpu','CPU (%)'),('memory_percent','RAM (%)'),
               ('disk_bytes_s','Disco (MiB/s)'),('network_bytes_s','Rede (MiB/s)'),('collection_s','Recolha (ms)')]

    def __init__(self,parent=None):
        super().__init__(parent)
        self.rows = []

    def rowCount(self,parent=QModelIndex()): return 0 if parent.isValid() else len(self.rows)
    def columnCount(self,parent=QModelIndex()): return len(self.columns)
    def headerData(self,section,orientation,role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole: return self.columns[section][1]

    def data(self,index,role=Qt.DisplayRole):
        if not index.isValid(): return None
        key = self.columns[index.column()][0]
        value = getattr(self.rows[index.row()],key)
        if role==Qt.UserRole: return value
        if role==Qt.TextAlignmentRole: return int(Qt.AlignLeft|Qt.AlignVCenter)
        if role==Qt.ToolTipRole:
            source=getattr(self.rows[index.row()],'provenance','medido')
            return f'Origem: {source} · '+datetime.fromtimestamp(self.rows[index.row()].timestamp,timezone.utc).astimezone().isoformat(timespec='milliseconds')
        if role==Qt.ForegroundRole and value is not None:
            if key=='cpu' and value>=85: return QColor('#d04c56')
            if key=='memory_percent' and value>=85: return QColor('#b77610')
        if role!=Qt.DisplayRole: return None
        if value is None: return '—'
        if key == 'timestamp': return datetime.fromtimestamp(value,timezone.utc).astimezone().strftime('%H:%M:%S.%f')[:-3]
        if key.endswith('bytes_s'): value /= 1024**2
        if key == 'collection_s': value *= 1000
        return f'{value:.2f}'.replace('.',',')

    def update(self,history):
        incoming=list(reversed(history))
        if self.rows and incoming:
            added=next((i for i,row in enumerate(incoming) if row.timestamp==self.rows[0].timestamp),None)
            if added is not None and len(incoming)>=added and len(self.rows)>=len(incoming)-added and all(
                    a.timestamp==b.timestamp for a,b in zip(incoming[added:],self.rows)):
                changed=any(a!=b for a,b in zip(incoming[added:],self.rows))
                if added:
                    self.beginInsertRows(QModelIndex(),0,added-1)
                    self.rows=incoming[:added]+self.rows
                    self.endInsertRows()
                if len(self.rows)>len(incoming):
                    self.beginRemoveRows(QModelIndex(),len(incoming),len(self.rows)-1)
                    self.rows=self.rows[:len(incoming)]
                    self.endRemoveRows()
                self.rows=incoming
                if changed and incoming: self.dataChanged.emit(self.index(added,0),self.index(len(incoming)-1,len(self.columns)-1))
                return
        self.beginResetModel()
        self.rows = incoming
        self.endResetModel()


class HistoryPage(QWidget):
    export_requested=Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8,24,8,8); layout.setSpacing(16)
        header=QHBoxLayout()
        title = QLabel('Histórico de desempenho')
        title.setObjectName('title')
        header.addWidget(title,1)
        self.live=QLabel('À espera de dados'); self.live.setObjectName('badge'); header.addWidget(self.live)
        layout.addLayout(header)
        cards=QHBoxLayout(); cards.setSpacing(12)
        self.metrics={}
        for key,name in [('count','Amostras registadas'),('average','CPU média'),('peak','Pico de CPU'),('duration','Período registado')]:
            card=QFrame(); card.setObjectName('resultCard')
            box=QVBoxLayout(card); box.setContentsMargins(18,14,18,14)
            caption=QLabel(name); caption.setObjectName('muted')
            value=QLabel('—'); value.setObjectName('metric')
            box.addWidget(caption); box.addWidget(value); cards.addWidget(card,1)
            self.metrics[key]=value
        layout.addLayout(cards)
        toolbar=QHBoxLayout()
        toolbar.addWidget(QLabel('Mostrar'))
        self.period=QComboBox()
        for name,seconds in [('Toda a sessão',None),('Últimos 5 minutos',300),('Últimos 15 minutos',900),('Última hora',3600)]:
            self.period.addItem(name,seconds)
        self.period.currentIndexChanged.connect(self.filter_changed)
        toolbar.addWidget(self.period); toolbar.addStretch()
        self.export_button=QPushButton('Exportar histórico CSV')
        self.export_button.setEnabled(False); self.export_button.clicked.connect(self.export_requested.emit)
        toolbar.addWidget(self.export_button)
        layout.addLayout(toolbar)
        self.history=[]
        note = QLabel('Medições desta sessão · atualização automática · os dados permanecem em memória até fechar a aplicação.')
        note.setWordWrap(True)
        note.setObjectName('muted')
        self.model = HistoryModel(self)
        self.proxy=QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model); self.proxy.setSortRole(Qt.UserRole)
        table = QTableView(); self.table=table
        table.setModel(self.proxy)
        table.setSortingEnabled(True); table.sortByColumn(0,Qt.DescendingOrder)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True); table.setShowGrid(False)
        table.verticalHeader().hide(); table.verticalHeader().setDefaultSectionSize(44)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(table,1)
        layout.addWidget(note)

    def filter_changed(self,*_): self.refresh(self.history)

    def refresh(self,history):
        self.history=list(history)
        seconds=self.period.currentData()
        visible=self.history if not self.history or seconds is None else [row for row in self.history if row.timestamp>=self.history[-1].timestamp-seconds]
        at_top=self.table.verticalScrollBar().value()==0
        self.model.update(visible)
        if at_top: self.table.scrollToTop()
        self.export_button.setEnabled(bool(self.history))
        self.metrics['count'].setText(str(len(visible)))
        cpu=[row.cpu for row in visible if row.cpu is not None]
        self.metrics['average'].setText(f'{sum(cpu)/len(cpu):.1f} %'.replace('.',',') if cpu else '—')
        self.metrics['peak'].setText(f'{max(cpu):.1f} %'.replace('.',',') if cpu else '—')
        duration=visible[-1].timestamp-visible[0].timestamp if visible else 0
        self.metrics['duration'].setText(f'{int(duration)//60} min {int(duration)%60:02d} s')
        if visible: self.live.setText('Em direto · '+datetime.fromtimestamp(visible[-1].timestamp,timezone.utc).astimezone().strftime('%H:%M:%S'))
        self.export_button.setToolTip('Exporta todas as amostras desta sessão, independentemente do filtro de apresentação.')
