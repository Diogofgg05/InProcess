"""Regression tests for thermal twin 7.0: provenance and temporal holdout."""
import csv
import math
import os
from dataclasses import replace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM","offscreen")

from expecto_process_manager.physics.digital_twin7 import (
    ThermalSample,ThermalSeries,load_thermal_csv,synthetic_thermal_series,
    calibrate_twin,forecast_scenario,
)


def test_synthetic_parameters_are_identified_to_reasonable_precision():
    series=synthetic_thermal_series()
    report=calibrate_twin(series)
    assert report.origin=="SIMULATED"
    assert report.train_points>report.validation_points
    assert report.model.tau_s==pytest.approx(36,rel=.10)
    assert report.model.resistance_k_w==pytest.approx(.58,rel=.10)
    assert report.model.capacity_j_k>0
    assert report.validation.rmse_c < 2
    assert report.validation.mae_c>0
    assert report.validation.points==len(report.validation_times_s)-1
    assert "sem usar temperaturas futuras" in " ".join(report.interpretation)


def test_training_values_never_use_holdout_target_temperatures():
    series=synthetic_thermal_series()
    report=calibrate_twin(series)
    cutoff=report.train_points
    modified=list(series.samples)
    for i in range(cutoff,len(modified)):
        modified[i]=replace(modified[i],cpu_temp_c=modified[i].cpu_temp_c+5)
    another=calibrate_twin(ThermalSeries(tuple(modified),"SIMULATED"))
    assert another.model==report.model
    assert another.validation.rmse_c != report.validation.rmse_c


def test_explicit_origin_preserved_when_loading_csv(tmp_path):
    series=synthetic_thermal_series(30)
    path=tmp_path/"sample.csv"
    with path.open("w",encoding="utf-8",newline="") as f:
        writer=csv.writer(f)
        writer.writerow(["time_s","cpu_temp_c","ambient_c","power_w"])
        for row in series.samples:
            writer.writerow([row.time_s,row.cpu_temp_c,row.ambient_c,row.power_w])
    loaded=load_thermal_csv(path)
    assert loaded.origin=="MEASURED_UNVERIFIED"
    assert len(loaded.samples)==30
    assert calibrate_twin(loaded).origin=="MEASURED_UNVERIFIED"


def test_omitted_or_mislabelled_csv_columns_are_rejected(tmp_path):
    path=tmp_path/"bad.csv"
    path.write_text("time_s,cpu_percent,ambient_c,power_w\n1,90,24,50\n",encoding="utf-8")
    with pytest.raises(ValueError,match="Cabeçalho"):
        load_thermal_csv(path)


def test_training_requires_excitation_and_identifiability():
    data=[ThermalSample(i,35,24,0) for i in range(40)]
    with pytest.raises(ValueError,match="identificáveis"):
        calibrate_twin(ThermalSeries(tuple(data),"SIMULATED"))


@pytest.mark.parametrize("bad",[
    [ThermalSample(i,35,24,50) for i in range(10)],
    [ThermalSample(i,35,24,-1) for i in range(40)],
    [ThermalSample(i,35,24,50) for i in [0]*40],
    [ThermalSample(i,math.nan,24,50) for i in range(40)],
])
def test_series_rejects_invalid_physical_or_temporal_inputs(bad):
    with pytest.raises(ValueError):
        ThermalSeries(tuple(bad),"SIMULATED")


def test_irregular_sampling_is_rejected():
    data=[ThermalSample(float(i),35,24,50) for i in range(40)]
    data[20]=replace(data[20],time_s=20.1)
    with pytest.raises(ValueError,match="uniforme"):
        ThermalSeries(tuple(data),"SIMULATED")


@pytest.mark.parametrize("fraction",[0.2,0.95,float("nan"),True,None])
def test_invalid_holdout_fraction_rejected(fraction):
    with pytest.raises(ValueError):
        calibrate_twin(synthetic_thermal_series(),train_fraction=fraction)


def test_future_is_bounded_to_training_domain():
    series=synthetic_thermal_series()
    report=calibrate_twin(series)
    times,values=forecast_scenario(series,report,power_w=60,ambient_c=24,horizon_s=60)
    assert times[-1]==pytest.approx(series.samples[-1].time_s+60)
    assert all(math.isfinite(v) for v in values)
    with pytest.raises(ValueError,match="Extrapolação"):
        forecast_scenario(series,report,power_w=10000,ambient_c=24)
    with pytest.raises(ValueError,match="Extrapolação"):
        forecast_scenario(series,report,power_w=60,ambient_c=100)


def test_metrics_include_baseline_and_do_not_claim_certified_intervals():
    result=calibrate_twin(synthetic_thermal_series())
    assert result.validation.persistence_rmse_c>=0
    assert result.validation.observed_abs_error_p90_c>=0
    assert "NÃO representa intervalo de confiança" in " ".join(result.interpretation)


def test_cancelled_identification_does_not_continue():
    from expecto_process_manager.core.cancellation import Cancellation,Cancelled
    c=Cancellation()
    c.cancel()
    with pytest.raises(Cancelled):
        calibrate_twin(synthetic_thermal_series(),token=c)


def test_gui_lazy_integration_works_offscreen(tmp_path):
    from PySide6.QtWidgets import QApplication
    from expecto_process_manager.interface.main_window import MainWindow
    import time
    app=QApplication.instance() or QApplication([])
    win=MainWindow(settings_path=tmp_path/"settings.ini",report_directory=tmp_path/"reports")
    try:
        assert 18 not in win.laboratory.created
        assert win.laboratory.search("gemeo digital")
        assert win.laboratory.currentIndex()==18
        page=win.laboratory.ensure(18)
        page.execute()
        limit=time.monotonic()+15
        while page.analysis is None and time.monotonic()<limit:
            app.processEvents()
            time.sleep(.01)
        assert page.analysis is not None,page.note.text()
        assert page.analysis.origin=="SIMULATED"
        assert "RMSE persistência" in page.report.toPlainText()
    finally:
        win.close()
        limit=time.monotonic()+15
        while not win.closed_ready and time.monotonic()<limit:
            app.processEvents()
            time.sleep(.01)
        assert win.closed_ready
