"""Physics Lab 6: transient 1-D conduction and coupled CPU/fan control.

All values are illustrative and SIMULATED. Neither model reads sensors nor
writes to the OS. Each solver is bounded in time, space and memory.
"""
from dataclasses import dataclass, replace
import math

from .coupled_models import TwoNodeThermal
from .numerical.ode import solve_ivp
from .numerical.validation import convergence_study, sensitivity_study


@dataclass(frozen=True)
class HeatSlab:
    length_m: float = 0.04
    diffusivity_m2_s: float = 1e-5
    conductivity_w_m_k: float = 180.0
    area_m2: float = .001
    initial_c: float = 65.0
    ambient_c: float = 25.0
    nodes: int = 21

    def __post_init__(self):
        for value in (self.length_m, self.diffusivity_m2_s,
                      self.conductivity_w_m_k, self.area_m2,
                      self.initial_c, self.ambient_c):
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
                raise ValueError("Valores físicos finitos obrigatórios.")
        if min(self.length_m, self.diffusivity_m2_s,
               self.conductivity_w_m_k, self.area_m2) <= 0:
            raise ValueError("Geometria e propriedades físicas positivas obrigatórias.")
        if min(self.initial_c, self.ambient_c) < -273.15:
            raise ValueError("Temperatura inferior ao zero absoluto.")
        if type(self.nodes) is not int or not 5 <= self.nodes <= 401:
            raise ValueError("Número de nós entre 5 e 401.")

    @property
    def dx(self):
        return self.length_m / (self.nodes - 1)

    @property
    def stable_dt(self):
        return self.dx ** 2 / (2 * self.diffusivity_m2_s)

    @property
    def volumetric_capacity(self):
        return self.conductivity_w_m_k / self.diffusivity_m2_s

    def exact(self, position_m, time_s):
        """Dirichlet ends held at ambient, initial interior sinusoidal mode."""
        if not 0 <= position_m <= self.length_m or time_s < 0:
            raise ValueError("Posição/tempo fora da região simulada.")
        amplitude = self.initial_c - self.ambient_c
        return self.ambient_c + amplitude * math.sin(math.pi * position_m / self.length_m) * math.exp(
            -self.diffusivity_m2_s * (math.pi / self.length_m) ** 2 * time_s
        )


@dataclass(frozen=True)
class HeatResult:
    positions_m: tuple[float, ...]
    times_s: tuple[float, ...]
    profiles_c: tuple[tuple[float, ...], ...]
    max_error_c: float
    rmse_c: float
    fourier: float
    energy_initial_j: float
    energy_final_j: float
    boundary_energy_j: float
    balance_error_j: float


def solve_heat(model: HeatSlab = HeatSlab(), *, duration_s: float = 4.0,
               dt_s: float | None = None, token=None) -> HeatResult:
    """Explicit conservative finite-volume equivalent with fixed Dirichlet ends.

    Interior nodes use the standard centered second difference and time Euler.
    The integrated boundary flux is computed with matching discrete gradients,
    yielding a discrete energy balance up to floating-point round-off.
    """
    if not isinstance(duration_s, (int, float)) or not math.isfinite(duration_s) or duration_s <= 0:
        raise ValueError("Duração positiva e finita obrigatória.")
    dt = model.stable_dt * .8 if dt_s is None else dt_s
    if not isinstance(dt, (int, float)) or isinstance(dt, bool) or not math.isfinite(dt) or dt <= 0:
        raise ValueError("Passo temporal positivo e finito obrigatório.")
    if dt > model.stable_dt * (1 + 1e-12):
        raise ValueError("Esquema explícito instável: número de Fourier acima de 0,5.")
    count = math.ceil(duration_s / dt)
    if count > 60000 or count * model.nodes > 1_500_000:
        raise ValueError("Orçamento numérico excedido; aumente dt ou diminua duração/nós.")
    h = duration_s / count
    fo = model.diffusivity_m2_s * h / model.dx**2
    x = tuple(i * model.dx for i in range(model.nodes))
    state = [model.exact(position, 0.) for position in x]
    initial = tuple(state)
    times = [0.]
    profiles = [initial]
    error_squared = 0.
    max_error = 0.
    samples = 0
    boundary_energy = 0.
    c_vol = model.volumetric_capacity * model.area_m2 * model.dx

    for index in range(1, count + 1):
        if token is not None and index % 64 == 0:
            token.check()
        # Fluxes leaving both ends, matching exactly the conservative update.
        boundary_energy += model.conductivity_w_m_k * model.area_m2 / model.dx * (
            state[1] - model.ambient_c + state[-2] - model.ambient_c
        ) * h
        nxt = [model.ambient_c] + [
            state[i] + fo * (state[i - 1] - 2 * state[i] + state[i + 1])
            for i in range(1, model.nodes - 1)
        ] + [model.ambient_c]
        state = nxt
        t = index * h
        # Bounded storage: up to 201 profiles, including last one.
        if index == count or index % max(1, math.ceil(count / 200)) == 0:
            times.append(t)
            profiles.append(tuple(state))
            for xx, value in zip(x, state):
                error = abs(value - model.exact(xx, t))
                max_error = max(max_error, error)
                error_squared += error * error
                samples += 1
    initial_e = c_vol * sum(v - model.ambient_c for v in initial[1:-1])
    final_e = c_vol * sum(v - model.ambient_c for v in state[1:-1])
    if token is not None:
        token.check()
    return HeatResult(x, tuple(times), tuple(profiles), max_error,
                      math.sqrt(error_squared / samples), fo,
                      initial_e, final_e, boundary_energy,
                      (final_e - initial_e) + boundary_energy)


