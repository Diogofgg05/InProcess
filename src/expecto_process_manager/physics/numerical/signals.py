"""Deterministic synthetic noise and explicitly described low-pass filters."""
from collections.abc import Sequence
import math
import random

from ._validation import finite_result, finite_values


def moving_average(values: Sequence[float], window: int = 5) -> list[float]:
    """Centered, noncausal moving average; clipped windows at both ends."""
    signal = finite_values(values, "amostras do sinal")
    if not isinstance(window, int) or isinstance(window, bool) or window < 1 or window % 2 == 0:
        raise ValueError("A janela deve ter um número ímpar positivo de amostras.")
    if window > 100_001:
        raise ValueError("A janela excede o limite de 100001 amostras.")
    if not signal:
        return []
    radius = window // 2
    # One pass with a sliding sum, rather than O(n*window) repeated slices.
    left, right = 0, min(len(signal), radius + 1)
    total = math.fsum(signal[left:right])
    result = [finite_result(total / (right - left))]
    for index in range(1, len(signal)):
        next_left = max(0, index - radius)
        next_right = min(len(signal), index + radius + 1)
        if next_left > left:
            total -= signal[left]
        if next_right > right:
            total += signal[right]
        left, right = next_left, next_right
        result.append(finite_result(total / (right - left)))
    return result


def exponential_filter(values: Sequence[float], alpha: float = 0.2, initial: float | None = None) -> list[float]:
    """Causal y_i=alpha*x_i+(1-alpha)*y_(i-1), with y_0=x_0 by default.

    If supplied, initial replaces y_0. Filtering changes signal and derivative
    bias/phase; it does not reconstruct the unknown noise-free observation.
    """
    signal = finite_values(values, "amostras do sinal")
    alpha = finite_values([alpha], "coeficientes do filtro")[0]
    if not 0 < alpha <= 1:
        raise ValueError("alpha deve pertencer ao intervalo ]0, 1].")
    first = None if initial is None else finite_values([initial], "estados iniciais")[0]
    if not signal:
        return []
    result = [signal[0] if first is None else first]
    for value in signal[1:]:
        result.append(finite_result(alpha * value + (1 - alpha) * result[-1]))
    return result


def add_gaussian_noise(values: Sequence[float], sigma: float, seed: int = 0) -> list[float]:
    """Independent simulated Gaussian noise, standard deviation sigma in signal units."""
    signal = finite_values(values, "amostras do sinal")
    sigma = finite_values([sigma], "desvios padrão")[0]
    if sigma < 0:
        raise ValueError("O desvio padrão do ruído não pode ser negativo.")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("A semente deve ser um inteiro para permitir reprodução.")
    generator = random.Random(seed)
    return [finite_result(value + generator.gauss(0, sigma)) for value in signal]
