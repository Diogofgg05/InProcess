"""InProcess 6.3: closed-loop thermal control laboratory (SIMULATED).

Two thermal capacitances + first-order fan dynamics; compare P, PI and PID.
The derivative acts on filtered measured temperature (no derivative kick on a
setpoint change), and the integral has conditional anti-windup. The plant is
stepped with a bounded explicit timestep; no OS process or fan is controlled.

A finite simulation cannot prove asymptotic closed-loop stability. The
reported settling is an *observed window criterion*, not eigenvalue proof.
"""
from dataclasses import dataclass, replace
import math

MODES = ("P", "PI", "PID")


@dataclass(frozen=True)
class ControlScenario:
    target_c: float = 47.0
    ambient_c: float = 24.0
    initial_die_c: float = 30.0
    initial_sink_c: float = 26.0
    base_power_w: float = 55.0
    disturbance_w: float = 35.0
    disturbance_at_s: float = 100.0
    disturbance_end_s: float = 180.0
    duration_s: float = 300.0
    dt_s: float = 0.2
    die_capacity_j_k: float = 120.0
    sink_capacity_j_k: float = 280.0
    interface_w_k: float = 6.0
    base_cooling_w_k: float = 1.2
    fan_gain_w_k: float = 2.0
    fan_time_constant_s: float = 3.0
    proportional_per_k: float = 0.06
    integral_per_k_s: float = 0.0015
    derivative_s_per_k: float = 0.15
    derivative_filter_s: float = 2.0
    max_integral_k_s: float = 350.0
    sensor_noise_amplitude_c: float = 0.0
    sensor_noise_hz: float = 1.3

    def __post_init__(self):
        for field in self.__dataclass_fields__:
            val=getattr(self,field)
            if isinstance(val,bool) or not isinstance(val,(int,float)) or not math.isfinite(val):
                raise ValueError(f"{field}: valor numérico finito obrigatório.")
        positive=("duration_s","dt_s","die_capacity_j_k","sink_capacity_j_k",
                  "interface_w_k","base_cooling_w_k","fan_time_constant_s",
                  "derivative_filter_s","max_integral_k_s","sensor_noise_hz")
        nonnegative=("base_power_w","disturbance_w","disturbance_at_s","disturbance_end_s",
                     "fan_gain_w_k","proportional_per_k","integral_per_k_s",
                     "derivative_s_per_k","sensor_noise_amplitude_c")
        if any(getattr(self,f)<=0 for f in positive) or any(getattr(self,f)<0 for f in nonnegative):
            raise ValueError("Parâmetros físicos e ganhos de controlo fora do domínio.")
        if min(self.ambient_c,self.initial_die_c,self.initial_sink_c,self.target_c)<-273.15:
            raise ValueError("Temperatura inferior ao zero absoluto.")
        if self.disturbance_at_s>self.disturbance_end_s or self.disturbance_end_s>self.duration_s:
            raise ValueError("Janela de perturbação deve estar dentro da duração.")
        if self.dt_s>min(self.die_capacity_j_k/self.interface_w_k,
                         self.sink_capacity_j_k/(self.interface_w_k+
                                                 self.base_cooling_w_k+self.fan_gain_w_k)):
            raise ValueError("Passo temporal demasiado elevado para a integração explícita.")
        if math.ceil(self.duration_s/self.dt_s)>30000:
            raise ValueError("Orçamento máximo de 30000 passos excedido.")


@dataclass(frozen=True)
class ControlMetrics:
    peak_die_c: float
    final_die_c: float
    final_abs_error_c: float
    iae_c_s: float
    itae_c_s2: float
    fan_mean_fraction: float
    fan_total_variation: float
    saturated_fraction: float
    observed_settling_s: float | None
    max_rate_c_s: float
    observed_bounded: bool
    energy_balance_residual_j: float


@dataclass(frozen=True)
class ControlTrace:
    mode: str
    times_s: tuple[float,...]
    die_c: tuple[float,...]
    sink_c: tuple[float,...]
    fan_fraction: tuple[float,...]
    command_fraction: tuple[float,...]
    sensor_c: tuple[float,...]
    power_w: tuple[float,...]
    metrics: ControlMetrics
    provenance: str = "SIMULATED"


def _disturbance_power(s:ControlScenario,t:float) -> float:
    return (s.base_power_w+s.disturbance_w
            if s.disturbance_at_s<=t<s.disturbance_end_s else s.base_power_w)


