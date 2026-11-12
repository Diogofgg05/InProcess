"""Physics Lab 6.1: implicit and Crank-Nicolson solvers for 1-D heat.

Linear, homogeneous conduction with prescribed, constant-temperature ends.
Methods use a banded O(n) tridiagonal solve (no dense matrices or new
runtime dependencies). Results are SIMULATED, not hardware measurements.

Crank-Nicolson is A-stable but is NOT positivity preserving for arbitrary
Fourier numbers. Backward Euler is L-stable. Explicit Euler requires Fo<=1/2.
"""
from dataclasses import dataclass
import math

from .physical_lab6 import HeatSlab, HeatResult, solve_heat


METHODS = ("explicit", "backward_euler", "crank_nicolson")
THETA = {"backward_euler": 1.0, "crank_nicolson": 0.5}


def _tridiagonal_solver(size: int, diagonal: float, off_diagonal: float):
    """Return reusable Thomas factors for an SPD diffusion matrix."""
    cprime = [0.0] * size
    pivots = [0.0] * size
    pivots[0] = diagonal
    for i in range(size - 1):
        cprime[i] = off_diagonal / pivots[i]
        pivots[i + 1] = diagonal - off_diagonal * cprime[i]
    if not all(math.isfinite(x) and x > 0 for x in pivots):
        raise ValueError("Matriz tridiagonal não admissível.")
    return cprime, pivots


def _solve_factors(rhs, cprime, pivots, off_diagonal):
    n = len(rhs)
    d = [0.0] * n
    d[0] = rhs[0] / pivots[0]
    for i in range(1, n):
        d[i] = (rhs[i] - off_diagonal * d[i - 1]) / pivots[i]
    solution = [0.0] * n
    solution[-1] = d[-1]
    for i in range(n - 2, -1, -1):
        solution[i] = d[i] - cprime[i] * solution[i + 1]
    return solution


def solve_heat_61(model: HeatSlab | None = None, *, duration_s: float = 4.0,
                  dt_s: float | None = None, method: str = "crank_nicolson",
                  token=None) -> HeatResult:
    """Euler explicit, backward Euler, or theta=1/2 Crank-Nicolson.

    Constant Dirichlet boundary values are removed as temperature deviations.
    Discrete energy uses the same theta-weighted boundary flux as the scheme
    and is conserved to rounding accuracy (not proof of physical calibration).
    """
    model = model if model is not None else HeatSlab()
    if method not in METHODS:
        raise ValueError("Método numérico desconhecido.")
    if method == "explicit":
        return solve_heat(model, duration_s=duration_s, dt_s=dt_s, token=token)

    if (not isinstance(duration_s, (int, float)) or isinstance(duration_s, bool)
            or not math.isfinite(duration_s) or duration_s <= 0):
        raise ValueError("Duração positiva e finita obrigatória.")
    step = model.stable_dt * 2 if dt_s is None else dt_s
    if (not isinstance(step, (int, float)) or isinstance(step, bool)
            or not math.isfinite(step) or step <= 0):
        raise ValueError("Passo temporal positivo e finito obrigatório.")
    count = math.ceil(duration_s / step)
    if count > 60000 or count * model.nodes > 1_500_000:
        raise ValueError("Orçamento numérico excedido; reduza passos ou nós.")

    h = duration_s / count
    fo = model.diffusivity_m2_s * h / model.dx ** 2
    theta = THETA[method]
    interior = model.nodes - 2
    off_diag = -theta * fo
    cprime, pivots = _tridiagonal_solver(interior, 1 + 2 * theta * fo, off_diag)
    original_x = tuple(i * model.dx for i in range(model.nodes))
    state = [model.exact(x, 0.0) - model.ambient_c for x in original_x[1:-1]]
    origin = state[:]
    times = [0.0]
    profile0 = (model.ambient_c, *(u + model.ambient_c for u in state), model.ambient_c)
    profiles = [profile0]
    error_sq = 0.0
    err_max = 0.0
    samples = 0
    boundary_energy = 0.0
    k_area_dx = model.conductivity_w_m_k * model.area_m2 / model.dx
    c_vol = model.volumetric_capacity * model.area_m2 * model.dx
    stride = max(1, math.ceil(count / 200))

    for index in range(1, count + 1):
        if token is not None and index % 64 == 0:
            token.check()
        previous_flux = k_area_dx * (state[0] + state[-1])
        old = [0.0] + state + [0.0]
        rhs = [
            (1 - 2 * (1-theta) * fo) * old[i]
            + (1-theta) * fo * (old[i-1] + old[i+1])
            for i in range(1, model.nodes - 1)
        ]
        state = _solve_factors(rhs, cprime, pivots, off_diag)
        if not all(math.isfinite(u) for u in state):
            raise ValueError("Solução numérica não finita.")
        current_flux = k_area_dx * (state[0] + state[-1])
        boundary_energy += h * ((1-theta)*previous_flux + theta*current_flux)
        if index == count or index % stride == 0:
            now = index*h
            profile = (model.ambient_c, *(u + model.ambient_c for u in state), model.ambient_c)
            times.append(now)
            profiles.append(profile)
            for xx, temp in zip(original_x, profile):
                error = abs(temp - model.exact(xx, now))
                error_sq += error * error
                err_max = max(err_max, error)
                samples += 1
    if token is not None:
        token.check()
    initial_e = c_vol * sum(origin)
    final_e = c_vol * sum(state)
    return HeatResult(
        original_x, tuple(times), tuple(profiles), err_max,
        math.sqrt(error_sq / samples), fo,
        initial_e, final_e, boundary_energy,
        final_e - initial_e + boundary_energy,
    )


