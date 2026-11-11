"""Bounded presentation data and an orbit chart with equal spatial scales."""
from dataclasses import dataclass
import math
from PySide6.QtWidgets import QWidget,QVBoxLayout,QApplication,QLabel
from PySide6.QtCharts import QChart,QChartView,QLineSeries,QValueAxis,QScatterSeries
from PySide6.QtGui import QPainter,QColor,QPen,QFont
from PySide6.QtCore import Qt,QPointF,QMargins,QTimer
from ..physics.gravity import G
from .legend import SeriesLegend


@dataclass(frozen=True)
class GravityPresentation:
    times: list[float]
    orbits: dict[str,list[tuple[float,float]]]
    energy_drift: dict[str,list[float]]
    momentum_drift: dict[str,list[float]]
    errors: dict[str,list[float]]
    note: str


def prepare_gravity(experiment,token) -> GravityPresentation:
    """Prepare and decimate away from the GUI thread; full arrays stay intact."""
    n=len(experiment.times)
    stride=max(1,math.ceil(max(1,n-1)/1499))
    indices=list(range(0,n,stride))
    if n and indices[-1]!=n-1: indices.append(n-1)
    times=[experiment.times[i] for i in indices]
    orbits,energy,momentum,position={},{},{},{}
    note=[]
    for name,trajectory in experiment.trajectories.items():
        token.check()
        orbits[name]=[(trajectory.x[i]/1000,trajectory.y[i]/1000) for i in indices]
        e0,l0=trajectory.energy[0],trajectory.angular_momentum[0]
        energy_scale=abs(G*experiment.config.central_mass*experiment.config.body_mass/experiment.config.radius)
        if e0!=0 and abs(e0)>1e-12*energy_scale:
            energy[name]=[(trajectory.energy[i]-e0)/abs(e0) for i in indices]
        else:
            note.append(f'{name}: energia relativa indefinida (energia inicial aproximadamente nula).')
        if l0!=0:
            momentum[name]=[(trajectory.angular_momentum[i]-l0)/abs(l0) for i in indices]
        else:
            note.append(f'{name}: momento angular relativo indefinido (momento inicial nulo).')
        if trajectory.position_error is not None:
            position[name]=[trajectory.position_error[i]/1000 for i in indices]
    x,y=getattr(experiment,'reference_x',None),getattr(experiment,'reference_y',None)
    if x is not None and y is not None:
        orbits['Referência circular']=[(x[i]/1000,y[i]/1000) for i in indices]
    if not position:
        note.append('Sem erro de posição: a referência analítica circular só se aplica ao fator de velocidade 1.')
    token.check()
    return GravityPresentation(times,orbits,energy,momentum,position,'\n'.join(note))


