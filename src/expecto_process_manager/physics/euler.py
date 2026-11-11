from collections.abc import Callable
from dataclasses import dataclass
import math
from .thermal_model import ThermalModel, finite
from ..core.cancellation import Cancellation


@dataclass
class Simulation:
    times: list[float]
    temperatures: list[float]
    powers: list[float]
    reference: list[float]
    provenance: str = "simulado"


def simulate(model: ThermalModel, initial: float, power: Callable[[float], float],
             duration: float, dt: float, *, cancellation: Cancellation | None = None) -> Simulation:
    finite(initial, duration, dt)
    if duration <= 0 or dt <= 0 or math.ceil(duration / dt) > 200_000:
        raise ValueError("Duração/passo inválidos ou mais de 200 000 passos.")
    if dt * model.dissipation / model.capacity >= 2:
        raise ValueError("Euler instável: é necessário dt < 2C/k.")
    times, temperatures, powers, reference = [0.0], [initial], [], [initial]
    for i in range(math.ceil(duration / dt)):
        if cancellation and i % 256 == 0:
            cancellation.check()
        t = times[-1]
        p = power(t)
        finite(p)
        if p < 0:
            raise ValueError("A potência térmica deve ser não negativa.")
        end = min((i + 1) * dt, duration)
        h = end - t
        powers.append(p)
        temperatures.append(temperatures[-1] + h * model.rate(temperatures[-1], p))
        # Exact per interval for the same zero-order-held forcing.
        reference.append(model.exact(reference[-1], p, h))
        times.append(end)
    final_power = power(duration)
    finite(final_power)
    if final_power < 0:
        raise ValueError("Potência negativa.")
    powers.append(final_power)
    return Simulation(times, temperatures, powers, reference)
