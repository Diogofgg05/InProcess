from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLineEdit,QComboBox,QTableView,
                              QLabel,QPushButton,QAbstractItemView,QHeaderView,QMenu,QToolButton)
from PySide6.QtCore import Qt,Signal,QAbstractTableModel,QSortFilterProxyModel,QModelIndex,QSize
from .theme import icon
from .delegates import ProcessDelegate,ProcessHeader
from .process_groups import ProcessGroups,ProcessTree,IDENTITY_ROLE


class ProcessModel(QAbstractTableModel):
    columns = [('name','Nome'),('pid','PID'),('cpu','CPU'),('memory','Memória'),
               ('disk','Disco'),('network','Rede'),('gpu','GPU'),('user','Utilizador'),
               ('status','Estado'),('elapsed','Tempo')]

    def __init__(self,parent=None):
        super().__init__(parent)
        self.rows = []
        self.process_icon = icon('process','#669de5')
        self.icons = {}

    def rowCount(self,parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self,parent=QModelIndex()):
        return len(self.columns)

    def headerData(self,section,orientation,role=Qt.DisplayRole):
        if role == Qt.TextAlignmentRole and orientation == Qt.Horizontal:
            return int(Qt.AlignLeft|Qt.AlignVCenter)
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.columns[section][1]

    def data(self,index,role=Qt.DisplayRole):
        if not index.isValid(): return None
        return self.record_data(self.rows[index.row()],index.column(),role)

    def record_data(self,record,column,role=Qt.DisplayRole):
        key = self.columns[column][0]
        value = record.get(key)
        if role == Qt.UserRole: return value
        if role == Qt.DecorationRole and key == 'name': return self.icons.get(record['name'],self.process_icon)
        if role == Qt.ToolTipRole:
            if key=='status' and 'status_age_s' in record:
                return f"{value} · medido há {record['status_age_s']:.1f} s (atualização até 5 s)"
            if value is None: return 'Indisponível ou em aquecimento. Rede/GPU por processo não expostas por este fornecedor.'
            return str(value)
        if role == Qt.TextAlignmentRole and key in ('cpu','memory','disk','network','gpu','pid','elapsed'):
            return int((Qt.AlignLeft if key=='pid' else Qt.AlignHCenter)|Qt.AlignVCenter)
        if role != Qt.DisplayRole: return None
        if value is None: return '—'
        if key in ('cpu','gpu'): return f'{value:.1f}%'.replace('.',',')
        if key == 'memory': return (f'{value/1e9:.1f} GB' if value>=1e9 else f'{value/1e6:.0f} MB').replace('.',',')
        if key == 'disk': return f'{value/1e6:.1f} MB/s'.replace('.',',')
        if key == 'network': return f'{value*8/1e6:.1f} Mb/s'.replace('.',',')
        if key == 'name': return value.removesuffix('.exe')
        if key == 'elapsed': return f'{value/3600:.1f} h' if value >= 3600 else f'{value:.0f} s'
        return str(value)

    def update(self,rows):
        old_keys = [(r['pid'],r['created']) for r in self.rows]
        new_keys = [(r['pid'],r['created']) for r in rows]
        if old_keys == new_keys:
            self.rows = rows
            if rows:
                self.dataChanged.emit(self.index(0,0),self.index(len(rows)-1,len(self.columns)-1),
                                      [Qt.DisplayRole,Qt.ToolTipRole,Qt.UserRole])
            return
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def notify_icons(self,names):
        affected=[i for i,row in enumerate(self.rows) if row['name'] in names]
        if affected:
            self.dataChanged.emit(self.index(affected[0],0),self.index(affected[-1],0),[Qt.DecorationRole])


