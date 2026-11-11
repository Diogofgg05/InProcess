"""Minimal SI dimension checks for the supported physical balance equations."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Dimension:
    mass: int=0
    length: int=0
    time: int=0
    temperature: int=0
    current: int=0

    def __mul__(self,other):
        return Dimension(*(a+b for a,b in zip(self.vector,other.vector)))

    def __truediv__(self,other):
        return Dimension(*(a-b for a,b in zip(self.vector,other.vector)))

    def __pow__(self,power: int):
        if not isinstance(power,int): raise ValueError('O expoente dimensional deve ser inteiro.')
        return Dimension(*(a*power for a in self.vector))

    @property
    def vector(self): return self.mass,self.length,self.time,self.temperature,self.current


KG=Dimension(mass=1)
M=Dimension(length=1)
S=Dimension(time=1)
K=Dimension(temperature=1)
J=KG*M**2/S**2
W=J/S
A=Dimension(current=1)
V=W/A
OHM=V/A
F=A*S/V
H=V*S/A
THERMAL_CAPACITY=J/K
THERMAL_CONDUCTANCE=W/K


def verify_balances():
    return {'power_integral':W*S==J,'thermal_storage':THERMAL_CAPACITY*K==J,
            'thermal_rate':THERMAL_CAPACITY*K/S==W,
            'heat_transfer':THERMAL_CONDUCTANCE*K==W,
            'time_constant':THERMAL_CAPACITY/THERMAL_CONDUCTANCE==S,
            'mechanical_energy':KG*(M/S)**2==J,
            'joule_heating':OHM*A**2==W, 'capacitor_energy':F*V**2==J,
            'inductor_energy':H*A**2==J, 'rc_time':OHM*F==S, 'rl_time':H/OHM==S}


# scale, offset: SI value = value*scale+offset. Temperature differences use K.
_UNITS = {
    's':(S,1,0), 'ms':(S,.001,0), 'K':(K,1,0), '°C':(K,1,273.15),
    'J':(J,1,0), 'Wh':(J,3600,0), 'W':(W,1,0), 'mW':(W,.001,0),
    'A':(A,1,0), 'mA':(A,.001,0), 'V':(V,1,0), 'Ω':(OHM,1,0),
    'F':(F,1,0), 'µF':(F,1e-6,0), 'H':(H,1,0), 'mH':(H,.001,0),
    'kg':(KG,1,0), 'N':(KG*M/S**2,1,0), 'N·m':(J,1,0),
    'kg·m²':(KG*M**2,1,0), 'm/s':(M/S,1,0), 'm/s²':(M/S**2,1,0),
    'Hz':(S**-1,1,0), 'rad/s':(S**-1,1,0), 'RPM':(S**-1,1,0),
}


def convert(value, source, target, *, rotational=False):
    """Convert compatible units; cyclic/angular frequency needs explicit context."""
    import math
    if source not in _UNITS or target not in _UNITS:
        raise ValueError('Unidade não suportada.')
    value = float(value)
    d1,s1,o1 = _UNITS[source]
    d2,s2,o2 = _UNITS[target]
    frequencies = {'Hz','RPM','rad/s'}
    if source != target and source in frequencies and target in frequencies:
        if not rotational:
            raise ValueError('A conversão exige uma frequência de rotação identificada.')
        factors = {'Hz':1., 'RPM':1/60, 'rad/s':1/(2*math.pi)}
        result = value*factors[source]/factors[target]
    else:
        if d1 != d2:
            raise ValueError('Dimensões incompatíveis.')
        result = (value*s1+o1-o2)/s2
    if not math.isfinite(result):
        raise ValueError('A conversão deve produzir um valor finito.')
    if source in ('K','°C') and value*s1+o1 < 0:
        raise ValueError('Temperatura abaixo do zero absoluto.')
    return result
