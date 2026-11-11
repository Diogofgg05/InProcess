"""Hypothetical ventilation-dependent cooling, without fan or RPM control."""
from collections.abc import Callable
from dataclasses import dataclass
import math
from numbers import Real

from .numerical._validation import finite_result, finite_values
from .numerical.ode import CancellationToken, solve_ivp


@dataclass(frozen=True)
class CoolingResult:
    times: list[float]
    temperatures: dict[str, list[float]]
    loss_energy: dict[str, list[float]]
    coefficient_values: list[float]
    reference: list[float] | None
    report: str


def simulate_cooling(
    initial: float = 60,
    ambient: float = 22,
    capacity: float = 100,
    base_dissipation: float = 2,
    ventilation_gain: float = 2,
    ventilation: float | Callable[[float], float] = 0.0,
    duration: float = 120,
    dt: float = .1,
    token: CancellationToken | None = None,
) -> CoolingResult:
    """Compare methods for C*T'=-k(t)*(T-Ta), k(t)=k0+beta*u(t).

    u is dimensionless in [0,1], not RPM. k0 and beta have units W/K. This
    linear relationship is an explicit illustrative hypothesis, not a sensor
    calibration. A callable must be a deterministic Python function of time;
    it is evaluated at each method's stages, without hidden interpolation.
    """
    initial, ambient, capacity, base_dissipation, ventilation_gain, duration, dt = finite_values(
        [initial, ambient, capacity, base_dissipation, ventilation_gain, duration, dt], "parâmetros de arrefecimento",
    )
    if capacity <= 0 or base_dissipation < 0 or ventilation_gain < 0:
        raise ValueError("C deve ser positivo; k0 e beta devem ser não negativos.")
    if duration <= 0 or dt <= 0:
        raise ValueError("A duração e o passo devem ser positivos.")
    if token is not None:
        token.check()
    constant_control = None
    if isinstance(ventilation, Real):
        constant_control = finite_values([ventilation], "níveis de ventilação")[0]
        if not 0 <= constant_control <= 1:
            raise ValueError("O nível hipotético de ventilação deve pertencer a [0, 1].")
    elif not callable(ventilation):
        raise ValueError("A ventilação deve ser um número em [0, 1] ou uma função Python de t.")

    def coefficient(time: float) -> float:
        value = constant_control if constant_control is not None else ventilation(time)
        if not isinstance(value, Real):
            raise ValueError("A função de ventilação deve devolver um número real em [0, 1].")
        value = float(value)
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("O nível hipotético de ventilação deve ser finito e pertencer a [0, 1].")
        return finite_result(base_dissipation + ventilation_gain * value)

    # Fail promptly for an invalid control at t=0, before allocating trajectories.
    initial_coefficient = coefficient(0.0)

    def function(time: float, state: list[float]) -> list[float]:
        loss = coefficient(time) * (state[0] - ambient)
        return [-loss / capacity, loss]

    temperatures, loss_energy = {}, {}
    times: list[float] = []
    for label, method in (("Euler", "euler"), ("Heun", "heun"), ("RK4", "rk4")):
        solution = solve_ivp(function, [initial, 0.0], (0, duration), dt, method, token)
        times = solution.times
        temperatures[label] = [state[0] for state in solution.values]
        loss_energy[label] = [state[1] for state in solution.values]
    coefficients = []
    for index, time in enumerate(times):
        if token is not None and index % 256 == 0:
            token.check()
        coefficients.append(coefficient(time))
    reference = None
    if constant_control is not None:
        reference = [finite_result(ambient + (initial - ambient) * math.exp(-(initial_coefficient / capacity) * time)) for time in times]
    lines = [
        "Arrefecimento com ventilação hipotética — dados inteiramente SIMULATED.",
        "Modelo: C dT/dt = −k(t)(T−Ta), com k(t)=k0+beta*u(t), 0≤u≤1.",
        f"T0={initial:g} °C; Ta={ambient:g} °C; C={capacity:g} J/K; k0={base_dissipation:g} W/K; beta={ventilation_gain:g} W/K.",
        f"Duração={duration:g} s; passo nominal={dt:g} s; {len(times)-1} intervalos, último encurtado quando necessário.",
        "A relação linear entre u e dissipação é uma hipótese ilustrativa explícita, sem calibração experimental; u não representa RPM nem percentagem real de uma ventoinha.",
        "Não há leitura, alteração ou controlo de ventoinhas. Os parâmetros não são inferidos do hardware.",
        "A função u(t), quando fornecida, deve ser determinística. Cada método avalia o mesmo modelo nos seus estágios; não se introduz interpolação escondida.",
        "T e energia cedida são resolvidas simultaneamente: T′=−Qloss/C e Eloss′=Qloss, Qloss=k(t)(T−Ta).",
        "C(T−T0)+Eloss deve conservar zero até arredondamento, como consistência algébrica dos mesmos estágios; este balanço não é uma referência independente de precisão.",
        "Eloss é uma transferência líquida para o ambiente e pode ser negativa se T0<Ta; nesse caso o ambiente aquece o nó.",
    ]
    if reference is None:
        lines.append("Ventilação variável: não se fornece uma referência analítica independente nem se inventa uma solução exata.")
    else:
        lines.append(f"Ventilação constante u={constant_control:g}: referência analítica T=Ta+(T0−Ta)exp(−kt/C), k={initial_coefficient:g} W/K.")
    for label in temperatures:
        residual = max(abs(capacity * (temperature - initial) + energy)
                       for temperature, energy in zip(temperatures[label], loss_energy[label]))
        lines.append(f"{label}: Tfinal={temperatures[label][-1]:.8g} °C; Eloss={loss_energy[label][-1]:.8g} J; resíduo máximo do balanço={residual:.6g} J.")
    lines.append("Um passo demasiado grande pode ser instável; conservação algébrica não garante temperaturas corretas. Descontinuidades de u(t) exigem alinhar os intervalos ou reduzir o passo para controlar o erro.")
    if token is not None:
        token.check()
    return CoolingResult(times, temperatures, loss_energy, coefficients, reference, "\n".join(lines))