def heat_convergence(model: HeatSlab | None = None, *, duration_s=2.0, token=None):
    """Temporal convergence at the same fixed spatial grid with independent reference.

    The exact continuum solution has an O(dx^2) spatial floor, so temporal
    order should not be inferred from the total error against that reference.
    Report errors as a descriptive convergence table, not an RK4 claim.
    """
    model = model or HeatSlab(nodes=21)
    rows = []
    for factor in (.8, .4, .2, .1):
        result = solve_heat(model, duration_s=duration_s,
                            dt_s=factor * model.stable_dt, token=token)
        rows.append({"requested_fourier": factor,
                     "actual_fourier": result.fourier,
                     "rmse_c": result.rmse_c,
                     "maximum_c": result.max_error_c,
                     "balance_residual_j": result.balance_error_j})
    return rows


def heat_sensitivity(model: HeatSlab | None = None, *, duration_s=2.0, token=None):
    base = model or HeatSlab(nodes=21)
    rows = []
    for factor in (.8, 1.0, 1.2):
        model = replace(base, diffusivity_m2_s=base.diffusivity_m2_s * factor)
        out = solve_heat(model, duration_s=duration_s, token=token)
        center = out.profiles_c[-1][model.nodes // 2]
        rows.append({"diffusivity_m2_s": model.diffusivity_m2_s,
                     "center_temperature_c": center, "rmse_c": out.rmse_c})
    return rows


@dataclass(frozen=True)
class FanControl:
    target_c: float = 47.
    proportional: float = .025
    integral: float = .0008
    max_integral: float = 100.
    base_conductance: float = 1.2
    fan_gain_w_k: float = 2.0
    fan_time_s: float = 3.0
    thermal_power_w: float = 70.

    def __post_init__(self):
        values = (self.target_c, self.proportional, self.integral, self.max_integral,
                  self.base_conductance, self.fan_gain_w_k, self.fan_time_s,
                  self.thermal_power_w)
        if not all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) for x in values):
            raise ValueError("Parâmetros do controlo devem ser finitos.")
        if (self.target_c < -273.15 or self.proportional < 0 or self.integral < 0
                or self.max_integral <= 0 or self.base_conductance <= 0
                or self.fan_gain_w_k < 0 or self.fan_time_s <= 0
                or self.thermal_power_w < 0):
            raise ValueError("Parâmetros do controlador fora do domínio físico.")


@dataclass(frozen=True)
class FanResult:
    times_s: tuple[float, ...]
    die_c: tuple[float, ...]
    sink_c: tuple[float, ...]
    fan_fraction: tuple[float, ...]
    max_die_c: float
    last_die_c: float
    mean_fan_fraction: float
    origin: str = "SIMULATED"


def simulate_fan_control(control: FanControl = FanControl(), *, adaptive=True,
                         duration_s=180., dt_s=.2, token=None) -> FanResult:
    """Coupled CPU + sink + first-order fan actuator and clamped PI controller.

    Note: this is PI, not a tuned PID; fan power is not inferred from fan
    fraction. The controller only acts inside the mathematical simulation.
    """
    if not all(isinstance(x, (float,int)) and math.isfinite(x) and x > 0
               for x in (duration_s,dt_s)):
        raise ValueError("Intervalos temporais positivos obrigatórios.")
    count = math.ceil(duration_s / dt_s)
    if count > 50000:
        raise ValueError("Limite de passos de controlo excedido.")
    h = duration_s / count
    physical = TwoNodeThermal(thermal_power=control.thermal_power_w,
                              ambient_conductance=control.base_conductance)
    die, sink, fan, accumulated = 30.,26.,0.,0.
    times, dies, sinks, fans = [0.],[die],[sink],[fan]
    for step in range(1,count+1):
        if token is not None and step % 64 == 0: token.check()
        error = die - control.target_c
        target_unbounded = control.proportional * error + control.integral * accumulated
        command = max(0., min(1., target_unbounded)) if adaptive else .5
        # Conditional integration anti-windup: only integrate at saturation
        # when the error points back inside the actuator bounds.
        if adaptive and (0 < target_unbounded < 1 or
                          (target_unbounded <= 0 and error > 0) or
                          (target_unbounded >= 1 and error < 0)):
            accumulated = max(-control.max_integral,
                              min(control.max_integral, accumulated + h * error))
        new_fan = (fan + h * command / control.fan_time_s) / (1 + h / control.fan_time_s)
        interface = physical.interface_conductance * (die - sink)
        dissipation = (control.base_conductance + control.fan_gain_w_k * fan) * (sink - physical.ambient)
        new_die = die + h*(physical.thermal_power - interface)/physical.die_capacity
        new_sink = sink + h*(interface - dissipation)/physical.sink_capacity
        die,sink,fan = new_die,new_sink,new_fan
        if not all(math.isfinite(v) for v in (die,sink,fan)) or min(die,sink)<-273.15:
            raise ValueError("Estado físico divergente; reduza o passo temporal.")
        times.append(step*h); dies.append(die); sinks.append(sink); fans.append(fan)
    if token is not None: token.check()
    return FanResult(tuple(times),tuple(dies),tuple(sinks),tuple(fans),
                     max(dies),die,sum(fans)/len(fans))


def fan_comparison(token=None):
    return {"fixed":simulate_fan_control(adaptive=False,token=token),
            "adaptive":simulate_fan_control(adaptive=True,token=token)}
