"""Signed pressure-volume work and explicitly qualified polytropic fits."""
import csv
from dataclasses import dataclass
import math
from pathlib import Path
from collections.abc import Sequence

from ..core.cancellation import Cancellation


MAX_SAMPLES = 100_001


@dataclass(slots=True)
class CompressionExperiment:
    volumes: list[float]
    pressures: list[float]
    work_by_gas: float
    work_on_gas: float
    simpson_work: float | None
    polytropic_index: float | None
    coefficient: float | None
    fit_rmse: float | None
    fitted_pressures: list[float] | None
    isothermal_pressures: list[float] | None
    adiabatic_pressures: list[float] | None
    report: str
    provenance: str = "origem não verificada"
    gamma: float = 1.4


def analyze_compression(volumes: Sequence[float], pressures: Sequence[float],
                        token: Cancellation | None = None, *,
                        provenance: str = "origem não verificada",
                        gamma: float = 1.4) -> CompressionExperiment:
    """Preserve sample order, including reverse branches and full P-V cycles.

    Work is BY the gas, W = integral(p dV); work ON the gas is -W.
    Positive pressure in Pa and volume in m³ are required. A global fit and
    Simpson are deliberately unavailable for multi-branch/cyclic data.
    """
    if token:
        token.check()
    if len(volumes) != len(pressures) or not 2 <= len(volumes) <= MAX_SAMPLES:
        raise ValueError(f"Forneça 2 a {MAX_SAMPLES} pares de volume e pressão.")
    if not isinstance(gamma, (float, int)) or not math.isfinite(gamma) or gamma <= 1:
        raise ValueError("O expoente adiabático γ deve ser finito e superior a 1.")
    try:
        vs, ps = list(map(float, volumes)), list(map(float, pressures))
    except (ValueError, TypeError, OverflowError) as error:
        raise ValueError("Volume (m³) e pressão (Pa) devem ser números finitos positivos.") from error
    if any(not math.isfinite(x) or x <= 0 for x in vs+ps):
        raise ValueError("Volume (m³) e pressão (Pa) devem ser números finitos positivos.")
    deltas = [b-a for a, b in zip(vs, vs[1:])]
    monotonic = all(d > 0 for d in deltas) or all(d < 0 for d in deltas)
    work = math.fsum((ps[i]+ps[i+1])*d/2 for i, d in enumerate(deltas))
    if not math.isfinite(work):
        raise ValueError("O trabalho excedeu a escala numérica suportada.")
    simpson = None
    uniform = monotonic and all(math.isclose(d, deltas[0], rel_tol=1e-9, abs_tol=0.0) for d in deltas)
    if uniform and len(deltas) % 2 == 0:
        simpson = deltas[0]/3 * (ps[0]+ps[-1]+4*math.fsum(ps[1:-1:2])+2*math.fsum(ps[2:-1:2]))
    index = coefficient = rmse = None
    fitted = None
    if monotonic and len(vs) >= 3:
        logs_v, logs_p = [math.log(v) for v in vs], [math.log(p) for p in ps]
        mean_v, mean_p = math.fsum(logs_v)/len(vs), math.fsum(logs_p)/len(ps)
        variance = math.fsum((v-mean_v)**2 for v in logs_v)
        if variance > 1e-24:
            slope = math.fsum((v-mean_v)*(p-mean_p) for v, p in zip(logs_v, logs_p))/variance
            index = -slope
            intercept = mean_p+index*mean_v
            try:
                coefficient = math.exp(intercept)
                fitted = [math.exp(mean_p+slope*(v-mean_v)) for v in logs_v]
            except OverflowError as error:
                raise ValueError("O ajuste politrópico excedeu a escala numérica suportada.") from error
            if not coefficient or any(not math.isfinite(p) for p in fitted):
                raise ValueError("O ajuste politrópico está mal condicionado para estes dados.")
            rmse = math.sqrt(math.fsum((p-q)**2 for p, q in zip(ps, fitted))/len(ps))
    # These curves are illustrative ideal-gas references, not fitted sensor data.
    try:
        ratios = [vs[0]/v for v in vs]
        isothermal = [ps[0]*ratio for ratio in ratios] if monotonic else None
        adiabatic = [ps[0]*ratio**gamma for ratio in ratios] if monotonic else None
    except OverflowError as error:
        raise ValueError("As curvas de referência excederam a escala numérica suportada.") from error
    if isothermal is not None and any(not math.isfinite(p) for p in isothermal+adiabatic):
        raise ValueError("As curvas de referência excederam a escala numérica suportada.")
    lines = [
        f"LABORATÓRIO DE COMPRESSOR — proveniência: {provenance}.",
        f"{len(vs)} amostras; volume em m³; pressão absoluta em Pa; trabalho em J.",
        "Convenção: W pelo gás = ∫ p dV; W sobre o gás = −W pelo gás. Compressão monotónica dá W pelo gás negativo.",
        "A ordem original dos pontos foi preservada, incluindo ciclos e mudanças de sentido.",
        f"Trapézios: W pelo gás={work:.10g} J; W sobre o gás={-work:.10g} J.",
    ]
    if simpson is not None:
        lines.append(f"Simpson 1/3: W pelo gás={simpson:.10g} J; diferença absoluta para trapézios={abs(simpson-work):.8g} J.")
        lines.append("Condições verificadas: ramo estritamente monotónico, passo de volume uniforme e número par de intervalos.")
    else:
        lines.append("Simpson indisponível: exige ramo monotónico, passo uniforme e número par de intervalos; não se reamostram os dados silenciosamente.")
    if index is not None:
        lines.extend([
            f"Ajuste log-linear: p Vⁿ = K; n={index:.10g}; K={coefficient:.10g} Pa·(m³)ⁿ.",
            f"RMSE do ajuste no domínio da pressão={rmse:.8g} Pa; mínimos quadrados efetuados no domínio logarítmico.",
            f"Referências ancoradas no primeiro ponto: isotérmica n=1; adiabática reversível n=γ={gamma:g}.",
            "As referências pressupõem gás ideal, massa fixa e processo quase estático; a curva adiabática pressupõe ainda ausência de calor e reversibilidade.",
        ])
    else:
        lines.append("Sem ajuste politrópico global: são necessários pelo menos três volumes distintos de um único ramo monotónico e bem condicionado.")
    lines.extend([
        "A diferença entre quadraturas estima sensibilidade ao método, não é o erro experimental verdadeiro.",
        "Limitações: o ajuste não descreve necessariamente fugas, atrito, transferência de calor, pulsação, válvulas ou dinâmica de um compressor real.",
        "Não foi confirmada a calibração, a sincronização nem a incerteza das medições importadas.",
    ])
    if token:
        token.check()
    return CompressionExperiment(vs, ps, work, -work, simpson, index, coefficient,
                                 rmse, fitted, isothermal, adiabatic, "\n".join(lines), provenance, gamma)


