from ..core.processes import ProcessService
from ..core.monitoring import Monitor
from ..physics.thermal_model import ThermalModel
from ..physics.euler import simulate
from ..physics.integration import integrate
from ..simulation.experiments import ExperimentConfig, Experiment, run_experiment
from ..physics.gravity import GravityConfig, GravityExperiment, FreeFallResult, run_gravity, free_fall_euler
from ..physics.engine import ScientificPhysicsEngine
import psutil


class Manager:
    """Read/simulation API. Process mutations live in the separate ProcessService."""
    def __init__(self) -> None:
        self.scientific=ScientificPhysicsEngine()
        self.processes = ProcessService()
        self.monitor = Monitor()

    def list_processes(self) -> list[dict]:
        return self.processes.list_processes()

    def get_cpu_usage(self) -> list[float]:
        return psutil.cpu_percent(percpu=True)

    def get_memory_usage(self) -> dict:
        return dict(psutil.virtual_memory()._asdict())

    def get_hardware(self,refresh: bool = False):
        """Explicit cached inventory query; may wait for bounded OS probes."""
        from ..core.hardware import detect_hardware
        return detect_hardware(refresh=refresh)

    def simulate_temperature(self, initial_temperature: float = 40, ambient_temperature: float = 22,
                             power: float = 45, duration: float = 120, dt: float = .1,
                             capacity: float = 100, dissipation: float = 2):
        return simulate(ThermalModel(ambient_temperature,capacity,dissipation),
                        initial_temperature,lambda t: power,duration,dt)

    def calculate_energy(self, times, powers, method: str = "trapezoid") -> float:
        """Energy in joules. Wh = joules / 3600."""
        return integrate(times,powers,method)

    def run_experiment(self, config: ExperimentConfig) -> Experiment:
        """Reproducible experiment, independent of the desktop UI."""
        return run_experiment(config)

    def simulate_gravity(self, config: GravityConfig | None = None) -> GravityExperiment:
        """Synthetic central-force orbits with three numerical integrators."""
        return run_gravity(config or GravityConfig())

    def simulate_free_fall(self, height: float = 100, initial_velocity: float = 0,
                           gravity: float = 9.80665, duration: float = 4, dt: float = .01) -> FreeFallResult:
        """Euler and analytic reference for uniform g, SI units, no ground impact."""
        return free_fall_euler(height=height,initial_velocity=initial_velocity,
                               gravity=gravity,duration=duration,dt=dt)
