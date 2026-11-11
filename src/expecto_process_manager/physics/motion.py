"""One-dimensional, forward-only AGV motion with a resolved stopping event.

This is an educational model, independent of process or hardware monitoring.
Acceleration and braking are constant commands; ``friction`` is linear drag in
s^-1 (acceleration due to drag = -friction * velocity), not a Coulomb coefficient.
"""
from dataclasses import dataclass
import math

from ..core.cancellation import Cancellation


MAX_STEPS = 100_000
METHODS = ("Euler", "Heun", "RK4")


@dataclass(frozen=True, slots=True)
class MotionConfig:
    position: float = 0.0
    velocity: float = 10.0
    acceleration: float = 0.0
    deceleration: float = 2.0
    friction: float = 0.0
    duration: float = 10.0
    dt: float = 0.1

    def __post_init__(self) -> None:
        values = (self.position, self.velocity, self.acceleration,
                  self.deceleration, self.friction, self.duration, self.dt)
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
            raise ValueError("Os parâmetros AGV devem ser números finitos.")
        if min(self.velocity, self.acceleration, self.deceleration, self.friction) < 0:
            raise ValueError("Velocidade, aceleração, desaceleração e atrito devem ser não negativos.")
        if self.duration <= 0 or self.dt <= 0:
            raise ValueError("Duração e passo temporal devem ser positivos.")
        if self.duration / self.dt > MAX_STEPS:
            raise ValueError(f"A simulação AGV está limitada a {MAX_STEPS} intervalos.")
        if self.dt * self.friction > 1:
            raise ValueError("Use Δt × atrito ≤ 1 para preservar a velocidade não negativa em Euler.")


@dataclass(slots=True)
class MotionTrajectory:
    positions: list[float]
    velocities: list[float]
    accelerations: list[float]
    stopping_time: float | None
    stopping_distance: float | None


@dataclass(slots=True)
class MotionExperiment:
    config: MotionConfig
    times: list[float]
    trajectories: dict[str, MotionTrajectory]
    reference: MotionTrajectory
    report: str


def _advance(x: float, v: float, h: float, command: float,
             friction: float, method: str) -> tuple[float, float]:
    """Euler/Heun/RK4 applied to (x',v')=(v,command-friction*v)."""
    a = command - friction * v
    z = h * friction
    if method == "Euler":
        return x + h * v, v + h * a
    if method == "Heun":
        return x + h*v + h*h*a/2, v + h*a*(1-z/2)
    return (x + h*v + h*h*a*(0.5-z/6+z*z/24),
            v + h*a*(1-z/2+z*z/6-z*z*z/24))


def _reference(config: MotionConfig, times: list[float]) -> MotionTrajectory:
    b, f, v0 = config.acceleration-config.deceleration, config.friction, config.velocity
    stop = None
    if v0 == 0 and b <= 0:
        stop = 0.0
    elif b < 0:
        stop = math.log1p(f*v0/-b)/f if f else v0/-b
    positions, velocities, accelerations = [], [], []
    stop_distance = None
    for t in times:
        s = min(t, stop) if stop is not None else t
        if f:
            z = f*s
            # Stable phi functions retain the constant-acceleration limit f→0.
            if abs(z) < 1e-4:
                phi1 = s*(1-z/2+z*z/6-z**3/24+z**4/120)
                phi2 = s*s*(0.5-z/6+z*z/24-z**3/120+z**4/720)
            else:
                phi1 = -math.expm1(-z)/f
                phi2 = (s-phi1)/f
            v = v0*math.exp(-z)+b*phi1
            displacement = v0*phi1+b*phi2
        else:
            v = v0+b*s
            displacement = v0*s+b*s*s/2
        stopped = stop is not None and t >= stop
        positions.append(config.position+displacement)
        velocities.append(0.0 if stopped else max(0.0, v))
        accelerations.append(0.0 if stopped else b-f*v)
        if stopped:
            stop_distance = displacement
    if stop is not None and stop > config.duration:
        stop = None
    return MotionTrajectory(positions, velocities, accelerations, stop, stop_distance)


