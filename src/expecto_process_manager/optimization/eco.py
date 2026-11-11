"""Compare task energy under NORMAL/ECO/ULTRA ECO without changing the OS."""
from collections.abc import Sequence
from dataclasses import dataclass
import math
from pathlib import Path

from ..core.cancellation import Cancellation
from ..core.energy import (integrate_power, load_power_csv, validate_times,
                           validate_powers, validate_temperatures)


POLICIES = ("NORMAL", "ECO", "ULTRA ECO")
PROVENANCES = ("SIMULATED", "MEASURED", "ESTIMATED")


@dataclass(frozen=True, slots=True)
class PolicyRun:
    policy: str
    times: Sequence[float]
    powers: Sequence[float] | None
    temperatures: Sequence[float] | None = None
    work_units: float = 1.0
    work_label: str = "tarefa"
    provenance: str = "SIMULATED"
    task_id: str = ""
    work_completed: bool = True
    temperature_provenance: str | None = None

    def __post_init__(self) -> None:
        name = str(self.policy).upper().replace("_", " ").strip()
        source = str(self.provenance).upper().strip()
        if name not in POLICIES:
            raise ValueError("Perfil energético inválido: use NORMAL, ECO ou ULTRA ECO.")
        if source not in PROVENANCES:
            raise ValueError("A potência deve ser identificada como SIMULATED, MEASURED ou ESTIMATED.")
        if self.temperature_provenance is not None and self.temperature_provenance not in PROVENANCES:
            raise ValueError("Proveniência de temperatura inválida.")
        if not isinstance(self.work_completed, bool):
            raise ValueError("A conclusão da tarefa deve ser declarada explicitamente como verdadeiro/falso.")
        if (not isinstance(self.work_units, (float, int)) or not math.isfinite(self.work_units)
                or self.work_units <= 0 or not isinstance(self.work_label, str) or not self.work_label.strip()):
            raise ValueError("O trabalho deve ser positivo, finito e ter uma unidade/descrição explícita.")
        if not isinstance(self.task_id, str):
            raise ValueError("A identificação da tarefa deve ser texto.")
        ts = validate_times(self.times)
        ps = validate_powers(ts, self.powers) if self.powers is not None else None
        temperatures = validate_temperatures(ts, self.temperatures) if self.temperatures is not None else None
        object.__setattr__(self, "policy", name)
        object.__setattr__(self, "provenance", source)
        object.__setattr__(self, "work_label", self.work_label.strip())
        object.__setattr__(self, "task_id", self.task_id.strip())
        object.__setattr__(self, "times", ts)
        object.__setattr__(self, "powers", ps)
        object.__setattr__(self, "temperatures", temperatures)


@dataclass(frozen=True, slots=True)
class PolicyMetrics:
    policy: str
    energy_j: float | None
    energy_wh: float | None
    duration: float
    max_temperature: float | None
    efficiency: float | None
    average_power: float | None
    peak_power: float | None
    feasible: bool
    reasons: tuple[str, ...]
    provenance: str
    work_units: float
    work_label: str


@dataclass(slots=True)
class EnergyComparison:
    rows: list[PolicyMetrics]
    feasible: list[PolicyMetrics]
    recommendation: str | None
    report: str
    comparable: bool
    reasons: tuple[str, ...]
    runs: tuple[PolicyRun, ...]


