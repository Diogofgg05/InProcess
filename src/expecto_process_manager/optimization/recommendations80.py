"""InProcess 8.0 — explainable READ-ONLY optimization recommendations.

No machine-learning claims or automatic priority/OS changes. Recommendations
require source evidence; missing, incomparable, simulated or uncalibrated
measurements create "INSUFFICIENT_EVIDENCE", not invented savings.
"""
from dataclasses import asdict, dataclass
import math

from .statistics73 import ScientificComparison


@dataclass(frozen=True)
class Recommendation:
    action: str
    status: str
    explanation: str
    supporting_metrics: tuple[str, ...]
    conditions: tuple[str, ...]
    confidence: str


def recommend_from_benchmark(report:ScientificComparison) -> Recommendation:
    if not isinstance(report,ScientificComparison):
        raise TypeError("É necessário um relatório estatístico 7.3.")
    if not report.comparable or not report.impacts:
        return Recommendation(
            "NO_CHANGE","INSUFFICIENT_EVIDENCE",
            "Não alterar prioridades: não há ensaios suficientemente comparáveis.",
            tuple(report.reasons),
            ("Repetir experiências na mesma máquina, com baseline e no mínimo 3 repetições.",),
            "NONE",
        )
    # Only the observed workload-time overhead is considered. A lower monitor
    # CPU percentage does not imply less energy, nor a change in priority
    # improving throughput.
    inprocess=[item for item in report.impacts if item.label=="INPROCESS"]
    if not inprocess:
        return Recommendation(
            "NO_CHANGE","INSUFFICIENT_EVIDENCE",
            "Falta cenário InProcess, não é possível avaliar o impacto do programa.",
            ("INPROCESS ausente",),
            ("Medir InProcess e baseline com tarefa idêntica.",),"NONE"
        )
    impact=inprocess[0]
    lo,hi=impact.difference_ci95_pct
    if not all(math.isfinite(x) for x in (impact.slowdown_pct,lo,hi)):
        raise ValueError("Intervalo de incerteza inválido.")
    if lo>5:
        return Recommendation(
            "REVIEW_BACKGROUND_LOAD","REVIEW_ONLY",
            "A duração da tarefa aumentou nos ensaios com InProcess. "
            "Analisar frequência de recolha, agregação de processos e carga do sistema; "
            "não aplicar mudanças automáticas.",
            (f"Impacto mediano: {impact.slowdown_pct:.2f}%",
             f"Bootstrap descritivo 95%: [{lo:.2f}%, {hi:.2f}%]"),
            ("Confirmar causas com ensaios independentes e ordem contrabalançada.",
             "Verificar responsividade e valores reais de energia."),
            "LIMITED",
        )
    return Recommendation(
        "NO_CHANGE","NO_JUSTIFIED_ACTION",
        "Os dados não justificam alterar prioridades ou políticas do SO. "
        "Não se demonstrou um ganho causal ou energético.",
        (f"Impacto mediano: {impact.slowdown_pct:.2f}%",
         f"Bootstrap descritivo 95%: [{lo:.2f}%, {hi:.2f}%]"),
        ("Recolher dados de potência física e incerteza antes de recomendações energéticas.",),
        "LIMITED",
    )


def recommend_energy(comparison:dict) -> Recommendation:
    if not isinstance(comparison,dict) or not comparison.get("comparable"):
        return Recommendation(
            "NO_CHANGE","INSUFFICIENT_EVIDENCE",
            "Não recomendar perfis energéticos sem medições comparáveis.",
            tuple(comparison.get("reasons",()) if isinstance(comparison,dict) else ()),
            ("Usar sensor, domínio de potência e trabalho comparáveis.",),"NONE"
        )
    best=comparison.get("best_energy")
    if not best or best not in comparison.get("results",{}):
        raise ValueError("Análise energética incompleta.")
    selected=comparison["results"][best]
    return Recommendation(
        "REVIEW_ENERGY_PROFILE","REVIEW_ONLY",
        f"O perfil {best} apresentou a menor energia no conjunto fornecido, "
        "mas é apenas um candidato a confirmação experimental.",
        (f"Energia observada: {selected['joules']:.4g} J",
         f"Domínio: {selected['power_scope']}",
         f"Proveniência: {selected['provenance']}"),
        ("Repetir os ensaios e estimar incerteza antes de adotar um perfil.",
         "Nenhuma alteração ao sistema é executada automaticamente."),
        "LIMITED",
    )


def combine_recommendations(benchmark:ScientificComparison|None=None,
                            energy:dict|None=None) -> dict:
    recommendations=[]
    if benchmark is not None:
        recommendations.append(recommend_from_benchmark(benchmark))
    if energy is not None:
        recommendations.append(recommend_energy(energy))
    if not recommendations:
        recommendations.append(Recommendation(
            "NO_CHANGE","INSUFFICIENT_EVIDENCE",
            "Sem dados experimentais para recomendar alterações.",(),
            ("Importar resultados válidos de desempenho e energia.",),"NONE"))
    return {
        "mode":"READ_ONLY",
        "version":"8.0",
        "automatic_os_actions":False,
        "recommendations":[asdict(r) for r in recommendations],
        "limits":[
            "As regras não são um modelo de inteligência artificial treinado.",
            "Não há aprendizagem automática, controlo de ventoinhas ou modificação de processos.",
            "Recomendações dependem do desenho experimental e das medições.",
        ]
    }
