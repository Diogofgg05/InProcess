"""Local signal analysis and linear one-dimensional acoustic propagation.

No microphone API. Imported samples have unverified provenance. Amplitudes are
in input units; no calibrated sound-pressure level or mechanical diagnosis.
"""
from dataclasses import dataclass
import cmath
import math

from .numerical._validation import finite_values, samples


@dataclass(frozen=True)
class Spectrum:
    frequencies: list[float]
    amplitudes: list[float]
    sample_rate: float
    resolution: float
    peak_frequency: float
    report: str


def spectrum(times, values, *, window='hann', expected_frequencies=(), token=None):
    """Radix-2 FFT without padding/truncation. Uniform 2^n samples required.

    One-sided coherent-gain-corrected amplitudes; DC is removed. Frequency
    resolution fs/N; Hann leakage and unresolved tones remain limitations.
    Aliasing cannot be inferred uniquely from sampled data alone.
    """
    t,y = samples(times,values,minimum=8)
    n = len(y)
    if n > 65536 or n & (n-1):
        raise ValueError('FFT exige 8 a 65536 amostras, em potência de dois; sem truncagem silenciosa.')
    dt = (t[-1]-t[0])/(n-1)
    if any(not math.isclose(b-a,dt,rel_tol=1e-7,abs_tol=dt*1e-9) for a,b in zip(t,t[1:])):
        raise ValueError('FFT exige amostragem uniforme; reamostrar apenas com hipóteses explícitas.')
    if window not in ('hann','rectangular'): raise ValueError('Janela inválida.')
    weights = [.5-.5*math.cos(2*math.pi*i/n) for i in range(n)] if window == 'hann' else [1.]*n
    mean = math.fsum(y)/n
    a = [complex((v-mean)*w) for v,w in zip(y,weights)]
    j = 0
    for i in range(1,n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j: a[i],a[j] = a[j],a[i]
    size = 2
    while size <= n:
        if token: token.check()
        factor = cmath.exp(-2j*math.pi/size)
        for start in range(0,n,size):
            w = 1.
            for k in range(size//2):
                u,v = a[start+k],w*a[start+k+size//2]
                a[start+k],a[start+k+size//2] = u+v,u-v
                w *= factor
        size *= 2
    scale = math.fsum(weights)
    amplitude = [abs(a[k])*(1 if k in (0,n//2) else 2)/scale for k in range(n//2+1)]
    fs = 1/dt
    f = [k*fs/n for k in range(n//2+1)]
    expected = finite_values(expected_frequencies)
    if any(v < 0 for v in expected): raise ValueError('Frequências esperadas não negativas obrigatórias.')
    warning = 'Risco de aliasing: frequência esperada ≥ Nyquist.' if any(v >= fs/2 for v in expected) else 'Ausência de aliasing não demonstrável apenas pelas amostras.'
    if token: token.check()
    return Spectrum(f,amplitude,fs,fs/n,f[max(range(1,len(f)),key=lambda k:amplitude[k])],
                    f'FFT unilateral; DC removida; janela {window}; Δf={fs/n:g} Hz; Nyquist={fs/2:g} Hz. '+warning+
                    ' Amplitude na unidade de entrada, sem dB SPL calibrados. Um pico não identifica uma avaria ou fonte mecânica.')


def tonal_frequencies(rpm, blades=1):
    rpm = finite_values([rpm])[0]
    if rpm < 0 or not isinstance(blades,int) or isinstance(blades,bool) or blades < 1:
        raise ValueError('RPM não negativas e número inteiro positivo de pás obrigatórios.')
    return {'rotation_hz':rpm/60,'blade_passage_hz':blades*rpm/60}


def wave_field(position, time, frequency=100., speed=343., amplitude=1., reflection=.5, length=1., attenuation=0.):
    """Incident + reflected plane wave, p in Pa, x in m, t in s.

    alpha=0 is an exact solution of p_tt=c² p_xx in a homogeneous medium.
    alpha>0 is a phenomenological lossy extension, not that lossless PDE.
    Reflection coefficient is a pressure amplitude ratio at x=length.
    """
    position,time,frequency,speed,amplitude,reflection,length,attenuation = finite_values(
        [position,time,frequency,speed,amplitude,reflection,length,attenuation])
    if speed <= 0 or frequency < 0 or length <= 0 or attenuation < 0 or not 0 <= position <= length or abs(reflection)>1:
        raise ValueError('Parâmetros da onda fora do domínio físico.')
    omega = 2*math.pi*frequency
    incident = amplitude*math.exp(-attenuation*position)*math.cos(omega*(time-position/speed))
    reflected = reflection*amplitude*math.exp(-attenuation*(2*length-position))*math.cos(omega*(time-(2*length-position)/speed))
    return incident+reflected
