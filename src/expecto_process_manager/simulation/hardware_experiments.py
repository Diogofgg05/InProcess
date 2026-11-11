"""Reproducible physical experiments using the existing numerical engine.

Results retain parameters, SI units, initial conditions, origin and version.
Imported observations are compared only at their actual time stamps.
"""
from dataclasses import asdict, dataclass, field
from html import escape
import csv
import json
import math
from pathlib import Path
from time import perf_counter

from ..core.cancellation import Cancellation
from ..physics.hardware_models import RCCircuit, RLCircuit, FanRotor, FanMotor, Oscillator
from ..physics.feedback import ThermalFeedback
from ..physics.numerical.ode import solve_ivp, METHODS
from ..physics.numerical._validation import finite_values, samples
from ..physics.numerical.validation import metrics
from ..physics.numerical.integration import quadrature


# name, unit, configurable physical domain. No expressions are evaluated.
PARAMETERS = {
    'resistance':('R','Ω',1e-6,1e9), 'capacitance':('C','F',1e-12,1e3),
    'inductance':('L','H',1e-9,1e4), 'voltage':('Vs','V',-1000,1000),
    'inertia':('J','kg·m²',1e-12,100), 'torque':('τmotor','N·m',-10,10),
    'damping':('Amortecimento','SI: ver equação',0,1e4), 'drag':('Resistência quadrática','N·m·s²',0,1e3),
    'constant':('Ke = Kt','V·s/rad = N·m/A',0,100), 'mass':('m','kg',1e-6,1e3),
    'stiffness':('k','N/m',1e-6,1e9), 'force':('F0','N',0,1e3), 'frequency':('f','Hz',0,1e5),
    'capacity':('C térmico','J/K',1e-3,1e6), 'ambient':('Ta','°C',-273.15,1000),
    'thermal_power':('Pth CPU','W',0,1e4),'base_conductance':('k0','W/K',1e-6,1e4),
    'speed_gain':('β','W·s/(K·rad)',0,1e3),'power':('Pth','W',0,1e4),
    'base':('k0','W/K',1e-6,1e4),'gain':('β','W/K',0,1e4),
    'target':('T alvo','°C',-273.15,1000),'proportional':('Kp','1/K',0,100),
    'lag':('τ controlo','s',1e-6,1e4),'disturbance':('Perturbação','W',0,1e4),
}

OBSERVABLE_UNITS = {
    'voltage_v':'V','current_a':'A','stored_j':'J','input_w':'W','joule_w':'W','drag_w':'W',
    'mechanical_w':'W','damping_w':'W','omega_rad_s':'rad/s','rpm':'RPM',
    'acceleration_rad_s2':'rad/s²','angular_momentum_kg_m2_s':'kg·m²/s',
    'temperature_c':'°C','conductance_w_k':'W/K','displacement_m':'m','velocity_m_s':'m/s','control':'1',
}
STATE_UNITS = {'rc':['V'],'rl':['A'],'rotor':['rad/s'],'motor':['A','rad/s','°C'],
               'vibration':['m','m/s'],'forced':['m','m/s'],'feedback':['°C','1']}


@dataclass(frozen=True)
class ModelSpec:
    title: str
    factory: object
    initial: tuple
    duration: float
    dt: float
    primary: str
    unit: str
    equations: str
    assumptions: str
    interpretation: str
    limitations: str


