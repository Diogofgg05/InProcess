"""Full chart labels that wrap instead of being shortened with ellipses."""
from PySide6.QtWidgets import QWidget,QLayout,QHBoxLayout,QLabel
from PySide6.QtCore import Qt,QRect,QSize


class FlowLayout(QLayout):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.items=[]
        self.setContentsMargins(0,0,0,0)
        self.setSpacing(10)

    def addItem(self,item): self.items.append(item)
    def count(self): return len(self.items)
    def itemAt(self,index): return self.items[index] if 0<=index<len(self.items) else None
    def takeAt(self,index): return self.items.pop(index) if 0<=index<len(self.items) else None
    def expandingDirections(self): return Qt.Orientations()
    def hasHeightForWidth(self): return True
    def heightForWidth(self,width): return self.arrange(QRect(0,0,max(1,width),0),True)
    def sizeHint(self): return self.minimumSize()

    def minimumSize(self):
        size=QSize(1,1)
        for item in self.items: size=size.expandedTo(item.minimumSize())
        return size

    def setGeometry(self,rect):
        super().setGeometry(rect)
        self.arrange(rect,False)

    def arrange(self,rect,test):
        x,y,line_height=rect.x(),rect.y(),0
        width=max(1,rect.width())
        for item in self.items:
            w=min(width,item.sizeHint().width())
            h=item.heightForWidth(w) if item.hasHeightForWidth() else item.sizeHint().height()
            h=max(h,18)
            if x>rect.x() and x+w>rect.x()+width:
                x=rect.x(); y+=line_height+4; line_height=0
            if not test: item.setGeometry(QRect(x,y,w,h))
            x+=w+self.spacing()
            line_height=max(line_height,h)
        return y-rect.y()+line_height


class SeriesLegend(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.flow=FlowLayout(self)
        self.entries=()

    def set_entries(self,entries):
        entries=tuple(entries)
        if entries==self.entries: return
        self.entries=entries
        while self.flow.count():
            item=self.flow.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        for name,color in entries:
            cell=QWidget()
            cell.setStyleSheet('background: transparent;')
            row=QHBoxLayout(cell)
            row.setContentsMargins(0,0,0,0)
            row.setSpacing(6)
            swatch=QLabel()
            swatch.setFixedSize(13,4)
            swatch.setStyleSheet(f'background: {color}; border-radius: 2px;')
            label=QLabel(name)
            label.setWordWrap(True)
            label.setStyleSheet('font-size: 12px; background: transparent;')
            label.setToolTip(name)
            row.addWidget(swatch)
            row.addWidget(label)
            self.flow.addWidget(cell)
        self.updateGeometry()


def series_color(name,index=0):
    lower=name.casefold()
    if 'analítica' in lower or 'referência' in lower:
        from PySide6.QtWidgets import QApplication
        return '#d9e6ff' if QApplication.instance() and QApplication.instance().property('dark') else '#294163'
    if 'rk4' in lower or 'runge' in lower: return '#00b967'
    if 'heun' in lower: return '#9351f5'
    if 'euler' in lower and 'simpl' not in lower: return '#069dff'
    colors={'Euler':'#21b9ff','Euler explícito':'#21b9ff','Euler expl.':'#21b9ff',
            'Euler simplético':'#b366ff','Euler simpl.':'#b366ff','Heun':'#b366ff',
            'RK4':'#28d58b','Velocity Verlet':'#28d58b','Verlet':'#28d58b',
            'Analítica':'#e6b454','Referência analítica':'#e6b454','Referência circular':'#e6b454',
            'Ref. ZOH':'#e6b454','Referência por intervalo':'#e6b454'}
    return colors.get(name,['#21b9ff','#b366ff','#28d58b','#e6b454','#fa875f'][index%5])
