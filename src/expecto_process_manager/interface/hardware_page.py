"""Lazy, asynchronous hardware inventory with explicit provenance."""
from __future__ import annotations

import csv
import json
import os
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt, Signal,QTimer
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QHeaderView, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QStyledItemDelegate, QToolButton, QTreeView,
    QVBoxLayout, QWidget,
)

from ..core.hardware import HardwareInventory, detect_hardware


class WrappedHardwareDelegate(QStyledItemDelegate):
    """Tree rows account for wrapping in every column, including provenance."""

    def __init__(self, tree):
        super().__init__(tree)
        self.tree = tree

    def sizeHint(self, option, index):
        self.initStyleOption(option, index)
        width = self.tree.columnWidth(index.column()) - 18
        if index.column() == 0:
            width -= self.tree.indentation() * (2 if index.parent().isValid() else 1)
        rect = option.fontMetrics.boundingRect(QRect(0, 0, max(40, width), 10000), Qt.TextFlag.TextWordWrap, option.text)
        return QSize(max(40, width), max(option.fontMetrics.height() + 12, rect.height() + 14))


def export_hardware(path: str | Path, inventory: HardwareInventory, token=None) -> str:
    """Atomic UTF-8 CSV or JSON export, called in a worker."""
    destination = Path(path)
    if destination.suffix.lower() not in {".csv", ".json"}:
        raise ValueError("Escolha a extensão .csv ou .json.")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig" if destination.suffix.lower() == ".csv" else "utf-8", newline="", dir=destination.parent, delete=False) as stream:
            temporary = stream.name
            if token:
                token.check()
            if destination.suffix.lower() == ".json":
                json.dump(inventory.as_dict(), stream, ensure_ascii=False, indent=2)
            else:
                writer = csv.DictWriter(stream, fieldnames=["collected_at", "platform", "category", "name", "value", "source"])
                writer.writeheader()
                for item in inventory.items:
                    if token:
                        token.check()
                    writer.writerow({"collected_at": inventory.collected_at, "platform": inventory.platform,
                                     "category": item.category, "name": item.name, "value": item.value, "source": item.source})
                for note in inventory.notes:
                    writer.writerow({"collected_at": inventory.collected_at, "platform": inventory.platform,
                                     "category": "Notas / limitações", "name": "Nota", "value": note, "source": "InProcess"})
        if token:
            token.check()
        os.replace(temporary, destination)
        return str(destination)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