SPECS = {
    'rc':ModelSpec('Circuito RC',RCCircuit,(0.,),5.,.01,'voltage_v','V',
        'Kirchhoff: Vs=Ri+Vc; i=C dVc/dt ⇒ dVc/dt=(Vs−Vc)/(RC); Ec=CVc²/2; P=Vi=Ri²+dEc/dt.',
        'Fonte ideal constante; R e C positivos e constantes; capacitor ideal; V0 configurável.',
        'τ=RC determina carga/descarga; Vs=0 permite descarga. As perdas RI² podem alimentar um nó térmico.',
        'Modelo de filtragem/armazenamento; não reproduz um VRM comutado ou campos internos do CPU.'),
    'rl':ModelSpec('Circuito RL',RLCircuit,(0.,),.5,.001,'current_a','A',
        'Kirchhoff: L di/dt=Vs−Ri; i=Vs/R+(i0−Vs/R)e^(−Rt/L); EL=Li²/2.',
        'Fonte DC ideal, indutor linear sem saturação e resistência constante.',
        'τ=L/R limita a rapidez da corrente; o campo magnético armazena energia enquanto RI² a dissipa.',
        'Não simula a comutação, núcleo magnético ou controlo de um VRM real.'),
    'rotor':ModelSpec('Dinâmica de rotação da ventoinha',FanRotor,(0.,),5.,.01,'omega_rad_s','rad/s',
        'Newton: Jω′=τmotor−bω−cω|ω|; L=Jω; Erot=Jω²/2; Pmec=τmotor ω.',
        'Rotor rígido de inércia constante; binário constante; resistência viscosa e arrasto quadrático.',
        'O equilíbrio iguala binário motor e resistente. L só se conserva quando o binário resultante é zero.',
        'Parâmetros ilustrativos; potência mecânica não é potência elétrica. Sem controlo de ventoinhas.'),
    'motor':ModelSpec('Ventoinha eletromecânica e arrefecimento',FanMotor,(0.,0.,30.),5.,.001,'omega_rad_s','rad/s',
        'L i′=V−Ri−Kω; Jω′=Ki−bω−cω|ω|; C T′=Pth−(k0+β|ω|)(T−Ta). Ke=Kt=K em SI.',
        'Motor DC equivalente; conversão ideal Ke=Kt; dissipação em função da rotação é hipótese explícita.',
        'A contraeletromotriz reduz a corrente após o arranque. Perdas RI² aquecem o motor, não o CPU deste modelo.',
        'Não descreve a eletrónica BLDC. Pth do CPU é entrada separada; não somar perdas do motor à mesma potência.'),
    'vibration':ModelSpec('Vibração livre amortecida',Oscillator,(.001,0.),2.,.001,'displacement_m','m',
        'Newton: mx″+cx′+kx=F0 cos(2πft); x′=v; v′=(F−cv−kx)/m; E=mv²/2+kx²/2.',
        'Um modo linear equivalente do suporte/chassis; pequenas deformações; parâmetros constantes.',
        'F0=0 dá vibração livre; ζ=c/(2√mk) separa regimes livre, subamortecido, crítico e sobreamortecido.',
        'Não implica medição de vibração pelo software nem diagnóstico de avaria.'),
    'forced':ModelSpec('Excitação periódica e ressonância',lambda **p:Oscillator(**({'force':.01}|p)),(0.,0.),3.,.001,'displacement_m','m',
        'mx″+cx′+kx=F0 cos(Ωt); A(Ω)=|F0|/√((k−mΩ²)²+(cΩ)²); Ω=2πf.',
        'Resposta linear; curva de amplitude estacionária distinta do transiente no tempo.',
        'Pico de deslocamento só existe para ζ<1/√2; frot=RPM/60 e fpassagem=Npás frot.',
        'Frequência elevada não prova ressonância. Sem amortecimento, ressonância não admite amplitude estacionária finita.'),
    'feedback':ModelSpec('Realimentação térmica não linear',ThermalFeedback,(30.,0.),180.,.1,'temperature_c','°C',
        'CT′=P+A sin(2πft)−(k0+βu)(T−Ta); τu u′=clip(Kp(T−Talvo),0,1)−u.',
        'Saturação não linear; atuador com atraso de primeira ordem, não atraso puro; ambiente constante.',
        'Equilíbrio e estabilidade local via traço/determinante do Jacobiano. Oscilações não demonstram caos.',
        'Controlador hipotético sem atuação no hardware; sem limiares com histerese, atraso puro ou alegação de caos.'),
}


