"""Physics Lab 6: numerical stability, conservation and GUI regression tests."""
import math
import os
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from expecto_process_manager.physics.physical_lab6 import (
    HeatSlab, solve_heat, heat_convergence, heat_sensitivity, FanControl,
    simulate_fan_control, fan_comparison,
)


def test_heat_reference_and_dirichlet_boundaries():
    model = HeatSlab()
    assert model.exact(0, 1) == pytest.approx(model.ambient_c)
    assert model.exact(model.length_m, 1) == pytest.approx(model.ambient_c)
    assert model.exact(model.length_m/2, 0) == pytest.approx(model.initial_c)
    result = solve_heat(model)
    assert result.fourier <= .5
    assert result.rmse_c < .2
    assert result.profiles_c[-1][0] == pytest.approx(model.ambient_c)
    assert result.profiles_c[-1][-1] == pytest.approx(model.ambient_c)
    assert result.profiles_c[-1][model.nodes//2] < model.initial_c


def test_heat_exact_against_fixed_space_convergence():
    model = HeatSlab(nodes=21)
    loose = solve_heat(model, dt_s=.8*model.stable_dt)
    tighter = solve_heat(model, dt_s=.1*model.stable_dt)
    assert tighter.max_error_c < loose.max_error_c
    assert tighter.rmse_c < loose.rmse_c


def test_discrete_energy_is_conserved_to_roundoff():
    model = HeatSlab(nodes=31)
    result = solve_heat(model, duration_s=2)
    assert result.energy_initial_j > result.energy_final_j > 0
    assert result.boundary_energy_j > 0
    assert abs(result.balance_error_j) < 1e-7


@pytest.mark.parametrize("factor", [1.01, 1.2, 2.0])
def test_unstable_fourier_number_is_rejected(factor):
    model = HeatSlab()
    with pytest.raises(ValueError, match="instável"):
        solve_heat(model, dt_s=factor*model.stable_dt)


def test_budget_prevents_unbounded_allocations():
    with pytest.raises(ValueError, match="Orçamento"):
        solve_heat(HeatSlab(nodes=401), duration_s=1000)


@pytest.mark.parametrize("changes", [
    {"nodes": 4}, {"nodes": 402}, {"nodes": 15.2}, {"diffusivity_m2_s":0},
    {"diffusivity_m2_s":float("nan")}, {"ambient_c":-274}, {"length_m":0},
])
def test_invalid_heat_domains_rejected(changes):
    with pytest.raises(ValueError):
        HeatSlab(**changes)


def test_convergence_and_sensitivity_have_reproducible_units():
    rows = heat_convergence()
    assert len(rows) == 4
    assert [r["actual_fourier"] for r in rows] == sorted(
        [r["actual_fourier"] for r in rows], reverse=True
    )
    assert all(r["rmse_c"] >= 0 and abs(r["balance_residual_j"]) < 1e-6 for r in rows)
    vals = heat_sensitivity()
    assert len(vals) == 3
    assert vals[0]["diffusivity_m2_s"] < vals[-1]["diffusivity_m2_s"]
    assert vals[0]["center_temperature_c"] > vals[-1]["center_temperature_c"]


def test_bounded_fan_control_and_reproducibility():
    pair = fan_comparison()
    assert pair == fan_comparison()
    for result in pair.values():
        assert len(result.times_s) == len(result.die_c) == len(result.fan_fraction)
        assert all(0 <= value <= 1 for value in result.fan_fraction)
        assert result.origin == "SIMULATED"
        assert math.isfinite(result.max_die_c)


def test_fixed_and_adaptive_fans_differ_without_hardware_access(monkeypatch):
    import os
    monkeypatch.setattr(os,"system",lambda *a,**k: (_ for _ in ()).throw(
        AssertionError("Não executar comandos do SO.")))
    fixed = simulate_fan_control(adaptive=False)
    adaptive = simulate_fan_control(adaptive=True)
    assert fixed.fan_fraction != adaptive.fan_fraction
    assert adaptive.max_die_c > 0
    assert abs(fixed.last_die_c-adaptive.last_die_c) > 1e-5


@pytest.mark.parametrize("changes", [
    {"fan_time_s":0}, {"thermal_power_w":-1},
    {"target_c":-274}, {"proportional":-1}, {"max_integral":0},
])
def test_invalid_fan_controller_rejected(changes):
    with pytest.raises(ValueError):
        FanControl(**changes)


def test_main_window_lazy_physics_lab6(tmp_path):
    from PySide6.QtWidgets import QApplication
    from expecto_process_manager.interface.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings_path=tmp_path/"settings.ini",report_directory=tmp_path/"reports")
    try:
        assert 15 not in window.laboratory.created
        page = window.laboratory.ensure(15)
        assert page.mode.count() == 4
        assert "SIMULATED" in page.note.text()
        assert page.result is None
    finally:
        window.close()
        import time
        deadline = time.monotonic() + 15
        while not window.closed_ready and time.monotonic()<deadline:
            app.processEvents()
            time.sleep(.01)
        assert window.closed_ready


def test_page_heat_executes_offscreen():
    from PySide6.QtWidgets import QApplication
    from expecto_process_manager.interface.physical_lab6_page import PhysicalLab6Page
    app = QApplication.instance() or QApplication([])
    page = PhysicalLab6Page()
    try:
        page.execute()
        import time
        deadline=time.monotonic()+15
        while page.result is None and time.monotonic()<deadline:
            app.processEvents()
            time.sleep(.01)
        assert page.result is not None
        assert page.result["origin"] == "SIMULATED"
        assert "Resíduo discreto" in page.report.toPlainText()
    finally:
        page.close()
        page.deleteLater()
