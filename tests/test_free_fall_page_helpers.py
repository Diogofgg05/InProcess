import csv
import pytest
from expecto_process_manager.core.cancellation import Cancellation,Cancelled
from expecto_process_manager.interface.free_fall_page import calculate_free_fall,export_free_fall


def parameters(**overrides):
    values=dict(height=100,initial_velocity=0,gravity=9.80665,duration=4,dt=.01)
    values.update(overrides)
    return values


def test_free_fall_presentation_matches_analytic_error():
    p=parameters()
    view=calculate_free_fall(p,Cancellation())
    assert view.max_error==pytest.approx(p['gravity']*p['duration']*p['dt']/2)
    assert view.max_energy_drift==pytest.approx(p['gravity']**2*p['duration']*p['dt']/2)
    assert view.result.velocities[-1]==pytest.approx(-p['gravity']*p['duration'])
    assert view.energy['Referência constante']==[p['gravity']*p['height']]*len(view.times)


def test_free_fall_preparation_bounded_and_no_ground_clamping():
    view=calculate_free_fall(parameters(height=1,duration=10,dt=.001),Cancellation())
    assert len(view.times)<=1500
    assert view.times[-1]==10
    assert view.result.heights[-1]<0
    assert len(view.result.times)>len(view.times)


def test_free_fall_export_full_series_and_cancel(tmp_path):
    view=calculate_free_fall(parameters(duration=1,dt=.1),Cancellation())
    path=tmp_path/'fall.csv'
    export_free_fall(path,view,Cancellation())
    with path.open(encoding='utf-8-sig',newline='') as stream: rows=list(csv.DictReader(stream))
    assert len(rows)==len(view.result.times)
    assert rows[0]['provenance']=='simulado'
    assert float(rows[-1]['time_s'])==1
    original=path.read_bytes()
    token=Cancellation()
    token.cancel()
    with pytest.raises(Cancelled): export_free_fall(path,view,token)
    assert path.read_bytes()==original
    assert list(tmp_path.iterdir())==[path]