def semidiscrete_exact_center(model: HeatSlab, time_s: float) -> float:
    """Exact center temperature of the finite-difference semi-discrete ODE.

    This isolates temporal truncation from spatial truncation for the
    sinusoidal initial condition; only odd node counts have a center node.
    """
    if model.nodes % 2 != 1:
        raise ValueError("Malha com número ímpar de nós obrigatória.")
    if not math.isfinite(time_s) or time_s < 0:
        raise ValueError("Tempo inválido.")
    eigenvalue = (-4.0 * model.diffusivity_m2_s / model.dx**2
                  * math.sin(math.pi/(2*(model.nodes-1)))**2)
    return (model.ambient_c +
            (model.initial_c-model.ambient_c)*math.exp(eigenvalue*time_s))


def temporal_order_study(model: HeatSlab | None = None, *,
                         duration_s: float = 4.0, method: str = "crank_nicolson",
                         token=None) -> list[dict]:
    """Observed global time order against the exact SEMI-DISCRETE solution.

    Uses 20, 40, 80 and 160 equal steps. This reference eliminates the
    spatial O(dx^2) floor, unlike comparisons to the continuous heat PDE.
    """
    model = model if model is not None else HeatSlab(nodes=21)
    if model.nodes % 2 != 1:
        raise ValueError("Use um número ímpar de nós para o estudo central.")
    reference = semidiscrete_exact_center(model, duration_s)
    rows = []
    for count in (20, 40, 80, 160):
        if token is not None:
            token.check()
        step = duration_s/count
        result = solve_heat_61(model, duration_s=duration_s,
                               dt_s=step, method=method, token=token)
        observed = result.profiles_c[-1][model.nodes//2]
        error = abs(observed-reference)
        order = None
        if rows and rows[-1]["error_c"] > 1e-13 and error > 1e-13:
            order = math.log2(rows[-1]["error_c"]/error)
        rows.append({
            "method": method, "steps": count, "dt_s": step,
            "fourier": result.fourier, "error_c": error,
            "observed_order": order,
            "energy_balance_j": result.balance_error_j,
        })
    return rows


def spatial_order_study(model: HeatSlab | None = None, *,
                        duration_s: float = 4.0, token=None) -> list[dict]:
    """Spatial O(dx^2) convergence of the semi-discrete exact eigenmode.

    Does not mix error from a time integrator into spatial order estimates.
    """
    model = model if model is not None else HeatSlab()
    rows = []
    for nodes in (11,21,41,81,161):
        if token is not None:
            token.check()
        from dataclasses import replace
        finer = replace(model, nodes=nodes)
        reference = finer.exact(finer.length_m/2, duration_s)
        sampled = semidiscrete_exact_center(finer, duration_s)
        error = abs(reference-sampled)
        order = (math.log2(rows[-1]["error_c"]/error)
                 if rows and rows[-1]["error_c"]>1e-14 and error>1e-14 else None)
        rows.append({"nodes": nodes, "dx_m": finer.dx,
                     "error_c": error, "observed_order": order})
    return rows
