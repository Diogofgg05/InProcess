"""Optional two-node CPU/GPU thermal model, independent of actual sensors."""
from dataclasses import dataclass
import math

from .numerical._validation import finite_result, finite_values
from .numerical.ode import CancellationToken, solve_ivp
from .numerical.validation import linear_stability


@dataclass(frozen=True)
class CoupledThermalConfig:
    ambient: float = 22
    cpu_capacity: float = 100
    gpu_capacity: float = 150
    cpu_dissipation: float = 2
    gpu_dissipation: float = 3
    coupling: float = .5

    def __post_init__(self) -> None:
        finite_values([self.ambient, self.cpu_capacity, self.gpu_capacity,
                       self.cpu_dissipation, self.gpu_dissipation, self.coupling], "parâmetros térmicos")
        if self.cpu_capacity <= 0 or self.gpu_capacity <= 0:
            raise ValueError("As capacidades térmicas devem ser positivas.")
        if min(self.cpu_dissipation, self.gpu_dissipation, self.coupling) < 0:
            raise ValueError("Os coeficientes de transferência térmica não podem ser negativos.")

    def rates(self, cpu_temperature: float, gpu_temperature: float, cpu_power: float, gpu_power: float) -> tuple[float, float]:
        """Coupling removes q from CPU and adds the same q to GPU, in watts."""
        transfer = self.coupling * (cpu_temperature - gpu_temperature)
        cpu_loss = self.cpu_dissipation * (cpu_temperature - self.ambient)
        gpu_loss = self.gpu_dissipation * (gpu_temperature - self.ambient)
        return ((cpu_power - cpu_loss - transfer) / self.cpu_capacity,
                (gpu_power - gpu_loss + transfer) / self.gpu_capacity)


@dataclass(frozen=True)
class CoupledThermalResult:
    times: list[float]
    cpu_temperatures: list[float]
    gpu_temperatures: list[float]
    cpu_powers: list[float]
    gpu_powers: list[float]
    independent_cpu: list[float]
    independent_gpu: list[float]
    stored_energy: list[float]
    input_energy: list[float]
    dissipated_energy: list[float]
    balance_residual: list[float]
    method: str
    report: str


def _independent(initial: float, ambient: float, power: float, capacity: float, dissipation: float, time: float) -> float:
    if dissipation == 0:
        return finite_result(initial + power * (time / capacity))
    exponent = -(dissipation / capacity) * time
    return finite_result(ambient + (initial - ambient) * math.exp(exponent) + (power / dissipation) * (-math.expm1(exponent)))


