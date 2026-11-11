"""Newtonian central-force laboratory in SI units, independent of Qt/hardware.

The central mass is fixed and point-like: this is the test-particle (Kepler)
approximation, not a barycentric two-body or general N-body simulation.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import math
from numbers import Real

from ..core.cancellation import Cancellation

G = 6.67430e-11  # m³ kg⁻¹ s⁻²; illustrative constant, no uncertainty propagation.
MAX_STEPS = 100_000
METHODS = ("Euler explícito", "Euler simplético", "Velocity Verlet")


def _finite_values(**values: float) -> None:
    for name, value in values.items():
        if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
            raise ValueError(f"{name}: é necessário um número real finito.")


def _step_count(duration: float, dt: float) -> int:
    _finite_values(duration=duration, dt=dt)
    if duration <= 0 or dt <= 0:
        raise ValueError("A duração e o passo temporal devem ser positivos.")
    if duration / dt > MAX_STEPS:
        raise ValueError(f"A simulação excede {MAX_STEPS:,} passos.")
    return max(1, math.ceil(duration / dt))


@dataclass(frozen=True, slots=True)
class GravityConfig:
    central_mass: float = 5.972e24
    body_mass: float = 1000
    radius: float = 7e6
    velocity_factor: float = 1.0
    duration: float = 10800
    dt: float = 10.0

    def __post_init__(self) -> None:
        _finite_values(central_mass=self.central_mass, body_mass=self.body_mass,
                       radius=self.radius, velocity_factor=self.velocity_factor)
        _step_count(self.duration, self.dt)
        # Generous numerical domains limit intermediate magnitudes.
        if not 1e-12 <= self.central_mass <= 1e40:
            raise ValueError("Massa central fora do domínio numérico [10⁻¹², 10⁴⁰] kg.")
        if not 0 < self.body_mass <= 1e30:
            raise ValueError("A massa do corpo deve estar em ]0, 10³⁰] kg.")
        if not 1e-3 <= self.radius <= 1e18:
            raise ValueError("Raio inicial fora do domínio numérico [10⁻³, 10¹⁸] m.")
        if not 0 <= self.velocity_factor <= 10:
            raise ValueError("O fator de velocidade deve estar entre 0 e 10.")
        if self.duration > 1e12 or self.dt > 1e12:
            raise ValueError("Duração/passo excedem o domínio numérico de 10¹² s.")

    @property
    def mu(self) -> float:
        return G * self.central_mass

    @property
    def circular_speed(self) -> float:
        return math.sqrt(self.mu / self.radius)

    @property
    def period(self) -> float:
        """Circular period corresponding to the initial radius, seconds."""
        return 2 * math.pi * self.radius / self.circular_speed


@dataclass(slots=True)
class GravityTrajectory:
    x: list[float]
    y: list[float]
    vx: list[float]
    vy: list[float]
    energy: list[float]
    angular_momentum: list[float]
    position_error: list[float] | None = None


@dataclass(slots=True)
class GravityExperiment:
    config: GravityConfig
    times: list[float]
    trajectories: dict[str, GravityTrajectory]
    report: str
    reference_x: list[float] | None = None
    reference_y: list[float] | None = None
    convergence: list[tuple[float, dict[str, float]]] = field(default_factory=list)
    provenance: str = "simulado"


def _time_grid(config: GravityConfig) -> list[float]:
    n = _step_count(config.duration, config.dt)
    return [min(i * config.dt, config.duration) for i in range(n + 1)]


def _acceleration(x: float, y: float, mu: float, cutoff: float) -> tuple[float, float]:
    radius = math.hypot(x, y)
    if not math.isfinite(radius) or radius <= cutoff:
        raise ValueError("Trajetória alcançou a singularidade numérica central; reduza o passo ou altere as condições iniciais.")
    # Unit direction times magnitude avoids forming radius**3.
    magnitude = mu / radius / radius
    return -magnitude * (x / radius), -magnitude * (y / radius)


def _check_segment(x: float, y: float, next_x: float, next_y: float, cutoff: float) -> None:
    """Reject a straight numerical step crossing the central singularity."""
    dx, dy = next_x - x, next_y - y
    length = math.hypot(dx, dy)
    if not math.isfinite(length):
        raise ValueError("A trajetória excedeu o domínio numérico; reduza o passo.")
    if length:
        along = -(x * (dx / length) + y * (dy / length))
        if 0 < along < length:
            if math.hypot(x + along * (dx / length), y + along * (dy / length)) <= cutoff:
                raise ValueError("Um passo atravessa a singularidade central; reduza o passo.")


def _integrate(config: GravityConfig, times: list[float], method: str,
               token: Cancellation) -> GravityTrajectory:
    mu, mass = config.mu, config.body_mass
    cutoff = max(1e-12 * config.radius, 1e-12)
    x, y = config.radius, 0.0
    vx, vy = 0.0, config.velocity_factor * config.circular_speed
    result = GravityTrajectory([], [], [], [], [], [])

    def append() -> None:
        radius = math.hypot(x, y)
        if radius <= cutoff or not all(math.isfinite(v) for v in (x, y, vx, vy)):
            raise ValueError("Estado singular ou não finito na trajetória.")
        speed = math.hypot(vx, vy)
        energy = mass * (speed * speed / 2 - mu / radius)
        momentum = mass * (x * vy - y * vx)
        if not math.isfinite(energy) or not math.isfinite(momentum):
            raise ValueError("Energia/momento angular excederam o domínio numérico.")
        result.x.append(x)
        result.y.append(y)
        result.vx.append(vx)
        result.vy.append(vy)
        result.energy.append(energy)
        result.angular_momentum.append(momentum)

    append()
    ax, ay = _acceleration(x, y, mu, cutoff)
    for i in range(len(times) - 1):
        if i % 128 == 0:
            token.check()
        h = times[i + 1] - times[i]
        if method == METHODS[0]:
            nx, ny = x + h * vx, y + h * vy
            nvx, nvy = vx + h * ax, vy + h * ay
        elif method == METHODS[1]:
            nvx, nvy = vx + h * ax, vy + h * ay
            nx, ny = x + h * nvx, y + h * nvy
        else:  # Velocity Verlet: position, new force, velocity.
            nx, ny = x + h * vx + h * h * ax / 2, y + h * vy + h * h * ay / 2
            _check_segment(x, y, nx, ny, cutoff)
            nax, nay = _acceleration(nx, ny, mu, cutoff)
            nvx, nvy = vx + h * (ax + nax) / 2, vy + h * (ay + nay) / 2
        _check_segment(x, y, nx, ny, cutoff)
        x, y, vx, vy = nx, ny, nvx, nvy
        ax, ay = _acceleration(x, y, mu, cutoff)
        append()
    token.check()
    return result


def _circular_reference(config: GravityConfig, times: list[float]) -> tuple[list[float], list[float]]:
    omega = config.circular_speed / config.radius
    return ([config.radius * math.cos(omega * t) for t in times],
            [config.radius * math.sin(omega * t) for t in times])


def _position_errors(trajectory: GravityTrajectory, rx: list[float], ry: list[float]) -> list[float]:
    return [math.hypot(x - a, y - b) for x, y, a, b in zip(trajectory.x, trajectory.y, rx, ry)]


def _rmse(values: list[float]) -> float:
    # hypot-style scaling avoids overflow for widely separated orbits.
    scale = max(values, default=0)
    return scale * math.sqrt(sum((value / scale) ** 2 for value in values) / len(values)) if scale else 0.0


def run_gravity(config: GravityConfig, token: Cancellation | None = None) -> GravityExperiment:
    """Compare Euler, symplectic Euler and Velocity Verlet for a central force.

    Position errors use an independent analytic circular reference only when
    ``velocity_factor == 1``. Other initial speeds retain conservation diagnostics
    but are never falsely labelled exact-reference validation.
    """
    token = token or Cancellation()
    token.check()
    times = _time_grid(config)
    trajectories = {}
    for method in METHODS:
        try:
            trajectories[method] = _integrate(config, times, method, token)
        except ValueError as error:
            raise ValueError(f"{method}: {error}") from error
    rx, ry = None, None
    convergence: list[tuple[float, dict[str, float]]] = []
    if config.velocity_factor == 1:
        rx, ry = _circular_reference(config, times)
        for trajectory in trajectories.values():
            trajectory.position_error = _position_errors(trajectory, rx, ry)
        base_step = min(config.dt, config.duration)
        convergence.append((base_step, {name: _rmse(t.position_error) for name, t in trajectories.items()}))
        # Bound automatic analysis work; the main trajectory still allows 100k.
        for factor in (2, 4):
            token.check()
            step = base_step / factor
            if step == 0 or config.duration / step > 20_000:
                continue
            trial_config = replace(config, dt=step)
            trial_times = _time_grid(trial_config)
            tx, ty = _circular_reference(trial_config, trial_times)
            errors = {}
            for method in METHODS:
                token.check()
                trajectory = _integrate(trial_config, trial_times, method, token)
                errors[method] = _rmse(_position_errors(trajectory, tx, ty))
            convergence.append((step, errors))

    lines = ["GRAVITAÇÃO NEWTONIANA — dados inteiramente simulados.",
             "Massa central pontual e fixa; corpo de teste sem atmosfera, colisões físicas ou relatividade.",
             "r'' = −GM r / |r|³; G = 6,67430×10⁻¹¹ m³ kg⁻¹ s⁻².",
             "E = m|v|²/2 − GMm/r (J); Lz = m(x·vy − y·vx) (kg·m²/s).",
             f"Velocidade circular inicial: {config.circular_speed:.8g} m/s; período circular: {config.period:.8g} s.",
             f"Passo nominal: {config.dt:g} s; duração: {config.duration:g} s; {len(times)-1} intervalos.",
             "Último intervalo encurtado quando necessário para respeitar a duração pedida."]
    if rx is None:
        lines.append("Referência analítica circular indisponível: o fator de velocidade é diferente de 1. Não é apresentado erro de posição contra uma órbita circular incorreta.")
    else:
        lines.append("Referência circular independente: x=R cos(ωt), y=R sin(ωt), ω=√(GM/R³).")
    for method, trajectory in trajectories.items():
        energy0, momentum0 = trajectory.energy[0], trajectory.angular_momentum[0]
        drift_e = max(abs(value - energy0) for value in trajectory.energy)
        drift_l = max(abs(value - momentum0) for value in trajectory.angular_momentum)
        characteristic = config.mu * config.body_mass / config.radius
        relative = f"{drift_e/abs(energy0):.6g}" if abs(energy0) > 1e-12 * characteristic else "indefinida (E₀≈0)"
        lines += ["", method,
                  f"Máximo |ΔE|: {drift_e:.8g} J; máximo |ΔE|/|E₀|: {relative}.",
                  f"Máximo |ΔLz|: {drift_l:.8g} kg·m²/s."]
        if trajectory.position_error is not None:
            lines.append(f"RMSE de posição: {_rmse(trajectory.position_error):.8g} m; máximo: {max(trajectory.position_error):.8g} m.")
    if convergence:
        lines += ["", "Convergência circular (passo s → RMSE de posição m):"]
        for step, result in convergence:
            lines.append(f"{step:g} → " + "; ".join(f"{method}: {error:.6g}" for method, error in result.items()))
        for (h1, e1), (h2, e2) in zip(convergence, convergence[1:]):
            for method in METHODS:
                if min(e1[method],e2[method]) > max(1e-12 * config.radius,1e-12):
                    order = (math.log(e1[method])-math.log(e2[method])) / math.log(h1 / h2)
                    lines.append(f"Ordem observada {method} ({h1:g}→{h2:g} s): {order:.4f}.")
                else:
                    lines.append(f"Ordem observada {method}: não estimada para erros próximos do limite de arredondamento.")
        if len(convergence) < 3:
            lines.append("Alguns refinamentos foram omitidos para limitar a análise automática a 20 000 passos por refinamento.")
    lines += ["", "Euler explícito pode ganhar energia e afastar a órbita; Euler simplético é de primeira ordem e conserva Lz até arredondamento.",
              "Velocity Verlet é de segunda ordem para a força suave, com erro de energia geralmente oscilatório quando o passo resolve a órbita.",
              "Passos demasiado grandes podem produzir trajetórias sem valor físico. O limite de passos não é um critério de estabilidade.",
              "A singularidade central é protegida numericamente; não existe aqui um modelo de superfície terrestre ou de impacto.",
              "A massa do corpo multiplica E/Lz, mas não altera a aceleração nesta aproximação. Para massas comparáveis é necessário um modelo de dois corpos com recuo."]
    token.check()
    return GravityExperiment(config, times, trajectories, "\n".join(lines), rx, ry, convergence)


@dataclass(slots=True)
class FreeFallResult:
    times: list[float]
    heights: list[float]
    velocities: list[float]
    reference_heights: list[float]
    reference_velocities: list[float]
    provenance: str = "simulado"


def free_fall_euler(height: float = 100, initial_velocity: float = 0,
                    gravity: float = 9.80665, duration: float = 4, dt: float = .01,
                    token: Cancellation | None = None) -> FreeFallResult:
    """Uniform downward g, upward-positive y; no ground/impact is modelled.

    A negative final height is a coordinate below y=0, not a simulated collision.
    The analytic reference assumes constant gravity and no air resistance.
    """
    _finite_values(height=height, initial_velocity=initial_velocity, gravity=gravity)
    n = _step_count(duration, dt)
    if height < 0 or gravity < 0:
        raise ValueError("A altura inicial e g devem ser não negativos.")
    token = token or Cancellation()
    token.check()
    times = [min(i * dt, duration) for i in range(n + 1)]
    heights, velocities = [height], [initial_velocity]
    y, v = height, initial_velocity
    for i in range(n):
        if i % 256 == 0:
            token.check()
        h = times[i + 1] - times[i]
        y, v = y + h * v, v - h * gravity
        if not math.isfinite(y) or not math.isfinite(v):
            raise ValueError("Queda livre excedeu o domínio numérico.")
        heights.append(y)
        velocities.append(v)
    reference_y = [height + initial_velocity * t - gravity * t * t / 2 for t in times]
    reference_v = [initial_velocity - gravity * t for t in times]
    if not all(math.isfinite(v) for v in reference_y + reference_v):
        raise ValueError("Referência de queda livre excedeu o domínio numérico.")
    token.check()
    return FreeFallResult(times, heights, velocities, reference_y, reference_v)
