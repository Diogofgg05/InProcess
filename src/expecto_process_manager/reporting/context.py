"""Report provenance without triggering expensive hardware discovery."""
from datetime import datetime,timezone
import hashlib
from importlib.metadata import version,PackageNotFoundError
from pathlib import Path
import platform
import psutil
from ..core.hardware import get_cached_hardware


def experiment_metadata(extra=None):
    try: software=version('expecto-process-manager')
    except PackageNotFoundError: software='desenvolvimento'
    root=Path(__file__).parents[1]
    digest=hashlib.sha256()
    for folder in ('physics','simulation','optimization'):
        for path in sorted((root/folder).rglob('*.py')):
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    metadata={'Instante do sistema (UTC)':datetime.now(timezone.utc).isoformat(),
              'Software':f'InProcess {software} · Physical Systems Lab 3.0',
              'Hash dos ficheiros científicos':digest.hexdigest()[:20],
              'Sistema':platform.platform(),'Python':platform.python_version(),
              'CPU lógicos':psutil.cpu_count(),'RAM total (GiB)':f'{psutil.virtual_memory().total/1024**3:.3f}'}
    hardware=get_cached_hardware()
    if hardware:
        metadata['Inventário de hardware: recolha Unix']=hardware.collected_at
        metadata['Inventário de hardware: idade (s)']=f'{hardware.age_s:.1f}'
        for item in hardware.items:
            if item.category in ('CPU','GPU','Placa principal','Firmware'):
                metadata[f'{item.category} · {item.name}']=item.value+' ['+item.source+']'
    else:
        metadata['Inventário detalhado']='Não solicitado nesta sessão; consulte Desempenho → Hardware.'
    metadata.update(extra or {})
    return metadata
