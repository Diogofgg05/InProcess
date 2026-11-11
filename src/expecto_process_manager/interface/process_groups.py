"""Expandable executable groups over the existing filtered process model.

Grouping is by executable name and user, not an invented OS parent/child tree.
Only child rows map to a process that may be controlled.
"""
from dataclasses import dataclass
from contextlib import contextmanager
from PySide6.QtCore import QAbstractItemModel,QModelIndex,Qt,QItemSelectionModel
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QTreeView,QApplication
from .theme import icon

IDENTITY_ROLE=Qt.UserRole+1


@dataclass
class Group:
    key: tuple
    children: list
    totals: dict


class ProcessTree(QTreeView):
    def selectRow(self,row):
        index=self.model().index(row,0)
        self.setCurrentIndex(index)
        self.selectionModel().select(index,QItemSelectionModel.ClearAndSelect|QItemSelectionModel.Rows)


class ProcessGroups(QAbstractItemModel):
    def __init__(self,proxy,parent=None):
        super().__init__(parent)
        self.proxy=proxy
        self.groups=[]
        self._column=0; self._order=Qt.AscendingOrder
        self._records=[]
        self.active=True
        self._batch_depth=0
        self._pending=False
        self.expanded_keys=None
        self.folder_icon=icon('folder','#3689f5')
        for signal in (proxy.modelReset,proxy.layoutChanged,proxy.rowsInserted,proxy.rowsRemoved):
            signal.connect(self.rebuild)
        proxy.sourceModel().dataChanged.connect(self.source_changed)

    def source_changed(self,first,last,roles):
        if roles and all(role==Qt.DecorationRole for role in roles):
            # Icons do not affect membership, totals, filters or sort order.
            # Notify the name column without rebuilding the process tree.
            if not self.active or self._pending: return
            affected=[]
            for i,group in enumerate(self.groups):
                children=[j for j,source in enumerate(group.children) if first.row()<=source<=last.row()]
                if not children: continue
                affected.append(i)
                if self.expanded_keys is None or ('group',group.key) in self.expanded_keys:
                    root=self.index(i,0)
                    self.dataChanged.emit(self.index(children[0],0,root),self.index(children[-1],0,root),[Qt.DecorationRole])
            if affected:
                self.dataChanged.emit(self.index(affected[0],0),self.index(affected[-1],0),[Qt.DecorationRole])
            return
        self.rebuild()

    def rebuild(self,*_):
        if self._batch_depth or not self.active:
            self._pending=True
            return
        self._pending=False
        records=self.proxy.sourceModel().rows
        buckets={}
        field=self.proxy.sourceModel().columns[self._column][0]
        def ordering_value(value):
            return (value is not None,value.casefold() if isinstance(value,str) else value if value is not None else 0)
        for source,row in enumerate(records):
            if not self.proxy.accepts_record(row): continue
            key=(row['name'].casefold(),row.get('user',''))
            buckets.setdefault(key,[]).append(source)
        groups=[]
        for key,children in buckets.items():
            children.sort(key=lambda i:ordering_value(records[i].get(field)),reverse=self._order==Qt.DescendingOrder)
            members=[records[i] for i in children]
            totals={'name':members[0]['name'],'pid':None,'user':key[1],'status':'grupo','elapsed':None}
            for measure in ('cpu','memory','disk','network','gpu'):
                values=[r.get(measure) for r in members]
                totals[measure]=sum(values) if all(v is not None for v in values) else None
            groups.append(Group(key,children,totals))
        field=self.proxy.sourceModel().columns[self._column][0]
        def ordering(group):
            value=group.totals.get(field)
            return (value is not None,value.casefold() if isinstance(value,str) else value if value is not None else 0,group.key)
        groups.sort(key=ordering,reverse=self._order==Qt.DescendingOrder)
        def structure(items):
            rows=self.proxy.sourceModel().rows
            return [(g.key,tuple((rows[i]['pid'],rows[i]['created']) for i in g.children)) for g in items]
        # Old child indices refer to the previous flat snapshot after a reset;
        # compare cached process identities, rather than dereferencing them.
        signature=structure(groups)
        self._lookup={}
        for i,g in enumerate(groups):
            self._lookup[('group',g.key)]=(i,None)
            for j,source in enumerate(g.children):
                row=records[source]
                self._lookup[('process',row['pid'],row['created'])]=(i,j)
        if signature==getattr(self,'_signature',None):
            self._records=records
            self.groups=groups
            if groups: self.dataChanged.emit(self.index(0,0),self.index(len(groups)-1,self.columnCount()-1))
            for i,g in enumerate(groups):
                if g.children and (self.expanded_keys is None or ('group',g.key) in self.expanded_keys):
                    root=self.index(i,0)
                    self.dataChanged.emit(self.index(0,0,root),self.index(len(g.children)-1,self.columnCount()-1,root))
        else:
            self.beginResetModel(); self._records=records; self.groups=groups; self._signature=signature; self.endResetModel()

    @contextmanager
    def batch_updates(self):
        self._batch_depth+=1
        try: yield
        finally:
            self._batch_depth-=1
            if not self._batch_depth and self._pending and self.active: self.rebuild()

    def set_active(self,active):
        self.active=active
        if active and self._pending: self.rebuild()

    def rowCount(self,parent=QModelIndex()):
        if not parent.isValid(): return len(self.groups)
        if parent.column()!=0 or parent.internalId()!=0: return 0
        return len(self.groups[parent.row()].children)

    def columnCount(self,parent=QModelIndex()): return len(self.proxy.sourceModel().columns)

    def index(self,row,column,parent=QModelIndex()):
        if row<0 or column<0 or column>=self.columnCount() or row>=self.rowCount(parent): return QModelIndex()
        return self.createIndex(row,column,parent.row()+1 if parent.isValid() else 0)

    def parent(self,index):
        return self.createIndex(index.internalId()-1,0,0) if index.isValid() and index.internalId() else QModelIndex()

    def headerData(self,section,orientation,role=Qt.DisplayRole):
        return self.proxy.sourceModel().headerData(section,orientation,role)

    def record(self,index):
        if not index.isValid() or not index.internalId(): return None
        group=self.groups[index.internalId()-1]
        return self._records[group.children[index.row()]]

    def identity(self,index): return self.data(index,IDENTITY_ROLE)

    def find(self,identity):
        location=getattr(self,'_lookup',{}).get(identity)
        if location is None: return QModelIndex()
        i,j=location
        root=self.index(i,0)
        return root if j is None else self.index(j,0,root)

    def data(self,index,role=Qt.DisplayRole):
        if not index.isValid(): return None
        record=self.record(index)
        source=self.proxy.sourceModel()
        if record is not None:
            if role==IDENTITY_ROLE: return ('process',record['pid'],record['created'])
            return source.record_data(record,index.column(),role)
        group=self.groups[index.row()]
        field=source.columns[index.column()][0]
        value=group.totals.get(field)
        if role==IDENTITY_ROLE: return ('group',group.key)
        if role==Qt.UserRole: return value
        if role==Qt.DecorationRole and index.column()==0:
            return source.icons.get(group.totals['name'],source.process_icon)
        if role==Qt.FontRole:
            font=QFont(); font.setPixelSize(max(11,round(14*(QApplication.instance().property('densityScale') or 1.))))
            font.setWeight(QFont.DemiBold); return font
        if role==Qt.TextAlignmentRole: return int(Qt.AlignLeft|Qt.AlignVCenter)
        if role==Qt.ToolTipRole:
            return f"{len(group.children)} processos · {group.key[1]}\nAgrupamento por executável e utilizador, sem inferir relações pai-filho.\nMemória: soma por processo, podendo incluir páginas partilhadas.\nTotais indisponíveis quando falta uma medição. Expanda para selecionar um processo."
        if role!=Qt.DisplayRole: return None
        if field=='name': return f"{group.totals['name'].removesuffix('.exe')} ({len(group.children)})"
        if field=='pid': return '—'
        if value is None: return '—'
        if field in ('cpu','gpu'): return f'{value:.1f}%'.replace('.',',')
        if field=='memory': return (f'{value/1e9:.1f} GB' if value>=1e9 else f'{value/1e6:.0f} MB').replace('.',',')
        if field=='disk': return f'{value/1e6:.1f} MB/s'.replace('.',',')
        if field=='network': return f'{value*8/1e6:.1f} Mb/s'.replace('.',',')
        return str(value)

    def sort(self,column,order=Qt.AscendingOrder):
        self._column,self._order=column,order
        with self.batch_updates():
            self.proxy.sort(column,order)
            self.rebuild()
