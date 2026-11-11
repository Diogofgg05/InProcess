"""Lumped thermal model. Parameters are hypotheses, not sensor calibration."""
from dataclasses import dataclass
import math


def finite(*values: float) -> None:
    if not all(math.isfinite(v) for v in values):
        raise ValueError("Os valores devem ser finitos.")


@dataclass(frozen=True)
class ThermalModel:
    ambient: float = 22
    capacity: float = 100
    dissipation: float = 2

    def __post_init__(self) -> None:
        finite(self.ambient, self.capacity, self.dissipation)
        if self.capacity <= 0 or self.dissipation <= 0:
            raise ValueError("C e k devem ser positivos.")
        if self.ambient < -273.15:
            raise ValueError('Temperatura ambiente abaixo do zero absoluto.')

    def rate(self, temperature: float, power: float) -> float:
        return (power - self.dissipation * (temperature - self.ambient)) / self.capacity

    def exact(self, initial: float, power: float, time: float) -> float:
        equilibrium = self.ambient + power / self.dissipation
        return equilibrium + (initial - equilibrium) * math.exp(-self.dissipation * time / self.capacity)
