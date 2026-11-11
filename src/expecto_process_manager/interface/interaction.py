"""Quiet pointer focus, with a separate keyboard-navigation indication."""
from PySide6.QtCore import QObject,QEvent,Qt
from PySide6.QtWidgets import QProxyStyle,QStyle,QApplication,QWidget


class QuietFocusStyle(QProxyStyle):
    def __init__(self): super().__init__('Fusion')

    def drawPrimitive(self,element,option,painter,widget=None):
        if element==QStyle.PE_FrameFocusRect: return
        super().drawPrimitive(element,option,painter,widget)


class KeyboardFocus(QObject):
    def eventFilter(self,watched,event):
        if event.type()==QEvent.FocusIn and isinstance(watched,QWidget):
            self.mark(watched,event.reason() in (Qt.TabFocusReason,Qt.BacktabFocusReason,Qt.ShortcutFocusReason))
        elif event.type()==QEvent.FocusOut and isinstance(watched,QWidget):
            self.mark(watched,False)
        elif event.type()==QEvent.MouseButtonPress:
            focused=QApplication.focusWidget()
            if focused: self.mark(focused,False)
        return False

    @staticmethod
    def mark(widget,value):
        if widget.property('keyboardFocus')==value: return
        widget.setProperty('keyboardFocus',value)
        if hasattr(widget,'style'):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()


def install_interaction(app):
    if getattr(app,'_expecto_keyboard_focus',None) is None:
        app.setStyle(QuietFocusStyle())
        app._expecto_keyboard_focus=KeyboardFocus(app)
        app.installEventFilter(app._expecto_keyboard_focus)
