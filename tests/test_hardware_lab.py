"""Independent equations, energy balances and failure paths for lab 5.0."""
import math
import json
import pytest

from expecto_process_manager.core.cancellation import Cancellation,Cancelled
from expecto_process_manager.physics.hardware_models import (
    RCCircuit,RLCircuit,FanRotor,FanMotor,Oscillator,heat_path,parallel_plates,ohm)
from expecto_process_manager.physics.feedback import ThermalFeedback
from expecto_process_manager.physics.acoustics import spectrum,tonal_frequencies,wave_field
from expecto_process_manager.physics.units import convert,verify_balances
from expecto_process_manager.physics.measurement import repeatability,propagate,energy_uncertainty
from expecto_process_manager.physics.numerical.ode import solve_ivp
from expecto_process_manager.physics.numerical.validation import convergence_study
from expecto_process_manager.physics.thermal_model import ThermalModel
from expecto_process_manager.simulation.hardware_experiments import (
    HardwareConfig,SPECS,run_hardware,export_hardware,import_observations,validate_observations)


def test_requested_cpu_reference_is_calculated_from_equation():
    model=ThermalModel(25,180,1.2)
    assert model.ambient+45/model.dissipation==62.5
    assert model.capacity/model.dissipation==150
    assert model.exact(30,45,120)==pytest.approx(47.8968086662)


@pytest.mark.parametrize('method,order',[('euler',1),('heun',2),('rk4',4)])
@pytest.mark.parametrize('model',[RCCircuit(),RLCircuit(resistance=1),FanRotor()])
def test_physical_first_order_convergence(model,method,order):
    def solve(dt): return solve_ivp(model.rhs,0.,(0.,1.),dt,method).values[-1][0]
    rows=convergence_study(solve,model.exact(1.),[.2,.1,.05])
    assert rows[-1].observed_order==pytest.approx(order,abs=.12)


def test_rc_discharge_and_half_source_energy_dissipated_on_charge():
    circuit=RCCircuit(resistance=2,capacitance=.5,voltage=4)
    result=run_hardware(HardwareConfig('rc',dict(resistance=2,capacitance=.5,voltage=4),duration=12,dt=.005))
    end=result.observables['rk4'][-1]
    assert end['voltage_v']==pytest.approx(4,abs=3e-5)
    assert end['stored_j']==pytest.approx(4,abs=1e-4)
    assert abs(result.balances['rk4'])<1e-4
    assert RCCircuit(2,.5,0).exact(1,4)==pytest.approx(4/math.e)
    assert circuit.observables([0])['current_a']==2


def test_rotor_newton_energy_angular_momentum_and_equilibrium():
    rotor=FanRotor(inertia=.1,torque=.2,damping=0)
    assert rotor.rhs(0,[2])==[2]
    obs=rotor.observables([2])
    assert obs['stored_j']==pytest.approx(.2)
    assert obs['angular_momentum_kg_m2_s']==pytest.approx(.2)
    free=FanRotor(inertia=.1,torque=0,damping=0)
    assert solve_ivp(free.rhs,2,(0,2),.1,'rk4').values[-1]==[2]
    for torque in (-.2,0,.2):
        drag=FanRotor(inertia=.1,torque=torque,damping=.1,drag=.2)
        assert drag.rhs(0,[drag.equilibrium])[0]==pytest.approx(0,abs=1e-15)


def test_electromechanical_conversion_has_no_spurious_energy_source():
    motor=FanMotor()
    y=[.4,20,40]
    di,dw,dT=motor.rhs(0,y)
    obs=motor.observables(y)
    stored_rate=motor.inductance*y[0]*di+motor.inertia*y[1]*dw
    assert stored_rate==pytest.approx(obs['input_w']-obs['joule_w']-obs['drag_w'])
    assert motor.capacity*dT==pytest.approx(motor.thermal_power-obs['conductance_w_k']*(40-motor.ambient))
    result=run_hardware(HardwareConfig('motor',duration=1,dt=.001))
    assert abs(result.balances['rk4'])<.001
    assert max(o['current_a'] for o in result.observables['rk4'])>result.observables['rk4'][-1]['current_a']