def simulate_coupled(
    config: CoupledThermalConfig,
    initial_cpu: float = 40,
    initial_gpu: float = 35,
    cpu_power: float = 45,
    gpu_power: float = 60,
    duration: float = 120,
    dt: float = .1,
    method: str = "rk4",
    token: CancellationToken | None = None,
) -> CoupledThermalResult:
    """Solve temperatures and energy balances with the same explicit method.

    The independent curves are analytical references for coupling=0. With a
    nonzero coupling they illustrate another physical model, not error bounds.
    Integrated balances are consistency diagnostics, not independent validation.
    """
    initial_cpu, initial_gpu, cpu_power, gpu_power, duration, dt = finite_values(
        [initial_cpu, initial_gpu, cpu_power, gpu_power, duration, dt], "condições da simulação",
    )
    if min(cpu_power, gpu_power) < 0:
        raise ValueError("As potências térmicas de aquecimento devem ser não negativas.")
    a = (config.cpu_dissipation + config.coupling) / config.cpu_capacity
    d = (config.gpu_dissipation + config.coupling) / config.gpu_capacity
    off_diagonal = config.coupling / math.sqrt(config.cpu_capacity) / math.sqrt(config.gpu_capacity)
    fastest_decay = (a + d + math.hypot(a - d, 2 * off_diagonal)) / 2
    stability = linear_stability(fastest_decay, dt, method)

    def function(_time: float, state: list[float]) -> list[float]:
        cpu, gpu = state[:2]
        rate_cpu, rate_gpu = config.rates(cpu, gpu, cpu_power, gpu_power)
        loss = config.cpu_dissipation * (cpu - config.ambient) + config.gpu_dissipation * (gpu - config.ambient)
        return [rate_cpu, rate_gpu, cpu_power + gpu_power, loss]

    trajectory = solve_ivp(function, [initial_cpu, initial_gpu, 0, 0], (0, duration), dt, method, token)
    times = trajectory.times
    cpu = [state[0] for state in trajectory.values]
    gpu = [state[1] for state in trajectory.values]
    inputs = [state[2] for state in trajectory.values]
    losses = [state[3] for state in trajectory.values]
    stored = [finite_result(config.cpu_capacity * (tc - initial_cpu) + config.gpu_capacity * (tg - initial_gpu)) for tc, tg in zip(cpu, gpu)]
    residual = [finite_result(received - lost - accumulated) for received, lost, accumulated in zip(inputs, losses, stored)]
    independent_cpu = [_independent(initial_cpu, config.ambient, cpu_power, config.cpu_capacity, config.cpu_dissipation, t) for t in times]
    independent_gpu = [_independent(initial_gpu, config.ambient, gpu_power, config.gpu_capacity, config.gpu_dissipation, t) for t in times]
    status = "estável" if stability.stable else "na fronteira ou fora da região de estabilidade"
    report = "\n".join([
        "Modelo térmico acoplado CPU/GPU — dados inteiramente SIMULATED.",
        "Cc Tc′ = Pc − kc(Tc−Ta) − kcg(Tc−Tg).",
        "Cg Tg′ = Pg − kg(Tg−Ta) + kcg(Tc−Tg).",
        f"Ta={config.ambient:g} °C; Cc={config.cpu_capacity:g} J/K; Cg={config.gpu_capacity:g} J/K; kc={config.cpu_dissipation:g} W/K; kg={config.gpu_dissipation:g} W/K; kcg={config.coupling:g} W/K.",
        f"Tc0={initial_cpu:g} °C; Tg0={initial_gpu:g} °C; Pc={cpu_power:g} W; Pg={gpu_power:g} W.",
        f"Método {method.upper()}; duração={duration:g} s; passo nominal={dt:g} s; {trajectory.steps} intervalos, último encurtado quando necessário.",
        f"Modo de decaimento mais rápido={fastest_decay:.6g} s⁻¹; fator de amplificação={stability.amplification:.6g}: {status}.",
        "O termo −kcg(Tc−Tg) na CPU cancela exatamente +kcg(Tc−Tg) na GPU ao somar os balanços: o acoplamento só transfere energia internamente.",
        f"Energia recebida={inputs[-1]:.8g} J; transferência líquida ao ambiente={losses[-1]:.8g} J; variação armazenada={stored[-1]:.8g} J.",
        f"Resíduo máximo |Eentrada − Eambiente − ΔU|={max(abs(value) for value in residual):.6g} J.",
        "As energias são integradas no mesmo sistema EDO, com os mesmos estágios; o balanço mede consistência algébrica, sem constituir referência independente de precisão.",
        "A transferência ao ambiente pode ser negativa quando os componentes estão abaixo de Ta. A energia armazenada é a variação relativa ao estado inicial.",
        "As curvas independentes usam solução analítica com kcg=0; para kcg diferente de zero representam uma comparação de modelos, não o erro numérico.",
        "Hipóteses: dois nós uniformes, potências e coeficientes constantes, ambiente fixo, sem controlo de ventoinhas ou sensores reais. Não se inferem parâmetros do hardware.",
    ])
    if token is not None:
        token.check()
    return CoupledThermalResult(times, cpu, gpu, [cpu_power] * len(times), [gpu_power] * len(times),
                                independent_cpu, independent_gpu, stored, inputs, losses, residual, method, report)