class ProcessProxy(QSortFilterProxyModel):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.query = ''
        self.mode = 0
        self.setSortRole(Qt.UserRole)

    def filterAcceptsRow(self,row,parent):
        return self.accepts_record(self.sourceModel().rows[row])

    def accepts_record(self,r):
        return (self.query in f"{r['name']} {r['pid']} {r['user']}".casefold()
                and (self.mode != 1 or (r.get('cpu') or 0) > 0)
                and (self.mode != 2 or r['memory'] > 100*1024**2)
                and (self.mode != 3 or r.get('kind') == 'application')
                and (self.mode != 4 or r.get('kind') == 'service')
                and (self.mode != 5 or r.get('kind') == 'process'))

    def lessThan(self,left,right):
        source=self.sourceModel()
        key=source.columns[left.column()][0]
        a,b = source.rows[left.row()].get(key),source.rows[right.row()].get(key)
        if a is None: return b is not None
        if b is None: return False
        if isinstance(a,str): return a.casefold() < str(b).casefold()
        return a < b


class ProcessesPage(QWidget):
    action = Signal(object,str)

    def __init__(self):
        super().__init__()
        self.rows = []
        self._display_active=True
        self._pending_rows=False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,25,0,0)
        layout.setSpacing(0)
        title = QLabel('Processos')
        title.setObjectName('title')
        title.setIndent(8)
        title.setFixedHeight(34)
        layout.addWidget(title)
        layout.addSpacing(18)
        bar = QHBoxLayout()
        bar.setSpacing(8)
        bar.setContentsMargins(8,0,0,0)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Procurar processos...')
        self.search.addAction(icon('search'),QLineEdit.LeadingPosition)
        for button in self.search.findChildren(QToolButton): button.setIconSize(QSize(24,24))
        self.search.setFixedHeight(43)
        self.filter = QComboBox()
        self.filter.setMinimumWidth(145)
        self.filter.setMaximumWidth(204)
        self.filter.addItems(['Todos os processos','Ativos (CPU > 0)','RAM > 100 MiB','Aplicações identificadas','Serviços identificados','Outros processos identificados'])
        self.filter.setToolTip('Windows: janelas visíveis e PIDs de serviços (cache 10 s). Linux: unidades cgroup .service/app-.scope. Classificação aproximada; processos desconhecidos só aparecem em Todos.')
        bar.addWidget(self.search,1)
        bar.addWidget(self.filter)
        self.grouping=QComboBox()
        self.grouping.addItems(['Pastas de processos','Lista de processos'])
        self.grouping.setToolTip('Agrupa pelo nome do executável e utilizador; não representa uma árvore de parentesco do sistema.')
        self.grouping.setMinimumWidth(140); self.grouping.setMaximumWidth(190)
        bar.addWidget(self.grouping)
        layout.addLayout(bar)
        self.insights_label = QLabel()
        self.insights_label.setObjectName('muted')
        self.insights_label.setTextFormat(Qt.PlainText)
        self.insights_label.setWordWrap(True)
        self.insights_label.setMargin(8)
        self.insights_label.setToolTip(
            'Observações de amostras consecutivas, não diagnósticos de avarias. '
            'Não é realizada qualquer otimização automática.'
        )
        self.insights_label.hide()
        layout.addWidget(self.insights_label)
        layout.addSpacing(20)
        self.model = ProcessModel(self)
        self.proxy = ProcessProxy(self)
        self.proxy.setSourceModel(self.model)
        # The grouped view sorts its own records. Keep the hidden flat proxy
        # from repeating that work for every CPU/memory update.
        self.proxy.setDynamicSortFilter(False)
        self.groups=ProcessGroups(self.proxy,self)
        self.table = QTableView()
        self.table.setHorizontalHeader(ProcessHeader(self.table))
        self.table.setModel(self.proxy)
        self.delegate=ProcessDelegate(self.table)
        self.table.setItemDelegate(self.delegate)
        self.table.setIconSize(QSize(28,28))
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(49)
        self.table.horizontalHeader().setFixedHeight(45)
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Interactive)
        self.table.horizontalHeader().setMinimumSectionSize(65)
        for i,width in enumerate([291,83,101,130,126,88,75,160,100,90]):
            self.table.setColumnWidth(i,width)
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        self.table.horizontalHeader().setMinimumSectionSize(70)
        columns = QPushButton('Colunas')
        menu = QMenu(columns)
        for i,(_,title) in enumerate(self.model.columns):
            action = menu.addAction(title)
            action.setCheckable(True)
            action.setChecked(i<6)
            if i==0: action.setEnabled(False)
            self.table.setColumnHidden(i,i>=6)
            action.toggled.connect(lambda checked,column=i:self.table.setColumnHidden(column,not checked))
        columns.setMenu(menu)
        self.columns_button=columns
        columns.setParent(self)
        columns.hide()
        self.table.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.horizontalHeader().customContextMenuRequested.connect(lambda point:menu.exec(self.table.horizontalHeader().mapToGlobal(point)))
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0,Qt.AscendingOrder)
        layout.addWidget(self.table,1)
        self.tree=ProcessTree()
        self.tree.setModel(self.groups)
        self.tree.setItemDelegate(ProcessDelegate(self.tree))
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setIndentation(22)
        self.tree.setAnimated(False)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree.setSortingEnabled(True); self.tree.sortByColumn(0,Qt.AscendingOrder)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0,QHeaderView.Stretch)
        for i,width in enumerate([291,102,90,115,100,85,75,160,100,90]):
            if i: self.tree.setColumnWidth(i,width)
            self.tree.setColumnHidden(i,self.table.isColumnHidden(i))
        for i,action in enumerate(menu.actions()):
            action.toggled.connect(lambda checked,c=i:self.tree.setColumnHidden(c,not checked))
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.context_menu)
        self.tree.doubleClicked.connect(lambda index:self.show_details() if index.internalId() else None)
        self.tree.selectionModel().selectionChanged.connect(self.selection)
        self.tree.header().setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.header().customContextMenuRequested.connect(lambda point:menu.exec(self.tree.header().mapToGlobal(point)))
        layout.addWidget(self.tree,1)
        self.table.hide()
        self._expanded=set()
        self.groups.expanded_keys=self._expanded
        self.tree.expanded.connect(lambda index:self._expanded.add(self.groups.identity(index)))
        self.tree.collapsed.connect(lambda index:self._expanded.discard(self.groups.identity(index)))
        self.grouping.currentIndexChanged.connect(self.change_view)
        self.details = QLabel('Selecione um processo · CPU: 100% por núcleo · — = indisponível/aquecimento')
        self.details.setObjectName('muted')
        self.details.setWordWrap(True)
        self.details.hide()
        actions = QHBoxLayout()
        actions.addStretch()
        self.buttons = []
        for text,action in [('Suspender','suspend'),('Continuar','resume'),('Terminar processo','terminate')]:
            button = QPushButton(text)
            if action == 'terminate': button.setObjectName('danger')
            button.setEnabled(False)
            button.clicked.connect(lambda checked=False,a=action:self.request(a))
            self.buttons.append(button)
            button.setParent(self)
            button.hide()
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.context_menu)
        self.table.doubleClicked.connect(lambda _:self.show_details())
        self.search.textChanged.connect(self.render)
        self.filter.currentIndexChanged.connect(self.render)
        self.table.selectionModel().selectionChanged.connect(self.selection)

    def show_insights(self, insights):
        """Present sustained activity as a short, passive, non-clickable notice."""
        message = "  •  ".join(insight.message for insight in insights[:2])
        if message != self.insights_label.text():
            self.insights_label.setText(message)
        if self.insights_label.isHidden() == bool(message):
            self.insights_label.setVisible(bool(message))

    def show_details(self):
        from PySide6.QtWidgets import QMessageBox
        row=self.selected()
        if row:
            age = row.get('status_age_s',0)
            QMessageBox.information(self,'Detalhes do processo',f"Nome: {row['name']}\nPID: {row['pid']}\nUtilizador: {row['user']}\nEstado: {row['status']} (medido há {age:.1f} s)\nTempo: {row['elapsed']:.0f} s\nCPU: 100% corresponde a um núcleo lógico.")

    def context_menu(self,point):
        view=self.active_view()
        index=view.indexAt(point)
        if not index.isValid(): return
        view.setCurrentIndex(index)
        menu=QMenu(view)
        if view is self.tree and not index.internalId():
            root=index.siblingAtColumn(0)
            menu.addAction('Recolher pasta' if view.isExpanded(root) else 'Expandir pasta',
                           lambda:view.setExpanded(root,not view.isExpanded(root)))
            menu.exec(view.viewport().mapToGlobal(point)); return
        menu.addAction('Detalhes',self.show_details)
        menu.addSeparator()
        for text,action in [('Suspender','suspend'),('Continuar','resume'),('Terminar processo','terminate')]:
            menu.addAction(text,lambda checked=False,a=action:self.request(a))
        menu.exec(view.viewport().mapToGlobal(point))

    def active_view(self): return self.tree if self.grouping.currentIndex()==0 else self.table

    def change_view(self,*_):
        grouped=self.grouping.currentIndex()==0
        self.tree.setVisible(grouped); self.table.setVisible(not grouped)
        self.proxy.setDynamicSortFilter(not grouped)
        if not grouped: self.proxy.invalidate()
        self.groups.set_active(grouped)
        if grouped:
            for identity in self._expanded:
                index=self.groups.find(identity)
                if index.isValid(): self.tree.setExpanded(index,True)
        self.selection()

    def selected(self):
        if not self._display_active: return None
        if self.grouping.currentIndex()==0:
            return self.groups.record(self.tree.currentIndex())
        selection = self.table.selectionModel().selectedRows()
        if not selection: return None
        index = self.proxy.mapToSource(selection[0])
        return self.model.rows[index.row()]

    def selection(self,*_):
        row = self.selected()
        for button in self.buttons: button.setEnabled(row is not None)
        if row:
            self.details.setText(f"{row['name']} · PID {row['pid']} · {row['user']} · {row['status']} · {row['elapsed']:.0f} s · CPU 100% por núcleo")
        else:
            self.details.setText('Selecione um processo · — = indisponível/aquecimento')

    def request(self,action):
        row = self.selected()
        if row: self.action.emit(row,action)

    def update_rows(self,rows):
        # Always retain the newest full snapshot for exports and diagnostics.
        # Only the visual model is coalesced while another page is selected.
        self.rows=rows
        if not self._display_active:
            self._pending_rows=True
            return
        self._pending_rows=False
        selected = self.selected()
        grouped=self.grouping.currentIndex()==0
        group_identity=self.groups.identity(self.tree.currentIndex()) if grouped else None
        expanded=set(self._expanded)
        with self.groups.batch_updates(): self.model.update(rows)
        if grouped:
            for identity in expanded:
                index=self.groups.find(identity)
                if index.isValid(): self.tree.setExpanded(index,True)
        if group_identity:
            index=self.groups.find(group_identity)
            if index.isValid(): self.tree.setCurrentIndex(index)
        if selected and not grouped:
            key = selected['pid'],selected['created']
            for i,row in enumerate(rows):
                if (row['pid'],row['created']) == key:
                    index = self.proxy.mapFromSource(self.model.index(i,0))
                    if index.isValid(): self.table.selectRow(index.row())
                    break
        self.selection()
        if not grouped and not selected and self.proxy.rowCount(): self.table.selectRow(0)

    def set_display_active(self,active):
        self._display_active=active
        if active and self._pending_rows: self.update_rows(self.rows)

    def render(self,*_):
        expanded=set(self._expanded)
        with self.groups.batch_updates():
            self.proxy.beginFilterChange()
            self.proxy.query = self.search.text().casefold()
            self.proxy.mode = self.filter.currentIndex()
            self.proxy.endFilterChange(QSortFilterProxyModel.Direction.Rows)
        for identity in expanded:
            index=self.groups.find(identity)
            if index.isValid(): self.tree.setExpanded(index,True)
        self.selection()
        if self.search.text(): self.tree.expandAll()
