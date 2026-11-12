"""InProcess 7.0 — identifiable first-order thermal digital-twin prototype.

C*dT/dt = P(t) - (T-Ta)/R, with zero-order-held P and Ta in each interval.
At constant dt the EXACT discrete map is:
    T[k+1]-Ta[k] = a*(T[k]-Ta[k]) + b*P[k],
    a=exp(-dt/(R*C)); b=R*(1-a).

a and b are calibrated with a physically constrained, identifiable two-
parameter OLS fit on an EARLIER contiguous block. The later holdout is scored
using an autonomous rollout, not one-step teacher-forcing. This does not
validate the model against real hardware without independent, calibrated
temperature, ambient and *thermal input power* measurements.
"""
import csv
from dataclasses import dataclass
from math import ceil, exp, isfinite, log, sin, pi, sqrt
from pathlib import Path
from statistics import mean


@dataclass(frozen=True)
class ThermalSample:
    time_s: float
    cpu_temp_c: float
    ambient_c: float
    power_w: float


@dataclass(frozen=True)
class ThermalSeries:
    samples: tuple[ThermalSample, ...]
    origin: str

    def __post_init__(self):
        if self.origin not in ("SIMULATED", "MEASURED_UNVERIFIED"):
            raise ValueError("Origem inválida; medições não podem ser declaradas validadas.")
        n=len(self.samples)
        if not 24<=n<=10000:
            raise ValueError("São necessárias 24 a 10000 amostras.")
        if any(not isinstance(r,ThermalSample) for r in self.samples):
            raise ValueError("Registo térmico inválido.")
        for row in self.samples:
            if not all(isfinite(v) for v in
                       (row.time_s,row.cpu_temp_c,row.ambient_c,row.power_w)):
                raise ValueError("Séries térmicas exigem valores finitos.")
            if (min(row.cpu_temp_c,row.ambient_c)<-273.15 or
                    row.power_w<0):
                raise ValueError("Temperatura não física ou potência negativa.")
        diffs=[self.samples[i+1].time_s-self.samples[i].time_s
               for i in range(n-1)]
        if any(d<=0 for d in diffs):
            raise ValueError("Tempos devem crescer estritamente.")
        step=mean(diffs)
        if any(abs(d-step)>max(1e-8,step*.001) for d in diffs):
            raise ValueError("A identificação requer passo temporal uniforme (0,1% de tolerância).")

    @property
    def dt_s(self):
        return (self.samples[-1].time_s-self.samples[0].time_s)/(len(self.samples)-1)


@dataclass(frozen=True)
class ThermalModel:
    tau_s: float
    resistance_k_w: float
    capacity_j_k: float
    a: float
    b: float
    dt_s: float
    train_power_min_w: float
    train_power_max_w: float
    train_ambient_min_c: float
    train_ambient_max_c: float

    def step(self,temp,ambient,power):
        return self.a*temp+(1-self.a)*ambient+self.b*power


@dataclass(frozen=True)
class ValidationMetrics:
    rmse_c: float
    mae_c: float
    bias_c: float
    persistence_rmse_c: float
    skill_vs_persistence: float | None
    r_squared: float | None
    observed_abs_error_p90_c: float
    points: int


@dataclass(frozen=True)
class ThermalTwinReport:
    origin: str
    train_points: int
    validation_points: int
    model: ThermalModel
    validation: ValidationMetrics
    validation_times_s: tuple[float, ...]
    validation_measured_c: tuple[float, ...]
    validation_predicted_c: tuple[float, ...]
    interpretation: tuple[str, ...]


