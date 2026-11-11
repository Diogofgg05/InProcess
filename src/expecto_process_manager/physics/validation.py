from collections.abc import Sequence
import math
from .thermal_model import finite


def errors(predicted: Sequence[float], observed: Sequence[float]) -> dict:
    if len(predicted) != len(observed) or not predicted:
        raise ValueError("Séries incompatíveis ou vazias.")
    finite(*predicted, *observed)
    absolute = [abs(a-b) for a,b in zip(predicted,observed)]
    return {"absolute": absolute,
            "relative": [e/abs(b) if b != 0 else None for e,b in zip(absolute,observed)],
            "rmse": math.sqrt(sum(e*e for e in absolute)/len(absolute)),
            "maximum": max(absolute)}