class HardwarePage(QWidget):
    """No detection during construction or the monitoring timer's callback."""
    inventory_ready=Signal(object)

    def __init__(self, tasks, parent=None):
        super().__init__(parent)
        self.tasks = tasks
        self.loaded = False
        self.busy = False
        self.timer=QTimer(self)
        self.timer.setInterval(60000)
        self.timer.timeout.connect(lambda:self.refresh(force=False))
        self.inventory: HardwareInventory | None = None
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        title = QLabel("Hardware do computador")
        title.setObjectName("title")
        layout.addWidget(title)
        self.summary = QLabel("Inventário de leitura, carregado ao abrir esta página. Sem privilégios administrativos.")
        self.summary.setWordWrap(True)
        self.summary.setObjectName("muted")
        layout.addWidget(self.summary)
        toolbar = QHBoxLayout()
        self.export_csv_button = QPushButton("Exportar CSV")
        self.export_csv_button.clicked.connect(lambda: self.export("csv"))
        toolbar.addWidget(self.export_csv_button)
        self.export_json_button = QPushButton("Exportar JSON")
        self.export_json_button.clicked.connect(lambda: self.export("json"))
        toolbar.addWidget(self.export_json_button)
        toolbar.addStretch()
        layout.addLayout(toolbar)
        self.tree = QTreeView()
        self.tree.setWordWrap(True)
        self.tree.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.tree.setUniformRowHeights(False)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setAlternatingRowColors(False)
        self.tree.setStyleSheet("QTreeView {border: none; outline: none;} QTreeView::item {padding: 5px 2px;}")
        self.tree.setItemDelegate(WrappedHardwareDelegate(self.tree))
        self.tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tree.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.model = QStandardItemModel(self)
        self.model.setHorizontalHeaderLabels(["Componente", "Informação detetada", "Origem"])
        self.tree.setModel(self.model)
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tree.setColumnWidth(0, 230)
        self.tree.setColumnWidth(2, 250)
        self.tree.header().sectionResized.connect(lambda *_: self.tree.doItemsLayout())
        layout.addWidget(self.tree, 1)
        self.notes = QLabel("Os campos indisponíveis são identificados; nenhuma capacidade ou leitura de sensor é inventada.")
        self.notes.setWordWrap(True)
        self.notes.setTextFormat(Qt.TextFormat.PlainText)
        self.notes.setObjectName("muted")
        self.notes_toggle = QToolButton()
        self.notes_toggle.setText("Fontes e limitações")
        self.notes_toggle.setCheckable(True)
        self.notes_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.notes_toggle.setArrowType(Qt.ArrowType.RightArrow)
        layout.addWidget(self.notes_toggle)
        self.notes_area = QScrollArea()
        self.notes_area.setWidgetResizable(True)
        self.notes_area.setMaximumHeight(140)
        self.notes_area.setWidget(self.notes)
        self.notes_area.hide()
        self.notes_toggle.toggled.connect(self._toggle_notes)
        layout.addWidget(self.notes_area)
        self._buttons()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh(force=False)
        self.timer.start()

    def hideEvent(self,event):
        self.timer.stop()
        super().hideEvent(event)

    def _toggle_notes(self, checked):
        self.notes_area.setVisible(checked)
        self.notes_toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)

    def refresh(self, *, force=True):
        if self.busy:
            return
        self.loaded = True
        self.busy = True
        self._buttons()
        self.summary.setText("A consultar o hardware em segundo plano… A consulta Windows tem um limite de 8 s.")
        self.tasks.start(lambda token: detect_hardware(token, refresh=force), self.display, self.failed)

    def _buttons(self):
        self.export_csv_button.setEnabled(self.inventory is not None and not self.busy)
        self.export_json_button.setEnabled(self.inventory is not None and not self.busy)

    def _summary(self):
        if self.inventory:
            collected = time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(self.inventory.collected_at))
            self.summary.setText(f"{self.inventory.platform} · {len(self.inventory.items)} campos · recolhido em {collected} · atualização automática · cache de 10 min.")

    def display(self, inventory):
        self.inventory = inventory
        self.busy = False
        self.model.removeRows(0, self.model.rowCount())
        categories = {}
        for item in inventory.items:
            if item.category not in categories:
                group = QStandardItem(item.category)
                font = group.font()
                font.setBold(True)
                group.setFont(font)
                self.model.appendRow([group, QStandardItem(""), QStandardItem("")])
                categories[item.category] = group
            row = [QStandardItem(value) for value in (item.name, item.value, item.source)]
            for cell in row:
                cell.setToolTip(cell.text())
            categories[item.category].appendRow(row)
        self.tree.expandAll()
        self.notes.setText("\n".join(inventory.notes))
        self.notes_toggle.setText(f"Fontes e limitações ({len(inventory.notes)})")
        self._summary()
        self._buttons()
        self.inventory_ready.emit(inventory)

    def failed(self, message):
        self.busy = False
        self.summary.setText(f"Não foi possível concluir a consulta: {message}")
        self._buttons()

    def export(self, extension):
        if not self.inventory or self.busy:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exportar inventário de hardware", f"hardware.{extension}", f"{extension.upper()} (*.{extension})")
        if not path:
            return
        if not Path(path).suffix:
            path += f".{extension}"
        self.busy = True
        self._buttons()
        self.tasks.start(lambda token: export_hardware(path, self.inventory, token), self._exported, self.failed)

    def _exported(self, path):
        self.busy = False
        self._summary()
        self.summary.setText(self.summary.text() + f" Exportado: {Path(path).name}.")
        self._buttons()
