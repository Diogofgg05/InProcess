"""Reproducible, GUI-independent experiment configuration and analysis."""
from dataclasses import dataclass, asdict, field
from bisect import bisect_right
from pathlib import Path
import json
import math
import os
import tempfile
import time
from ..core.cancellation import Cancellation
from ..physics.thermal_model import ThermalModel, finite
from ..physics.euler import simulate, Simulation
from ..physics.integration import validate, integrate, cumulative
from ..physics.differentiation import derivative, smooth
from ..physics.validation import errors
from ..physics.numerical.validation import linear_stability
from .scenarios import power_profile, SCENARIOS
from .noise import add_noise


@dataclass(frozen=True)
class ExperimentConfig:
    initial: float = 40
    ambient: float = 22
    power: float = 45
    capacity: float = 100
    dissipation: float = 2
    duration: float = 120
    dt: float = .1
    noise: float = .2
    seed: int = 42
    scenario: str = "Constante"
    source_times: tuple[float,...] = field(default_factory=tuple)
    source_powers: tuple[float,...] = field(default_factory=tuple)
    provenance: str = "simulado"

    def __post_init__(self):
        object.__setattr__(self,'source_times',tuple(self.source_times))
        object.__setattr__(self,'source_powers',tuple(self.source_powers))
        finite(self.initial,self.ambient,self.power,self.duration,self.dt,self.noise)
        if self.initial < -273.15:
            raise ValueError('Temperatura inicial abaixo do zero absoluto.')
        ThermalModel(self.ambient,self.capacity,self.dissipation)
        if self.duration <= 0 or self.dt <= 0 or self.noise < 0 or self.power < 0:
            raise ValueError("Configuração física inválida.")
        if not isinstance(self.seed,int) or self.scenario not in SCENARIOS:
            raise ValueError("Semente/cenário inválidos.")
        if self.provenance not in ('simulado','importado; origem não verificada'):
            raise ValueError("Proveniência não suportada.")
        if self.source_times or self.source_powers:
            validate(self.source_times,self.source_powers)
            if len(self.source_times) > 200_001 or min(self.source_powers) < 0:
                raise ValueError("Série de potência inválida.")
            if self.duration > self.source_times[-1]-self.source_times[0]+1e-9:
                raise ValueError("A potência importada não cobre a duração.")
            if self.provenance != 'importado; origem não verificada':
                raise ValueError("Série externa requer origem não verificada.")


@dataclass
class Experiment:
    config: ExperimentConfig
    simulation: Simulation
    noisy: list[float]
    derivatives: list[list[float]]
    energy: list[float]
    error: dict
    convergence: list[tuple[float,float | None]]
    report: str
    method_solutions: dict[str,list[float]] = field(default_factory=dict)
    method_errors: dict[str,dict] = field(default_factory=dict)
    method_timings: dict[str,float] = field(default_factory=dict)
    method_convergence: dict[str,list[dict]] = field(default_factory=dict)
    energy_zoh: list[float] = field(default_factory=list)
    energy_balance: dict[str,list[float]] = field(default_factory=dict)


_METHODS = {'Euler':'euler','Heun':'heun','RK4':'rk4'}
_STUDY_STEPS = (1.,.5,.1,.05,.01)
_MAX_TRIAL_STEPS = 20_000
_MAX_STUDY_STEPS = 60_000


def _thermal_steps(model,initial,times,powers,method,token):
    """Temperature loop only: every RK stage uses the same interval power P_n.

    Sampling/CSV lookup, analytical reference, error calculation and rendering
    are deliberately outside this function and outside its measured duration.
    """
    if method not in _METHODS:
        raise ValueError('Método térmico desconhecido.')
    values = [initial]
    rate = model.rate
    for i in range(len(times)-1):
        if i % 256 == 0: token.check()
        h = times[i+1]-times[i]
        temperature,power = values[-1],powers[i]
        k1 = rate(temperature,power)
        if method == 'Euler':
            # Direct explicit Euler discretization of C T' = P-k(T-Ta).
            temperature += h*k1
        elif method == 'Heun':
            k2 = rate(temperature+h*k1,power)
            temperature += h*(k1/2+k2/2)
        else:
            k2 = rate(temperature+h*k1/2,power)
            k3 = rate(temperature+h*k2/2,power)
            k4 = rate(temperature+h*k3,power)
            temperature += h*(k1/6+k2/3+k3/3+k4/6)
        if not math.isfinite(temperature):
            raise ValueError('A temperatura excedeu o domínio numérico; reveja escalas e passo.')
        values.append(temperature)
    token.check()
    return values


