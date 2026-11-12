"""Two educational multi-physics computer hardware models.

Both are idealized SIMULATED systems with explicitly independent input
parameters. They do not interrogate or control actual CPU/battery hardware.
"""
from dataclasses import dataclass, fields
import math

from .numerical._validation import finite_values


def _check(model, positive=(), nonnegative=()):
    values = {f.name: getattr(model, f.name) for f in fields(model)}
    finite_values(values.values(), "parâmetros físicos")
    if any(values[name] <= 0 for name in positive) or any(values[name] < 0 for name in nonnegative):
        raise ValueError("Parâmetros fora do domínio físico.")
    if values["ambient"] < -273.15:
        raise ValueError("Temperatura ambiente abaixo do zero absoluto.")


@dataclass(frozen=True)
class TwoNodeThermal:
    """CPU die <-> sink -> ambient: two coupled thermal capacitances.

    Cdie*dTdie/dt = P - Gi*(Tdie - Tsink)
    Csink*dTsink/dt = Gi*(Tdie - Tsink) - Ga*(Tsink - Ta)
    """

    die_capacity: float = 120.0       # J/K
    sink_capacity: float = 280.0      # J/K
    interface_conductance: float = 6.0  # W/K
    ambient_conductance: float = 1.2    # W/K
    ambient: float = 24.0              # degC
    thermal_power: float = 70.0        # W

    def __post_init__(self):
        _check(self, ("die_capacity", "sink_capacity",
                       "interface_conductance", "ambient_conductance"),
               ("thermal_power",))

    @property
    def equilibrium(self):
        sink = self.ambient + self.thermal_power / self.ambient_conductance
        return (sink + self.thermal_power / self.interface_conductance, sink)

    def rhs(self, t, y):
        die, sink = y
        between = self.interface_conductance * (die - sink)
        ambient_loss = self.ambient_conductance * (sink - self.ambient)
        return [(self.thermal_power - between) / self.die_capacity,
                (between - ambient_loss) / self.sink_capacity]

    def exact(self, t, initial=(30.0, 26.0)):
        """Independent closed-form solution for constant power/ambient.

        Derives Tdie from the two real eigenvalues of the linear system,
        and recovers Tsink from the first heat equation.
        """
        if t < 0 or not math.isfinite(t):
            raise ValueError("Tempo não negativo e finito obrigatório.")
        initial = finite_values(initial, "estado térmico inicial")
        if len(initial) != 2 or min(initial) < -273.15:
            raise ValueError("Condições iniciais térmicas inválidas.")
        ci, cs, gi, ga = (self.die_capacity, self.sink_capacity,
                          self.interface_conductance, self.ambient_conductance)
        a, b = -gi / ci, gi / ci
        c, d = gi / cs, -(gi + ga) / cs
        gap = math.hypot(a - d, 2 * math.sqrt(b * c))
        plus, minus = (a + d + gap) / 2, (a + d - gap) / 2
        die_eq, _ = self.equilibrium
        deviation = initial[0] - die_eq
        derivative = self.rhs(0.0, initial)[0]
        coefficient_plus = (derivative - minus * deviation) / gap
        coefficient_minus = deviation - coefficient_plus
        ep, em = math.exp(plus * t), math.exp(minus * t)
        die = die_eq + coefficient_plus * ep + coefficient_minus * em
        die_rate = coefficient_plus * plus * ep + coefficient_minus * minus * em
        sink = die + (ci * die_rate - self.thermal_power) / gi
        return (die, sink)

    def observables(self, y):
        die, sink = y
        if min(die, sink) < -273.15:
            raise ValueError("Temperatura simulada abaixo do zero absoluto.")
        transfer = self.interface_conductance * (die - sink)
        cooling = self.ambient_conductance * (sink - self.ambient)
        return {
            "cpu_temp_c": die, "sink_temp_c": sink,
            "interface_w": transfer, "cooling_w": cooling,
            "input_w": self.thermal_power,
            "stored_j": (self.die_capacity * (die - self.ambient)
                         + self.sink_capacity * (sink - self.ambient)),
        }


