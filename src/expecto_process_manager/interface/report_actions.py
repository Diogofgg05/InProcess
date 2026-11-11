from pathlib import Path
import os
import shutil
import tempfile
from PySide6.QtWidgets import QFrame,QHBoxLayout,QLabel,QPushButton,QDialog,QVBoxLayout,QTextBrowser,QFileDialog
from PySide6.QtCore import Qt,QUrl,Signal
from PySide6.QtGui import QDesktopServices
from ..reporting.service import generate_report


class ReportDialog(QDialog):
    def __init__(self,generated,parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle(generated.title)
        self.resize(950,740)
        box=QVBoxLayout(self)
        browser=QTextBrowser()
        browser.setOpenExternalLinks(False)
        browser.setStyleSheet('background: white; color: #18283d; border: none; padding: 14px;')
        browser.setHtml(generated.preview_html)
        box.addWidget(browser,1)
        buttons=QHBoxLayout()
        open_browser=QPushButton('Abrir relatório completo no navegador')
        open_browser.clicked.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(generated.path)))
        buttons.addWidget(open_browser)
        close=QPushButton('Fechar')
        close.clicked.connect(self.close)
        buttons.addWidget(close)
        box.addLayout(buttons)


class ReportActions(QFrame):
    generated_ready=Signal(object)
    def __init__(self,page,kind,tasks,output_directory,context=None):
        super().__init__(page)
        self.page,self.kind,self.tasks=page,kind,tasks
        self.output_directory=output_directory
        self.capture_context=context or (lambda:{})
        self.generated=None
        self.job=None
        self.version=0
        row=QHBoxLayout(self)
        row.setContentsMargins(0,5,0,0)
        self.status=QLabel('Relatório gerado automaticamente após executar.')
        self.status.setObjectName('muted')
        self.status.setWordWrap(True)
        row.addWidget(self.status,1)
        self.open_button=QPushButton('Ver relatório')
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self.open)
        row.addWidget(self.open_button)
        self.save_button=QPushButton('Guardar HTML')
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save)
        row.addWidget(self.save_button)
        self.png_button=QPushButton('Gráficos PNG')
        self.png_button.clicked.connect(self.export_png)
        self.png_button.setEnabled(False)
        row.addWidget(self.png_button)

    def publish(self,result):
        self.version+=1
        version=self.version
        if self.job: self.job.token.cancel()
        context=dict(getattr(self.page,'result_context',{}) or {})
        extra=self.capture_context()
        metadata=dict(context.get('metadata',{}))
        metadata.update(extra.get('metadata',{}))
        context.update(extra)
        context['metadata']=metadata
        self.status.setText('A gerar o relatório com explicações, resultados e gráficos…')
        self.open_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.png_button.setEnabled(True)
        self.job=self.tasks.start(lambda token:generate_report(self.kind,result,context,self.output_directory,token),
                                 lambda generated:self.ready(generated,version),
                                 lambda error:self.failed(error) if version==self.version else None)

    def ready(self,generated,version):
        if version!=self.version: return
        self.job=None
        self.generated=generated
        self.status.setText('Relatório pronto · '+Path(generated.path).name)
        self.status.setToolTip(generated.path)
        self.open_button.setEnabled(True)
        self.save_button.setEnabled(True)
        self.generated_ready.emit(generated)

    def failed(self,message):
        self.status.setText(message)

    def open(self):
        if self.generated:
            dialog=ReportDialog(self.generated,self.page)
            dialog.show()
            self.dialog=dialog

    def save(self):
        if not self.generated: return
        path,_=QFileDialog.getSaveFileName(self,'Guardar relatório',Path(self.generated.path).name,'HTML (*.html)')
        if path:
            source=self.generated.path
            def copy(token):
                token.check()
                if Path(source).resolve()==Path(path).resolve(): return
                handle=tempfile.NamedTemporaryFile(dir=Path(path).parent,delete=False)
                temporary=handle.name
                handle.close()
                try:
                    shutil.copyfile(source,temporary)
                    token.check()
                    os.replace(temporary,path)
                finally:
                    if os.path.exists(temporary): os.unlink(temporary)
            self.tasks.start(copy,lambda _:self.status.setText('Relatório guardado.'),self.failed)

    def export_png(self):
        directory=QFileDialog.getExistingDirectory(self,'Exportar gráficos PNG')
        if not directory: return
        plots=list(getattr(self.page,'plots',[]))
        # Qt rendering belongs to the GUI; image encoding/file I/O runs outside it.
        images=[plot.grab().toImage() for plot in plots]
        def write(token):
            for i,image in enumerate(images,1):
                token.check()
                target=Path(directory)/f'{self.kind}-{i}.png'
                handle=tempfile.NamedTemporaryFile(dir=target.parent,delete=False)
                temporary=handle.name
                handle.close()
                try:
                    if not image.save(temporary,'PNG'): raise OSError('Não foi possível codificar o PNG.')
                    token.check()
                    os.replace(temporary,target)
                finally:
                    if os.path.exists(temporary): os.unlink(temporary)
        self.tasks.start(write,lambda _:self.status.setText(f'{len(images)} gráficos PNG exportados.'),self.failed)