@dataclass(frozen=True)
class HardwareConfig:
    model: str = 'rc'
    parameters: dict = field(default_factory=dict)
    initial: tuple | None = None
    duration: float | None = None
    dt: float | None = None


@dataclass
class HardwareExperiment:
    config: HardwareConfig
    metadata: dict
    times: list
    solutions: dict
    observables: dict
    reference: list | None
    errors: dict
    balances: dict
    frequency_response: dict | None
    report: str


def run_hardware(config=HardwareConfig(),token=None):
    token = token or Cancellation()
    token.check()
    if config.model not in SPECS: raise ValueError('Modelo físico desconhecido.')
    spec = SPECS[config.model]
    try: model = spec.factory(**config.parameters)
    except TypeError as error: raise ValueError('Parâmetros não reconhecidos pelo modelo.') from error
    initial = finite_values(config.initial if config.initial is not None else spec.initial)
    if len(initial)!=len(spec.initial): raise ValueError('Dimensão das condições iniciais inválida.')
    if config.model == 'motor' and initial[2]<-273.15: raise ValueError('Temperatura abaixo do zero absoluto.')
    if config.model == 'feedback' and (initial[0]<-273.15 or not 0<=initial[1]<=1): raise ValueError('Estado térmico/controlo inválido.')
    duration,dt = finite_values([spec.duration if config.duration is None else config.duration,spec.dt if config.dt is None else config.dt])
    if duration<=0 or dt<=0 or duration/dt>50000: raise ValueError('Duração/passo positivos; máximo 50000 passos por método.')
    deadline = perf_counter()+20
    class Budget:
        def check(self):
            token.check()
            if perf_counter()>deadline: raise ValueError('Limite de cálculo de 20 s excedido; reduza duração ou número de passos.')
    budget = Budget()
    trajectories,observations,timings = {},{},{}
    for method in METHODS:
        start = perf_counter()
        result = solve_ivp(model.rhs,initial,(0.,duration),dt,method,budget)
        trajectories[method] = result.values
        observations[method] = [model.observables(y) for y in result.values]
        timings[method] = perf_counter()-start
    times = result.times
    reference = None
    if config.model in ('rc','rl') or config.model=='rotor' and model.drag==0:
        reference = [model.exact(t,initial[0]) for t in times]
    elif config.model in ('vibration','forced'):
        reference = [model.exact_forced(t,initial) for t in times]
    errors = {method:metrics([o[spec.primary] for o in obs],reference) for method,obs in observations.items()} if reference is not None else {}
    balances = {}
    for method,obs in observations.items():
        budget.check()
        if 'stored_j' not in obs[0]: continue
        # Independently quadrature net input at nodes. Includes quadrature error.
        net = []
        for t,y,o in zip(times,trajectories[method],obs):
            if config.model in ('vibration','forced'):
                net.append(model.force*math.cos(2*math.pi*model.frequency*t)*y[1]-o['damping_w'])
            else: net.append(o['input_w']-o.get('joule_w',0)-o.get('drag_w',0))
        received = quadrature(times,net)
        balances[method] = received-(obs[-1]['stored_j']-obs[0]['stored_j'])
    response = None
    if config.model in ('vibration','forced'):
        frequencies = [model.natural_frequency*i/200 for i in range(401)]
        amplitudes = [model.amplitude(f) for f in frequencies]
        response = {'frequency_hz':frequencies,'amplitude_m':[v if math.isfinite(v) else None for v in amplitudes],
                    'natural_hz':model.natural_frequency,'damping_ratio':model.damping_ratio,
                    'resonance_hz':model.resonance_frequency,'regime':model.regime}
    metadata = {'model_version':'5.0.0','origin':'SIMULATED','parameters':asdict(model),
                'parameter_units':{n:PARAMETERS[n][1] for n in asdict(model)},
                'initial':initial,'initial_units':STATE_UNITS[config.model],
                'observable_units':{n:OBSERVABLE_UNITS[n] for n in observations['rk4'][0]},
                'duration_s':duration,'dt_s':dt,'methods':list(METHODS),
                'primary':spec.primary,'primary_unit':spec.unit,'equations':spec.equations,
                'timings_s':timings,'timing_scope':'solver and observables; not a statistical benchmark'}
    if 'damping' in metadata['parameter_units']:
        metadata['parameter_units']['damping'] = 'kg/s' if config.model in ('vibration','forced') else 'N·m·s/rad'
    lines = [spec.title,'Origem: SIMULATED; parâmetros ilustrativos, não calibrados.',
             'Problema físico: '+spec.interpretation,'Leis e derivação: '+spec.equations,
             'Hipóteses: '+spec.assumptions, 'Métodos: Euler, Heun e RK4; último intervalo encurtado.',
             f'Condições iniciais: {initial}; duração={duration:g} s; Δt={dt:g} s.',
             *[f'{n}={v:g} {metadata["parameter_units"][n]}' for n,v in asdict(model).items()]]
    for method,obs in observations.items():
        lines.append(f'{method}: {spec.primary} final={obs[-1][spec.primary]:.9g} {spec.unit}.')
        if method in errors:
            e = errors[method]
            lines.append(f'Analítica independente: MAE={e["mae"]:.8g}; RMSE={e["rmse"]:.8g}; máximo={e["maximum"]:.8g} {spec.unit}.')
        if method in balances: lines.append(f'Resíduo energético final (quadratura por trapézios): {balances[method]:.8g} J; inclui erro de quadratura.')
    if not errors: lines.append('Sem solução analítica independente nesta execução; curva e balanço não bastam para validar o modelo.')
    if response: lines.append(f'Regime: {model.regime}; f natural={model.natural_frequency:.8g} Hz; ζ={model.damping_ratio:.8g}; pico={model.resonance_frequency} Hz.')
    if config.model=='feedback': lines.append('Linearização em potência média, sem perturbação: '+str(model.equilibrium_analysis()))
    lines += ['Interpretação: '+spec.interpretation,'Limitações: '+spec.limitations,
              'Passos excessivos podem ser instáveis; reduzir Δt e comparar resultados. Validação numérica não é validação experimental.']
    budget.check()
    return HardwareExperiment(config,metadata,times,trajectories,observations,reference,errors,balances,response,'\n'.join(lines))


