"""Constant-power thermal comparison; parameters represent a lumped model."""
from dataclasses import dataclass
import math

from ..thermal_model import ThermalModel
from ._validation import finite_result, finite_values
from .ode import CancellationToken, METHODS, solve_ivp
from .validation import linear_stability, metrics


@dataclass(frozen=True)
class ThermalComparison:
    times: list[float]
    solutions: dict[str, list[float]]
    reference: list[float]
    report: str


def compare_thermal(
    initial: float,
    ambient: float,
    power: float,
    capacity: float,
    dissipation: float,
    duration: float,
    dt: float,
    token: CancellationToken | None = None,
) -> ThermalComparison:
    """Compare Euler, Heun and RK4 to the analytic solution at constant power."""
    initial, ambient, power, capacity, dissipation, duration, dt = finite_values(
        [initial, ambient, power, capacity, dissipation, duration, dt], "parâmetros térmicos",
    )
    model = ThermalModel(ambient=ambient, capacity=capacity, dissipation=dissipation)
    if initial < -273.15:
        raise ValueError('Temperatura inicial abaixo do zero absoluto.')
    if power < 0:
        raise ValueError("A potência térmica de aquecimento deve ser não negativa.")
    solutions: dict[str, list[float]] = {}
    times: list[float] = []
    stability = {method: linear_stability(dissipation / capacity, dt, method) for method in METHODS}
    for method in METHODS:
        result = solve_ivp(lambda _t, state: model.rate(state[0], power), initial, (0, duration), dt, method, token)
        times = result.times
        solutions[method] = [state[0] for state in result.values]
    reference = [finite_result(model.exact(initial, power, time)) for time in times]
    equilibrium = finite_result(ambient + power / dissipation)
    lines = [
        "Modelo térmico concentrado — dados inteiramente simulados.",
        "Equação: C dT/dt = P − k(T − Ta), com potência constante e ambiente constante.",
        f"T0 = {initial:g} °C; Ta = {ambient:g} °C; P = {power:g} W; C = {capacity:g} J/°C; k = {dissipation:g} W/°C.",
        f"Duração = {duration:g} s; passo nominal = {dt:g} s; {len(times) - 1} intervalos.",
        f"Equilíbrio = {equilibrium:g} °C; constante de tempo C/k = {capacity / dissipation:g} s.",
        "Referência independente: T(t) = Teq + (T0 − Teq) exp(−kt/C).",
    ]
    for method, values in solutions.items():
        error = metrics(values, reference)
        status = "estável" if stability[method].stable else "na fronteira ou fora da região de estabilidade"
        lines.append(f"{method.upper()}: RMSE = {error['rmse']:.6g} °C; MAE = {error['mae']:.6g} °C; erro máximo = {error['maximum']:.6g} °C; fator de amplificação = {stability[method].amplification:.6g} ({status}).")
    lines.extend([
        f"Energia térmica fornecida: P × duração = {power * duration:g} J ({power * duration / 3600:g} Wh).",
        "O último intervalo é encurtado quando necessário. Estabilidade refere-se a y′ = −(k/C)y, com passo nominal.",
        "Hipóteses: temperatura uniforme equivalente, C e k constantes, sem controlo de ventoinhas ou variação de potência.",
        "Os parâmetros não são uma calibração do processador; percentagem de CPU não equivale a potência elétrica medida.",
    ])
    if token is not None:
        token.check()
    return ThermalComparison(times, solutions, reference, "\n".join(lines))


def time_to_threshold(initial: float, ambient: float, power: float, capacity: float, dissipation: float, target: float) -> float | None:
    """First t>=0 reaching target; None means unreachable in finite model time."""
    initial, ambient, power, capacity, dissipation, target = finite_values(
        [initial, ambient, power, capacity, dissipation, target], "parâmetros térmicos",
    )
    model = ThermalModel(ambient, capacity, dissipation)
    if power < 0:
        raise ValueError("A potência térmica de aquecimento deve ser não negativa.")
    if initial == target:
        return 0.0
    equilibrium = finite_result(ambient + power / dissipation)
    if initial == equilibrium:
        return None
    ratio = (target - equilibrium) / (initial - equilibrium)
    if not 0 < ratio < 1:
        return None
    return finite_result(-model.capacity / model.dissipation * math.log(ratio))
