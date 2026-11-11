"""Read-only consumption calculations using explicit power in watts.

CPU utilization is never a power source. A trace's provenance belongs to its
caller; a numeric CSV alone cannot establish that a calibrated sensor measured it.
"""
from collections.abc import Sequence
import csv
from dataclasses import dataclass
import math
from pathlib import Path

from .cancellation import Cancellation


MAX_SAMPLES = 200_001


@dataclass(frozen=True, slots=True)
class EnergyUse:
    joules: float
    watt_hours: float
    duration: float
    average_power: float
    peak_power: float

    @property
    def energy_j(self) -> float:
        return self.joules

    @property
    def energy_wh(self) -> float:
        return self.watt_hours


@dataclass(frozen=True, slots=True)
class PowerTrace:
    times: tuple[float, ...]
    powers: tuple[float, ...]
    temperatures: tuple[float, ...] | None = None


def validate_times(times: Sequence[float]) -> tuple[float, ...]:
    if not 2 <= len(times) <= MAX_SAMPLES:
        raise ValueError(f"São necessárias 2 a {MAX_SAMPLES} amostras de tempo.")
    try:
        values = tuple(float(t) for t in times)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("Os instantes devem ser números finitos em segundos.") from error
    if (any(not math.isfinite(t) for t in values)
            or not math.isfinite(values[-1]-values[0])
            or any(b <= a for a, b in zip(values, values[1:]))):
        raise ValueError("Os instantes devem ser finitos e estritamente crescentes.")
    return values


def validate_powers(times: Sequence[float], powers: Sequence[float]) -> tuple[float, ...]:
    if len(times) != len(powers):
        raise ValueError("É necessária uma potência em W por instante.")
    try:
        values = tuple(float(p) for p in powers)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("A potência deve ser um número finito não negativo em watts.") from error
    if any(not math.isfinite(p) or p < 0 for p in values):
        raise ValueError("A potência deve ser finita e não negativa em watts.")
    return values


def validate_temperatures(times: Sequence[float], temperatures: Sequence[float]) -> tuple[float, ...]:
    if len(times) != len(temperatures):
        raise ValueError("É necessária uma temperatura por instante, ou nenhuma série de temperatura.")
    try:
        values = tuple(float(t) for t in temperatures)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("A temperatura deve ser finita em °C.") from error
    if any(not math.isfinite(t) or t < -273.15 for t in values):
        raise ValueError("A temperatura deve ser finita e não inferior ao zero absoluto.")
    return values


def integrate_power(times: Sequence[float], powers: Sequence[float],
                    token: Cancellation | None = None) -> EnergyUse:
    """Trapezoid energy in J and Wh; irregular timestamps are accepted."""
    if token:
        token.check()
    ts = validate_times(times)
    ps = validate_powers(ts, powers)
    terms = []
    for i in range(len(ts)-1):
        if token and i % 256 == 0:
            token.check()
        terms.append((ps[i]/2+ps[i+1]/2)*(ts[i+1]-ts[i]))
    try:
        energy = math.fsum(terms)
    except OverflowError as error:
        raise ValueError("A energia excedeu a escala numérica suportada.") from error
    duration = ts[-1]-ts[0]
    if not math.isfinite(energy) or not math.isfinite(duration):
        raise ValueError("Energia ou duração fora da escala numérica suportada.")
    return EnergyUse(energy, energy/3600, duration, energy/duration, max(ps))


def load_power_csv(path: str | Path, token: Cancellation | None = None) -> PowerTrace:
    """Import time_s,power_w and optional temperature_c, all explicit SI units.

    This function does not assign sensor provenance. Headers are deliberately
    strict to prevent percentages or differently scaled units being accepted.
    """
    if token:
        token.check()
    target = Path(path)
    if target.stat().st_size > 16*1024*1024:
        raise ValueError("O CSV energético excede 16 MiB.")
    times, powers, temperatures = [], [], []
    with target.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        fields = reader.fieldnames
        if (not fields or len(set(fields)) != len(fields)
                or not {"time_s", "power_w"}.issubset(fields)
                or not set(fields).issubset({"time_s", "power_w", "temperature_c"})):
            raise ValueError("CSV: time_s,power_w e, opcionalmente, temperature_c; unidades s, W e °C.")
        has_temperature = "temperature_c" in fields
        try:
            for line, row in enumerate(reader, start=2):
                if token and line % 256 == 0:
                    token.check()
                if len(times) >= MAX_SAMPLES:
                    raise ValueError(f"O CSV está limitado a {MAX_SAMPLES} amostras.")
                try:
                    if None in row or any(value is None for value in row.values()):
                        raise ValueError
                    times.append(float(row["time_s"]))
                    powers.append(float(row["power_w"]))
                    if has_temperature:
                        temperatures.append(float(row["temperature_c"]))
                except (TypeError, ValueError) as error:
                    raise ValueError(f"Linha {line}: valores numéricos completos em s, W e °C são obrigatórios.") from error
        except csv.Error as error:
            raise ValueError(f"CSV energético malformado: {error}") from error
    ts = validate_times(times)
    ps = validate_powers(ts, powers)
    temp = validate_temperatures(ts, temperatures) if has_temperature else None
    if token:
        token.check()
    return PowerTrace(ts, ps, temp)
