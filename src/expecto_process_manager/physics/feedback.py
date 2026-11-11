"""Illustrative thermal proportional feedback with actuator response lag.

Nonlinear saturation does not constitute evidence of chaos. No OS commands.
"""
from dataclasses import dataclass
import math
from .hardware_models import _validate


@dataclass(frozen=True)
class ThermalFeedback:
    capacity: float = 180.
    ambient: float = 25.
    power: float = 45.
    base: float = .8  # W/K
    gain: float = 3.  # W/K per dimensionless command
    target: float = 45.
    proportional: float = .1  # 1/K
    lag: float = 5.  # s, actuator time constant, not a pure dead time
    disturbance: float = 0.  # W
    frequency: float = .05  # Hz

    def __post_init__(self):
        _validate(self, ('capacity','base','lag'), ('power','gain','proportional','disturbance','frequency'))
        if self.disturbance>self.power or min(self.ambient,self.target)<-273.15:
            raise ValueError('Potência perturbada e temperaturas devem permanecer físicas.')

    def command(self,temp): return min(1.,max(0.,self.proportional*(temp-self.target)))

    def rhs(self,t,y):
        temp,u = y
        power = self.power+self.disturbance*math.sin(2*math.pi*self.frequency*t)
        return [(power-(self.base+self.gain*u)*(temp-self.ambient))/self.capacity,
                (self.command(temp)-u)/self.lag]

    def equilibrium_analysis(self):
        low,high = self.ambient,self.ambient+self.power/self.base
        for _ in range(80):
            middle = (low+high)/2
            if (self.base+self.gain*self.command(middle))*(middle-self.ambient)<self.power: low=middle
            else: high=middle
        temp = (low+high)/2
        u = self.command(temp)
        slope = self.proportional if 0<u<1 else 0.
        a = -(self.base+self.gain*u)/self.capacity
        b = -self.gain*(temp-self.ambient)/self.capacity
        c,d = slope/self.lag,-1/self.lag
        trace,det = a+d,a*d-b*c
        return {'temperature_c':temp,'control':u,'trace_s_inv':trace,'determinant_s_inv2':det,
                'locally_stable':trace<0 and det>0,'oscillatory_linearization':trace*trace<4*det,
                'at_saturation_boundary':math.isclose(self.proportional*(temp-self.target),0.,abs_tol=1e-9) or math.isclose(self.proportional*(temp-self.target),1.,abs_tol=1e-9)}

    def observables(self,y):
        temp,u = y
        return {'temperature_c':temp,'control':u,'conductance_w_k':self.base+self.gain*u}
