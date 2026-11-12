"""Physics Lab 6.2: physically bounded, conservative 2-D diffusion tests."""
from dataclasses import replace
import math
import os

os.environ.setdefault("QT_QPA_PLATFORM","offscreen")

import pytest
from expecto_process_manager.physics.heat_2d import (
    HeatPlate2D, solve_heat_2d, heat_2d_grid_study,
)


def test_conservative_energy_with_heterogeneous_materials_and_source():
    model=HeatPlate2D()
    result=solve_heat_2d(model,duration_s=2)
    assert result.origin=="SIMULATED"
    assert len(result.frames_c[0])==model.ny
    assert len(result.frames_c[0][0])==model.nx
    assert result.heat_input_j==pytest.approx(model.source_w*2,abs=1e-9)
    assert result.final_j-result.initial_j == pytest.approx(
        result.heat_input_j-result.boundary_loss_j,abs=1e-7
    )
    assert abs(result.balance_residual_j)<1e-7
    assert result.dt_s < result.conservative_limit_s
    assert len(result.times_s)<=26


@pytest.mark.parametrize("boundary",["insulated","convection","dirichlet"])
def test_all_boundary_conditions_have_conservative_flux(boundary):
    model=HeatPlate2D(boundary=boundary,source_w=3)
    result=solve_heat_2d(model,duration_s=2)
    assert abs(result.balance_residual_j)<1e-7
    if boundary=="insulated":
        assert result.boundary_loss_j==pytest.approx(0)
        assert result.final_j-result.initial_j==pytest.approx(6,abs=1e-7)
    else:
        assert result.boundary_loss_j > 0


def test_insulated_plate_with_no_source_preserves_energy():
    model=HeatPlate2D(boundary="insulated",source_w=0)
    result=solve_heat_2d(model,duration_s=3)
    assert result.heat_input_j==0
    assert result.boundary_loss_j==0
    assert result.final_j==pytest.approx(result.initial_j,abs=1e-7)


def test_uniform_material_with_dirichlet_has_analytic_reference():
    model=HeatPlate2D(nx=21,ny=21,inclusion=False,source_w=0,boundary="dirichlet")
    result=solve_heat_2d(model,duration_s=2)
    assert result.rmse_exact_c is not None
    assert result.rmse_exact_c < 1.0
    assert result.max_c <= model.initial_peak_c + 1e-8
    assert result.min_c >= model.ambient_c - 1e-8


def test_grid_refinement_reduces_continuum_error():
    rows=heat_2d_grid_study(duration_s=1)
    assert [r["nx"] for r in rows]==[9,13,17,25]
    assert rows[-1]["rmse_c"] < rows[0]["rmse_c"]
    assert all(abs(r["energy_balance_j"]) < 1e-7 for r in rows)


def test_material_changes_transient_field():
    baseline=HeatPlate2D(inclusion=True,inclusion_k_w_m_k=18)
    modified=replace(baseline,inclusion_k_w_m_k=180)
    x=solve_heat_2d(baseline,duration_s=2)
    y=solve_heat_2d(modified,duration_s=2)
    center=baseline.ny//2
    assert abs(x.frames_c[-1][center][baseline.nx//2] -
               y.frames_c[-1][center][modified.nx//2]) > 1e-5


def test_ambient_bounds_and_invalid_materials_are_rejected():
    for props in (
        {"nx":6},{"ny":82},{"nx":True},{"source_w":-1},
        {"matrix_k_w_m_k":0},{"matrix_k_w_m_k":float("nan")},
        {"inclusion_volumetric_capacity_j_m3_k":0},
        {"ambient_c":-274},{"boundary":"periodic"},{"inclusion":0},
        {"initial_peak_c":20},
    ):
        with pytest.raises(ValueError):
            HeatPlate2D(**props)


def test_large_timestep_rejected_before_computing():
    model=HeatPlate2D()
    from expecto_process_manager.physics.heat_2d import _network
    limit=_network(model)[-1]
    with pytest.raises(ValueError, match="limite"):
        solve_heat_2d(model,dt_s=limit*1.1)


def test_large_computation_rejected():
    model=HeatPlate2D(nx=81,ny=81)
    with pytest.raises(ValueError,match="Orçamento"):
        solve_heat_2d(model,duration_s=1000)


def test_exact_only_for_valid_reference_case():
    model=HeatPlate2D()
    with pytest.raises(ValueError,match="Referência analítica"):
        model.exact(0.05,0.04,1)


def test_cancellation():
    from expecto_process_manager.core.cancellation import Cancellation,Cancelled
    token=Cancellation()
    token.cancel()
    with pytest.raises(Cancelled):
        solve_heat_2d(duration_s=2,token=token)


def test_lab2d_lazy_navigation_and_heatmap(tmp_path):
    from PySide6.QtWidgets import QApplication
    from expecto_process_manager.interface.main_window import MainWindow

    app=QApplication.instance() or QApplication([])
    window=MainWindow(settings_path=tmp_path/"settings.ini",report_directory=tmp_path/"reports")
    try:
        assert 16 not in window.laboratory.created
        assert window.laboratory.search("calor 2d")
        assert window.laboratory.currentIndex()==16
        page=window.laboratory.ensure(16)
        assert page.result is None
        assert page.boundary.count()==3
        assert page.inclusion.isChecked()
        model,duration=page.parameters()
        assert model.nx==25
        assert duration==6
        frame=((24.0,25.0),(26.0,27.0))
        page.heatmap.update_frame(frame,24,27)
        assert page.heatmap._image.width()==2
        assert page.heatmap._image.height()==2
    finally:
        window.close()
        import time
        deadline=time.monotonic()+15
        while not window.closed_ready and time.monotonic()<deadline:
            app.processEvents()
            time.sleep(.01)
        assert window.closed_ready


def test_gui_runs_and_switches_frames():
    from PySide6.QtWidgets import QApplication
    from expecto_process_manager.interface.thermal2d_page import Thermal2DPage
    import time

    app=QApplication.instance() or QApplication([])
    page=Thermal2DPage()
    try:
        page.nx.setText("11")
        page.ny.setText("11")
        page.duration.setText("1")
        page.execute()
        limit=time.monotonic()+15
        while page.result is None and time.monotonic()<limit:
            app.processEvents()
            time.sleep(.01)
        assert page.result is not None
        assert page.result.origin=="SIMULATED"
        assert page.frame_slider.maximum()>0
        page.frame_slider.setValue(0)
        assert "t=0.000" in page.frame_label.text()
        page.frame_slider.setValue(page.frame_slider.maximum())
        assert "Resíduo conservativo" in page.report.toPlainText()
    finally:
        page.close()
        page.deleteLater()
