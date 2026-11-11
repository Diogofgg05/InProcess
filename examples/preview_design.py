"""Capture the desktop design with real monitoring and synthetic lab results."""
from pathlib import Path
import tempfile
import time
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from expecto_process_manager.main import configure_app
from expecto_process_manager.interface.main_window import MainWindow


def wait(app,predicate,seconds=20):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:
        app.processEvents(); time.sleep(.01)
    app.processEvents()
    if not predicate(): raise RuntimeError('A pré-visualização não terminou a tempo.')


def main():
    directory=Path('data/design')
    directory.mkdir(parents=True,exist_ok=True)
    app=QApplication([]); configure_app(app)
    with tempfile.TemporaryDirectory() as temp:
        window=MainWindow(settings_path=Path(temp)/'preferences.ini',report_directory=Path(temp)/'reports')
        try:
            window.resize(1680,1000); window.show()
            wait(app,lambda:len(window.history_rows)>=2)
            window.adaptive.apply(); app.processEvents()
            window.grab().save(str(directory/'processes.png'))
            groups=window.processes.groups
            if groups.groups:
                i=max(range(len(groups.groups)),key=lambda r:len(groups.groups[r].children))
                root=groups.index(i,0)
                window.processes.tree.setExpanded(root,True)
                window.processes.tree.scrollTo(root)
                app.processEvents(); window.grab().save(str(directory/'processes-expanded.png'))
            for width,height in ((1200,680),(900,560)):
                window.resize(width,height); window.adaptive.apply(); app.processEvents()
                QTest.qWait(450)
                window.titlebar.repaint(); window.sidebar_brand.repaint(); app.processEvents()
                # Flush the offscreen backing store after reflow before saving.
                window.grab()
                window.grab().save(str(directory/f'processes-{width}x{height}.png'))
            window.resize(1680,1000); window.adaptive.apply(); app.processEvents()
            window.nav.setCurrentRow(6)
            window.physics.execute()
            wait(app,lambda:window.physics.experiment is not None and not window.tasks.active())
            window.grab().save(str(directory/'laboratory.png'))
            window.physics.modes.button(2).click()
            app.processEvents(); window.grab().save(str(directory/'experiment.png'))
            window.physics.modes.button(0).click()
            window.resize(1000,780)
            window.adaptive.apply()
            app.processEvents(); window.grab().save(str(directory/'laboratory-compact.png'))
            window.resize(900,560); window.adaptive.apply(); app.processEvents()
            QTest.qWait(180)
            window.grab().save(str(directory/'laboratory-900x560.png'))
            window.resize(1680,1000)
            window.adaptive.apply()
            for index,name in ((1,'performance'),(2,'history'),(3,'applications'),(4,'users'),(5,'services'),(8,'settings')):
                window.nav.setCurrentRow(index)
                app.processEvents()
                if index==2: wait(app,lambda:len(window.history_rows)>=10)
                if index in (3,4,5):
                    page=window.inventory_pages[index-3]
                    wait(app,lambda:page.job is None)
                    print(name+': '+page.note.text())
                window.grab().save(str(directory/(name+'.png')))
                if index==8:
                    for tab,label in ((1,'data'),(2,'system')):
                        window.settings_page.tabs.setCurrentIndex(tab)
                        window.adaptive.apply(); QTest.qWait(150)
                        window.grab().save(str(directory/f'settings-{label}.png'))
                    window.settings_page.tabs.setCurrentIndex(0)
                    window.resize(900,650); window.adaptive.apply(); QTest.qWait(200)
                    window.grab(); window.grab().save(str(directory/'settings-compact.png'))
                    window.settings_page.choose_theme(0); QTest.qWait(200)
                    window.grab(); window.grab().save(str(directory/'settings-dark.png'))
                    window.settings_page.choose_theme(1)
            print(directory.resolve())
        finally:
            window.close(); wait(app,lambda:window.closed_ready)


if __name__=='__main__': main()