@pytest.mark.parametrize('damping,regime',[(0,'não amortecido'),(.08,'subamortecido'),(2*math.sqrt(.02*20),'crítico'),(3,'sobreamortecido')])
def test_oscillator_all_free_damping_regimes(damping,regime):
    model=Oscillator(damping=damping)
    result=solve_ivp(model.rhs,[.001,.002],(0,.5),.0005,'rk4')
    assert model.regime==regime
    assert result.values[-1][0]==pytest.approx(model.exact_free(.5,(.001,.002)),abs=2e-11)
    assert model.natural_frequency==pytest.approx(5.0329212104)
    assert model.observables(result.values[-1])['stored_j']<=model.observables([.001,.002])['stored_j']+1e-12


def test_resonance_peak_is_not_always_natural_frequency():
    model=Oscillator(force=.01)
    peak=model.resonance_frequency
    assert peak<model.natural_frequency
    assert model.amplitude(peak)>model.amplitude(0)
    assert model.amplitude(peak)>model.amplitude(peak*.9)
    assert model.amplitude(peak)>model.amplitude(peak*1.1)
    assert Oscillator(damping=10,force=.01).resonance_frequency is None
    assert tonal_frequencies(1200,7)=={'rotation_hz':20,'blade_passage_hz':140}


@pytest.mark.parametrize('damping',[0,.08,3])
def test_forced_transient_matches_independent_formula(damping):
    model=Oscillator(force=.01,damping=damping)
    result=solve_ivp(model.rhs,[.001,.002],(0,.8),.0005,'rk4')
    assert result.values[-1][0]==pytest.approx(model.exact_forced(.8,(.001,.002)),abs=2e-10)


def test_undamped_exact_resonance_grows_without_finite_steady_amplitude():
    model=Oscillator(force=.01,damping=0,frequency=math.sqrt(1000)/(2*math.pi))
    result=solve_ivp(model.rhs,[0.,0.],(0,1),.0005,'rk4')
    assert result.values[-1][0]==pytest.approx(model.exact_forced(1),abs=2e-10)
    assert math.isinf(model.amplitude(model.natural_frequency))


def test_fourier_and_convection_share_one_heat_flow():
    result=heat_path(60,25,200,.001,.005,25)
    assert -200*.001*result['gradient_k_m']==pytest.approx(result['heat_w'])
    assert 25*.001*(result['surface_c']-25)==pytest.approx(result['heat_w'])
    assert 25<result['surface_c']<60
    plates=parallel_plates(5,.001,.01)
    assert plates['field_v_m']==5000
    assert plates['energy_j']==pytest.approx(.5*plates['capacitance_f']*25)


@pytest.mark.parametrize('kwargs',[dict(voltage=12,current=2),dict(voltage=12,resistance=6),dict(current=2,resistance=6)])
def test_ohm_and_three_equivalent_joule_power_equations(kwargs):
    result=ohm(**kwargs)
    v,i,r=result['voltage_v'],result['current_a'],result['resistance_ohm']
    assert result['joule_w']==v*i==r*i*i==v*v/r==24
    with pytest.raises(ValueError): ohm(voltage=0,current=0)


@pytest.mark.parametrize('window',['hann','rectangular'])
def test_fft_single_tone_amplitude_and_nyquist_warning(window):
    fs,n,f=1024,1024,64
    t=[i/fs for i in range(n)]
    y=[3+2*math.sin(2*math.pi*f*time) for time in t]
    result=spectrum(t,y,window=window,expected_frequencies=[600])
    assert result.peak_frequency==64
    assert result.amplitudes[64]==pytest.approx(2,abs=1e-12)
    assert result.amplitudes[0]==pytest.approx(0,abs=1e-12)
    assert result.resolution==1
    assert 'Risco de aliasing' in result.report


def test_fft_rejects_irregular_sampling_and_hidden_truncation():
    with pytest.raises(ValueError): spectrum([0,1,2,3,4,5,6,8],[0]*8)
    with pytest.raises(ValueError): spectrum(list(range(9)),[0]*9)


def test_lossless_wave_satisfies_pde_and_reflecting_boundary():
    x,t,dx,dt=.3,.001,1e-4,1e-4/343
    p=lambda x,t:wave_field(x,t,frequency=100)
    pxx=(p(x+dx,t)-2*p(x,t)+p(x-dx,t))/dx**2
    ptt=(p(x,t+dt)-2*p(x,t)+p(x,t-dt))/dt**2
    assert ptt==pytest.approx(343**2*pxx,rel=1e-6)
    assert wave_field(1,t,reflection=-1)==pytest.approx(0,abs=1e-12)


