"""SI hardware models, independent of solvers, GUI and acquisition.

Idealized educational components; parameters are never hardware measurements.
Each rhs receives t,y for the existing generic Euler/Heun/RK4 engine.
"""
from dataclasses import dataclass, fields
import math

from .numerical._validation import finite_values


def _validate(model, positive=(), nonnegative=()):
    names = [f.name for f in fields(model)]
    finite_values([getattr(model,n) for n in names], 'parâmetros físicos')
    if any(getattr(model,n) <= 0 for n in positive) or any(getattr(model,n) < 0 for n in nonnegative):
        raise ValueError('Parâmetros fora do domínio físico.')


@dataclass(frozen=True)
class RCCircuit:
    resistance: float = 1000.  # ohm
    capacitance: float = .001  # F
    voltage: float = 5.  # V; zero gives discharge

    def __post_init__(self):
        _validate(self, ('resistance','capacitance'))

    @property
    def time_constant(self): return self.resistance*self.capacitance

    def rhs(self,t,y): return [(self.voltage-y[0])/self.time_constant]

    def exact(self,t,initial=0.):
        return self.voltage+(initial-self.voltage)*math.exp(-t/self.time_constant)

    def observables(self,y):
        v = y[0]
        i = (self.voltage-v)/self.resistance
        return {'voltage_v':v,'current_a':i,'stored_j':.5*self.capacitance*v*v,
                'input_w':self.voltage*i,'joule_w':self.resistance*i*i}


@dataclass(frozen=True)
class RLCircuit:
    resistance: float = 10.
    inductance: float = 1.  # H
    voltage: float = 5.

    def __post_init__(self): _validate(self, ('resistance','inductance'))

    @property
    def time_constant(self): return self.inductance/self.resistance

    def rhs(self,t,y): return [(self.voltage-self.resistance*y[0])/self.inductance]

    def exact(self,t,initial=0.):
        eq = self.voltage/self.resistance
        return eq+(initial-eq)*math.exp(-t/self.time_constant)

    def observables(self,y):
        i = y[0]
        return {'current_a':i,'stored_j':.5*self.inductance*i*i,
                'input_w':self.voltage*i,'joule_w':self.resistance*i*i}


@dataclass(frozen=True)
class FanRotor:
    inertia: float = 1e-5  # kg m²
    torque: float = .002  # N m
    damping: float = 1e-5  # N m s
    drag: float = 0.  # N m s²; aerodynamic omega*abs(omega)

    def __post_init__(self): _validate(self, ('inertia',), ('damping','drag'))

    def rhs(self,t,y):
        w = y[0]
        return [(self.torque-self.damping*w-self.drag*w*abs(w))/self.inertia]

    def exact(self,t,initial=0.):
        if self.drag: raise ValueError('Referência analítica apenas para resistência linear.')
        if self.damping == 0: return initial+self.torque*t/self.inertia
        eq = self.torque/self.damping
        return eq+(initial-eq)*math.exp(-self.damping*t/self.inertia)

    @property
    def equilibrium(self):
        if self.drag:
            return 2*self.torque/(self.damping+math.sqrt(self.damping**2+4*self.drag*abs(self.torque))) if self.torque else 0.
        return self.torque/self.damping if self.damping else None

    def observables(self,y):
        w = y[0]
        return {'omega_rad_s':w,'rpm':w*60/(2*math.pi), 'acceleration_rad_s2':self.rhs(0,y)[0],
                'angular_momentum_kg_m2_s':self.inertia*w, 'stored_j':.5*self.inertia*w*w,
                'input_w':self.torque*w,'drag_w':self.damping*w*w+self.drag*abs(w)**3}


@dataclass(frozen=True)
class FanMotor:
    resistance: float = 10.
    inductance: float = .1
    voltage: float = 12.
    constant: float = .02  # Ke=Kt in coherent SI; ideal reversible conversion
    inertia: float = 1e-5
    damping: float = 1e-5
    drag: float = 0.
    capacity: float = 180.  # CPU thermal capacity J/K
    ambient: float = 25.
    thermal_power: float = 45.
    base_conductance: float = 1.
    speed_gain: float = .005  # W/K per rad/s, explicit uncalibrated hypothesis

    def __post_init__(self):
        _validate(self, ('resistance','inductance','inertia','capacity','base_conductance'),
                  ('constant','damping','drag','thermal_power','speed_gain'))
        if self.ambient < -273.15: raise ValueError('Ambiente abaixo do zero absoluto.')

    def rhs(self,t,y):
        i,w,temp = y
        conductance = self.base_conductance+self.speed_gain*abs(w)
        return [(self.voltage-self.resistance*i-self.constant*w)/self.inductance,
                (self.constant*i-self.damping*w-self.drag*w*abs(w))/self.inertia,
                (self.thermal_power-conductance*(temp-self.ambient))/self.capacity]

    def observables(self,y):
        i,w,temp = y
        return {'current_a':i, 'omega_rad_s':w,'rpm':w*60/(2*math.pi),'temperature_c':temp,
                'stored_j':.5*self.inductance*i*i+.5*self.inertia*w*w,
                'input_w':self.voltage*i,'joule_w':self.resistance*i*i,
                'mechanical_w':self.constant*i*w,'drag_w':self.damping*w*w+self.drag*abs(w)**3,
                'conductance_w_k':self.base_conductance+self.speed_gain*abs(w)}