class OrbitPlot(QWidget):
    """Planar coordinates in km; one km occupies equal pixels on both axes."""
    def __init__(self):
        super().__init__()
        self.chart=QChart()
        self.setObjectName('plotCard')
        self.chart.legend().hide()
        self.chart.setBackgroundRoundness(10)
        self.chart.setMargins(QMargins(5,5,5,5))
        self.view=QChartView(self.chart)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setMinimumHeight(180)
        layout=QVBoxLayout(self)
        layout.setContentsMargins(10,9,10,5)
        layout.setSpacing(3)
        title=QLabel('Órbitas simuladas · escalas espaciais iguais')
        title.setWordWrap(True)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet('font-size: 13px; background: transparent;')
        layout.addWidget(title)
        self.legend=SeriesLegend()
        layout.addWidget(self.legend)
        layout.addWidget(self.view)
        self.x_axis,self.y_axis=QValueAxis(),QValueAxis()
        self.x_axis.setTitleText('x (km)')
        self.y_axis.setTitleText('y (km)')
        self.chart.addAxis(self.x_axis,Qt.AlignBottom)
        self.chart.addAxis(self.y_axis,Qt.AlignLeft)
        self.lines={}
        self._bounds=(-1,1,-1,1)
        self._adjusting=False
        self.center=QScatterSeries()
        self.center.setName('Massa central (ponto)')
        self.center.setMarkerSize(8)
        self.center.append(0,0)
        self.chart.addSeries(self.center)
        self.center.attachAxis(self.x_axis)
        self.center.attachAxis(self.y_axis)
        for marker in self.chart.legend().markers(self.center): marker.setVisible(False)
        self._scale_timer=QTimer(self)
        self._scale_timer.setSingleShot(True)
        self._scale_timer.timeout.connect(self._equalize)
        self.chart.plotAreaChanged.connect(lambda _:self._scale_timer.start(0))
        self.theme()

    def theme(self):
        dark=QApplication.instance().property('dark') is not False
        self.chart.setTheme(QChart.ChartThemeDark if dark else QChart.ChartThemeLight)
        self.chart.setBackgroundBrush(QColor('#141a23' if dark else '#ffffff'))
        self.chart.setPlotAreaBackgroundVisible(False)
        for axis in (self.x_axis,self.y_axis):
            axis.setGridLinePen(QPen(QColor('#2a3442' if dark else '#e5e9f0'),.5))
        self.center.setColor(QColor('#ffbd57'))
        self.center.setBorderColor(QColor('#ffbd57'))
        legend_font=QFont(self.chart.legend().font())
        legend_font.setPixelSize(11)
        self.chart.legend().setFont(legend_font)

    def set_orbits(self,orbits):
        for name in list(self.lines):
            if name not in orbits:
                old=self.lines.pop(name)
                self.chart.removeSeries(old)
                old.deleteLater()
        all_points=[]
        colors=['#21b9ff','#b366ff','#28d58b','#e6b454']
        for i,(name,points) in enumerate(orbits.items()):
            if name not in self.lines:
                line=QLineSeries()
                line.setName(name)
                self.chart.addSeries(line)
                line.attachAxis(self.x_axis)
                line.attachAxis(self.y_axis)
                self.lines[name]=line
            line=self.lines[name]
            pen=QPen(QColor(colors[i%len(colors)]),1.4)
            if name=='Referência circular': pen.setStyle(Qt.DashLine)
            line.setPen(pen)
            line.replace([QPointF(x,y) for x,y in points])
            all_points.extend(points)
        all_points.append((0,0))
        self._bounds=(min(p[0] for p in all_points),max(p[0] for p in all_points),
                      min(p[1] for p in all_points),max(p[1] for p in all_points))
        self.legend.set_entries([('Massa central','#ffbd57')]+[(name,line.pen().color().name()) for name,line in self.lines.items()])
        self._equalize()

    def _equalize(self,*_):
        if self._adjusting: return
        area=self.chart.plotArea()
        if area.width()<=0 or area.height()<=0: return
        self._adjusting=True
        try:
            left,right,bottom,top=self._bounds
            cx,cy=(left+right)/2,(bottom+top)/2
            xspan,yspan=max(right-left,1e-6)*1.12,max(top-bottom,1e-6)*1.12
            ratio=area.width()/area.height()
            if xspan/yspan<ratio: xspan=yspan*ratio
            else: yspan=xspan/ratio
            xr,yr=(cx-xspan/2,cx+xspan/2),(cy-yspan/2,cy+yspan/2)
            if not (math.isclose(self.x_axis.min(),xr[0],rel_tol=1e-9,abs_tol=1e-9)
                    and math.isclose(self.x_axis.max(),xr[1],rel_tol=1e-9,abs_tol=1e-9)):
                self.x_axis.setRange(*xr)
            if not (math.isclose(self.y_axis.min(),yr[0],rel_tol=1e-9,abs_tol=1e-9)
                    and math.isclose(self.y_axis.max(),yr[1],rel_tol=1e-9,abs_tol=1e-9)):
                self.y_axis.setRange(*yr)
        finally:
            self._adjusting=False
