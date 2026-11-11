from dataclasses import asdict
import csv
import json
import math
import pytest
from expecto_process_manager.core.cancellation import Cancellation,Cancelled
from expecto_process_manager.physics.gravity import GravityConfig,run_gravity
from expecto_process_manager.interface.gravity_page import _save_config,_open_config,_export
from expecto_process_manager.interface.gravity_visuals import prepare_gravity


def test_gravity_configuration_round_trip(tmp_path):
    config=GravityConfig(duration=300,dt=5,velocity_factor=.9)
    path=tmp_path/'gravity.json'
    _save_config(path,config,Cancellation())
    payload=json.loads(path.read_text(encoding='utf-8'))
    assert payload['provenance']=='simulado'
    loaded,presentation=_open_config(path,Cancellation())
    assert asdict(loaded.config)==asdict(config)
    fresh=run_gravity(config)
    assert loaded.trajectories['Velocity Verlet'].x==fresh.trajectories['Velocity Verlet'].x
    assert not presentation.errors


def test_gravity_csv_full_samples_and_units(tmp_path):
    experiment=run_gravity(GravityConfig(duration=100,dt=10))
    path=tmp_path/'gravity.csv'
    _export(path,experiment,Cancellation())
    with path.open(encoding='utf-8-sig',newline='') as stream:
        rows=list(csv.DictReader(stream))
    assert len(rows)==len(experiment.times)*len(experiment.trajectories)
    assert float(rows[0]['x_m'])==experiment.config.radius
    assert float(rows[0]['time_s'])==0
    assert all(row['provenance']=='simulado' for row in rows)
    assert float(rows[-1]['time_s'])==100


@pytest.mark.parametrize('operation',['config','csv'])
def test_gravity_cancel_preserves_existing_destination(tmp_path,operation):
    target=tmp_path/'original.txt'
    target.write_text('original',encoding='utf-8')
    token=Cancellation()
    token.cancel()
    with pytest.raises(Cancelled):
        if operation=='config': _save_config(target,GravityConfig(),token)
        else: _export(target,run_gravity(GravityConfig(duration=10,dt=1)),token)
    assert target.read_text(encoding='utf-8')=='original'
    assert list(tmp_path.iterdir())==[target]


def test_gravity_rejects_file_schema_and_size(tmp_path):
    path=tmp_path/'bad.json'
    path.write_text('{"schema": "other"}',encoding='utf-8')
    with pytest.raises(ValueError): _open_config(path,Cancellation())
    path.write_bytes(b' '*65537)
    with pytest.raises(ValueError): _open_config(path,Cancellation())


def test_preparation_is_bounded_and_keeps_endpoints():
    experiment=run_gravity(GravityConfig(duration=2000,dt=.5))
    view=prepare_gravity(experiment,Cancellation())
    assert len(view.times)<=1500
    assert view.times[0]==0
    assert view.times[-1]==experiment.times[-1]
    assert len(experiment.times)>len(view.times)
    for series in view.orbits.values(): assert len(series)==len(view.times)


def test_near_escape_energy_relative_is_marked_undefined():
    experiment=run_gravity(GravityConfig(duration=100,dt=10,velocity_factor=math.sqrt(2)))
    view=prepare_gravity(experiment,Cancellation())
    assert not view.energy_drift
    assert 'energia relativa indefinida' in view.note