def _constant_convergence(config,model,token):
    """Bounded study, independent constant-power reference and timed loops."""
    result = {method:[] for method in _METHODS}
    used_steps = 0
    for step in _STUDY_STEPS:
        token.check()
        count = math.ceil(config.duration/step)
        reason = None
        if count > _MAX_TRIAL_STEPS:
            reason = f'Excede {_MAX_TRIAL_STEPS} passos por execução.'
        elif used_steps+count*len(_METHODS) > _MAX_STUDY_STEPS:
            reason = f'Excede o orçamento total de {_MAX_STUDY_STEPS} passos do estudo.'
        if reason is None:
            times = [min(i*step,config.duration) for i in range(count+1)]
            powers = [config.power]*len(times)
            reference = [model.exact(config.initial,config.power,t) for t in times]
        for method,name in _METHODS.items():
            row = dict(dt=step,rmse=None,maximum=None,seconds=None,order=None,steps=count,omitted_reason=reason)
            if reason is None:
                if not linear_stability(model.dissipation/model.capacity,step,name).stable:
                    row['omitted_reason'] = 'Passo na fronteira ou fora da região de estabilidade do método.'
                else:
                    begin = time.perf_counter()
                    values = _thermal_steps(model,config.initial,times,powers,method,token)
                    row['seconds'] = time.perf_counter()-begin
                    used_steps += count
                    error = errors(values,reference)
                    row.update(rmse=error['rmse'],maximum=error['maximum'])
            result[method].append(row)
    for rows in result.values():
        previous = None
        for row in rows:
            if row['rmse'] is not None and row['rmse'] > 1e-12:
                if previous is not None:
                    row['order'] = (math.log(previous['rmse'])-math.log(row['rmse']))/(math.log(previous['dt'])-math.log(row['dt']))
                previous = row
    return result


def run_experiment(config: ExperimentConfig, token: Cancellation | None = None) -> Experiment:
    token = token or Cancellation()
    token.check()
    c = config
    model = ThermalModel(c.ambient,c.capacity,c.dissipation)
    profile = power_profile(c.scenario,c.power,c.duration)
    if c.source_times:
        def profile(t):
            i = bisect_right(c.source_times,t+c.source_times[0])-1
            return c.source_powers[max(0,i)]
    r = simulate(model,c.initial,profile,c.duration,c.dt,cancellation=token)
    solutions,timings,method_errors = {},{},{}
    for method in _METHODS:
        begin = time.perf_counter()
        solutions[method] = _thermal_steps(model,c.initial,r.times,r.powers,method,token)
        timings[method] = time.perf_counter()-begin
        method_errors[method] = errors(solutions[method],r.reference)
    # Output temperature is always a simulation even when forcing was imported.
    noisy = add_noise(r.temperatures,c.noise,c.seed)
    derivatives = [derivative(r.times,v) for v in (r.temperatures,noisy,smooth(noisy))]
    err = errors(r.temperatures,r.reference)
    method_convergence = _constant_convergence(c,model,token)
    convergence = [(row['dt'],row['rmse']) for row in reversed(method_convergence['Euler'])]
    energy_zoh = [0.0]
    for i in range(len(r.times)-1):
        energy_zoh.append(energy_zoh[-1]+r.powers[i]*(r.times[i+1]-r.times[i]))
    balances = {}
    for method,temperatures in solutions.items():
        token.check()
        losses = cumulative(r.times,[c.dissipation*(temperature-c.ambient) for temperature in temperatures])
        balances[method] = [received-c.capacity*(temperature-c.initial)-lost
                            for received,temperature,lost in zip(energy_zoh,temperatures,losses)]
    lines = ["VALIDAÇÃO NUMÉRICA — temperaturas e observações sintéticas.",
             f"Potência: {c.provenance}; temperatura: simulada.",
             "Forçamento importado: retenção à esquerda (ZOH); tempos relativos ao início.",
             "Referência analítica por intervalo para o mesmo forçamento retido; não é a solução exata de saltos não alinhados.",
             "Euler explícito, Heun e RK4 usam a mesma potência Pn em todos os estágios de cada intervalo.",
             "Erro relativo em Celsius depende da origem da escala; indefinido para referência zero.",
             "Comparação de métodos com referência analítica por intervalo:"]
    for method in _METHODS:
        error = method_errors[method]
        lines.append(f"{method}: RMSE {error['rmse']:.8g} °C; máximo {error['maximum']:.8g} °C.")
    lines += ["", "Convergência em potência constante (Δt s → RMSE °C):",
              f"Limites: {_MAX_TRIAL_STEPS} passos por execução e {_MAX_STUDY_STEPS} passos no estudo; intervalos finais encurtados.",
              "Tempos reais estão nos metadados de comparação: medem apenas o ciclo de temperaturas, sem referência, amostragem, erros ou apresentação. Não são benchmarks estatísticos."]
    for method,rows in method_convergence.items():
        for row in rows:
            line = f"{method}, Δt={row['dt']:g} s: "
            if row['omitted_reason'] is not None:
                line += f"omitido — {row['omitted_reason']}"
            else:
                line += f"RMSE={row['rmse']:.8g} °C; máximo={row['maximum']:.8g} °C"
                if row['order'] is not None: line += f"; ordem observada={row['order']:.4f}"
                elif row['rmse'] <= 1e-12: line += "; ordem não estimada junto do limite de arredondamento"
            lines.append(line)
    lines += ["", "Energia da potência amostrada:"]
    for method in ['rectangle','trapezoid','simpson']:
        token.check()
        try:
            value = integrate(r.times,r.powers,method)
            lines.append(f"{method}: {value:.8g} J = {value/3600:.8g} Wh")
        except ValueError as error:
            lines.append(f"{method}: {error}")
    lines += [f"RMSE derivada ruidosa/limpa: {errors(derivatives[1],derivatives[0])['rmse']:.6g} °C/s",
              f"RMSE derivada filtrada/limpa: {errors(derivatives[2],derivatives[0])['rmse']:.6g} °C/s",
              "Ruído independente: Var(Dcentral) = σ²/(2Δt²). Média móvel de 7 pontos introduz viés nas transições.",
              "Euler estável: 0 < Δt·k/C < 2. Resposta monótona: Δt·k/C ≤ 1.",
              "Em saltos, trapézios/Simpson interpolam; retângulos seguem a retenção usada na simulação.",
              f"Energia de entrada ZOH: {energy_zoh[-1]:.8g} J = {energy_zoh[-1]/3600:.8g} Wh.",
              "Balanço: Ein,ZOH − C(T−T0) − integral k(T−Ta)dt; as perdas são integradas por trapézios e incluem erro de quadratura.",
              "C e k ilustrativos, não calibrados. Modelo ignora DVFS, ventoinhas e gradientes espaciais."]
    for method,balance in balances.items():
        lines.append(f"{method}: resíduo máximo do balanço com perdas por trapézios = {max(abs(value) for value in balance):.8g} J.")
    token.check()
    return Experiment(c,r,noisy,derivatives,cumulative(r.times,r.powers),err,convergence,'\n'.join(lines),
                      solutions,method_errors,timings,method_convergence,energy_zoh,balances)