def import_compression_csv(path: str | Path, token: Cancellation | None = None) -> CompressionExperiment:
    """Read explicit SI headers; imported values never imply verified sensors."""
    target = Path(path)
    if target.stat().st_size > 16*1024*1024:
        raise ValueError("O CSV do compressor excede 16 MiB.")
    volumes, pressures = [], []
    with target.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["volume_m3", "pressure_pa"]:
            raise ValueError("O CSV deve ter os cabeçalhos volume_m3,pressure_pa, em SI e nesta ordem.")
        for line, row in enumerate(reader, start=2):
            if token and line % 256 == 0:
                token.check()
            if len(volumes) >= MAX_SAMPLES:
                raise ValueError(f"O CSV está limitado a {MAX_SAMPLES} amostras.")
            try:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError
                volumes.append(float(row["volume_m3"]))
                pressures.append(float(row["pressure_pa"]))
            except (ValueError, TypeError) as error:
                raise ValueError(f"Linha {line}: volume e pressão devem ser números SI válidos.") from error
    return analyze_compression(volumes, pressures, token, provenance="CSV importado; origem não verificada")


def synthetic_compression(samples: int = 101, exponent: float = 1.3,
                          token: Cancellation | None = None) -> CompressionExperiment:
    """A labelled synthetic reference, never a fabricated compressor experiment."""
    if not isinstance(samples, int) or not 3 <= samples <= MAX_SAMPLES:
        raise ValueError("O cenário sintético precisa de 3 a 100001 amostras.")
    if not math.isfinite(exponent) or not 0 < exponent <= 3:
        raise ValueError("Use um expoente sintético positivo até 3.")
    volumes = [0.01-0.005*i/(samples-1) for i in range(samples)]
    pressures = [100_000*(0.01/v)**exponent for v in volumes]
    return analyze_compression(volumes, pressures, token, provenance=f"simulado; pVⁿ constante, n={exponent:g}")
