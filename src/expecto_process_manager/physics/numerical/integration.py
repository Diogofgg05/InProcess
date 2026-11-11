"""Composite quadrature; midpoint inputs are separate from endpoint samples."""
from collections.abc import Sequence
import math

from ._validation import finite_result, finite_values, samples


def quadrature(times: Sequence[float], values: Sequence[float], method: str = "trapezoid") -> float:
    """Integrate endpoint samples; Simpson 1/3 requires an even uniform grid.

    ``left`` and ``right`` use the corresponding rectangle on each interval.
    ``midpoint`` is intentionally unavailable: endpoint samples do not supply
    measured/evaluated midpoint values. Use integrate_midpoints instead.
    """
    x, y = samples(times, values)
    if method == "simpson":
        intervals = len(x) - 1
        h = (x[-1] - x[0]) / intervals
        if intervals % 2 or any(not math.isclose(b - a, h, rel_tol=1e-8, abs_tol=abs(h) * 1e-10) for a, b in zip(x, x[1:])):
            raise ValueError("Simpson 1/3 exige um número par de intervalos uniformes.")
        result = (h / 3) * math.fsum([y[0], y[-1], *[4 * v for v in y[1:-1:2]], *[2 * v for v in y[2:-1:2]]])
    elif method in ("left", "right", "trapezoid"):
        if method == "left":
            heights = y[:-1]
        elif method == "right":
            heights = y[1:]
        else:
            heights = [a / 2 + b / 2 for a, b in zip(y, y[1:])]
        result = math.fsum((b - a) * height for a, b, height in zip(x, x[1:], heights))
    else:
        raise ValueError("Escolha left, right, trapezoid ou simpson; pontos médios exigem amostras próprias.")
    return finite_result(result)


def integrate_midpoints(edges: Sequence[float], mid_values: Sequence[float]) -> float:
    """Use one genuine midpoint sample per interval; supports unequal widths."""
    x = finite_values(edges, "limites dos intervalos")
    y = finite_values(mid_values, "amostras nos pontos médios")
    if len(x) != len(y) + 1 or len(x) < 2:
        raise ValueError("Forneça uma amostra no ponto médio de cada intervalo.")
    if any(b <= a or not math.isfinite(b - a) for a, b in zip(x, x[1:])):
        raise ValueError("Os limites devem ser estritamente crescentes e finitos.")
    return finite_result(math.fsum((b - a) * value for a, b, value in zip(x, x[1:], y)))
