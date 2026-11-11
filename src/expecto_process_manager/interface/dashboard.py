import platform
import time
import psutil
from PySide6.QtWidgets import QWidget,QFrame,QVBoxLayout,QHBoxLayout,QLabel,QGridLayout
from PySide6.QtGui import QPainter,QPen,QColor,QPainterPath,QLinearGradient,QBrush
from PySide6.QtCore import Qt,QPointF
from .theme import icon


class Sparkline(QWidget):
    def __init__(self,color):
        super().__init__()
        self.color=color
        self.values=[]
        self.setMinimumHeight(30)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def set_values(self,values):
        self.values=values[-90:]
        self.update()

    def paintEvent(self,event):
        if len(self.values)<2: return
        p=QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        maximum=max(max(self.values)*1.1,1)
        points=[QPointF(i*(self.width()-2)/(len(self.values)-1)+1,
                        self.height()-2-v/maximum*(self.height()-5)) for i,v in enumerate(self.values)]
        path=QPainterPath(points[0])
        for point in points[1:]: path.lineTo(point)
        area=QPainterPath(path)
        area.lineTo(self.width()-1,self.height())
        area.lineTo(1,self.height())
        area.closeSubpath()
        gradient=QLinearGradient(0,0,0,self.height())
        top,bottom=QColor(self.color),QColor(self.color)
        top.setAlpha(80); bottom.setAlpha(24)
        gradient.setColorAt(0,top); gradient.setColorAt(1,bottom)
        p.fillPath(area,QBrush(gradient))
        p.setPen(QPen(QColor(self.color),1.35))
        p.drawPath(path)


class ResourceCard(QFrame):
    def __init__(self,name,kind,color):
        super().__init__()
        self.setObjectName('resourceCard')
        layout=QVBoxLayout(self)
        layout.setContentsMargins(12,7,12,8)
        layout.setSpacing(0)
        top=QHBoxLayout()
        top.setSpacing(12)
        symbol=QLabel()
        symbol.setFixedSize(28,28)
        symbol.setPixmap(icon(kind,color).pixmap(28,28))
        tint=QColor(color)
        symbol.setStyleSheet(f'background: rgba({tint.red()}, {tint.green()}, {tint.blue()}, 24); border-radius: 6px;')
        top.addWidget(symbol)
        top.addWidget(QLabel(name),1)
        self.hint=QLabel()
        self.hint.setObjectName('muted')
        self.hint.setStyleSheet('font-size: 13px;')
        top.addWidget(self.hint)
        layout.addLayout(top)
        self.value=QLabel('—')
        self.value.setObjectName('value')
        self.value.setFixedHeight(31)
        self.description=QLabel('A aguardar amostras')
        self.description.setObjectName('muted')
        self.description.setFixedHeight(21)
        self.description.setStyleSheet('font-size: 14px;')
        for label in (self.value,self.description):
            row=QHBoxLayout()
            row.setContentsMargins(40,0,0,0)
            row.addWidget(label)
            layout.addLayout(row)
        self.spark=Sparkline(color)
        graph=QHBoxLayout()
        graph.setContentsMargins(28,0,0,0)
        graph.addWidget(self.spark)
        layout.addLayout(graph,1)

    def refresh(self,value,description,values):
        self.value.setText(value)
        self.description.setText(description)
        self.spark.set_values(values)