@dataclass(frozen=True)
class Oscillator:
    mass: float = .02  # kg equivalent modal mass
    damping: float = .08  # kg/s
    stiffness: float = 20.  # N/m
    force: float = 0.  # N
    frequency: float = 5.  # Hz

    def __post_init__(self):
        _validate(self, ('mass','stiffness'), ('damping','frequency'))

    @property
    def natural_frequency(self): return math.sqrt(self.stiffness/self.mass)/(2*math.pi)

    @property
    def damping_ratio(self): return self.damping/(2*math.sqrt(self.mass*self.stiffness))

    @property
    def regime(self):
        z = self.damping_ratio
        return 'não amortecido' if z == 0 else 'crítico' if math.isclose(z,1,rel_tol=1e-10) else 'subamortecido' if z < 1 else 'sobreamortecido'

    @property
    def resonance_frequency(self):
        z = self.damping_ratio
        return self.natural_frequency*math.sqrt(1-2*z*z) if z < 1/math.sqrt(2) else None

    def rhs(self,t,y):
        x,v = y
        return [v,(self.force*math.cos(2*math.pi*self.frequency*t)-self.damping*v-self.stiffness*x)/self.mass]

    def exact_free(self,t,initial=(.001,0.)):
        x,v = initial
        a = self.damping/(2*self.mass)
        w0 = math.sqrt(self.stiffness/self.mass)
        if math.isclose(a,w0,rel_tol=1e-10): return math.exp(-a*t)*(x+(v+a*x)*t)
        if a < w0:
            wd = math.sqrt(w0*w0-a*a)
            return math.exp(-a*t)*(x*math.cos(wd*t)+(v+a*x)*math.sin(wd*t)/wd)
        # Separate decaying exponentials avoid overflow from cosh at large t.
        root = math.sqrt(a*a-w0*w0)
        r1 = -w0*w0/(a+root)
        r2 = -a-root
        c1 = (v-r2*x)/(r1-r2)
        return c1*math.exp(r1*t)+(x-c1)*math.exp(r2*t)

    def amplitude(self,frequency):
        frequency = finite_values([frequency])[0]
        if frequency < 0: raise ValueError('Frequência negativa.')
        w = 2*math.pi*frequency
        denominator = math.hypot(self.stiffness-self.mass*w*w,self.damping*w)
        return abs(self.force)/denominator if denominator else (math.inf if self.force else 0.)

    def exact_forced(self,t,initial=(0.,0.)):
        """Independent transient + particular solution, including ideal resonance."""
        if self.force==0: return self.exact_free(t,initial)
        w=2*math.pi*self.frequency
        detuning=self.stiffness-self.mass*w*w
        denominator=detuning**2+(self.damping*w)**2
        if self.damping==0 and math.isclose(w,math.sqrt(self.stiffness/self.mass),rel_tol=1e-12):
            return self.exact_free(t,initial)+self.force*t*math.sin(w*t)/(2*self.mass*w)
        particular=self.force*(detuning*math.cos(w*t)+self.damping*w*math.sin(w*t))/denominator
        xpart0=self.force*detuning/denominator
        vpart0=self.force*self.damping*w*w/denominator
        return particular+self.exact_free(t,(initial[0]-xpart0,initial[1]-vpart0))

    def observables(self,y):
        x,v = y
        return {'displacement_m':x,'velocity_m_s':v,'stored_j':.5*self.mass*v*v+.5*self.stiffness*x*x,
                'damping_w':self.damping*v*v}


def parallel_plates(voltage, separation, area, relative_permittivity=1.):
    voltage,separation,area,relative_permittivity = finite_values([voltage,separation,area,relative_permittivity])
    if min(separation,area,relative_permittivity) <= 0: raise ValueError('Geometria/permissividade positiva obrigatória.')
    capacitance = 8.8541878128e-12*relative_permittivity*area/separation
    return {'field_v_m':voltage/separation,'capacitance_f':capacitance,'energy_j':.5*capacitance*voltage**2}


def ohm(*,voltage=None,current=None,resistance=None):
    """Solve a passive Ohmic element from exactly two known quantities."""
    if sum(v is not None for v in (voltage,current,resistance))!=2:
        raise ValueError('Forneça exatamente duas grandezas entre V, I e R.')
    finite_values([v for v in (voltage,current,resistance) if v is not None])
    if resistance is not None and resistance<=0: raise ValueError('Resistência positiva obrigatória.')
    if voltage is None: voltage=resistance*current
    elif current is None: current=voltage/resistance
    else:
        if current==0: raise ValueError('Não é possível identificar R com corrente nula.')
        resistance=voltage/current
        if resistance<=0: raise ValueError('Os dados não descrevem uma resistência passiva positiva.')
    power=voltage*current
    finite_values([voltage,current,resistance,power])
    return {'voltage_v':voltage,'current_a':current,'resistance_ohm':resistance,'joule_w':power}


def heat_path(hot=60., cold=25., conductivity=200., area=.001, thickness=.005, h=25.):
    """Steady 1-D slab + convection in series; same heat traverses both."""
    hot,cold,conductivity,area,thickness,h = finite_values([hot,cold,conductivity,area,thickness,h])
    if min(conductivity,area,thickness,h) <= 0 or min(hot,cold) < -273.15:
        raise ValueError('Geometria/coeficientes positivos e temperaturas físicas obrigatórios.')
    conduction = thickness/(conductivity*area)
    convection = 1/(h*area)
    power = (hot-cold)/(conduction+convection)
    surface = cold+power*convection
    return {'conduction_k_w':conduction,'convection_k_w':convection,'heat_w':power,
            'surface_c':surface,'gradient_k_m':(surface-hot)/thickness,'flux_w_m2':power/area}
