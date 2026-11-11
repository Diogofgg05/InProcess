from PySide6.QtCore import QObject,QEvent
from PySide6.QtWidgets import QScrollArea,QBoxLayout,QLayout,QFormLayout


class ResponsiveLab(QObject):
    """Stack parameters above charts when the viewport becomes narrow."""
    def __init__(self,page):
        super().__init__(page)
        self.targets=[]
        for area in page.findChildren(QScrollArea):
            content=area.widget()
            body=content.layout() if content else None
            if isinstance(body,QBoxLayout):
                body.setSizeConstraint(QLayout.SetNoConstraint)
                content.setMinimumWidth(0)
                self.targets.append((area.viewport(),body))
                area.viewport().installEventFilter(self)
                self.adapt(area.viewport(),body)

    def adapt(self,viewport,body):
        if viewport.width()<850:
            body.setDirection(QBoxLayout.TopToBottom)
        elif viewport.width()>950:
            body.setDirection(QBoxLayout.LeftToRight)

    def eventFilter(self,watched,event):
        if event.type()==QEvent.Resize:
            for viewport,body in self.targets:
                if watched is viewport: self.adapt(viewport,body)
        return False
