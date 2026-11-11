from collections.abc import Sequence
import math
from .thermal_model import finite


def validate(times: Sequence[float], values: Sequence[float]) -> None:
    if len(times) != len(values) or len(times) < 2:
        raise ValueError("São necessários pelo menos dois pares de amostras.")
    finite(*times, *values)
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError("Os tempos devem ser estritamente crescentes.")


def integrate(times: Sequence[float], values: Sequence[float], method: str = "trapezoid") -> float:
    validate(times, values)
    if method == "rectangle":
        return sum((b-a)*v for a, b, v in zip(times, times[1:], values))
    if method == "trapezoid":
        return sum((times[i+1]-times[i])*(values[i]+values[i+1])/2 for i in range(len(times)-1))
    if method != "simpson":
        raise ValueError("Método desconhecido.")
    h = times[1]-times[0]
    if (len(times)-1) % 2 or any(not math.isclose(b-a, h, rel_tol=1e-8, abs_tol=1e-12) for a,b in zip(times,times[1:])):
        raise ValueError("Simpson requer intervalos uniformes e em número par.")
    return h/3*(values[0]+values[-1]+4*sum(values[1:-1:2])+2*sum(values[2:-1:2]))


def cumulative(times: Sequence[float], values: Sequence[float]) -> list[float]:
    validate(times, values)
    result = [0.0]
    for i in range(len(times)-1):
        result.append(result[-1]+(times[i+1]-times[i])*(values[i]+values[i+1])/2)
    return result
