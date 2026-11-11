from pathlib import Path
import re
import pytest
from expecto_process_manager.core.cancellation import Cancellation,Cancelled
from expecto_process_manager.reporting.document import ScientificReport,Figure,Curve
from expecto_process_manager.reporting.render import render_report,save_report,figure_html
from expecto_process_manager.reporting.service import generate_report
from expecto_process_manager.simulation.experiments import ExperimentConfig,run_experiment
from expecto_process_manager.physics.engine import ScientificPhysicsEngine
from expecto_process_manager.physics.units import verify_balances,W,S,J


def test_html_escapes_values_and_is_self_contained(tmp_path):
    report=ScientificReport('<script>x</script>','test','SIMULATED','Testar',
                            assumptions=['<unsafe>'],parameters=[('P',50,'W')],
                            equations=['E = P · Δt'],metadata={'Teste':'<script>bad</script>'})
    html=render_report(report)
    assert '<script>' not in html
    assert '&lt;script&gt;' in html
    assert 'E = P · Δt' in html
    assert '<script src=' not in html and '<link rel=' not in html
    path=save_report(tmp_path/'report.html',report)
    assert Path(path).read_text(encoding='utf-8')==html


def test_report_cancellation_preserves_existing_file(tmp_path):
    path=tmp_path/'existing.html'
    path.write_text('original',encoding='utf-8')
    token=Cancellation(); token.cancel()
    with pytest.raises(Cancelled):
        save_report(path,ScientificReport('T','test','SIMULATED',''),token)
    assert path.read_text(encoding='utf-8')=='original'


def test_svg_equal_scale_and_complete_legend():
    name='Euler explícito com identificação completa sem reticências'
    html=figure_html(Figure('Órbita','x (km)','y (km)',[Curve(name,[1,0,-1,0,1],[0,1,0,-1,0])],True))
    assert name in html
    data=re.search(r'<path d="([ML0-9., -]+)" fill="none" stroke="#2176c1"',html).group(1)
    points=[tuple(map(float,p)) for p in re.findall(r'[ML]([\d.]+),([\d.]+)',data)]
    rx=(points[0][0]-points[2][0])/2
    ry=(points[3][1]-points[1][1])/2
    assert rx==pytest.approx(ry,abs=.002)


def test_thermal_automatic_report_contains_models_and_real_methods(tmp_path):
    experiment=run_experiment(ExperimentConfig(duration=10,dt=.1))
    generated=generate_report('thermal',experiment,{'metadata':{'Instrumentação':'SIMULATED'}},tmp_path,Cancellation())
    html=Path(generated.path).read_text(encoding='utf-8')
    for text in ('Euler','Heun','RK4','Balanço térmico','C/k','Hipóteses','Limitações','SIMULATED','Tempo do cálculo'):
        assert text in html
    assert '<svg' in html
    assert '<svg' not in generated.preview_html


def test_scientific_api_and_dimensions():
    engine=ScientificPhysicsEngine()
    assert engine.integrate([0,5,10],[50,50,50])==500
    result=engine.solve(lambda t,y:-y[0],1,(0,1),.1,'rk4')
    assert result.values[-1][0]==pytest.approx(.36787944,rel=1e-5)
    assert W*S==J
    assert all(verify_balances().values())