def simulate_control(s:ControlScenario|None=None, *, mode:str="PID",token=None) -> ControlTrace:
    s=s if s is not None else ControlScenario()
    if mode not in MODES:
        raise ValueError("Controlador inválido: P, PI ou PID.")
    n=math.ceil(s.duration_s/s.dt_s)
    h=s.duration_s/n
    die,sink,fan=s.initial_die_c,s.initial_sink_c,0.0
    integral=0.0
    filtered=s.initial_die_c
    time=[0.0]
    die_tr=[die]
    sink_tr=[sink]
    fan_tr=[fan]
    cmd_tr=[0.0]
    sensor_tr=[die]
    power_tr=[_disturbance_power(s,0.)]
    saturation=0
    variation=0.0
    iae=0.0
    itae=0.0
    peak=die
    max_rate=0.0
    heat_in_j=0.0
    ambient_loss_j=0.0

    def stored(d,si):
        return (s.die_capacity_j_k*(d-s.ambient_c)+
                s.sink_capacity_j_k*(si-s.ambient_c))

    initial_energy=stored(die,sink)
    for i in range(n):
        if token is not None and i%64==0:
            token.check()
        t=i*h
        power=_disturbance_power(s,t)
        # Deterministic perturbation; not calibrated sensor noise.
        measured=die+s.sensor_noise_amplitude_c*math.sin(2*math.pi*s.sensor_noise_hz*t)
        # Exact update of first-order low-pass on measurement.
        alpha=1-math.exp(-h/s.derivative_filter_s)
        next_filtered=filtered+alpha*(measured-filtered)
        # Filtering the temperature before differentiation avoids setpoint kicks.
        rate=(next_filtered-filtered)/h
        error=measured-s.target_c
        kp=s.proportional_per_k*error
        ki=s.integral_per_k_s*integral if mode in ("PI","PID") else 0.0
        kd=s.derivative_s_per_k*rate if mode=="PID" else 0.0
        raw=kp+ki+kd
        cmd=max(0.0,min(1.0,raw))
        if mode in ("PI","PID"):
            # Anti-windup: freeze integral only when error pushes further
            # into saturation, with a finite integral clamp.
            if (0<raw<1 or (raw<=0 and error>0)
                    or (raw>=1 and error<0)):
                integral=max(-s.max_integral_k_s,
                             min(s.max_integral_k_s,integral+h*error))
        if raw<=0 or raw>=1:
            saturation+=1
        # Stable exact step for fan actuator with zero-order held command.
        next_fan=cmd+(fan-cmd)*math.exp(-h/s.fan_time_constant_s)
        interface=s.interface_w_k*(die-sink)
        convection=(s.base_cooling_w_k+s.fan_gain_w_k*fan)*(sink-s.ambient_c)
        next_die=die+h*(power-interface)/s.die_capacity_j_k
        next_sink=sink+h*(interface-convection)/s.sink_capacity_j_k
        if (not all(math.isfinite(v) for v in (next_die,next_sink,next_fan))
                or min(next_die,next_sink)<-273.15
                or not 0<=next_fan<=1):
            raise ValueError("Instabilidade numérica ou estado não físico.")
        heat_in_j+=h*power
        ambient_loss_j+=h*convection
        iae+=h*abs(error)
        itae+=h*t*abs(error)
        variation+=abs(next_fan-fan)
        max_rate=max(max_rate,abs(next_die-die)/h)
        die,sink,fan=next_die,next_sink,next_fan
        filtered=next_filtered
        peak=max(peak,die)
        time.append((i+1)*h)
        die_tr.append(die)
        sink_tr.append(sink)
        fan_tr.append(fan)
        cmd_tr.append(cmd)
        sensor_tr.append(measured)
        power_tr.append(power)
    if token is not None:
        token.check()

    # Observed settling only AFTER the perturbation ends, and only when all
    # remaining samples stay inside a ±2 °C tolerance around the setpoint.
    end_idx=next((i for i,t in enumerate(time) if t>=s.disturbance_end_s),len(time)-1)
    last_outside=max((i for i in range(end_idx,len(time))
                      if abs(die_tr[i]-s.target_c)>2.0),default=end_idx-1)
    settling=(time[last_outside+1]-s.disturbance_end_s
              if last_outside+1<len(time) else None)
    balance=(stored(die,sink)-initial_energy)-heat_in_j+ambient_loss_j
    metrics=ControlMetrics(
        peak_die_c=peak,final_die_c=die,
        final_abs_error_c=abs(die-s.target_c),
        iae_c_s=iae,itae_c_s2=itae,
        fan_mean_fraction=sum(fan_tr)/len(fan_tr),
        fan_total_variation=variation,
        saturated_fraction=saturation/n,
        observed_settling_s=settling,
        max_rate_c_s=max_rate,
        observed_bounded=all(math.isfinite(v) and v>=-273.15 for v in die_tr+sink_tr),
        energy_balance_residual_j=balance,
    )
    return ControlTrace(mode,tuple(time),tuple(die_tr),tuple(sink_tr),
                        tuple(fan_tr),tuple(cmd_tr),tuple(sensor_tr),
                        tuple(power_tr),metrics)


def compare_controllers(s:ControlScenario|None=None, token=None) -> dict[str,ControlTrace]:
    s=s if s is not None else ControlScenario()
    return {mode:simulate_control(s,mode=mode,token=token) for mode in MODES}


def gain_sensitivity(s:ControlScenario|None=None,token=None) -> list[dict]:
    s=s if s is not None else ControlScenario()
    rows=[]
    for multiplier in (.75,1.,1.25):
        if token is not None:token.check()
        changed=replace(s,proportional_per_k=s.proportional_per_k*multiplier,
                        integral_per_k_s=s.integral_per_k_s*multiplier,
                        derivative_s_per_k=s.derivative_s_per_k*multiplier)
        result=simulate_control(changed,mode="PID",token=token)
        rows.append({"gain_factor":multiplier,
                     "iae_c_s":result.metrics.iae_c_s,
                     "peak_c":result.metrics.peak_die_c,
                     "saturation":result.metrics.saturated_fraction})
    return rows
