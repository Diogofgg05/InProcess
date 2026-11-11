from collections.abc import Sequence
from .integration import validate


def derivative(times: Sequence[float], values: Sequence[float]) -> list[float]:
    validate(times, values)
    result = [(values[1]-values[0])/(times[1]-times[0])]
    for i in range(1, len(times)-1):
        a, b = times[i]-times[i-1], times[i+1]-times[i]
        result.append(-b/(a*(a+b))*values[i-1]+(b-a)/(a*b)*values[i]+a/(b*(a+b))*values[i+1])
    result.append((values[-1]-values[-2])/(times[-1]-times[-2]))
    return result


def smooth(values: Sequence[float], radius: int = 3) -> list[float]:
    if radius < 0:
        raise ValueError("Raio inválido.")
    return [sum(values[max(0,i-radius):i+radius+1])/len(values[max(0,i-radius):i+radius+1]) for i in range(len(values))]
