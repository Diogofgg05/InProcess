from PySide6.QtWidgets import QWidget,QVBoxLayout,QApplication,QLabel
from PySide6.QtCharts import QChart,QChartView,QLineSeries,QLogValueAxis,QValueAxis
from PySide6.QtGui import QPainter,QColor,QPen
from PySide6.QtCore import QPointF,Qt,QMargins
from .legend import SeriesLegend,series_color


class Plot(QWidget):
    def __init__(self,title: str,unit: str,logarithmic=False,x_title=None,log_y=False):
        super().__init__()
        self.unit=unit
        self.logarithmic=logarithmic
        self.log_y=log_y
        self.setAttribute(Qt.WA_StyledBackground,True)
        self.chart=QChart()
        self.setObjectName('plotCard')
        self.chart.legend().hide()
        self.chart.setBackgroundRoundness(10)
        self.chart.setMargins(QMargins(5,5,5,5))
        self.view=QChartView(self.chart)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setMinimumHeight(170)
        layout=QVBoxLayout(self)
        layout.setContentsMargins(10,9,10,5)
        layout.setSpacing(3)
        self.title_label=QLabel(title)
        self.title_label.setAlignment(Qt.AlignLeft|Qt.AlignVCenter)
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet('font-size: 14px; font-weight: 600; background: transparent; padding: 3px 5px; border: none;')
        layout.addWidget(self.title_label)
        self.legend=SeriesLegend()
        layout.addWidget(self.legend)
        layout.addWidget(self.view)
        self.lines={}
        axis_type=QLogValueAxis if logarithmic else QValueAxis
        self.x_axis,self.y_axis=axis_type(),QLogValueAxis() if log_y else axis_type()
        if logarithmic:
            self.x_axis.setBase(10)
            self.y_axis.setBase(10)
        elif log_y:
            self.y_axis.setBase(10)
            self.y_axis.setLabelFormat('%.0e')
        self.x_axis.setTitleText(x_title or ('Passo Δt (s)' if logarithmic else 'Tempo (s)'))
        self.y_axis.setTitleText(unit)
        self.chart.addAxis(self.x_axis,Qt.AlignBottom)
        self.chart.addAxis(self.y_axis,Qt.AlignLeft)
        self.theme()

    def theme(self):
        dark=QApplication.instance().property('dark') is not False
        self.chart.setTheme(QChart.ChartThemeDark if dark else QChart.ChartThemeLight)
        self.chart.setBackgroundBrush(QColor('#11171f' if dark else '#ffffff'))
        self.view.setStyleSheet('background: transparent; border: none;')
        self.chart.setPlotAreaBackgroundVisible(False)
        for axis in (self.x_axis,self.y_axis):
            axis.setGridLinePen(QPen(QColor('#2a3442' if dark else '#e7edf6'),.7))
            axis.setLabelsColor(QColor('#b0c1dc' if dark else '#526788'))
            axis.setTitleBrush(QColor('#eef2fa' if dark else '#203454'))
            axis.setLinePen(QPen(QColor('#334155' if dark else '#dbe5f2'),.7))
        for index,(name,line) in enumerate(self.lines.items()):
            line.setPen(self.series_pen(name,index))

    @staticmethod
    def series_pen(name,index):
        reference=any(word in name.casefold() for word in ('analítica','referência'))
        return QPen(QColor(series_color(name,index)),1.8,Qt.DashLine if reference else Qt.SolidLine)

    def update_series(self,times,series: dict):
        # Preserve Qt series and axes across samples, instead of destroying and
        # reconstructing the entire scene on every monitor refresh.
        for name in list(self.lines):
            if name not in series:
                old=self.lines.pop(name)
                self.chart.removeSeries(old)
                old.deleteLater()
        stride=max(1,(len(times)+1499)//1500)
        indices=list(range(0,len(times),stride))
        if indices and indices[-1]!=len(times)-1: indices.append(len(times)-1)
        bounds=[]
        for name,values in series.items():
            if name not in self.lines:
                line=QLineSeries()
                line.setName(name)
                self.chart.addSeries(line)
                line.attachAxis(self.x_axis)
                line.attachAxis(self.y_axis)
                self.lines[name]=line
                line.setPen(self.series_pen(name,len(self.lines)-1))
            points=[QPointF(float(times[i]),float(values[i])) for i in indices
                    if values[i] is not None and (not self.logarithmic or times[i]>0)
                    and (not (self.logarithmic or self.log_y) or values[i]>0)]
            self.lines[name].replace(points)
            if points:
                bounds.append((min(p.x() for p in points),max(p.x() for p in points),
                               min(p.y() for p in points),max(p.y() for p in points)))
        self.legend.set_entries([(name,line.pen().color().name()) for name,line in self.lines.items()])
        if not bounds: return
        left,right=min(b[0] for b in bounds),max(b[1] for b in bounds)
        low,high=min(b[2] for b in bounds),max(b[3] for b in bounds)
        if self.logarithmic:
            self.x_axis.setRange(left*.8,right*1.2)
            self.y_axis.setRange(low*.5,high*2)
        else:
            self.x_axis.setRange(left,right if right>left else left+1)
            if self.log_y:
                import math
                self.y_axis.setBase(100 if math.log10(high/low)>7 else 10)
                if times: self.x_axis.setRange(min(times),max(times))
                self.y_axis.setRange(low*.5,high*2)
            else:
                pad=(high-low)*.07 if high!=low else max(abs(low)*.02,.01)
                self.y_axis.setRange(low-pad,high+pad)
