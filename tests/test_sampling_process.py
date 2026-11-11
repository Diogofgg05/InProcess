import io
import json
from types import SimpleNamespace
from unittest.mock import Mock
from expecto_process_manager.core.monitoring import Snapshot
from expecto_process_manager.core import sampling_process


def test_protocol_is_read_only_and_publishes_sensor_age(monkeypatch):
    provider = Mock()
    provider.monitor = SimpleNamespace(history=[])
    provider.sample.return_value = Snapshot(100,None,[],10,90,10,0,None,None,None,
                                           swap_sampled_at=150,temperature_sampled_at=None,
                                           frequency_sampled_at=199)
    provider.list_processes.return_value = [dict(status='running',status_sampled_at=198,
                                                kind='process',kind_sampled_at=190)]
    monkeypatch.setattr(sampling_process,'PsutilProvider',lambda:provider)
    monkeypatch.setattr(sampling_process.time,'time',lambda:200)
    request = io.StringIO('\n'.join(json.dumps(r) for r in [
        {'version':1,'op':'terminate','pid':123},
        {'version':1,'op':'sample','refresh_pids':[123,'456']},
        {'version':99,'op':'sample'}])+'\n')
    output = io.StringIO()
    sampling_process.serve(request,output)
    first,valid,last = [json.loads(line) for line in output.getvalue().splitlines()]
    assert not first['ok'] and not last['ok']
    assert valid['ok']
    assert valid['snapshot']['swap_age_s']==50
    assert valid['snapshot']['frequency_age_s']==1
    assert valid['snapshot']['temperature_age_s'] is None
    assert valid['rows'][0]['status_age_s']==2
    provider.processes.invalidate_status.assert_called_once_with(123)
    provider.processes.control.assert_not_called()
    assert provider.monitor.history.maxlen==1


def test_protocol_recovers_after_measurement_failure(monkeypatch):
    provider=Mock()
    provider.monitor=SimpleNamespace(history=[])
    snapshot=Snapshot(1,0,[0],10,90,10,0,None,None,None)
    provider.sample.side_effect=[OSError('sensor indisponível'),snapshot]
    provider.list_processes.return_value=[]
    monkeypatch.setattr(sampling_process,'PsutilProvider',lambda:provider)
    requests=io.StringIO('{"version":1,"op":"sample"}\n'*2)
    output=io.StringIO()
    sampling_process.serve(requests,output)
    first,second=[json.loads(line) for line in output.getvalue().splitlines()]
    assert not first['ok'] and second['ok']
    assert first['error']=='sensor indisponível'
