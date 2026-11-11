import random
from ..physics.thermal_model import finite


def add_noise(values: list[float], sigma: float, seed: int = 42) -> list[float]:
    finite(sigma)
    if sigma < 0:
        raise ValueError("O desvio padrão deve ser não negativo.")
    rng = random.Random(seed)
    return [v+rng.gauss(0,sigma) for v in values]
