import csv
import os
import tempfile
from pathlib import Path
from ..physics.integration import validate
from .cancellation import Cancellation


def export_csv(path: str | Path, rows: list[dict], cancellation: Cancellation | None = None) -> None:
    if not rows:
        raise ValueError("Não existem dados para exportar.")
    temp = None
    try:
        with tempfile.NamedTemporaryFile('w',newline='',encoding='utf-8-sig',dir=Path(path).parent,delete=False) as stream:
            temp = stream.name
            writer = csv.DictWriter(stream,fieldnames=list(rows[0]))
            writer.writeheader()
            for i,row in enumerate(rows):
                if cancellation and i % 256 == 0: cancellation.check()
                writer.writerow(row)
        if cancellation: cancellation.check()
        os.replace(temp,path)
    finally:
        if temp and os.path.exists(temp): os.unlink(temp)


def import_power(path: str | Path, cancellation: Cancellation | None = None) -> tuple[list[float], list[float], str]:
    if Path(path).stat().st_size > 10 * 1024 * 1024:
        raise ValueError("CSV demasiado grande (máximo 10 MiB).")
    with open(path,encoding="utf-8-sig",newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames) or not {'time_s','power_w'}.issubset(reader.fieldnames):
            raise ValueError("CSV requer colunas time_s (s) e power_w (W).")
        times, powers = [], []
        try:
            for i,row in enumerate(reader):
                if cancellation and i % 256 == 0:
                    cancellation.check()
                if i >= 200_001 or None in row:
                    raise ValueError("CSV excede o limite de amostras ou contém colunas extra.")
                if row.get('time_unit','s') != 's' or row.get('power_unit','W') != 'W':
                    raise ValueError("Unidades suportadas: s e W.")
                times.append(float(row['time_s']))
                powers.append(float(row['power_w']))
        except (TypeError, csv.Error) as error:
            raise ValueError(f"CSV malformado: {error}") from error
    validate(times,powers)
    if any(p < 0 for p in powers):
        raise ValueError("Potência negativa.")
    return times,powers,"importado; origem não verificada"