def load_thermal_csv(path: str | Path) -> ThermalSeries:
    """Read user supplied CSV safely, without auto-detecting assumed units."""
    filepath=Path(path)
    if filepath.stat().st_size>2_000_000:
        raise ValueError("CSV acima de 2 MB; reduza os dados.")
    rows=[]
    with filepath.open("r",encoding="utf-8-sig",newline="") as stream:
        reader=csv.DictReader(stream)
        fields={"time_s","cpu_temp_c","ambient_c","power_w"}
        if reader.fieldnames is None or set(reader.fieldnames)!=fields:
            raise ValueError("Cabeçalho obrigatório: time_s,cpu_temp_c,ambient_c,power_w")
        for i,row in enumerate(reader):
            if i>=10000:
                raise ValueError("CSV limitado a 10000 amostras.")
            try:
                rows.append(ThermalSample(
                    float(row["time_s"]),float(row["cpu_temp_c"]),
                    float(row["ambient_c"]),float(row["power_w"])
                ))
            except (TypeError,ValueError,KeyError,OverflowError) as e:
                raise ValueError(f"Linha {i+2}: campo numérico inválido.") from e
    return ThermalSeries(tuple(rows),"MEASURED_UNVERIFIED")


def synthetic_thermal_series(count:int=300,dt_s:float=1.) -> ThermalSeries:
    """Deterministic teaching dataset with withheld future perturbation."""
    if type(count) is not int or not 24<=count<=3000 or not isfinite(dt_s) or not 0<dt_s<=10:
        raise ValueError("Dimensões da série sintética inválidas.")
    tau=36.
    resistance=.58
    a=exp(-dt_s/tau)
    b=resistance*(1-a)
    temp=30.
    data=[]
    for index in range(count):
        time=index*dt_s
        ambient=24+.4*sin(.03*index)
        power=(42 if index<70 else 85 if index<150 else
               53 if index<225 else 72) + 4*sin(index*.17)
        measured=temp+.03*sin(index*.91)
        data.append(ThermalSample(time,measured,ambient,power))
        temp=a*temp+(1-a)*ambient+b*power
    return ThermalSeries(tuple(data),"SIMULATED")


def _validate_split(train_fraction):
    if (isinstance(train_fraction,bool) or not isinstance(train_fraction,(int,float))
            or not isfinite(train_fraction) or not .55<=train_fraction<=.85):
        raise ValueError("Fraçao de treino entre 0,55 e 0,85.")


