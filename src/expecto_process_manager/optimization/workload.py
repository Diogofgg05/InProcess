"""Read-only bridge between measured process activity and ECO assessment.

Process CPU/RSS cannot be converted into watts. This module deliberately
does not alter EnergyComparison, PolicyRun or the numerical energy advice.
"""
from dataclasses import dataclass
from collections.abc import Sequence

from ..core.insights import ProcessInsight


@dataclass(frozen=True, slots=True)
class WorkloadContext:
    state: str
    observed_processes: int
    hints: tuple[str, ...]
    report: str


def assess_workload(insights: Sequence[ProcessInsight], *,
                    observed_processes: int | None = None,
                    collected: bool = True) -> WorkloadContext:
    """Explain why live process telemetry cannot certify an energy experiment."""
    if observed_processes is not None and (type(observed_processes) is not int or observed_processes < 0):
        raise ValueError("Número de processos observados inválido.")
    signals = tuple(insights)[:2]
    if not all(isinstance(item, ProcessInsight) for item in signals):
        raise TypeError("O contexto requer ProcessInsight válido.")
    count = observed_processes if observed_processes is not None else 0

    if not collected:
        state = "NO_SNAPSHOT"
        hints = ("Aguardar uma amostra real do monitor antes de contextualizar a carga.",)
    elif signals:
        state = "ACTIVE_WORKLOAD"
        hints = tuple(
            f"{signal.name} (PID {signal.pid}): {signal.kind} sustentado "
            f"em {signal.samples} amostras. Pode ser uma tarefa legítima."
            for signal in signals
        )
    else:
        state = "NO_SUSTAINED_SIGNAL"
        hints = ("Nenhum processo ultrapassou os limiares persistentes do detector; "
                 "isto não comprova ausência de cargas em segundo plano.",)

    text = [
        "CONTEXTO DE CARGA — dados de processos reportados pelo sistema operativo.",
        f"Estado: {state}; processos acessíveis no último snapshot: {count}.",
        *hints,
        "Amostras de CPU/RAM não são séries de potência elétrica em watts.",
        "O snapshot do monitor não está sincronizado com o período de aquisição "
        "dos perfis NORMAL/ECO/ULTRA ECO e não valida uma comparação energética.",
        "Não são executadas ações sobre processos, perfis energéticos ou hardware.",
    ]
    return WorkloadContext(state, count, hints, "\n".join(text))
