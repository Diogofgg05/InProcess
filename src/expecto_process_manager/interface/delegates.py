from PySide6.QtWidgets import QStyledItemDelegate,QApplication,QStyle,QHeaderView
from PySide6.QtCore import Qt,QRect,QSize
from PySide6.QtGui import QColor,QLinearGradient,QBrush,QFont,QPainter,QPolygonF,QPen
from PySide6.QtCore import QPointF


class NavigationDelegate(QStyledItemDelegate):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.symbol_cache={}

    def paint(self,painter,option,index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        rect=option.rect.adjusted(0,1,0,-1)
        dark=QApplication.instance().property('dark') is not False
        selected=bool(option.state & QStyle.State_Selected)
        scale=QApplication.instance().property('densityScale') or 1.
        if index.row() in (6,8):
            painter.setPen(QPen(QColor('#263241' if dark else '#e4ebf5'),1))
            painter.drawLine(rect.left()+12,rect.top()+1,rect.right()-12,rect.top()+1)
            rect=rect.adjusted(0,5,0,0)
        if selected:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor('#1c3350' if dark else '#e8f1ff'))
            painter.drawRoundedRect(rect,10,10)
            painter.setBrush(QColor('#438fff' if dark else '#1478f5'))
            painter.drawRoundedRect(QRect(rect.left()+2,rect.center().y()-round(10*scale),3,round(20*scale)),1.5,1.5)
        elif option.state & QStyle.State_MouseOver:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor('#1a2532' if dark else '#f0f4fa'))
            painter.drawRoundedRect(rect,10,10)
        symbol=index.data(Qt.DecorationRole)
        icon_size=max(17,round(22*scale))
        icon_rect=QRect(rect.left()+round(12*scale),rect.center().y()-icon_size//2,icon_size,icon_size)
        if symbol:
            color='#5a9dff' if selected and dark else '#1478f5' if selected else '#a7b8ce' if dark else '#5b6c86'
            key=(symbol.cacheKey(),icon_size,color)
            pixmap=self.symbol_cache.get(key)
            if pixmap is None:
                pixmap=symbol.pixmap(icon_size,icon_size)
                tint=QPainter(pixmap)
                tint.setCompositionMode(QPainter.CompositionMode_SourceIn)
                tint.fillRect(pixmap.rect(),QColor(color)); tint.end()
                if len(self.symbol_cache)>=96: self.symbol_cache.clear()
                self.symbol_cache[key]=pixmap
            painter.drawPixmap(icon_rect,pixmap)
        font=QFont(option.font)
        font.setPixelSize(max(11,round(14*(QApplication.instance().property('densityScale') or 1.))))
        font.setWeight(QFont.DemiBold if selected else QFont.Normal)
        painter.setFont(font)
        painter.setPen(QColor('#76b0ff' if selected and dark else '#1267d5' if selected else '#bdcde5' if dark else '#34445e'))
        painter.drawText(rect.adjusted(round(48*scale),0,-5,0),Qt.AlignLeft|Qt.AlignVCenter,index.data())
        painter.restore()


class ProcessDelegate(QStyledItemDelegate):
    def sizeHint(self,option,index):
        size=super().sizeHint(option,index)
        size.setHeight(round(49*(QApplication.instance().property('densityScale') or 1.)))
        return size

    def paint(self,painter,option,index):
        if index.column()!=0:
            return super().paint(painter,option,index)
        painter.save()
        self.initStyleOption(option,index)
        dark=QApplication.instance().property('dark') is not False
        selected=bool(option.state & QStyle.State_Selected)
        if selected: painter.fillRect(option.rect,QColor('#1b2430' if dark else '#dce8ff'))
        painter.setPen(QColor('#1a232e' if dark else '#e3e8ef'))
        painter.drawLine(option.rect.bottomLeft(),option.rect.bottomRight())
        symbol=index.data(Qt.DecorationRole)
        scale=QApplication.instance().property('densityScale') or 1.
        size=max(18,round(28*scale))
        if symbol: symbol.paint(painter,QRect(option.rect.left()+round(16*scale),option.rect.center().y()-size//2,size,size))
        painter.setFont(option.font)
        painter.setPen(QColor('#e5edfb' if dark else '#172033'))
        text=option.fontMetrics.elidedText(index.data(),Qt.ElideRight,option.rect.width()-round(65*scale))
        painter.drawText(option.rect.adjusted(round(57*scale),0,-8,0),Qt.AlignLeft|Qt.AlignVCenter,text)
        painter.restore()


class ProcessHeader(QHeaderView):
    def __init__(self,parent=None):
        super().__init__(Qt.Horizontal,parent)
        self.setSectionsClickable(True)

    def paintSection(self,painter,rect,logical_index):
        if logical_index!=0:
            return super().paintSection(painter,rect,logical_index)
        painter.save()
        dark=QApplication.instance().property('dark') is not False
        painter.fillRect(rect,QColor('#0c1117' if dark else '#f8f9fb'))
        painter.setPen(QColor('#252f3d' if dark else '#dce2eb'))
        painter.drawLine(rect.bottomLeft(),rect.bottomRight())
        font=QFont(self.font())
        font.setPixelSize(14)
        font.setWeight(QFont.Normal)
        painter.setFont(font)
        painter.setPen(QColor('#b0c1dc' if dark else '#566780'))
        painter.drawText(rect.adjusted(14,0,-10,0),Qt.AlignLeft|Qt.AlignVCenter,'Nome')
        if self.isSortIndicatorShown() and self.sortIndicatorSection()==0:
            x,y=rect.left()+66,rect.center().y()
            direction=-1 if self.sortIndicatorOrder()==Qt.AscendingOrder else 1
            painter.setRenderHint(QPainter.Antialiasing)
            painter.drawPolyline(QPolygonF([QPointF(x-3,y-direction*2),QPointF(x,y+direction*2),QPointF(x+3,y-direction*2)]))
        painter.restore()
