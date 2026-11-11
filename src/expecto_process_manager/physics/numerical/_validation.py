"""Small shared validation helpers; no NumPy or Qt dependency."""
from collections.abc import Sequence
import math


def finite_values(values: Sequence[float], name: str = "valores") -> list[float]:
    try:
        result = [float(value) for value in values]
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"Os {name} devem ser números reais finitos.") from exc
    if not all(math.isfinite(value) for value in result):
        raise ValueError(f"Os {name} devem ser números reais finitos.")
    return result


def samples(times: Sequence[float], values: Sequence[float], minimum: int = 2) -> tuple[list[float], list[float]]:
    x = finite_values(times, "tempos")
    y = finite_values(values)
    if len(x) != len(y) or len(x) < minimum:
        raise ValueError(f"São necessários pelo menos {minimum} pares de amostras.")
    if any(b <= a or not math.isfinite(b - a) for a, b in zip(x, x[1:])):
        raise ValueError("Os tempos devem ser estritamente crescentes, com intervalos finitos.")
    return x, y


def finite_result(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("O cálculo excedeu a precisão numérica; reveja escalas e passo temporal.")
    return value
