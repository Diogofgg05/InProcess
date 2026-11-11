import psutil
from collections import namedtuple
from expecto_process_manager.core.inventory import inventory
from expecto_process_manager.core.cancellation import Cancellation


def test_users_are_reported_without_fabrication(monkeypatch):
    User = namedtuple('User','name terminal host')
    monkeypatch.setattr(psutil,'users',lambda:[User('tester',None,'')])
    headers,rows,note = inventory('users',Cancellation())
    assert rows == [['tester','—','local']]
    assert len(headers)==3


def test_service_queries_handle_permissions(monkeypatch):
    from expecto_process_manager.core import inventory as module
    class Service:
        def display_name(self): raise psutil.AccessDenied()
    monkeypatch.setattr(module.platform,'system',lambda:'Windows')
    monkeypatch.setattr(psutil,'win_service_iter',lambda:iter([Service()]),raising=False)
    headers,rows,note = inventory('services',Cancellation())
    assert rows == []


def test_service_list_survives_removed_services_without_querying_descriptions(monkeypatch):
    from expecto_process_manager.core import inventory as module
    class Service:
        def __init__(self,error=None): self.error=error
        def as_dict(self): raise AssertionError('Optional descriptions must not be requested')
        def display_name(self): return 'Accessible service'
        def name(self): return 'accessible'
        def status(self):
            if self.error: raise self.error
            return 'running'
        def pid(self): return 123
    monkeypatch.setattr(module.platform,'system',lambda:'Windows')
    monkeypatch.setattr(psutil,'win_service_iter',lambda:iter([Service(FileNotFoundError('QueryServiceConfig2W')),
        Service(),Service(psutil.AccessDenied())]),raising=False)
    headers,rows,note=inventory('services',Cancellation())
    assert rows==[['Accessible service','accessible','running','123']]
    assert '2 serviços indisponíveis' in note


def test_linux_startup_reads_entries(tmp_path,monkeypatch):
    from expecto_process_manager.core import inventory as module
    folder = tmp_path/'.config/autostart'
    folder.mkdir(parents=True)
    (folder/'app.desktop').write_text('[Desktop Entry]\nName=Test app\nExec=never-execute-this\n',encoding='utf-8')
    monkeypatch.setattr(module.platform,'system',lambda:'Linux')
    monkeypatch.setattr(module.Path,'home',lambda:tmp_path)
    _,rows,_ = inventory('startup',Cancellation())
    assert ['Test app','never-execute-this','Configurado'] in rows
