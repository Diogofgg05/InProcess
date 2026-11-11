"""Visible-page polling, read-only inventory and stable search/selection."""
from datetime import datetime
from PySide6.QtCore import QTimer,Qt,QSortFilterProxyModel
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QTableView,QLineEdit,
                              QHeaderView,QAbstractItemView)
from PySide6.QtGui import QStandardItemModel,QStandardItem
from ..core.inventory import inventory


class InventoryPage(QWidget):
    def __init__(self,title,kind,tasks):
        super().__init__()
        self.kind,self.tasks=kind,tasks
        self.loaded=False
        self.job=None
        self.timer=QTimer(self)
        self.timer.setInterval({'users':10000,'services':15000,'startup':30000}[kind])
        self.timer.timeout.connect(self.refresh)
        layout=QVBoxLayout(self)
        layout.setContentsMargins(8,24,8,8); layout.setSpacing(16)
        header=QHBoxLayout()
        label=QLabel(title); label.setObjectName('title'); header.addWidget(label,1)
        self.live=QLabel('Atualização automática'); self.live.setObjectName('badge'); header.addWidget(self.live)
        layout.addLayout(header)
        self.search=QLineEdit()
        self.search.setPlaceholderText('Pesquisar por nome, estado ou identificador…')
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        self.table=QTableView()
        self.model=QStandardItemModel(self)
        self.proxy=QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model); self.proxy.setFilterKeyColumn(-1)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.search.textChanged.connect(self.proxy.setFilterFixedString)
        self.table.setModel(self.proxy)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setSortingEnabled(True); self.table.sortByColumn(0,Qt.AscendingOrder)
        self.table.setShowGrid(False); self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide(); self.table.verticalHeader().setDefaultSectionSize(44)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table,1)
        self.note=QLabel('Consulta apenas de leitura · atualização automática enquanto esta página estiver aberta.')
        self.note.setObjectName('muted'); self.note.setWordWrap(True); layout.addWidget(self.note)

    def showEvent(self,event):
        super().showEvent(event)
        self.refresh(); self.timer.start()

    def hideEvent(self,event):
        self.timer.stop()
        super().hideEvent(event)

    def refresh(self):
        if self.job is not None: return
        self.loaded=True
        self.live.setText('A consultar…')
        self.job=self.tasks.start(lambda token:inventory(self.kind,token),self.display,self.failed)

    def display(self,result):
        self.job=None
        headers,rows,note=result
        selected=self.table.currentIndex()
        selected_row=None
        if selected.isValid():
            source=self.proxy.mapToSource(selected).row()
            selected_row=tuple(self.model.item(source,c).text() for c in range(self.model.columnCount()))
        old_rows=[[self.model.item(r,c).text() for c in range(self.model.columnCount())] for r in range(self.model.rowCount())]
        if old_rows!=rows or self.model.columnCount()!=len(headers):
            self.model.clear(); self.model.setHorizontalHeaderLabels(headers)
            for row in rows:
                cells=[QStandardItem(str(v)) for v in row]
                for cell in cells: cell.setToolTip(cell.text())
                self.model.appendRow(cells)
            if selected_row:
                for r,row in enumerate(rows):
                    if tuple(row)==selected_row:
                        self.table.setCurrentIndex(self.proxy.mapFromSource(self.model.index(r,0))); break
        self.note.setText(f'{len(rows)} entradas · {note}')
        self.live.setText('Em direto · '+datetime.now().astimezone().strftime('%H:%M:%S'))
        self.live.setToolTip(f'Nova consulta a cada {self.timer.interval()/1000:g} s; suspensa ao sair da página.')

    def failed(self,message):
        self.job=None
        self.live.setText('Nova tentativa automática')
        self.note.setText('Informação indisponível nesta consulta. A atualização automática voltará a tentar.')
        self.note.setToolTip(message)
