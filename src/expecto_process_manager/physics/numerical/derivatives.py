"""Finite differences on strictly increasing uniform or nonuniform samples."""
from collections.abc import Sequence
import math

from ._validation import finite_result, samples


def _quadratic_derivative(x: list[float], y: list[float], at: float, order: int) -> float:
    # Translate the abscissas before constructing Lagrange weights, avoiding
    # cancellation of large absolute timestamps in expressions such as 2t-a-b.
    offsets = [value - at for value in x]
    total = []
    for i in range(3):
        others = [j for j in range(3) if j != i]
        j, k = others
        denominator = (offsets[i] - offsets[j]) * (offsets[i] - offsets[k])
        if denominator == 0 or not math.isfinite(denominator):
            raise ValueError("As escalas temporais impedem o cálculo das diferenças finitas.")
        numerator = -(offsets[j] + offsets[k]) if order == 1 else 2.0
        # Derivatives annihilate constants. Subtracting a common level makes
        # that property exact and reduces cancellation for temperature offsets.
        total.append((y[i] - y[0]) * numerator / denominator)
    return finite_result(math.fsum(total))


def differentiate(
    times: Sequence[float],
    values: Sequence[float],
    method: str = "central",
    order: int = 1,
) -> list[float]:
    """Return a derivative at every sample, using genuine local coordinates.

    First derivative: forward/backward use two points (first-order on a uniform
    grid). At the unavailable endpoint they use the opposite one-sided stencil.
    Central uses a three-point quadratic interior and one-sided quadratic ends;
    two samples fall back to the common secant slope. Second derivatives use
    three-point quadratic stencils, centered/forward/backward where available,
    shifted at boundaries. They are second-order at uniform interior centers,
    generally first-order on irregular grids and at one-sided boundaries.
    """
    if method not in ("forward", "backward", "central"):
        raise ValueError("Escolha forward, backward ou central.")
    if order not in (1, 2) or isinstance(order, bool):
        raise ValueError("A ordem da derivada deve ser 1 ou 2.")
    x, y = samples(times, values, minimum=3 if order == 2 else 2)
    count = len(x)
    if order == 1 and (method != "central" or count == 2):
        result = []
        for i in range(count):
            left = max(0, i - 1) if method == "backward" or i == count - 1 else i
            result.append(finite_result((y[left + 1] - y[left]) / (x[left + 1] - x[left])))
        return result
    result = []
    for i in range(count):
        left = i - 1 if method == "central" else i if method == "forward" else i - 2
        left = max(0, min(count - 3, left))
        result.append(_quadratic_derivative(x[left:left + 3], y[left:left + 3], x[i], order))
    return result