def test_feedback_equilibrium_and_local_stability():
    model=ThermalFeedback()
    analysis=model.equilibrium_analysis()
    assert model.rhs(0,[analysis['temperature_c'],analysis['control']])==pytest.approx([0,0],abs=1e-13)
    assert analysis['locally_stable']
    assert analysis['trace_s_inv']<0
    assert analysis['determinant_s_inv2']>0


def test_units_and_measurement_uncertainties():
    assert all(verify_balances().values())
    assert convert(1,'W','mW')==1000
    assert convert(3600,'J','Wh')==1
    assert convert(25,'°C','K')==298.15
    assert convert(1200,'RPM','rad/s',rotational=True)==pytest.approx(40*math.pi)
    with pytest.raises(ValueError): convert(50,'Hz','RPM')
    with pytest.raises(ValueError): convert(1,'V','A')
    with pytest.raises(ValueError): convert(-1,'K','°C')
    assert propagate([2,3],[.1,.2])==pytest.approx(math.sqrt(.04+.36))
    assert propagate([1,1],[1,1],[[1,1],[1,1]])==2
    with pytest.raises(ValueError): propagate([1,-1],[1,1],[[1,2],[2,1]])
    assert energy_uncertainty([0,1,2],[1,1,1])==pytest.approx(math.sqrt(1.5))
    result=repeatability([1,2,3],.1)
    assert result['mean']==2 and result['sample_std']==1


@pytest.mark.parametrize('key',list(SPECS))
def test_each_physical_experiment_exports_reproducible_results(key,tmp_path):
    result=run_hardware(HardwareConfig(key,duration=.1,dt=.001))
    path=export_hardware(result,tmp_path)
    assert path.exists()
    saved=json.loads((tmp_path/(key+'.json')).read_text(encoding='utf-8'))
    assert saved['metadata']['origin']=='SIMULATED'
    assert saved['metadata']['model_version']=='5.0.0'
    assert len(saved['metadata']['parameter_units'])==len(saved['metadata']['parameters'])
    replay=run_hardware(HardwareConfig(**saved['config']))
    assert replay.solutions==result.solutions
    assert 'method,origin' in (tmp_path/(key+'.csv')).read_text(encoding='utf-8').splitlines()[0]


def test_observations_are_compared_at_actual_nonuniform_times(tmp_path):
    path=tmp_path/'measurement.csv'
    path.write_text('time_s,value,unit\n0,0,V\n0.33,1.405381332840,V\n1,3.160602794143,V\n',encoding='utf-8')
    times,observed=import_observations(path,'V')
    result=run_hardware(HardwareConfig('rc',duration=1,dt=.01))
    validation=validate_observations(result,times,observed)
    assert validation['origin']=='IMPORTED_UNVERIFIED'
    assert validation['errors']['rmse']<1e-8
    with pytest.raises(ValueError): import_observations(path,'A')
    with pytest.raises(ValueError): validate_observations(result,[0,2],[0,0])


def test_work_and_memory_budgets_and_cancellation():
    with pytest.raises(ValueError): run_hardware(HardwareConfig(duration=1e6,dt=.001))
    with pytest.raises(ValueError): solve_ivp(lambda t,y:y,[0]*100,(0,100000),1)
    token=Cancellation(); token.cancel()
    with pytest.raises(Cancelled): run_hardware(token=token)
    with pytest.raises(Cancelled): spectrum(list(range(8)),[0]*8,token=token)


def test_report_axes_resolve_small_physical_energy_values():
    import re
    from expecto_process_manager.reporting.document import Figure,Curve
    from expecto_process_manager.reporting.render import figure_html
    html=figure_html(Figure('Energia','Tempo (s)','J',[Curve('Capacitor',[0,1],[0,1e-5])]))
    path=re.search(r'<path d="(M[^\"]+)" fill="none" stroke="#2176c1"',html).group(1)
    points=re.findall(r'[ML]([\d.]+),([\d.]+)',path)
    assert abs(float(points[-1][1])-float(points[0][1]))>200


@pytest.mark.parametrize('factory,kwargs',[(RCCircuit,{'resistance':0}),(RLCircuit,{'inductance':-1}),
    (FanRotor,{'inertia':0}),(Oscillator,{'mass':0}),(FanMotor,{'constant':-1}),
    (ThermalFeedback,{'disturbance':100}),(ThermalModel,{'ambient':-274})])
def test_invalid_physical_domains(factory,kwargs):
    with pytest.raises(ValueError): factory(**kwargs)
