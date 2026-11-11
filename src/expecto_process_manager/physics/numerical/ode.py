"""Fixed-step initial-value solvers for scalar or vector differential equations."""
from collections.abc import Callable, Sequence
from dataclasses import dataclass
import math
from numbers import Real
from typing import Protocol

from ._validation import finite_values

MAX_STEPS = 200_000
MAX_STATE_VALUES = 2_000_000
METHODS = ("euler", "heun", "rk4")
State = list[float]
ODEFunction = Callable[[float, State], float | Sequence[float]]


class CancellationToken(Protocol):
    def check(self) -> None: ...


@dataclass(frozen=True)
class ODEResult:
    times: list[float]
    values: list[State]
    method: str

    @property
    def steps(self) -> int:
        return len(self.times) - 1


def _state(value: float | Sequence[float]) -> State:
    result = finite_values([value] if isinstance(value, Real) else value, "estados")
    if not result:
        raise ValueError("O estado deve ter pelo menos uma componente.")
    return result


def solve_ivp(
    function: ODEFunction,
    initial: float | Sequence[float],
    t_span: tuple[float, float],
    dt: float,
    method: str = "euler",
    token: CancellationToken | None = None,
) -> ODEResult:
    """Solve y'=f(t,y); f always receives a vector, including scalar problems.

    The final step is shortened to hit t_span[1]. All stored states are vectors.
    Cancellation is checked before every right-hand-side evaluation. No strings
    are evaluated, no interpolation/adaptive step size is silently introduced.
    """
    if method not in METHODS:
        raise ValueError("Método EDO inválido: escolha euler, heun ou rk4.")
    endpoints = finite_values(t_span, "limites temporais")
    if len(endpoints) != 2:
        raise ValueError("t_span deve conter exatamente dois limites.")
    start, finish = endpoints
    step = finite_values([dt], "passos temporais")[0]
    duration = finish - start
    if not math.isfinite(duration) or duration <= 0 or step <= 0:
        raise ValueError("A duração e o passo temporal devem ser positivos e finitos.")
    ratio = duration / step
    if not math.isfinite(ratio) or ratio > MAX_STEPS:
        raise ValueError(f"A simulação excede o limite de {MAX_STEPS} passos.")
    count = max(1, math.ceil(ratio))
    state = _state(initial)
    dimension = len(state)
    if (count+1)*dimension > MAX_STATE_VALUES:
        raise ValueError(f'A simulação excede o limite de {MAX_STATE_VALUES} valores de estado.')
    if not callable(function):
        raise ValueError("A função da EDO deve ser uma função Python.")

    def evaluate(time: float, value: State) -> State:
        if token is not None:
            token.check()
        # Copies prevent a user callback from mutating the stored trajectory.
        derivative = _state(function(time, list(value)))
        if len(derivative) != dimension:
            raise ValueError("A derivada deve ter a mesma dimensão do estado inicial.")
        return derivative

    def shifted(value: State, slope: State, scale: float) -> State:
        return finite_values([v + scale * s for v, s in zip(value, slope)], "estados calculados")

    times = [start]
    values = [list(state)]
    for index in range(1, count + 1):
        time = times[-1]
        next_time = finish if index == count else start + index * step
        h = next_time - time
        if not math.isfinite(h) or h <= 0:
            raise ValueError("O passo é demasiado pequeno para a escala dos tempos fornecidos.")
        k1 = evaluate(time, state)
        if method == "euler":
            state = shifted(state, k1, h)
        elif method == "heun":
            k2 = evaluate(next_time, shifted(state, k1, h))
            state = shifted(state, [a / 2 + b / 2 for a, b in zip(k1, k2)], h)
        else:
            k2 = evaluate(time + h / 2, shifted(state, k1, h / 2))
            k3 = evaluate(time + h / 2, shifted(state, k2, h / 2))
            k4 = evaluate(next_time, shifted(state, k3, h))
            slope = [a / 6 + b / 3 + c / 3 + d / 6 for a, b, c, d in zip(k1, k2, k3, k4)]
            state = shifted(state, slope, h)
        times.append(next_time)
        values.append(state)
    if token is not None:
        token.check()
    return ODEResult(times, values, method)