def run_motion(config: MotionConfig, token: Cancellation | None = None) -> MotionExperiment:
    """Compare three integrators; do not allow numerical travel after braking.

    A zero crossing is located within its step by bisection of that method's
    partial-step formula. Position is advanced only to that event and then held.
    Each method therefore retains its own integration error instead of silently
    replacing its result with the analytic stopping distance.
    """
    if not isinstance(config, MotionConfig):
        raise TypeError("É necessária uma MotionConfig válida.")
    if token:
        token.check()
    steps = math.ceil(config.duration/config.dt)
    times = [min(i*config.dt, config.duration) for i in range(steps+1)]
    command = config.acceleration-config.deceleration
    trajectories = {}
    for method in METHODS:
        x, v = config.position, config.velocity
        stopped = v == 0 and command <= 0
        stopping_time = 0.0 if stopped else None
        stopping_distance = 0.0 if stopped else None
        xs, vs, accelerations = [x], [v], [0.0 if stopped else command-config.friction*v]
        for i in range(1, len(times)):
            if token and i % 256 == 0:
                token.check()
            h = times[i]-times[i-1]
            if not stopped:
                next_x, next_v = _advance(x, v, h, command, config.friction, method)
                if command < 0 and next_v <= 0:
                    low, high = 0.0, h
                    for _ in range(50):
                        middle = (low+high)/2
                        if _advance(x, v, middle, command, config.friction, method)[1] > 0:
                            low = middle
                        else:
                            high = middle
                    event_dt = (low+high)/2
                    next_x = _advance(x, v, event_dt, command, config.friction, method)[0]
                    next_v = 0.0
                    stopped = True
                    stopping_time = times[i-1]+event_dt
                    stopping_distance = next_x-config.position
                x, v = next_x, next_v
                if not math.isfinite(x) or not math.isfinite(v) or v < -1e-12:
                    raise ValueError("Integração AGV inválida; reduza o passo ou a escala dos parâmetros.")
            xs.append(x)
            vs.append(v)
            accelerations.append(0.0 if stopped else command-config.friction*v)
        trajectories[method] = MotionTrajectory(xs, vs, accelerations, stopping_time, stopping_distance)
    reference = _reference(config, times)
    lines = [
        "LABORATÓRIO AGV — dados inteiramente simulados.",
        "Modelo: dx/dt = v; dv/dt = a − b − c·v até à paragem.",
        "Unidades: posição m; velocidade m/s; a e b m/s²; c s⁻¹; tempo s.",
        "Hipóteses: movimento retilíneo para a frente; comandos constantes; atrito linear; piso ideal.",
        "A travagem mantém o veículo imóvel após v = 0; não se modela marcha-atrás nem controlo real.",
        f"Condições: x₀={config.position:g} m; v₀={config.velocity:g} m/s; a={config.acceleration:g} m/s²; b={config.deceleration:g} m/s²; c={config.friction:g} s⁻¹.",
        f"Duração={config.duration:g} s; Δt nominal={config.dt:g} s; {steps} intervalos; último intervalo ajustado à duração.",
        "Euler: ordem 1; Heun: ordem 2; RK4: ordem 4 para este sistema suave antes da paragem.",
        "O evento é localizado dentro do passo por bisseção; a distância fica congelada nesse instante.",
        "Referência independente: v=v₀+(a−b)t e x=x₀+v₀t+(a−b)t²/2 se c=0; solução exponencial se c>0.",
    ]
    if reference.stopping_time is not None:
        lines.append(f"Referência analítica: paragem em {reference.stopping_time:.10g} s; distância {reference.stopping_distance:.10g} m.")
    else:
        lines.append("A referência não atinge uma paragem finita dentro da duração escolhida.")
    for method, trajectory in trajectories.items():
        errors = [abs(x-y) for x, y in zip(trajectory.positions, reference.positions)]
        rmse = math.sqrt(math.fsum(e*e for e in errors)/len(errors))
        lines.append(f"{method}: erro máximo de posição={max(errors):.8g} m; RMSE={rmse:.8g} m.")
        if trajectory.stopping_time is not None:
            lines.append(f"  Paragem={trajectory.stopping_time:.10g} s; distância={trajectory.stopping_distance:.10g} m.")
    lines.append("Estes resultados verificam a discretização do modelo, não a segurança ou a travagem de um veículo físico.")
    if token:
        token.check()
    return MotionExperiment(config, times, trajectories, reference, "\n".join(lines))
