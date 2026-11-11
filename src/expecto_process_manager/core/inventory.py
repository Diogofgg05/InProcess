"""Read-only inventory. Unsupported information is never synthesized."""
import configparser
import os
from pathlib import Path
import platform
import subprocess
import psutil
from .cancellation import Cancellation


def inventory(kind: str, token: Cancellation) -> tuple[list[str],list[list[str]],str]:
    token.check()
    if kind == 'users':
        rows = [[u.name,u.terminal or '—',u.host or 'local'] for u in psutil.users()]
        return ['Utilizador','Terminal','Origem'],rows,'Sessões reportadas pelo sistema; não é uma lista de todas as contas.'
    if kind == 'services':
        if platform.system() == 'Windows':
            rows = []
            skipped = 0
            for service in psutil.win_service_iter():
                token.check()
                try:
                    # Avoid querying optional descriptions (QueryServiceConfig2W).
                    s = dict(display_name=service.display_name(),name=service.name(),
                             status=service.status(),pid=service.pid())
                    rows.append([s['display_name'],s['name'],s['status'],str(s.get('pid') or '—')])
                except (psutil.Error,OSError):
                    skipped += 1
                    continue
            note = 'Serviços Windows · consulta sem alterações.'
            if skipped: note += f' {skipped} serviços indisponíveis ou removidos durante a consulta.'
            return ['Nome','Identificador','Estado','PID'],rows,note
        result = subprocess.run(['systemctl','list-units','--type=service','--all','--no-pager','--no-legend','--plain'],
                                capture_output=True,text=True,timeout=5,check=True)
        rows = []
        for line in result.stdout.splitlines():
            parts = line.split(None,4)
            if len(parts) >= 4: rows.append(parts[:4])
        return ['Unidade','Carregamento','Ativo','Subestado'],rows,'Serviços systemd · consulta sem alterações.'
    if kind == 'startup':
        rows = []
        if platform.system() == 'Windows':
            import winreg
            for hive,label in [(winreg.HKEY_CURRENT_USER,'Utilizador'),(winreg.HKEY_LOCAL_MACHINE,'Sistema')]:
                for view in [winreg.KEY_WOW64_64KEY,winreg.KEY_WOW64_32KEY]:
                    try:
                        with winreg.OpenKey(hive,r'Software\Microsoft\Windows\CurrentVersion\Run',0,winreg.KEY_READ|view) as key:
                            for i in range(winreg.QueryInfoKey(key)[1]):
                                token.check()
                                name,value,_ = winreg.EnumValue(key,i)
                                row = [name,str(value),label+' · registo']
                                if row not in rows: rows.append(row)
                    except OSError:
                        pass
            folders = [(Path(os.environ.get('APPDATA',''))/'Microsoft/Windows/Start Menu/Programs/Startup','Utilizador'),
                       (Path(os.environ.get('PROGRAMDATA',''))/'Microsoft/Windows/Start Menu/Programs/Startup','Sistema')]
            for folder,label in folders:
                if folder.is_dir():
                    rows += [[p.stem,str(p),label+' · pasta'] for p in folder.iterdir() if p.is_file()]
            note = 'Entradas Run e pastas Startup; não inclui tarefas agendadas ou todas as políticas de arranque.'
        else:
            folders = [Path('/etc/xdg/autostart'),Path.home()/'.config/autostart']
            entries = {}
            for folder in folders:
                for p in folder.glob('*.desktop'):
                    token.check()
                    parser = configparser.ConfigParser(interpolation=None,strict=False)
                    try:
                        parser.read(p,encoding='utf-8')
                        s = parser['Desktop Entry']
                        entries[p.name] = [s.get('Name',p.stem),s.get('Exec','—'),'Desativado' if s.get('Hidden','false')=='true' else 'Configurado']
                    except (configparser.Error,KeyError,UnicodeError):
                        continue
            rows = list(entries.values())
            note = 'XDG autostart; não inclui todos os mecanismos de sessão. Entradas não são executadas.'
        return ['Aplicação','Comando/localização','Origem/estado'],rows,note
    raise ValueError('Inventário desconhecido.')
