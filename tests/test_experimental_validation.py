"""Synthetic fixtures test provenance checks; these are not physical evidence."""
import csv
import hashlib
import json

import pytest

from expecto_process_manager.core import experimental_sensors as sensors
from expecto_process_manager.core.latency import LatencyTrace
from expecto_process_manager.physics.calibration import predict_zoh
from expecto_process_manager.physics.experimental_validation import evaluate_sessions, load_session


def session(root, name, start, *, interpretation='board_electrical', change=None):
    folder=root/name
    folder.mkdir()
    times=[start+i for i in range(100)]
    powers=[40. if i<50 else 20. for i in range(100)]
    temperatures=predict_zoh(times,powers,30.,22.,100.,2.)
    rows=[dict(index=0,device='fixture-gpu',temperature_scope='gpu_die',
               power_scope='gpu_board_electrical',utc_epoch_s=t,temperature_c=v,power_w=p)
          for t,v,p in zip(times,temperatures,powers)]
    if change: change(rows)
    target=folder/'sensors.csv'
    with target.open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    manifest=dict(schema=1,run_id=name,origin='MEASURED',csv=target.name,
                  sha256=hashlib.sha256(target.read_bytes()).hexdigest(),power_interpretation=interpretation)
    path=folder/'manifest.json'
    path.write_text(json.dumps(manifest),encoding='utf-8')
    return path


def test_nvidia_keeps_unavailable_values_and_explicit_domains():
    first,second=sensors.parse_nvidia('0, GPU A, 42, 5.2, 3\n1, GPU B, N/A, [Not Supported], N/A')
    assert first['temperature_c']==42 and first['power_w']==5.2
    assert first['temperature_scope']=='gpu_die'
    assert first['power_scope']=='gpu_board_electrical'
    assert first['calibrated'] is False and first['ambient_c'] is None
    assert second['temperature_c'] is None and second['power_w'] is None


@pytest.mark.parametrize('text',['0, GPU, -300, 2, 0','0, GPU, 42, -1, 0','unexpected'])
def test_invalid_driver_responses_are_rejected(text):
    with pytest.raises(ValueError): sensors.parse_nvidia(text)


def test_sensor_absence_is_not_synthetic_data(monkeypatch):
    monkeypatch.setattr(sensors.shutil,'which',lambda _:None)
    assert sensors.read_nvidia()==[]


def test_trace_bounded_and_records_failed_callbacks(monkeypatch):
    now=[0.]
    monkeypatch.setattr('expecto_process_manager.core.latency.time.perf_counter',lambda:now[0])
    trace=LatencyTrace(limit=2)
    for i in range(3):
        now[0]=i
        with trace.measure('update'): now[0]+=.1
    with pytest.raises(RuntimeError):
        with trace.measure('failed'): raise RuntimeError()
    trace.pulse(2.2,.3)
    assert len(trace.events)==2
    assert trace.spikes[-1]['overlapping_callbacks'][-1]['name']=='failed'
    assert 'not proof' in trace.as_dict()['interpretation']
    trace.pulse(3,.025)
    assert len(trace.spikes)==1


def test_independent_recordings_still_require_ambient_and_power_assumption(tmp_path):
    a=session(tmp_path,'a',0); b=session(tmp_path,'b',200)
    result=evaluate_sessions(a,b)
    assert result['status']=='NOT_EVALUATED' and len(result['reasons'])==2
    assert result['independent_recordings'] and not result['physical_validation']
    assert 'fit' not in result


def test_explicit_exploration_recovers_fixture_without_certifying_hardware(tmp_path):
    a=session(tmp_path,'a',0); b=session(tmp_path,'b',200)
    result=evaluate_sessions(a,b,ambient_c=22,allow_electrical_proxy=True)
    assert result['status']=='EXPLORATORY'
    assert result['fit']['capacity']==pytest.approx(100,rel=1e-6)
    assert result['fit']['validation']['errors']['rmse']<1e-8
    assert result['physical_validation'] is False


def test_validation_power_domain_also_requires_explicit_assumption(tmp_path):
    a=session(tmp_path,'a',0,interpretation='thermal_input')
    b=session(tmp_path,'b',200)
    assert evaluate_sessions(a,b,ambient_c=22)['status']=='NOT_EVALUATED'


def test_hash_and_recording_reuse_are_rejected(tmp_path):
    a=session(tmp_path,'a',0)
    with pytest.raises(ValueError,match='distintos'): evaluate_sessions(a,a)
    (a.parent/'sensors.csv').write_text('tampered',encoding='utf-8')
    with pytest.raises(ValueError,match='hash'): load_session(a)


def test_overlapping_trials_are_rejected(tmp_path):
    a=session(tmp_path,'a',0); b=session(tmp_path,'b',50)
    with pytest.raises(ValueError,match='disjuntas'): evaluate_sessions(a,b)


@pytest.mark.parametrize('change',[
    lambda r:r[1].update(utc_epoch_s=r[0]['utc_epoch_s']),
    lambda r:r[1].update(temperature_c='nan'),
    lambda r:r[1].update(power_w=-1),
    lambda r:r[1].update(device='another-device'),
    lambda r:r[1].update(power_scope='cpu_package'),
])
def test_invalid_experimental_samples_are_rejected(tmp_path,change):
    path=session(tmp_path,'a',0,change=change)
    with pytest.raises(ValueError): load_session(path)
