"""Error metrics, bounded convergence/sensitivity studies and scalar stability."""
from collections.abc import Callable, Sequence
from dataclasses import dataclass
import math
from numbers import Real
from typing import TypedDict

from ._validation import finite_result, finite_values
from .ode import CancellationToken, METHODS


class ErrorMetrics(TypedDict):
    absolute: list[float]
    relative: list[float | None]
    mae: float
    rmse: float
    maximum: float


def metrics(predicted: Sequence[float], reference: Sequence[float]) -> ErrorMetrics:
    """Relative error is undefined (None) when the reference value is zero."""
    observed = finite_values(reference, "valores de referência")
    calculated = finite_values(predicted, "previsões")
    if not observed or len(observed) != len(calculated):
        raise ValueError("Previsões e referência devem ter o mesmo tamanho não vazio.")
    absolute = [finite_result(abs(a - b)) for a, b in zip(calculated, observed)]
    relative = [finite_result(error / abs(value)) if value != 0 else None for error, value in zip(absolute, observed)]
    maximum = max(absolute)
    # Scale first: squaring a large finite error need not overflow the RMSE.
    scaled = [value / maximum for value in absolute] if maximum else absolute
    return {
        "absolute": absolute,
        "relative": relative,
        "mae": maximum * (math.fsum(scaled) / len(scaled)),
        "rmse": maximum * math.sqrt(math.fsum(value * value for value in scaled) / len(scaled)),
        "maximum": maximum,
    }


def _vector(value: float | Sequence[float]) -> list[float]:
    result = finite_values([value] if isinstance(value, Real) else value)
    if not result:
        raise ValueError("A resposta do modelo não pode estar vazia.")
    return result


@dataclass(frozen=True)
class ConvergenceRow:
    step: float
    rmse: float
    maximum: float
    observed_order: float | None


def convergence_study(
    solver: Callable[[float], float | Sequence[float]],
    reference: float | Sequence[float],
    steps: Sequence[float],
    token: CancellationToken | None = None,
) -> list[ConvergenceRow]:
    """Compare responses at common locations; never compare unaligned grids.

    solver(dt) must return the same physical quantity at the same times for
    every dt (e.g. the final state). Maximum 16 solves; each solver owns its
    internal step limit. Observed order uses consecutive nonzero RMSE values.
    """
    grid = finite_values(steps, "passos temporais")
    if not 2 <= len(grid) <= 16 or any(value <= 0 for value in grid):
        raise ValueError("Escolha entre 2 e 16 passos temporais positivos.")
    if any(b >= a for a, b in zip(grid, grid[1:])):
        raise ValueError("Os passos devem ser estritamente decrescentes.")
    target = _vector(reference)
    rows: list[ConvergenceRow] = []
    for step in grid:
        if token is not None:
            token.check()
        error = metrics(_vector(solver(step)), target)
        order = None
        if rows and rows[-1].rmse > 0 and error["rmse"] > 0:
            order = (math.log(rows[-1].rmse) - math.log(error["rmse"])) / (math.log(rows[-1].step) - math.log(step))
        rows.append(ConvergenceRow(step, error["rmse"], error["maximum"], order))
    if token is not None:
        token.check()
    return rows


@dataclass(frozen=True)
class SensitivityResult:
    parameter: float
    step: float
    baseline: list[float]
    lower: list[float]
    upper: list[float]
    derivative: list[float]
    relative: list[float | None]


def sensitivity_study(
    function: Callable[[float], float | Sequence[float]],
    parameter: float,
    step: float,
    token: CancellationToken | None = None,
) -> SensitivityResult:
    """Three model calls; step has the units of the perturbed parameter.

    Returns a central finite-difference sensitivity and p/f * df/dp. The latter
    is undefined at a zero response. The caller must keep p±step admissible.
    """
    parameter, step = finite_values([parameter, step], "parâmetros")
    if step <= 0 or not math.isfinite(parameter + step) or not math.isfinite(parameter - step):
        raise ValueError("A perturbação deve ser positiva e manter parâmetros finitos.")
    if parameter + step == parameter or parameter - step == parameter:
        raise ValueError("A perturbação é demasiado pequena para a precisão numérica.")
    responses = []
    for value in (parameter, parameter - step, parameter + step):
        if token is not None:
            token.check()
        responses.append(_vector(function(value)))
    baseline, lower, upper = responses
    if len(lower) != len(baseline) or len(upper) != len(baseline):
        raise ValueError("A dimensão da resposta deve permanecer constante.")
    derivative = [finite_result((b / 2 - a / 2) / step) for a, b in zip(lower, upper)]
    relative = [finite_result((parameter / value) * slope) if value != 0 else None for value, slope in zip(baseline, derivative)]
    if token is not None:
        token.check()
    return SensitivityResult(parameter, step, baseline, lower, upper, derivative, relative)


@dataclass(frozen=True)
class StabilityResult:
    amplification: float
    stable: bool


def linear_stability(decay_rate: float, dt: float, method: str = "euler") -> StabilityResult:
    """Absolute stability for y'=-a y, a>=0; equality is the marginal boundary."""
    decay_rate, dt = finite_values([decay_rate, dt], "parâmetros de estabilidade")
    if decay_rate < 0 or dt <= 0 or method not in METHODS:
        raise ValueError("Use uma taxa de decaimento não negativa, dt positivo e um método conhecido.")
    z = -decay_rate * dt
    if not math.isfinite(z) or abs(z) > 1e70:
        raise ValueError("O produto da taxa pelo passo excede a escala numérica suportada.")
    amplification = 1 + z
    if method in ("heun", "rk4"):
        amplification += z * z / 2
    if method == "rk4":
        amplification += z ** 3 / 6 + z ** 4 / 24
    amplitude = finite_result(abs(amplification))
    return StabilityResult(amplitude, amplitude < 1 or (decay_rate == 0 and amplitude == 1))
