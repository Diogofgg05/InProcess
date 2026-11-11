from PySide6.QtWidgets import QTabWidget,QWidget
from PySide6.QtCore import Qt


class LazyTabs(QTabWidget):
    """Construct chart-heavy pages only when they are opened or requested."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self.factories=[]
        self.created={}
        self._building=False
        self.setUsesScrollButtons(True)
        self.tabBar().setElideMode(Qt.ElideNone)
        self.currentChanged.connect(self._selected)

    def add_lazy(self,title,factory):
        self.factories.append(factory)
        self.addTab(QWidget(),title)

    def ensure(self,index):
        if index in self.created: return self.created[index]
        if self._building: return self.widget(index)
        self._building=True
        try:
            widget=self.factories[index]()
            self.created[index]=widget
            title=self.tabText(index)
            visible=self.isTabVisible(index)
            selected=self.currentIndex()
            old=self.widget(index)
            self.blockSignals(True)
            try:
                self.removeTab(index)
                self.insertTab(index,widget,title)
                self.setTabVisible(index,visible)
                self.setCurrentIndex(selected)
            finally:
                self.blockSignals(False)
            old.deleteLater()
            return widget
        finally:
            self._building=False

    def _selected(self,index):
        if self.isVisible() and index>=0 and not self._building: self.ensure(index)

    def showEvent(self,event):
        super().showEvent(event)
        self._selected(self.currentIndex())
