"""Measurement uncertainty; independent errors unless covariance is supplied."""
import math
from .numerical._validation import finite_values, samples


def repeatability(values, resolution=0.):
    values = finite_values(values)
    resolution = finite_values([resolution])[0]
    if len(values)<2 or resolution<0: raise ValueError('Duas repetições e resolução não negativa obrigatórias.')
    mean = math.fsum(values)/len(values)
    std = math.sqrt(math.fsum((v-mean)**2 for v in values)/(len(values)-1))
    u_resolution = resolution/math.sqrt(12)  # uniform rounding distribution
    return {'mean':mean,'sample_std':std,'standard_uncertainty_mean':math.hypot(std/math.sqrt(len(values)),u_resolution),
            'resolution_uncertainty':u_resolution}


def propagate(gradient, uncertainties, covariance=None):
    """First-order u_f² = gᵀΣg; covariance includes diagonal variances."""
    g,u = finite_values(gradient),finite_values(uncertainties)
    if not g or len(g)!=len(u) or min(u)<0: raise ValueError('Incertezas/pesos inválidos.')
    if covariance is None: return math.hypot(*(a*b for a,b in zip(g,u)))
    matrix = [finite_values(row) for row in covariance]
    n = len(g)
    if len(matrix)!=n or any(len(row)!=n for row in matrix): raise ValueError('Dimensão de covariância inválida.')
    # PSD check through a tolerance-aware LDL decomposition, including zero pivots.
    work = [row[:] for row in matrix]
    tolerance = max(1e-300,max(abs(v) for row in matrix for v in row))*1e-12
    for i in range(n):
        if not math.isclose(matrix[i][i],u[i]**2,rel_tol=1e-9,abs_tol=tolerance): raise ValueError('Diagonal incompatível com as incertezas.')
        for j in range(n):
            if abs(matrix[i][j]-matrix[j][i])>tolerance: raise ValueError('Covariância não simétrica.')
        pivot = work[i][i]
        if pivot < -tolerance: raise ValueError('Covariância não positiva semidefinida.')
        if pivot <= tolerance:
            if any(abs(work[i][j])>tolerance for j in range(i+1,n)): raise ValueError('Covariância não positiva semidefinida.')
            continue
        for j in range(i+1,n):
            for k in range(i+1,n): work[j][k] -= work[j][i]*work[i][k]/pivot
    variance = math.fsum(g[i]*matrix[i][j]*g[j] for i in range(n) for j in range(n))
    return math.sqrt(max(0.,variance))


def energy_uncertainty(times, power_uncertainties):
    """Independent power errors, exact time stamps, trapezoidal energy in J."""
    t,u = samples(times,power_uncertainties)
    if min(u)<0: raise ValueError('Incertezas não negativas obrigatórias.')
    weights = [(t[1]-t[0])/2]+[(t[i+1]-t[i-1])/2 for i in range(1,len(t)-1)]+[(t[-1]-t[-2])/2]
    return propagate(weights,u)
