"""InProcess 7.6 — energy measurement ingestion with explicit provenance.

A user-provided sensor CSV is NOT inherently calibrated. Energy is integrated
from watts using actual timestamps (trapezoids); CPU utilization is never
translated to watts. Sensor scope and unit metadata are mandatory.
"""
from dataclasses import dataclass, asdict
from pathlib import Path
import csv
import math


@dataclass(frozen=True)
class EnergyReading:
    time_s: float
    power_w: float
    temperature_c: float | None = None


@dataclass(frozen=True)
class EnergyTrace:
    readings: tuple[EnergyReading, ...]
    device: str
    sensor: str
    power_scope: str
    provenance: str = "MEASURED_UNVERIFIED"

    def __post_init__(self):
        if self.provenance not in ("MEASURED_UNVERIFIED", "CALIBRATED_EXTERNALLY", "SIMULATED"):
            raise ValueError("Proveniência inválida.")
        if not all(isinstance(v, str) and v.strip() for v in (self.device,self.sensor,self.power_scope)):
            raise ValueError("Identificar equipamento, sensor e domínio da potência.")
        if len(self.readings) < 3 or len(self.readings) > 100000:
            raise ValueError("São necessárias 3–100000 observações.")
        previous = None
        for row in self.readings:
            if not isinstance(row, EnergyReading):
                raise ValueError("Amostra inválida.")
            if (not math.isfinite(row.time_s) or not math.isfinite(row.power_w)
                    or row.power_w < 0):
                raise ValueError("Tempo/potência inválidos.")
            if row.temperature_c is not None and (
                not math.isfinite(row.temperature_c) or row.temperature_c < -273.15
            ):
                raise ValueError("Temperatura inválida.")
            if previous is not None and row.time_s <= previous:
                raise ValueError("Os timestamps devem ser estritamente crescentes.")
            previous = row.time_s


@dataclass(frozen=True)
class EnergyResult:
    joules: float
    watt_hours: float
    mean_power_w: float
    duration_s: float
    maximum_power_w: float
    temperature_min_c: float | None
    temperature_max_c: float | None
    provenance: str
    sensor: str
    power_scope: str
    limits: tuple[str,...]


def load_energy_trace_csv(path, *, device, sensor, power_scope,
                          provenance="MEASURED_UNVERIFIED") -> EnergyTrace:
    path=Path(path)
    if path.stat().st_size > 8_000_000:
        raise ValueError("CSV demasiado grande.")
    with path.open(encoding="utf-8-sig",newline="") as handle:
        reader=csv.DictReader(handle)
        if reader.fieldnames not in (
            ["time_s","power_w"],["time_s","power_w","temperature_c"]
        ):
            raise ValueError("Colunas obrigatórias: time_s,power_w[,temperature_c].")
        temps="temperature_c" in reader.fieldnames
        samples=[]
        for i,row in enumerate(reader):
            if i>=100000:
                raise ValueError("Limite de amostras excedido.")
            try:
                raw=row.get("temperature_c") if temps else None
                temp=float(raw) if raw not in ("",None) else None
                samples.append(EnergyReading(float(row["time_s"]),
                                             float(row["power_w"]), temp))
            except (ValueError,TypeError,OverflowError) as exc:
                raise ValueError(f"Erro na linha {i+2}.") from exc
    return EnergyTrace(tuple(samples),device,sensor,power_scope,provenance)


def integrate_energy(trace:EnergyTrace) -> EnergyResult:
    if not isinstance(trace,EnergyTrace):
        raise TypeError("É necessária uma série térmica/energética validada.")
    readings=trace.readings
    energy=math.fsum(
        (b.time_s-a.time_s)*(a.power_w+b.power_w)/2
        for a,b in zip(readings,readings[1:])
    )
    duration=readings[-1].time_s-readings[0].time_s
    temps=[r.temperature_c for r in readings if r.temperature_c is not None]
    return EnergyResult(
        joules=energy,watt_hours=energy/3600,
        mean_power_w=energy/duration,duration_s=duration,
        maximum_power_w=max(r.power_w for r in readings),
        temperature_min_c=min(temps) if temps else None,
        temperature_max_c=max(temps) if temps else None,
        provenance=trace.provenance,sensor=trace.sensor,power_scope=trace.power_scope,
        limits=(
            "O domínio de potência indicado deve corresponder à medição efetiva do sensor.",
            "Importar CSV não valida sincronismo, calibração nem precisão instrumental.",
            "Potência elétrica medida não é necessariamente potência térmica do CPU.",
            "Energia cobre apenas a janela recolhida; não inclui consumo fora da janela.",
            "Não comparar sensores/domínios diferentes como se medissem o mesmo sistema.",
        ),
    )


def compare_energy_traces(traces:dict[str,EnergyTrace], *, comparable_work: bool=False) -> dict:
    if len(traces)<2 or not all(isinstance(v,EnergyTrace) for v in traces.values()):
        raise ValueError("Precisam-se dois ou mais cenários medidos.")
    result={k:integrate_energy(v) for k,v in traces.items()}
    reasons=[]
    if not comparable_work:
        reasons.append("Não está comprovada a equivalência do trabalho executado.")
    if len({(v.device,v.sensor,v.power_scope) for v in traces.values()})!=1:
        reasons.append("Os sensores, equipamentos ou domínios energéticos diferem.")
    if len({v.provenance for v in traces.values()})!=1:
        reasons.append("Proveniências diferentes.")
    if any(v.provenance=="SIMULATED" for v in traces.values()):
        reasons.append("Cenários simulados não comprovam eficiência física real.")
    return {
        "comparable":not reasons,
        "reasons":reasons,
        "results":{k:asdict(v) for k,v in result.items()},
        "best_energy":min(result,key=lambda k:result[k].joules) if not reasons else None,
        "warnings":[
            "A comparabilidade não substitui calibração nem validação experimental.",
            "Diferenças em joules não são necessariamente significativas sem repetições e incerteza.",
        ],
    }
