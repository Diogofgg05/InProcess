"""InProcess 7.3 — honest statistical analysis of independent benchmark trials.

Descriptive statistics and bootstrap uncertainty on *trial durations*. No
claims of measured UI latency, power, energy, or cross-platform superiority.
A comparison is not accepted without at least three successful repetitions
per scenario under the same workload and machine fingerprint.
"""
from dataclasses import asdict, dataclass
import math
import random
import statistics
from collections import defaultdict

from .benchmarks71 import BenchmarkTrial, validate_comparison


@dataclass(frozen=True)
class ScenarioStats:
    label: str
    n: int
    median_duration_s: float
    mean_duration_s: float
    stdev_duration_s: float | None
    p95_duration_s: float
    median_observer_cpu_core_pct: float | None
    median_observer_rss_mib: float | None


@dataclass(frozen=True)
class RelativeImpact:
    label: str
    slowdown_pct: float
    difference_ci95_pct: tuple[float, float]
    paired: bool
    interpretation: str


@dataclass(frozen=True)
class ScientificComparison:
    comparable: bool
    reasons: tuple[str, ...]
    stats: tuple[ScenarioStats, ...]
    impacts: tuple[RelativeImpact, ...]
    metadata: dict


def _percentile(values, fraction):
    values = sorted(values)
    if not values:
        raise ValueError("Não existem valores.")
    pos = fraction * (len(values)-1)
    i = int(pos)
    if i == len(values)-1:
        return values[i]
    return values[i] + (values[i+1] - values[i]) * (pos-i)


def _bootstrap_relative(base, other, *, draws=1000, seed=731):
    """Reproducible unpaired bootstrap for the *median duration ratio*.

    The interval describes sampling variability conditional on the trials,
    not a calibrated causal effect or correction for thermal/OS drift.
    """
    rng = random.Random(seed)
    samples = []
    for _ in range(draws):
        b = statistics.median(rng.choice(base) for _ in base)
        o = statistics.median(rng.choice(other) for _ in other)
        samples.append(100 * (o / b - 1))
    return (_percentile(samples, .025), _percentile(samples, .975))


def analyse_benchmarks(trials: list[BenchmarkTrial],
                       *, minimum_repetitions: int = 3) -> ScientificComparison:
    if not isinstance(minimum_repetitions, int) or isinstance(minimum_repetitions, bool) or minimum_repetitions < 3:
        raise ValueError("São necessárias pelo menos três repetições por cenário.")
    basic = validate_comparison(trials)
    reasons = list(basic["reasons"])
    by_label = defaultdict(list)
    for t in trials:
        by_label[t.label].append(t)
    for label, group in by_label.items():
        if len(group) < minimum_repetitions:
            reasons.append(f"{label}: repetições insuficientes ({len(group)}/{minimum_repetitions}).")
    if not by_label.get("BASELINE"):
        reasons.append("Não existe baseline.")
    stats = []
    for label, values in sorted(by_label.items()):
        good = [x for x in values if x.status == "SUCCESS"]
        if not good:
            continue
        durations = [t.task_duration_s for t in good]
        cpu = [t.observer_cpu_core_percent for t in good]
        memory = [t.observer_peak_rss_mib for t in good]
        stats.append(ScenarioStats(
            label=label, n=len(good),
            median_duration_s=statistics.median(durations),
            mean_duration_s=statistics.mean(durations),
            stdev_duration_s=statistics.stdev(durations) if len(durations)>1 else None,
            p95_duration_s=_percentile(durations, .95),
            median_observer_cpu_core_pct=statistics.median(cpu) if all(x is not None for x in cpu) else None,
            median_observer_rss_mib=statistics.median(memory) if all(x is not None for x in memory) else None,
        ))
    impacts = []
    if not reasons:
        base = [t.task_duration_s for t in by_label["BASELINE"]]
        if statistics.median(base) <= 0:
            reasons.append("Duração de baseline inválida.")
        else:
            for label, group in sorted(by_label.items()):
                if label == "BASELINE":
                    continue
                values = [t.task_duration_s for t in group]
                delta = 100 * (statistics.median(values)/statistics.median(base)-1)
                lo,hi = _bootstrap_relative(base, values)
                impacts.append(RelativeImpact(
                    label,delta,(lo,hi),False,
                    "Intervalo bootstrap não emparelhado da mediana; descritivo, "
                    "não prova causalidade nem equivalência térmica."
                ))
    return ScientificComparison(
        comparable=not reasons,reasons=tuple(dict.fromkeys(reasons)),
        stats=tuple(stats),impacts=tuple(impacts),
        metadata={
            "version": "7.3",
            "method": "unpaired bootstrap on median duration ratio",
            "bootstrap_draws": 1000, "bootstrap_seed": 731,
            "ui_latency": "NOT_MEASURED",
            "electric_power": "NOT_MEASURED",
            "energy": "NOT_MEASURED",
            "warning": "Recolha real exigida; não há resultados predefinidos ou fictícios.",
        },
    )


def report_dict(report: ScientificComparison) -> dict:
    return asdict(report)