def calibrate_twin(series:ThermalSeries, *, train_fraction:float=.7,
                   token=None) -> ThermalTwinReport:
    """Identify from first 70% transitions, autonomously test on last 30%."""
    if not isinstance(series,ThermalSeries):
        raise TypeError("É necessária uma série térmica validada.")
    _validate_split(train_fraction)
    samples=series.samples
    n=len(samples)
    count=int((n-1)*train_fraction)
    step=series.dt_s
    if count<10 or len(samples)-count<6:
        raise ValueError("Divisão treino/validação insuficiente.")
    xx=xp=pp=xy=py=0.
    for i in range(count):
        if token is not None and i%64==0:
            token.check()
        item=samples[i]
        nxt=samples[i+1]
        x=item.cpu_temp_c-item.ambient_c
        p=item.power_w
        y=nxt.cpu_temp_c-item.ambient_c
        xx+=x*x
        xp+=x*p
        pp+=p*p
        xy+=x*y
        py+=p*y
    determinant=xx*pp-xp*xp
    if (xx<=1e-12 or pp<=1e-12 or determinant<=1e-6*xx*pp):
        raise ValueError("Dados não identificáveis: é necessária excitação independente de potência e temperatura.")
    a=(xy*pp-py*xp)/determinant
    b=(xx*py-xp*xy)/determinant
    if not 0<a<1 or b<=0 or not all(isfinite(v) for v in (a,b)):
        raise ValueError("Calibração não física: fatores discretos fora de 0<a<1, b>0.")
    tau=-step/log(a)
    resistance=b/(1-a)
    capacity=tau/resistance
    if (not all(isfinite(v) for v in (tau,resistance,capacity))
            or tau<=0 or resistance<=0 or capacity<=0
            or tau>1e7 or resistance>100 or capacity>1e8):
        raise ValueError("Parâmetros físicos não admissíveis.")
    training=samples[:count]
    model=ThermalModel(
        tau,resistance,capacity,a,b,step,
        min(r.power_w for r in training),max(r.power_w for r in training),
        min(r.ambient_c for r in training),max(r.ambient_c for r in training)
    )
    times=[samples[count].time_s]
    measured=[samples[count].cpu_temp_c]
    predicted=[samples[count].cpu_temp_c]
    current=predicted[0]
    for i in range(count,n-1):
        if token is not None and i%64==0:
            token.check()
        current=model.step(current,samples[i].ambient_c,samples[i].power_w)
        if not isfinite(current) or current<-273.15:
            raise ValueError("Previsão fora do domínio térmico.")
        times.append(samples[i+1].time_s)
        measured.append(samples[i+1].cpu_temp_c)
        predicted.append(current)
    # First point is a measured initial condition, not a prediction.
    truth=measured[1:]
    forecast=predicted[1:]
    errors=[f-v for f,v in zip(forecast,truth)]
    length=len(errors)
    rmse=sqrt(sum(e*e for e in errors)/length)
    persistence=[samples[i].cpu_temp_c for i in range(count,n-1)]
    persistence_rmse=sqrt(sum((p-v)**2 for p,v in zip(persistence,truth))/length)
    skill=(1-rmse**2/persistence_rmse**2 if persistence_rmse>1e-12 else None)
    total_variation=sum((v-mean(truth))**2 for v in truth)
    r2=(1-sum(e*e for e in errors)/total_variation
        if total_variation>1e-12 else None)
    ordered=sorted(abs(e) for e in errors)
    p90=ordered[ceil(.9*length)-1]
    metrics=ValidationMetrics(
        rmse_c=rmse,mae_c=sum(abs(e) for e in errors)/length,
        bias_c=sum(errors)/length,
        persistence_rmse_c=persistence_rmse,
        skill_vs_persistence=skill,r_squared=r2,
        observed_abs_error_p90_c=p90,points=length
    )
    notes=[
        "Dados ordenados temporalmente: o treino utiliza apenas as primeiras transições.",
        "Previsão autoregressiva no segmento final, sem usar temperaturas futuras para corrigir o modelo.",
        "A faixa P90 é um quantil empírico de erros neste teste; NÃO representa intervalo de confiança calibrado.",
        "O modelo tem uma só capacidade térmica; não equivale aos modelos CPU–dissipador de dois nós.",
        "A excitação dos dados e a calibração de potência térmica são condições necessárias para alegar validade física.",
    ]
    if series.origin=="SIMULATED":
        notes.append("Resultados provenientes de dados sintéticos; não constituem validação experimental.")
    else:
        notes.append("Dados declarados medidos, sem verificação externa da cadeia de sensores, calibração ou sincronismo.")
    if skill is not None and skill<=0:
        notes.append("O modelo NÃO ultrapassou o baseline de persistência no holdout.")
    if token is not None:
        token.check()
    return ThermalTwinReport(
        series.origin,count+1,length,model,metrics,
        tuple(times),tuple(measured),tuple(predicted),tuple(notes)
    )


def forecast_scenario(series:ThermalSeries,report:ThermalTwinReport,*,
                      power_w:float,ambient_c:float,horizon_s:float=120.) -> tuple[tuple[float,...],tuple[float,...]]:
    """Forecast a hypothetical constant-input experiment *within train domain*."""
    m=report.model
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v)
           for v in (power_w,ambient_c,horizon_s)):
        raise ValueError("Entrada futura inválida.")
    if (not m.train_power_min_w<=power_w<=m.train_power_max_w
            or not m.train_ambient_min_c<=ambient_c<=m.train_ambient_max_c):
        raise ValueError("Extrapolação recusada: entradas fora da faixa de calibração.")
    if not 0<horizon_s<=600:
        raise ValueError("Horizonte máximo de 600 segundos.")
    steps=ceil(horizon_s/m.dt_s)
    if steps>10000:
        raise ValueError("Orçamento de previsão excedido.")
    last=series.samples[-1]
    times=[last.time_s]
    values=[last.cpu_temp_c]
    t=last.time_s
    temperature=last.cpu_temp_c
    for i in range(steps):
        h=min(m.dt_s,horizon_s-i*m.dt_s)
        # Exact continuous-time discretization for the shorter final segment.
        alpha=exp(-h/m.tau_s)
        temperature=alpha*temperature+(1-alpha)*(ambient_c+m.resistance_k_w*power_w)
        t+=h
        values.append(temperature)
        times.append(t)
    return tuple(times),tuple(values)
