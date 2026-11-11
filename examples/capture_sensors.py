"""Capture real NVIDIA telemetry locally, without changing clocks or workloads."""
import argparse
import csv
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import time
import uuid
from expecto_process_manager.core.experimental_sensors import capabilities,read_nvidia


def capture(directory,duration=120.,interval=2.):
    if not 2<=duration<=3600 or not .5<=interval<=60: raise ValueError('Duração 2..3600 s; intervalo 0,5..60 s.')
    directory=Path(directory); directory.mkdir(parents=True,exist_ok=True)
    if (directory/'manifest.json').exists() or (directory/'sensors.csv').exists():
        raise ValueError('A pasta já contém uma aquisição. Escolhe outra pasta para preservar a evidência.')
    manifest=dict(schema=1,run_id=str(uuid.uuid4()),started_at=datetime.now(timezone.utc).isoformat(),
        origin='DRIVER_REPORTED',device_kind='gpu',power_interpretation='board_electrical',
        ambient_c=None,ambient_source=None,uncertainties=None,capabilities=capabilities(),
        configured_interval_s=interval,planned_duration_s=duration,errors=[])
    start=time.perf_counter(); epoch=time.time(); manifest['start_epoch_s']=epoch
    rows=[]; tick=0
    try:
        while time.perf_counter()-start<=duration:
            t0=time.perf_counter(); sensors=read_nvidia()
            if not sensors: raise ValueError('Nenhum sensor NVIDIA disponível; não se criam valores sintéticos.')
            midpoint=(t0+time.perf_counter())/2-start
            for sensor in sensors:
                rows.append(dict(time_s=midpoint,utc_epoch_s=epoch+midpoint,**sensor))
            tick+=1
            delay=min(duration-(time.perf_counter()-start),max(0,start+tick*interval-time.perf_counter()))
            if delay<=0 and time.perf_counter()-start>=duration: break
            time.sleep(max(0,delay))
    except KeyboardInterrupt: manifest['interrupted']=True
    except Exception as error: manifest['errors'].append(str(error))
    manifest['actual_duration_s']=time.perf_counter()-start
    manifest['samples']=len(rows)
    manifest['finished_at']=datetime.now(timezone.utc).isoformat()
    target=directory/'sensors.csv'
    if rows:
        with target.open('w',encoding='utf-8',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
        manifest['csv']='sensors.csv'; manifest['sha256']=hashlib.sha256(target.read_bytes()).hexdigest()
    manifest['cpu_thermal_validation']='NOT_VALIDATED'
    manifest['limitations']=['GPU readings do not validate CPU parameters.','Board electrical power is not automatically die thermal input.',
                            'No ambient sensor or external calibration is available. Device readings may be time-averaged.']
    path=directory/'manifest.json'; path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
    return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration',type=float,default=120)
    parser.add_argument('--interval',type=float,default=2)
    parser.add_argument('--output',type=Path,default=Path('data/validation/gpu-session'))
    args=parser.parse_args(); print(capture(args.output,args.duration,args.interval))