def save_experiment(path: str, experiment: Experiment, token: Cancellation) -> None:
    token.check()
    payload = {'schema':1,'units':{'time':'s','temperature':'°C','power':'W','energy':'J'},
               'methods':{'thermal':'Euler explícito','reference':'analítica por intervalo ZOH',
                          'energy':'trapézios','filter':'média móvel raio 3',
                          'thermal_comparison':list(_METHODS)},
               'config':asdict(experiment.config),'results':asdict(experiment.simulation)}
    if experiment.method_solutions:
        payload['comparison'] = {
            'method_solutions':experiment.method_solutions,
            'method_errors':{name:{key:value for key,value in error.items() if not isinstance(value,list)}
                             for name,error in experiment.method_errors.items()},
            'method_timings_s':experiment.method_timings,
            'method_convergence':experiment.method_convergence,
            'energy_zoh_j':experiment.energy_zoh,
            'timing_scope':'temperature integration loops only; no reference, sampling, errors or UI',
        }
    target = Path(path)
    temp = None
    try:
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=target.parent,delete=False) as stream:
            temp = stream.name
            json.dump(payload,stream,ensure_ascii=False,allow_nan=False)
        token.check()
        os.replace(temp,target)
    finally:
        if temp and os.path.exists(temp):
            os.unlink(temp)


def load_experiment(path: str, token: Cancellation) -> Experiment:
    token.check()
    if Path(path).stat().st_size > 40*1024*1024:
        raise ValueError("Experiência demasiado grande (máximo 40 MiB).")
    with open(path,encoding='utf-8') as stream:
        payload = json.load(stream)
    if payload.get('schema') != 1 or payload.get('units') != {'time':'s','temperature':'°C','power':'W','energy':'J'}:
        raise ValueError("Versão/unidades da experiência incompatíveis.")
    try:
        config = ExperimentConfig(**payload['config'])
    except (KeyError,TypeError) as error:
        raise ValueError("Configuração da experiência inválida.") from error
    # Recompute; never trust saved result arrays as physical observations.
    return run_experiment(config,token)
