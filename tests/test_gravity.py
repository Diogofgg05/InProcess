import math
from dataclasses import replace
import pytest

from expecto_process_manager.core.cancellation import Cancellation, Cancelled
from expecto_process_manager.physics.gravity import (
    G, METHODS, GravityConfig, run_gravity, free_fall_euler,
)


def test_circular_reference_and_initial_invariants():
    config = GravityConfig(duration=1000, dt=20)
    result = run_gravity(config)
    assert result.provenance == 'simulado'
    assert result.times[-1] == 1000
    assert result.reference_x[0] == config.radius
    assert result.reference_y[0] == 0
    omega = math.sqrt(G * config.central_mass / config.radius**3)
    assert result.reference_x[-1] == pytest.approx(config.radius * math.cos(omega * 1000))
    assert result.reference_y[-1] == pytest.approx(config.radius * math.sin(omega * 1000))
    for trajectory in result.trajectories.values():
        assert trajectory.energy[0] == pytest.approx(-G * config.central_mass * config.body_mass / (2*config.radius))
        assert trajectory.angular_momentum[0] == pytest.approx(config.body_mass * config.radius * config.circular_speed)
        assert len(trajectory.x) == len(result.times)
        assert trajectory.position_error[0] == 0


def test_convergence_first_and_second_order():
    result = run_gravity(GravityConfig(duration=1000, dt=20))
    assert [step for step, errors in result.convergence] == [20, 10, 5]
    coarse, medium, fine = [errors for step, errors in result.convergence]
    for method in METHODS[:2]:
        observed = math.log(medium[method]/fine[method], 2)
        assert .85 < observed < 1.15
    observed_verlet = math.log(medium[METHODS[2]]/fine[METHODS[2]], 2)
    assert 1.9 < observed_verlet < 2.1
    assert fine[METHODS[2]] < fine[METHODS[0]]


def test_symplectic_methods_preserve_angular_momentum():
    result = run_gravity(GravityConfig(duration=10000, dt=20))
    for method in METHODS[1:]:
        values = result.trajectories[method].angular_momentum
        assert max(abs(value-values[0])/abs(values[0]) for value in values) < 1e-12
    euler = result.trajectories[METHODS[0]].energy
    verlet = result.trajectories[METHODS[2]].energy
    assert max(abs(v-verlet[0]) for v in verlet) < max(abs(v-euler[0]) for v in euler)


def test_non_circular_case_never_claims_exact_position_reference():
    result = run_gravity(GravityConfig(velocity_factor=.8, duration=100, dt=2))
    assert result.reference_x is None and result.reference_y is None
    assert result.convergence == []
    assert all(t.position_error is None for t in result.trajectories.values())
    assert 'indisponível' in result.report


def test_endpoint_short_interval():
    result = run_gravity(GravityConfig(duration=11, dt=3))
    assert result.times == [0, 3, 6, 9, 11]


def test_duration_smaller_than_step_and_extreme_small_time():
    result = run_gravity(GravityConfig(duration=1e-300, dt=1e12))
    assert result.times == [0, 1e-300]
    assert all(len(trajectory.x)==2 for trajectory in result.trajectories.values())


def test_step_refinement_does_not_divide_by_underflowed_zero():
    result = run_gravity(GravityConfig(duration=5e-324, dt=5e-324))
    assert result.times[-1] == 5e-324
    assert len(result.convergence) == 1


@pytest.mark.parametrize('kwargs', [
    {'central_mass': 0}, {'body_mass': 0}, {'radius': 0}, {'radius': math.inf},
    {'dt': 0}, {'duration': -1}, {'dt': 1e-20}, {'velocity_factor': -1},
    {'velocity_factor': math.nan}, {'central_mass': 'invalid'}, {'duration': True},
])
def test_invalid_gravity_input(kwargs):
    with pytest.raises(ValueError):
        GravityConfig(**kwargs)


def test_central_singularity_cannot_be_crossed_silently():
    # Radial zero-speed fall; the point-mass singularity is not an Earth surface.
    with pytest.raises(ValueError, match='singularidade'):
        run_gravity(GravityConfig(velocity_factor=0, duration=5000, dt=10))


def test_cancelled_simulation():
    token = Cancellation()
    token.cancel()
    with pytest.raises(Cancelled):
        run_gravity(GravityConfig(), token)
    with pytest.raises(Cancelled):
        free_fall_euler(token=token)


def test_test_particle_mass_does_not_change_trajectory():
    config = GravityConfig(duration=100, dt=10)
    light = run_gravity(config)
    heavy = run_gravity(replace(config, body_mass=config.body_mass*2))
    for method in METHODS:
        assert heavy.trajectories[method].x == light.trajectories[method].x
        assert heavy.trajectories[method].energy[-1] == pytest.approx(2*light.trajectories[method].energy[-1])


def test_free_fall_against_independent_reference():
    coarse = free_fall_euler(height=100, duration=4, dt=.1)
    fine = free_fall_euler(height=100, duration=4, dt=.05)
    exact_height = 100-9.80665*4**2/2
    exact_velocity = -9.80665*4
    assert coarse.reference_heights[-1] == pytest.approx(exact_height)
    assert coarse.velocities[-1] == pytest.approx(exact_velocity)
    assert coarse.reference_velocities[-1] == pytest.approx(exact_velocity)
    # Explicit Euler position error is +g*T*h/2 for uniform steps.
    assert coarse.heights[-1]-exact_height == pytest.approx(9.80665*4*.1/2)
    assert (coarse.heights[-1]-exact_height)/(fine.heights[-1]-exact_height) == pytest.approx(2)


def test_free_fall_final_partial_step_and_zero_gravity():
    result = free_fall_euler(height=10, initial_velocity=2, gravity=0, duration=1, dt=.3)
    assert result.times == [0, .3, .6, .8999999999999999, 1]
    assert result.heights[-1] == pytest.approx(12)
    assert result.velocities[-1] == 2