@dataclass(frozen=True)
class BatteryThermalRC:
    """Thevenin 1-RC battery, positive constant discharge and lumped heat.

    Q*ds/dt = -I
    Cp*du/dt = I-u/Rp
    Cth*dT/dt = I**2*R0 + u**2/Rp - k*(T-Ta)

    OCV(s) is a linear educational approximation, not an actual cell curve.
    """

    capacity_ah: float = 4.0
    voltage_empty: float = 10.0
    voltage_full: float = 12.6
    internal_resistance: float = 0.07
    polarization_resistance: float = 0.04
    polarization_capacitance: float = 1500.0
    discharge_current: float = 2.0
    thermal_capacity: float = 120.0
    cooling: float = 0.55
    ambient: float = 25.0

    def __post_init__(self):
        _check(self, ("capacity_ah", "internal_resistance",
                       "polarization_resistance", "polarization_capacitance",
                       "thermal_capacity", "cooling"),
               ("discharge_current",))
        if self.voltage_empty <= 0 or self.voltage_full <= self.voltage_empty:
            raise ValueError("A tensão em carga plena deve exceder a tensão em vazio.")

    @property
    def capacity_coulombs(self):
        return self.capacity_ah * 3600.0

    @property
    def time_constant(self):
        return self.polarization_resistance * self.polarization_capacitance

    def ocv(self, soc):
        return self.voltage_empty + (self.voltage_full - self.voltage_empty) * soc

    def rhs(self, t, y):
        soc, polarization, temp = y
        i = self.discharge_current
        losses = i * i * self.internal_resistance + polarization**2 / self.polarization_resistance
        return [-i / self.capacity_coulombs,
                (i - polarization / self.polarization_resistance) / self.polarization_capacitance,
                (losses - self.cooling * (temp - self.ambient)) / self.thermal_capacity]

    def exact(self, t, initial=(0.85, 0.0, 25.0)):
        """Independent exact terminal voltage for constant discharge current."""
        if t < 0 or not math.isfinite(t):
            raise ValueError("Tempo não negativo e finito obrigatório.")
        s0, u0 = initial[:2]
        soc = s0 - self.discharge_current * t / self.capacity_coulombs
        pol = self.discharge_current * self.polarization_resistance + (
            u0 - self.discharge_current * self.polarization_resistance
        ) * math.exp(-t / self.time_constant)
        return self.ocv(soc) - self.discharge_current * self.internal_resistance - pol

    def observables(self, y):
        soc, u, temp = y
        if not -1e-9 <= soc <= 1 + 1e-9 or temp < -273.15:
            raise ValueError("SOC ou temperatura fora do domínio físico.")
        i = self.discharge_current
        voc = self.ocv(soc)
        terminal = voc - i * self.internal_resistance - u
        ohmic = i * i * self.internal_resistance
        polarization_loss = u*u / self.polarization_resistance
        cooling = self.cooling * (temp - self.ambient)
        chemical = self.capacity_coulombs * (
            self.voltage_empty * soc
            + 0.5 * (self.voltage_full - self.voltage_empty) * soc * soc
        )
        capacitor = self.polarization_capacitance * u*u / 2.0
        relative_heat = self.thermal_capacity * (temp - self.ambient)
        return {
            "soc": soc, "polarization_v": u, "terminal_voltage_v": terminal,
            "current_a": i, "temperature_c": temp,
            "chemical_j": chemical, "capacitor_j": capacitor,
            "thermal_relative_j": relative_heat,
            "stored_j": chemical + capacitor + relative_heat,
            "load_w": i * terminal, "loss_joule_w": ohmic,
            "loss_polarization_w": polarization_loss, "cooling_w": cooling,
        }
