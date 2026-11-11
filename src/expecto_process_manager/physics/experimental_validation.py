"""Independent recorded trials with explicit provenance and a physical-evidence gate."""
import csv
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
from .calibration import ThermalSeries,fit_thermal


def load_session(manifest_path,device_index=0):
    path=Path(manifest_path)
    if path.stat().st_size>2*1024*1024: raise ValueError('Manifesto demasiado grande.')
    metadata=json.loads(path.read_text(encoding='utf-8'))
    if metadata.get('schema')!=1 or metadata.get('origin') not in ('DRIVER_REPORTED','MEASURED'):
        raise ValueError('Sessão sem esquema/origem experimental suportados.')
    filename=metadata.get('csv')
    if not isinstance(filename,str) or Path(filename).name!=filename: raise ValueError('O CSV deve estar na pasta da sessão.')
    target=path.parent/filename
    if target.stat().st_size>10*1024*1024: raise ValueError('CSV demasiado grande.')
    if hashlib.sha256(target.read_bytes()).hexdigest()!=metadata.get('sha256'):
        raise ValueError('O CSV foi alterado depois da aquisição; hash incompatível.')
    rows=[]
    with target.open(encoding='utf-8-sig',newline='') as stream:
        for row in csv.DictReader(stream):
            if int(row.get('index',device_index))==device_index: rows.append(row)
            if len(rows)>20000: raise ValueError('Máximo de 20000 amostras por sessão.')
    if len(rows)<4: raise ValueError('Sessão sem amostras suficientes.')
    for key in ('device','temperature_scope','power_scope'):
        if not rows[0].get(key) or any(row.get(key)!=rows[0][key] for row in rows):
            raise ValueError('Domínio/dispositivo inconsistente dentro da sessão: '+key)
    times=[]; temperatures=[]; powers=[]
    for row in rows:
        try: t,temp,power=[float(row[k]) for k in ('utc_epoch_s','temperature_c','power_w')]
        except (TypeError,ValueError,KeyError) as error: raise ValueError('Amostra sem tempo/temperatura/potência válidos.') from error
        if not all(math.isfinite(v) for v in (t,temp,power)) or temp< -273.15 or power<0: raise ValueError('Amostra física inválida.')
        if times and t<=times[-1]: raise ValueError('Tempos experimentais não crescentes.')
        times.append(t); temperatures.append(temp); powers.append(power)
    metadata=dict(metadata,selected_device=rows[0].get('device'),device_index=device_index,
                  temperature_scope=rows[0].get('temperature_scope'),power_scope=rows[0].get('power_scope'))
    return metadata,ThermalSeries(times,temperatures,powers)


def evaluate_sessions(training_path,validation_path,*,ambient_c=None,allow_electrical_proxy=False,token=None):
    training,data=load_session(training_path)
    validation,holdout=load_session(validation_path)
    if not all(isinstance(m.get('run_id'),str) and m['run_id'] for m in (training,validation)) or training['run_id']==validation['run_id']:
        raise ValueError('Treino e validação devem ser aquisições com identificadores distintos.')
    if training['sha256']==validation['sha256']: raise ValueError('Treino e validação reutilizam os mesmos dados.')
    for key in ('selected_device','temperature_scope','power_scope','device_index'):
        if training.get(key)!=validation.get(key): raise ValueError('Sessões de dispositivos/domínios incompatíveis: '+key)
    if not (data.times[-1]<holdout.times[0] or holdout.times[-1]<data.times[0]):
        raise ValueError('As sessões devem ter janelas de aquisição disjuntas.')
    reasons=[]
    if ambient_c is None: reasons.append('Não existe temperatura ambiente medida/declarada; C e k não são ajustados com ambiente inventado.')
    elif not math.isfinite(ambient_c) or ambient_c< -273.15: raise ValueError('Ambiente inválido.')
    electrical=any(m.get('power_interpretation')!='thermal_input' for m in (training,validation))
    if electrical and not allow_electrical_proxy:
        reasons.append('Potência elétrica de placa não é automaticamente entrada térmica do modelo. É necessária uma hipótese explícita para um estudo exploratório.')
    result=dict(schema=1,target=training['selected_device'],origin='EXPERIMENTAL_INPUT',
        training_run=training['run_id'],validation_run=validation['run_id'],independent_recordings=True,
        training_samples=len(data.times),validation_samples=len(holdout.times),ambient_c=ambient_c,
        status='NOT_EVALUATED' if reasons else 'EXPLORATORY',physical_validation=False,reasons=reasons,
        input_scope={key:training.get(key) for key in ('temperature_scope','power_scope')},
        limitations=['Distinct run IDs and hashes prevent accidental reuse; they do not certify instrument calibration.',
            'Unknown sensor uncertainty and electrical-to-thermal conversion prevent a physical validation claim.',
            'No guarantee of CPU thermal safety is inferred from GPU data.'])
    if not reasons:
        try:
            fit=fit_thermal(data.times,data.temperatures,data.powers,ambient_c,validation=holdout,token=token)
            result['fit']=asdict(fit)
        except ValueError as error:
            result['status']='NOT_IDENTIFIABLE'; result['reasons'].append(str(error))
    return result
