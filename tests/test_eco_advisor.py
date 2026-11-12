"""Regression tests for the energy-aware, non-mutating ECO advisor."""
import os
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from expecto_process_manager.optimization.eco import compare_policies, synthetic_policy_runs
from expecto_process_manager.optimization.advisor import energy_advice
from expecto_process_manager.core.cancellation import Cancellation


def test_lowest_energy_can_be_too_slow_to_recommend():
    comparison = compare_policies(synthetic_policy_runs())
    assert comparison.recommendation == "ULTRA ECO"
    advice = energy_advice(comparison)
    assert advice.status == "KEEP_NORMAL"
    assert advice.candidate is None
    assert "Manter NORMAL" in advice.report
    assert "SOMENTE LEITURA" in advice.report


def test_relaxed_slowdown_accepts_ultra_eco_in_simulation():
    advice = energy_advice(compare_policies(synthetic_policy_runs()), max_slowdown_percent=100)
    assert advice.status == "CANDIDATE"
    assert advice.candidate == "ULTRA ECO"
    assert advice.saved_j == pytest.approx(100)
    assert advice.saved_wh == pytest.approx(100 / 3600)
    assert advice.savings_percent == pytest.approx(100 / 6)
    assert advice.slowdown_percent == pytest.approx(100)
    assert "cenário simulado" in advice.report
    assert "não constitui autorização" in advice.report


def test_minimum_savings_prevents_noise_sized_recommendations():
    runs = synthetic_policy_runs()
    runs[2] = replace(runs[2], powers=[59.5] * 3, times=[0, 5, 10])
    comparison = compare_policies(runs)
    assert energy_advice(comparison, min_savings_percent=2).status == "KEEP_NORMAL"
    assert energy_advice(comparison, min_savings_percent=.5).candidate == "ULTRA ECO"


def test_infeasible_baseline_does_not_claim_energy_savings():
    comparison = compare_policies(synthetic_policy_runs(), max_temperature=65)
    advice = energy_advice(comparison)
    assert advice.status == "INSUFFICIENT_DATA"
    assert advice.candidate is None
    assert "NORMAL não está disponível" in advice.report


def test_missing_normal_baseline_means_no_comparison():
    comparison = compare_policies(synthetic_policy_runs()[1:])
    advice = energy_advice(comparison)
    assert advice.status == "INSUFFICIENT_DATA"
    assert advice.saved_j is None


def test_incomparable_task_is_inconclusive():
    runs = synthetic_policy_runs()
    runs[1] = replace(runs[1], work_completed=False)
    advice = energy_advice(compare_policies(runs))
    assert advice.status == "INSUFFICIENT_DATA"
    assert not advice.candidate


def test_reference_zero_energy_is_inconclusive_not_division_by_zero():
    runs = synthetic_policy_runs()
    runs[0] = replace(runs[0], powers=[0, 0, 0])
    advice = energy_advice(compare_policies(runs))
    assert advice.status == "INSUFFICIENT_DATA"
    assert advice.savings_percent is None


def test_measured_label_is_not_certification():
    runs = [replace(run, provenance="MEASURED") for run in synthetic_policy_runs()]
    advice = energy_advice(compare_policies(runs), max_slowdown_percent=100)
    assert advice.candidate == "ULTRA ECO"
    assert "declarados como medidos" in advice.report
    assert "não prova calibração" in advice.report


@pytest.mark.parametrize("value", [-1, 101, float("nan"), float("inf"), True, None, "10"])
def test_invalid_minimum_savings_rejected(value):
    with pytest.raises(ValueError, match="Poupança mínima"):
        energy_advice(compare_policies(synthetic_policy_runs()), min_savings_percent=value)


@pytest.mark.parametrize("value", [-1, 1001, float("nan"), float("inf"), False, None, "25"])
def test_invalid_slowdown_rejected(value):
    with pytest.raises(ValueError, match="Atraso máximo"):
        energy_advice(compare_policies(synthetic_policy_runs()), max_slowdown_percent=value)


def test_advisor_does_not_invoke_shell(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("O parecer não pode executar comandos no sistema.")
    monkeypatch.setattr(os, "system", forbidden)
    advice = energy_advice(compare_policies(synthetic_policy_runs()), max_slowdown_percent=100)
    assert advice.status == "CANDIDATE"


def test_eco_page_displays_advice_without_changing_os():
    from PySide6.QtWidgets import QApplication
    from expecto_process_manager.interface.eco_page import EcoPage, _calculate

    app = QApplication.instance() or QApplication([])
    page = EcoPage()
    try:
        assert page.minimum_savings.value() == 5
        assert page.maximum_slowdown.value() == 25
        comparison, preview, advice = _calculate(
            synthetic_policy_runs(), page.config(), Cancellation(), page.advisory_limits()
        )
        assert comparison.recommendation == "NORMAL"
        assert advice.status == "KEEP_NORMAL"
        assert "PARECER ENERGÉTICO" in comparison.report
        page.display((comparison, preview, advice))
        assert "Manter NORMAL" in page.advice_note.text()

        page.maximum_slowdown.setValue(100)
        page.limit_duration.setChecked(False)
        comparison2, preview2, advice2 = _calculate(
            synthetic_policy_runs(), page.config(), Cancellation(), page.advisory_limits()
        )
        assert advice2.candidate == "ULTRA ECO"
        page.display((comparison2, preview2, advice2))
        assert "ULTRA ECO" in page.advice_note.text()
        assert "não uma poupança real comprovada" in page.advice_note.text()
    finally:
        page.close()
        page.deleteLater()
