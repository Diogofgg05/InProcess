"""Read-only, evidence-aware screening of ECO/ULTRA ECO alternatives.

The source comparison remains unchanged. This layer never invokes operating-
system APIs or makes a claim of physically verified energy savings.
"""
from dataclasses import dataclass
import math

from .eco import EnergyComparison


@dataclass(frozen=True, slots=True)
class EnergyAdvice:
    status: str
    candidate: str | None
    baseline: str
    saved_j: float | None
    saved_wh: float | None
    savings_percent: float | None
    slowdown_percent: float | None
    provenance: str
    reasons: tuple[str, ...]
    report: str


def energy_advice(
    comparison: EnergyComparison, *,
    min_savings_percent: float = 5.0,
    max_slowdown_percent: float = 25.0,
) -> EnergyAdvice:
    """Compare feasible alternatives with NORMAL using time/energy constraints."""
    for label, value, maximum in (
        ("Poupança mínima", min_savings_percent, 100),
        ("Atraso máximo", max_slowdown_percent, 1000),
    ):
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or not 0 <= value <= maximum):
            raise ValueError(f"{label}: percentagem inválida (0 a {maximum}).")
    if not isinstance(comparison, EnergyComparison):
        raise TypeError("É necessária uma comparação energética válida.")

    by_name = {row.policy: row for row in comparison.rows}
    reference = by_name.get("NORMAL")
    source = comparison.runs[0].provenance if comparison.runs else "UNAVAILABLE"
    reasons = []
    status, candidate = "INSUFFICIENT_DATA", None
    saved = savings = slowdown = None

    if not comparison.comparable:
        reasons.extend(comparison.reasons)
    elif reference is None or not reference.feasible or reference.energy_j is None:
        reasons.append("O perfil NORMAL não está disponível ou não satisfaz os limites; não há referência admissível.")
    elif reference.energy_j <= 0:
        reasons.append("A energia NORMAL deve ser positiva para calcular uma poupança percentual.")
    else:
        admissible = []
        for row in comparison.feasible:
            if row.policy == "NORMAL" or row.energy_j is None:
                continue
            reduction = reference.energy_j - row.energy_j
            reduction_pct = 100 * reduction / reference.energy_j
            penalty_pct = 100 * (row.duration - reference.duration) / reference.duration
            if reduction <= 0 or reduction_pct + 1e-12 < min_savings_percent:
                continue
            if penalty_pct > max_slowdown_percent + 1e-12:
                continue
            admissible.append((row.energy_j, row.duration, row.policy,
                               reduction, reduction_pct, penalty_pct))
        if admissible:
            _, _, candidate, saved, savings, slowdown = min(admissible)
            status = "CANDIDATE"
        else:
            status = "KEEP_NORMAL"
            reasons.append("Nenhuma alternativa reduz energia o suficiente sem ultrapassar o atraso permitido.")

    saved_wh = saved / 3600 if saved is not None else None
    label = {"SIMULATED": "cenário simulado", "ESTIMATED": "dados estimados",
             "MEASURED": "dados declarados como medidos"}.get(source, "origem não verificada")
    lines = [
        "PARECER ENERGÉTICO — SOMENTE LEITURA / DRY RUN",
        f"Referência: NORMAL; origem: {label}.",
        f"Critérios: redução mínima {min_savings_percent:g}% e atraso máximo {max_slowdown_percent:g}% face a NORMAL.",
    ]
    if candidate:
        lines.append(
            f"Candidato: {candidate}; diferença {saved:.9g} J ({saved_wh:.9g} Wh), "
            f"{savings:.6g}% menos energia; diferença temporal {slowdown:+.6g}% face a NORMAL."
        )
    elif status == "KEEP_NORMAL":
        lines.append("Manter NORMAL nesta comparação: não existe alternativa que cumpra ambos os critérios.")
    else:
        lines.append("Parecer inconclusivo: referência ou comparação insuficiente.")
    lines.extend(reasons)
    lines.extend([
        "Não foi alterada qualquer prioridade, processo, frequência ou política energética do sistema operativo.",
        "Um CSV com origem declarada MEASURED não prova calibração, repetibilidade nem significância estatística.",
        "Este parecer não garante poupança real ou segurança térmica e não constitui autorização para otimização automática.",
    ])
    return EnergyAdvice(status, candidate, "NORMAL", saved, saved_wh, savings,
                        slowdown, source, tuple(reasons), "\n".join(lines))