def import_observations(path, unit, token=None):
    """Strict common CSV schema: time_s,value,unit. Never resamples silently."""
    if Path(path).stat().st_size>8*1024*1024: raise ValueError('CSV excede 8 MiB.')
    times,values = [],[]
    with open(path,encoding='utf-8-sig',newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames!=['time_s','value','unit']: raise ValueError('Cabeçalho obrigatório: time_s,value,unit')
        for row in reader:
            if token: token.check()
            if len(times)>=50001: raise ValueError('Máximo 50001 observações.')
            if row.get('unit')!=unit: raise ValueError(f'Unidade obrigatória: {unit}')
            times.append(row['time_s']); values.append(row['value'])
    return samples(times,values)


def validate_observations(experiment, times, values, token=None):
    """Evaluate the same ODE at measured times; no interpolation of observations.

    Model initial state applies at t=0. Each observation interval is solved with
    the configured dt using RK4; this is a numerical prediction, not a fit.
    """
    t,y = samples(times,values)
    if len(t)>50001 or t[0]<0 or t[-1]>experiment.metadata['duration_s']:
        raise ValueError('Observações fora da janela simulada ou em número excessivo.')
    token = token or Cancellation()
    spec = SPECS[experiment.config.model]
    model = spec.factory(**experiment.metadata['parameters'])
    state = experiment.metadata['initial'][:]
    previous = 0.
    predictions = []
    used_steps = 0
    deadline = perf_counter()+20
    for time in t:
        token.check()
        if perf_counter()>deadline: raise ValueError('Validação excedeu 20 s.')
        if time>previous:
            used_steps += math.ceil((time-previous)/experiment.metadata['dt_s'])
            if used_steps>100000: raise ValueError('Validação excede 100000 passos.')
            result = solve_ivp(model.rhs,state,(previous,time),experiment.metadata['dt_s'],'rk4',token)
            state = result.values[-1]
        predictions.append(model.observables(state)[spec.primary])
        previous = time
    return {'origin':'IMPORTED_UNVERIFIED','unit':spec.unit,'times_s':t,'observed':y,
            'predicted':predictions,'errors':metrics(predictions,y),
            'limitation':'Comparação com dados de origem não verificada; sem ajuste automático e sem certificação de sensores.'}


def export_hardware(experiment, directory, token=None, validation=None):
    """CSV + full JSON provenance + self-contained scientific HTML report."""
    token = token or Cancellation()
    directory = Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    stem = experiment.config.model
    metadata = dict(experiment.metadata)
    metadata['validation'] = validation
    data = asdict(experiment)|{'validation':validation}
    with open(directory/(stem+'.json'),'w',encoding='utf-8') as stream:
        json.dump(data,stream,ensure_ascii=False,allow_nan=False)
    columns = list(experiment.observables['rk4'][0])
    with open(directory/(stem+'.csv'),'w',encoding='utf-8',newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['time_s','method','origin',*columns])
        for method,observations in experiment.observables.items():
            for t,obs in zip(experiment.times,observations):
                token.check()
                writer.writerow([t,method,'SIMULATED',*[obs[n] for n in columns]])
    from ..reporting.document import Curve,Figure
    from ..reporting.render import CSS,figure_html
    colors = ('#2176c1','#9756b6','#1c946b')
    primary = experiment.metadata['primary']
    curves = [Curve(m,experiment.times,[o[primary] for o in obs],color)
              for (m,obs),color in zip(experiment.observables.items(),colors)]
    if experiment.reference is not None: curves.append(Curve('Analítica independente',experiment.times,experiment.reference,'#d48b18'))
    figures = [Figure('Resposta física','Tempo (s)',experiment.metadata['primary_unit'],curves)]
    if 'stored_j' in experiment.observables['rk4'][0]:
        figures.append(Figure('Energia armazenada','Tempo (s)','J',[
            Curve(m,experiment.times,[o['stored_j'] for o in obs],color)
            for (m,obs),color in zip(experiment.observables.items(),colors)]))
    if experiment.frequency_response:
        response = experiment.frequency_response
        figures.append(Figure('Resposta em frequência · amplitude estacionária','Frequência (Hz)','m',[
            Curve('Modelo linear',response['frequency_hz'],response['amplitude_m'])]))
    if validation:
        figures.append(Figure('Observações e previsão nos mesmos tempos','Tempo (s)',validation['unit'],[
            Curve('Origem não verificada',validation['times_s'],validation['observed']),
            Curve('Previsão RK4',validation['times_s'],validation['predicted'],'#1c946b')]))
    body = '<!doctype html><html lang="pt"><meta charset="utf-8"><title>InProcess · experiência física</title><style>'+CSS+'</style><body><main><h1>'+escape(SPECS[stem].title)+'</h1><pre>'+escape(experiment.report)+'</pre>'+''.join(figure_html(f) for f in figures)
    if validation: body += '<h2>Comparação experimental · origem não verificada</h2><pre>'+escape(json.dumps(validation['errors'],ensure_ascii=False,indent=2))+'</pre>'
    body += '<h2>Metadados de reprodução</h2><pre>'+escape(json.dumps(metadata,ensure_ascii=False,indent=2))+'</pre></main></body></html>'
    (directory/(stem+'.html')).write_text(body,encoding='utf-8')
    token.check()
    return directory/(stem+'.html')
