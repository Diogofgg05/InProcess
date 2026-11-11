"""Bounded two-axis density, applied after resize settles rather than per pixel."""
import re
from PySide6.QtCore import QObject,QTimer,QEvent,QSize,Qt
from PySide6.QtWidgets import (QApplication,QWidget,QLayout,QLabel,QAbstractButton,QLineEdit,
                              QComboBox,QAbstractSpinBox,QTableView,QTreeView,QHeaderView)
from .theme import apply_density
from .charts import Plot


class AdaptiveLayout(QObject):
    def __init__(self,window):
        super().__init__(window)
        self.window=window
        self.timer=QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(80)
        self.timer.timeout.connect(self.apply)
        window.installEventFilter(self)
        window.pages.currentChanged.connect(lambda _:self.timer.start())
        window.laboratory.currentChanged.connect(lambda _:self.timer.start())
        self.apply()

    def eventFilter(self,watched,event):
        if event.type() in (QEvent.Resize,QEvent.Show): self.timer.start()
        return False

    def apply(self):
        w=self.window
        scale=max(.75,min(1.,round(min(w.width()/1500,w.height()/980)/.05)*.05))
        app=QApplication.instance()
        signature=(w.width(),w.height(),w.pages.currentIndex(),
                   tuple(w.laboratory.created),app.property('expectoThemeSignature'))
        if signature==getattr(self,'_signature',None) and app.property('densityScale')==scale:
            return
        self._signature=signature
        self.scale=scale
        w.setProperty('densityScale',scale)
        apply_density(app,scale)
        w.sidebar.setFixedWidth(round(206*scale))
        w.titlebar.setFixedHeight(round(60*scale))
        w.titlebar.adapt(w.width())
        w.footer.setFixedHeight(round(103*scale))
        w.footer.setVisible(w.nav.currentRow() in (0,1) and w.height()>=650)
        w.update_resource_visibility()
        w.nav.setIconSize(QSize(round(24*scale),round(24*scale)))
        for i in range(w.nav.count()): w.nav.item(i).setSizeHint(QSize(round(180*scale),round(51*scale)))
        for widget in w.findChildren(QWidget):
            if isinstance(widget,(QLabel,QAbstractButton,QLineEdit,QComboBox,QAbstractSpinBox)):
                original=widget.property('_densityHeight')
                if original is None and 0<widget.minimumHeight()==widget.maximumHeight()<200:
                    original=widget.height(); widget.setProperty('_densityHeight',original)
                if original:
                    widget.setFixedHeight(max(1 if original<16 else 16,round(original*scale)))
                    if isinstance(widget,QLabel) and widget.pixmap() and not widget.pixmap().isNull():
                        pixmap=widget.property('_densityPixmap')
                        if pixmap is None:
                            pixmap=widget.pixmap().copy(); widget.setProperty('_densityPixmap',pixmap)
                        width=widget.property('_densityIconWidth')
                        if width is None and widget.minimumWidth()==widget.maximumWidth():
                            width=widget.width(); widget.setProperty('_densityIconWidth',width)
                        if width: widget.setFixedWidth(round(width*scale))
                        widget.setPixmap(pixmap.scaled(max(1,round(pixmap.width()*scale)),max(1,round(pixmap.height()*scale)),Qt.KeepAspectRatio,Qt.SmoothTransformation))
                if isinstance(widget,QAbstractButton) and not widget.icon().isNull():
                    original_icon=widget.property('_densityIconSize')
                    if original_icon is None:
                        original_icon=[widget.iconSize().width(),widget.iconSize().height()]
                        widget.setProperty('_densityIconSize',original_icon)
                    widget.setIconSize(QSize(*[max(12,round(value*scale)) for value in original_icon]))
            if isinstance(widget,QTableView):
                widget.verticalHeader().setDefaultSectionSize(round((49 if widget is w.processes.table else 44)*scale))
            if isinstance(widget,(QTableView,QTreeView)):
                header=widget.horizontalHeader() if isinstance(widget,QTableView) else widget.header()
                header.setMinimumHeight(round(36*scale))
            if isinstance(widget,QLabel) and 'font-size:' in widget.styleSheet():
                original=widget.property('_densityInlineStyle')
                if original is None:
                    original=widget.styleSheet(); widget.setProperty('_densityInlineStyle',original)
                updated=re.sub(r'font-size:\s*([\d.]+)px',lambda m:f'font-size: {max(10,round(float(m[1])*scale))}px',original)
                if widget.styleSheet()!=updated: widget.setStyleSheet(updated)
        for layout in w.findChildren(QLayout):
            original=layout.property('_densityMargins')
            if original is None:
                m=layout.contentsMargins(); original=[m.left(),m.top(),m.right(),m.bottom()]
                layout.setProperty('_densityMargins',original)
                layout.setProperty('_densitySpacing',layout.spacing())
            layout.setContentsMargins(*[round(value*scale) for value in original])
            spacing=layout.property('_densitySpacing')
            if spacing is not None and spacing>=0: layout.setSpacing(round(spacing*scale))
        for plot in w.findChildren(Plot):
            plot.view.setMinimumHeight(round(170*scale))
            if plot.minimumHeight()>0: plot.setMinimumHeight(round(260*scale))
            for axis in (plot.x_axis,plot.y_axis):
                font=axis.labelsFont(); font.setPixelSize(max(9,round(12*scale))); axis.setLabelsFont(font)
        w.laboratory.adapt_density(scale)
        for view in (w.processes.table,w.processes.tree):
            for column,width in enumerate((291,102,90,115,100,85,75,160,100,90)):
                if column: view.setColumnWidth(column,max(55,round(width*scale)))
        w.processes.tree.doItemsLayout()
        w.system_label.setVisible(w.height()>=600)
        w.system_icon.setVisible(w.height()>=600)
        w.system_divider.setVisible(w.height()>=600)