class ResourcePanel(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName('resources')
        self.setFixedWidth(381)
        layout=QVBoxLayout(self)
        layout.setContentsMargins(12,10,12,20)
        layout.setSpacing(13)
        self.cards=[]
        for name,kind,color in [('CPU','cpu','#008cff'),('Memória','memory','#9455f5'),
                                ('Disco','disk','#13b86b'),('Rede','network','#f29b25'),('GPU','gpu','#12a8bd')]:
            card=ResourceCard(name,kind,color)
            self.cards.append(card)
            layout.addWidget(card,1)
        system=QFrame()
        system.setObjectName('systemCard')
        system.setFixedHeight(162)
        box=QVBoxLayout(system)
        box.setContentsMargins(12,10,12,12)
        box.setSpacing(6)
        top=QHBoxLayout()
        symbol=QLabel()
        symbol.setFixedSize(24,24)
        symbol.setPixmap(icon('info').pixmap(24,24))
        top.addWidget(symbol)
        top.addSpacing(8)
        top.addWidget(QLabel('Sistema'),1)
        box.addLayout(top)
        grid=QGridLayout()
        grid.setContentsMargins(32,0,0,0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        self.system_values=[]
        for i,(label,value) in enumerate([('SO',f'{platform.system()} {platform.release()}'),('Kernel',platform.version()),
                                          ('Arquitetura',platform.machine()),('Tempo ativo','—')]):
            name=QLabel(label)
            name.setObjectName('muted')
            name.setStyleSheet('font-size: 13px;')
            name.setFixedWidth(84)
            text=QLabel(value)
            text.setStyleSheet('font-size: 13px;')
            text.setToolTip(value)
            grid.addWidget(name,i,0)
            grid.addWidget(text,i,1)
            self.system_values.append(text)
        box.addLayout(grid)
        grid.setColumnStretch(1,1)
        layout.addWidget(system)
        self.uptime=self.system_values[-1]
        self.boot_time=psutil.boot_time()
        self.core_count=psutil.cpu_count()
        self.gpu_inventory_hint=''

    def set_inventory(self,inventory):
        gpu=[item for item in inventory.items if item.category=='GPU' and ('Adaptador' in item.name or 'configurado' in item.name.lower())]
        if gpu:
            self.gpu_inventory_hint=f'{len(gpu)} detetadas'
            self.cards[4].hint.setText(self.gpu_inventory_hint)
            self.cards[4].setToolTip('\n'.join(item.value+' ['+item.source+']' for item in gpu)+'\nIdentificação não fornece utilização, potência ou temperatura.')

    def refresh(self,history):
        s=history[-1]
        cpu='—' if s.cpu is None else f'{s.cpu:.0f}%'
        self.cards[0].hint.setText(f'{self.core_count or "—"} núcleos')
        frequency=getattr(s,'cpu_frequency_mhz',None)
        description='Aquecimento' if s.cpu is None else (f'{frequency/1000:.1f} GHz' if frequency else 'Utilização medida')
        self.cards[0].refresh(cpu,description,[h.cpu for h in history if h.cpu is not None])
        frequency_age = getattr(s,'frequency_age_s',None)
        self.cards[0].setToolTip('Frequência indisponível' if frequency_age is None else f'Frequência medida há {frequency_age:.2f} s (cadência 2 s). CPU medida em cada recolha.')
        total=getattr(s,'memory_total',0) or s.memory_used+s.memory_available
        self.cards[1].refresh(f'{s.memory_percent:.0f}%',f'{s.memory_used/1e9:.1f} / {total/1e9:.1f} GB',
                              [h.memory_percent for h in history])
        for i,key,desc in [(2,'disk_bytes_s','Leitura + escrita'),(3,'network_bytes_s','Envio + receção')]:
            value=getattr(s,key)
            self.cards[i].value.setStyleSheet('font-size: 25px; font-weight: 600;')
            self.cards[i].refresh('—' if value is None else f'{value/1e6:.1f} MB/s',desc,
                                  [getattr(h,key) for h in history if getattr(h,key) is not None])
        rx,tx=getattr(s,'network_received_s',None),getattr(s,'network_sent_s',None)
        if rx is not None and tx is not None:
            self.cards[3].description.setText(f'{rx*8/1e6:.1f} Mb/s ↓  {tx*8/1e6:.1f} Mb/s ↑')
        self.cards[4].refresh('—','Sensor indisponível',[])
        self.cards[4].hint.setText(self.gpu_inventory_hint)
        minutes=int((time.time()-self.boot_time)/60)
        self.uptime.setText(f'{minutes//1440} dias, {minutes//60%24} h, {minutes%60} min')


class SummaryBar(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName('footer')
        self.setFixedHeight(103)
        row=QHBoxLayout(self)
        row.setContentsMargins(22,17,18,17)
        row.setSpacing(14)
        self.labels=[]
        for i,(title,kind,color) in enumerate([('Processos','history','#afc3e0'),('CPU','process','#00b7ff'),
                ('Memória','memory','#ad4dff'),('Disco','disk','#00e64a'),('Rede','network','#ffa122')]):
            if i:
                divider=QFrame()
                divider.setFixedSize(1,57)
                divider.setObjectName('divider')
                row.addWidget(divider)
            cell=QHBoxLayout()
            cell.setSpacing(12)
            symbol=QLabel()
            symbol.setFixedSize(28,32)
            symbol.setPixmap(icon(kind,color).pixmap(28,28))
            cell.addWidget(symbol)
            text=QVBoxLayout()
            text.setSpacing(4)
            label=QLabel(title)
            label.setObjectName('muted')
            label.setStyleSheet('font-size: 13px;')
            value=QLabel('—')
            value.setStyleSheet('font-size: 20px;')
            text.addWidget(label)
            text.addWidget(value)
            cell.addLayout(text,1)
            row.addLayout(cell,1)
            self.labels.append(value)

    def refresh(self,s,count):
        values=[str(count),'—' if s.cpu is None else f'{s.cpu:.0f}%',f'{s.memory_percent:.0f}%',
                '—' if s.disk_bytes_s is None else f'{s.disk_bytes_s/1e6:.1f} MB/s',
                '—' if s.network_bytes_s is None else f'{s.network_bytes_s/1e6:.1f} MB/s']
        for label,value in zip(self.labels,values): label.setText(value)
