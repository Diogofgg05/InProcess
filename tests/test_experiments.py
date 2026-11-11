from dataclasses import replace
import math
import pytest
from expecto_process_manager.simulation.experiments import ExperimentConfig,run_experiment,save_experiment,load_experiment
from expecto_process_manager.core.metrics import import_power,export_csv
from expecto_process_manager.core.cancellation import Cancellation,Cancelled
from expecto_process_manager.physics.euler import simulate
from expecto_process_manager.physics.thermal_model import ThermalModel
from expecto_process_manager.physics.differentiation import derivative,smooth
from expecto_process_manager.physics.validation import errors
from expecto_process_manager.simulation.noise import add_noise


def test_reproducible_round_trip(tmp_path):
    config = ExperimentConfig(duration=3,dt=.05,noise=.4,seed=123,scenario='Redução')
    experiment = run_experiment(config)
    path = tmp_path/'experiment.json'
    save_experiment(str(path),experiment,Cancellation())
    loaded = load_experiment(str(path),Cancellation())
    assert loaded.config == config
    assert loaded.simulation == experiment.simulation
    assert loaded.noisy == experiment.noisy
    assert loaded.report == experiment.report


def test_imported_power_retention_and_temperature_provenance():
    c = ExperimentConfig(initial=22,ambient=22,capacity=10,dissipation=1,duration=2,dt=.5,
                         source_times=[10,11,12],source_powers=[0,20,20],provenance='importado; origem não verificada')
    r = run_experiment(c).simulation
    # Exactly zero until the step at elapsed t=1, then constant 20 W for 1 s.
    exact = 22+20*(1-math.exp(-1/10))
    assert r.reference[-1] == pytest.approx(exact)
    assert r.temperatures[2] == 22
    assert r.provenance == 'simulado'


@pytest.mark.parametrize('body',[
    '', 'time,power\n0,1\n1,2', 'time_s,power_w\n0,1\n0,2',
    'time_s,power_w\n0,nan\n1,2','time_s,power_w\n0,-1\n1,2',
    'time_s,power_w\n0\n1,2', 'time_s,power_w\n0,1,extra\n1,2',
    'time_s,power_w,time_unit,power_unit\n0,1,ms,W\n1,2,ms,W'])
def test_bad_csv(tmp_path,body):
    path = tmp_path/'bad.csv'
    path.write_text(body,encoding='utf-8')
    with pytest.raises(ValueError): import_power(path)


def test_csv_size_limit(tmp_path):
    path = tmp_path/'big.csv'
    with open(path,'wb') as f: f.truncate(10*1024*1024+1)
    with pytest.raises(ValueError,match='grande'): import_power(path)


def test_cancellation_preserves_destination(tmp_path):
    token = Cancellation()
    token.cancel()
    path = tmp_path/'existing.csv'
    path.write_text('original',encoding='utf-8')
    with pytest.raises(Cancelled): export_csv(path,[{'a':1}],token)
    assert path.read_text(encoding='utf-8') == 'original'
    assert list(tmp_path.iterdir()) == [path]
    with pytest.raises(Cancelled): run_experiment(ExperimentConfig(),token)
    with pytest.raises(Cancelled): simulate(ThermalModel(),40,lambda t:45,10,.1,cancellation=token)


def test_experiment_schema_rejected(tmp_path):
    path = tmp_path/'wrong.json'
    path.write_text('{"schema": 100}',encoding='utf-8')
    with pytest.raises(ValueError): load_experiment(str(path),Cancellation())


@pytest.mark.parametrize('seed',[1,42,123])
@pytest.mark.parametrize('sigma',[.05,.2,1])
def test_noise_filter_multiple_realizations(seed,sigma):
    times = [i/100 for i in range(501)]
    clean = [math.sin(t) for t in times]
    noisy = add_noise(clean,sigma,seed)
    reference = derivative(times,clean)
    assert errors(derivative(times,smooth(noisy)),reference)['rmse'] < errors(derivative(times,noisy),reference)['rmse']


def test_config_rejects_uncovered_data():
    with pytest.raises(ValueError):
        ExperimentConfig(duration=3,source_times=[0,1],source_powers=[10,20],provenance='importado; origem não verificada')