def compare_policies(runs: Sequence[PolicyRun], *, max_duration: float | None = None,
                     max_temperature: float | None = None,
                     token: Cancellation | None = None) -> EnergyComparison:
    """Rank energy only for the same declared, completed task and workload.

    Lower power alone is not savings. Missing power, different provenance,
    incomplete work or incompatible task metadata block any recommendation.
    A temperature limit cannot be certified when a trace lacks temperatures.
    """
    if token:
        token.check()
    if not 1 <= len(runs) <= 3 or not all(isinstance(run, PolicyRun) for run in runs):
        raise ValueError("Forneça um a três ensaios PolicyRun.")
    if len({run.policy for run in runs}) != len(runs):
        raise ValueError("Cada perfil deve ter um único ensaio nesta comparação.")
    if max_duration is not None and (not math.isfinite(max_duration) or max_duration <= 0):
        raise ValueError("O limite de duração deve ser finito e positivo.")
    if max_temperature is not None and (not math.isfinite(max_temperature) or max_temperature < -273.15):
        raise ValueError("O limite térmico deve ser finito e não inferior ao zero absoluto.")
    reasons = []
    first = runs[0]
    if len(runs) < 2:
        reasons.append("São necessários pelo menos dois perfis para comparar.")
    if not first.task_id or any(run.task_id != first.task_id for run in runs):
        reasons.append("A mesma tarefa deve ser identificada explicitamente em todos os perfis.")
    if any(run.work_label != first.work_label or not math.isclose(run.work_units, first.work_units, rel_tol=1e-9, abs_tol=0)
           for run in runs):
        reasons.append("Os perfis não concluíram a mesma quantidade de trabalho com a mesma unidade.")
    if any(not run.work_completed for run in runs):
        reasons.append("Há ensaios com trabalho por concluir.")
    if any(run.powers is None for run in runs):
        reasons.append("Falta potência explícita em watts em pelo menos um perfil; CPU% não substitui potência.")
    if len({run.provenance for run in runs}) != 1:
        reasons.append("Potências medidas, estimadas e simuladas não são comparáveis como uma única experiência.")
    rows = []
    for run in runs:
        if token:
            token.check()
        energy = integrate_power(run.times, run.powers, token) if run.powers is not None else None
        duration = run.times[-1]-run.times[0]
        temperature = max(run.temperatures) if run.temperatures is not None else None
        unavailable = []
        if energy is None:
            unavailable.append("Potência indisponível.")
        if not run.work_completed:
            unavailable.append("Tarefa incompleta.")
        if max_duration is not None and duration > max_duration:
            unavailable.append("Duração superior ao limite.")
        if max_temperature is not None:
            if temperature is None:
                unavailable.append("Não há temperatura para verificar o limite térmico.")
            elif temperature > max_temperature:
                unavailable.append("Temperatura máxima superior ao limite.")
        # Work/J is undefined for an all-zero trace; do not report infinity.
        efficiency = run.work_units/energy.joules if energy is not None and energy.joules > 0 else None
        rows.append(PolicyMetrics(run.policy, energy.joules if energy else None,
                                  energy.watt_hours if energy else None, duration, temperature,
                                  efficiency, energy.average_power if energy else None,
                                  energy.peak_power if energy else None, not unavailable,
                                  tuple(unavailable), run.provenance, run.work_units, run.work_label))
    feasible = [row for row in rows if row.feasible]
    comparable = not reasons
    recommendation = (min(feasible, key=lambda row: (row.energy_j, row.duration)).policy
                      if comparable and feasible else None)
    lines = [
        "COMPARAÇÃO ENERGÉTICA — análise apenas de leitura; nenhuma política do sistema foi alterada.",
        f"Tarefa declarada: {first.task_id or 'não identificada'}; trabalho: {first.work_units:g} {first.work_label}.",
        "Energia por trapézios: E = ∫P(t)dt; potência em W, tempo em s, energia em J e Wh (1 Wh = 3600 J).",
        "Eficiência = trabalho concluído / energia; a potência média isolada não determina o consumo total.",
        f"Restrições: duração ≤ {str(max_duration)+' s' if max_duration is not None else 'sem limite'}; temperatura ≤ {str(max_temperature)+' °C' if max_temperature is not None else 'sem limite'}.",
    ]
    for run, row in zip(runs, rows):
        energy_label = f"{row.energy_j:.9g} J ({row.energy_wh:.9g} Wh)" if row.energy_j is not None else "indisponível"
        temp_label = f"{row.max_temperature:.6g} °C" if row.max_temperature is not None else "indisponível"
        efficiency_label = f"{row.efficiency:.9g} {row.work_label}/J" if row.efficiency is not None else "indefinida"
        lines.append(f"{row.policy}: potência {row.provenance}; E={energy_label}; duração={row.duration:.9g} s; Tmax={temp_label}; eficiência={efficiency_label}.")
        lines.append(f"  Temperatura: {run.temperature_provenance or 'origem não declarada'}; tarefa {'concluída' if run.work_completed else 'incompleta'}; {'admissível' if row.feasible else '; '.join(row.reasons)}.")
    if reasons:
        lines.append("Sem recomendação: "+" ".join(reasons))
    elif not feasible:
        lines.append("Sem recomendação: nenhum perfil satisfaz as restrições.")
    else:
        label = {"SIMULATED": "neste cenário simulado", "ESTIMATED": "segundo o modelo de potência estimada", "MEASURED": "segundo as medições fornecidas"}[first.provenance]
        lines.append(f"Perfil de menor energia admissível {label}: {recommendation}. Empates são resolvidos pela menor duração.")
    if any(run.provenance == "SIMULATED" for run in runs):
        lines.append("Dados sintéticos não demonstram poupança real neste computador.")
    lines.extend([
        "A proveniência é fornecida pelo utilizador; importar CSV não confirma calibração nem origem de sensores.",
        "Potência e temperatura têm proveniências independentes. Uma temperatura simulada não é uma medição térmica.",
        "A comparação cobre apenas o intervalo amostrado; não inclui energia anterior/posterior nem perdas fora da fronteira de medição.",
        "Limitações: trabalho/tarefa devem ser equivalentes; configurações, carga de fundo e fronteira de potência devem ser comparáveis; não se estimou incerteza nem significância estatística.",
        "Uma recomendação é uma comparação dos valores fornecidos, não uma promessa de poupança ou uma alteração automática do sistema.",
    ])
    return EnergyComparison(rows, feasible, recommendation, "\n".join(lines), comparable, tuple(reasons), tuple(runs))


def load_policy_csv(path: str | Path, *, policy: str, work_units: float, work_label: str,
                    provenance: str, task_id: str, work_completed: bool = True,
                    temperature_provenance: str | None = None,
                    token: Cancellation | None = None) -> PolicyRun:
    trace = load_power_csv(path, token)
    return PolicyRun(policy, trace.times, trace.powers, trace.temperatures, work_units,
                     work_label, provenance, task_id, work_completed, temperature_provenance)


def synthetic_policy_runs() -> list[PolicyRun]:
    """ECO draws fewer watts yet uses more joules than NORMAL in this example."""
    scenarios = (("NORMAL", 10, 60, 70), ("ECO", 15, 45, 62), ("ULTRA ECO", 20, 25, 55))
    return [PolicyRun(name, (0, duration/2, duration), (power, power, power),
                      (25, temperature, temperature), 1, "tarefa sintética", "SIMULATED",
                      "exemplo-mesma-tarefa-1", True, "SIMULATED")
            for name, duration, power, temperature in scenarios]
