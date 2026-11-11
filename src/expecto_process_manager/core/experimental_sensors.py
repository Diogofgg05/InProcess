"""Read-only physical telemetry; unavailable readings remain None.

NVIDIA reports GPU die temperature and electrical board power. Those domains
are explicit: board watts are not certified thermal input to a CPU/die model.
"""
import csv
import math
import platform
import shutil
import subprocess
import time


def optional_number(value):
    try: number=float(value)
    except (ValueError,TypeError): return None
    return number if math.isfinite(number) else None


def parse_nvidia(text):
    rows=[]
    for row in csv.reader(text.splitlines()):
        if not row: continue
        if len(row)!=5: raise ValueError('Resposta NVIDIA com colunas inesperadas.')
        index,name,temp,power,load=[value.strip() for value in row]
        temperature,power_w,utilization=optional_number(temp),optional_number(power),optional_number(load)
        if temperature is not None and temperature < -273.15: raise ValueError('Temperatura física inválida.')
        if power_w is not None and power_w<0: raise ValueError('Potência inválida.')
        rows.append(dict(index=int(index),device=name,temperature_c=temperature,power_w=power_w,utilization_percent=utilization,
                         origin='DRIVER_REPORTED',instrument='nvidia-smi',temperature_scope='gpu_die',
                         power_scope='gpu_board_electrical',power_temporal_response='driver-defined; may be averaged',
                         calibrated=False,ambient_c=None))
    return rows


def read_nvidia(timeout=3):
    executable=shutil.which('nvidia-smi')
    if not executable: return []
    started=time.perf_counter()
    result=subprocess.run([executable,'--query-gpu=index,name,temperature.gpu,power.draw,utilization.gpu',
                           '--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=timeout,
                          check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    rows=parse_nvidia(result.stdout)
    for row in rows: row['read_duration_ms']=(time.perf_counter()-started)*1000
    return rows


def capabilities():
    import psutil
    result=dict(platform=platform.platform(),python=platform.python_version(),
                cpu_temperature_api=hasattr(psutil,'sensors_temperatures'),cpu_power_sensor=None,
                cpu_thermal_validation_ready=False,nvidia=[],limitations=[])
    try: result['nvidia']=read_nvidia()
    except (OSError,subprocess.SubprocessError,ValueError) as error:
        result['limitations'].append('NVIDIA: '+type(error).__name__)
    if result['cpu_temperature_api']:
        try:
            result['temperature_channels']={name:[dict(label=x.label,current_c=x.current) for x in items]
                                            for name,items in psutil.sensors_temperatures().items()}
        except (OSError,psutil.Error): result['temperature_channels']={}
    result['limitations']+=['CPU utilization is not power. GPU power and temperature do not validate a CPU thermal model.',
                            'No external calibration or ambient measurement is available automatically.']
    return result
