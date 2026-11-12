"""Reproducible validation for the two new physical models (SIMULATED)."""
import math
import pytest

from expecto_process_manager.physics.coupled_models import TwoNodeThermal, BatteryThermalRC
from expecto_process_manager.physics.numerical.ode import solve_ivp
from expecto_process_manager.simulation.hardware_experiments import (
    HardwareConfig, run_hardware, export_hardware, SPECS, STATE_UNITS
)


def test_thermal_equilibrium_and_flux_are_consistent():
    model = TwoNodeThermal()
    a, b = model.equilibrium
    assert a > b > model.ambient
    assert model.rhs(0., (a, b)) == pytest.approx((0., 0.), abs=1e-12)
    obs = model.observables((a, b))
    assert obs["interface_w"] == pytest.approx(70)
    assert obs["cooling_w"] == pytest.approx(70)


@pytest.mark.parametrize("t", [0, 2, 10, 50, 240])
def test_two_node_closed_form_matches_numerical_independent_reference(t):
    model = TwoNodeThermal()
    exact = model.exact(t, (30., 26.))
    if t == 0:
        assert exact == pytest.approx((30, 26), abs=1e-11)
    else:
        result = solve_ivp(model.rhs, (30., 26.), (0, t), .05, "rk4")
        assert result.values[-1] == pytest.approx(exact, abs=1e-7)


def test_heat_balance_matches_external_power_minus_sink_cooling():
    model = TwoNodeThermal()
    y = (58., 37.)
    d = model.rhs(0, y)
    o = model.observables(y)
    stored_rate = model.die_capacity * d[0] + model.sink_capacity * d[1]
    assert stored_rate == pytest.approx(o["input_w"] - o["cooling_w"])
    assert "interface_w" in o
    assert abs(stored_rate) < 1e6


def test_battery_rc_analytical_voltage_and_coulomb_balance():
    model = BatteryThermalRC()
    init = (.85, 0., 25.)
    result = solve_ivp(model.rhs, init, (0, 120), .1, "rk4")
    end = result.values[-1]
    obs = model.observables(end)
    assert end[0] == pytest.approx(.85 - 240 / (4 * 3600), abs=1e-12)
    assert obs["terminal_voltage_v"] == pytest.approx(model.exact(120, init), abs=1e-9)


def test_battery_electro_thermal_energy_conservation():
    model = BatteryThermalRC()
    y = (.85, .03, 30.)
    ds, du, dt = model.rhs(0, y)
    o = model.observables(y)
    stored_rate = (
        model.capacity_coulombs * model.ocv(y[0]) * ds
        + model.polarization_capacitance * y[1] * du
        + model.thermal_capacity * dt
    )
    assert stored_rate == pytest.approx(-o["load_w"] - o["cooling_w"], abs=1e-10)


def test_battery_voltage_drops_under_load():
    model = BatteryThermalRC()
    a = model.exact(0)
    b = model.exact(120)
    assert b < a
    assert 0 < b < model.voltage_full


@pytest.mark.parametrize("bad", [
    dict(capacity_ah=0), dict(internal_resistance=-1), dict(ambient=-274),
    dict(voltage_full=9), dict(polarization_capacitance=0),
])
def test_invalid_battery_parameters_rejected(bad):
    with pytest.raises(ValueError):
        BatteryThermalRC(**bad)


@pytest.mark.parametrize("bad", [
    dict(die_capacity=0), dict(sink_capacity=-2),
    dict(ambient_conductance=0), dict(interface_conductance=0),
    dict(ambient=-274),
])
def test_invalid_cpu_sink_parameters_rejected(bad):
    with pytest.raises(ValueError):
        TwoNodeThermal(**bad)


@pytest.mark.parametrize("key,initial_unit", [
    ("thermal_two_node", "°C"),
    ("battery_rc", "1"),
])
def test_models_registered_for_lab_ui(key,initial_unit):
    assert key in SPECS
    assert STATE_UNITS[key][0] == initial_unit


@pytest.mark.parametrize("key,limit", [
    ("thermal_two_node", 1e-4),
    ("battery_rc", 1e-4),
])
def test_full_experiment_has_analytic_comparison_and_balance(key, limit):
    result = run_hardware(HardwareConfig(key))
    assert result.metadata["origin"] == "SIMULATED"
    assert result.metadata["model_version"] == "5.1.0"
    assert result.reference is not None
    assert result.errors["rk4"]["maximum"] < limit
    assert math.isfinite(result.balances["rk4"])
    assert abs(result.balances["rk4"]) < 1.0
    assert all(name in result.observables for name in ("euler", "heun", "rk4"))


def test_battery_will_not_over_discharge():
    config = HardwareConfig("battery_rc", initial=(.001, 0., 25.), duration=120)
    with pytest.raises(ValueError, match="SOC=0"):
        run_hardware(config)


def test_battery_rejects_unphysical_initial_soc():
    with pytest.raises(ValueError, match="SOC inicial"):
        run_hardware(HardwareConfig("battery_rc", initial=(1.2, 0., 25.)))


def test_export_keeps_origin_and_reproducible_si_metadata(tmp_path):
    result = run_hardware(HardwareConfig("battery_rc", duration=2, dt=.1))
    target = export_hardware(result, tmp_path)
    assert target.exists()
    import json
    payload = json.loads((tmp_path / "battery_rc.json").read_text(encoding="utf-8"))
    assert payload["metadata"]["origin"] == "SIMULATED"
    assert payload["metadata"]["primary_unit"] == "V"
    assert "loss_joule_w" in payload["metadata"]["observable_units"]
    assert (tmp_path / "battery_rc.csv").exists()
