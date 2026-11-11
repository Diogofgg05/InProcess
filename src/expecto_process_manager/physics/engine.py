"""Reusable scientific API. No Qt, psutil, operating-system actions or LLMs."""
from .numerical.derivatives import differentiate
from .numerical.integration import quadrature,integrate_midpoints
from .numerical.ode import solve_ivp
from .numerical.thermalcomparison import compare_thermal,time_to_threshold
from .numerical.validation import metrics,convergence_study,sensitivity_study,linear_stability
from .numerical.signals import moving_average,exponential_filter,add_gaussian_noise
from .hardware_models import heat_path, parallel_plates, ohm
from .acoustics import spectrum, wave_field, tonal_frequencies
from .measurement import repeatability, propagate, energy_uncertainty


class ScientificPhysicsEngine:
    ohm=staticmethod(ohm)
    heat_path=staticmethod(heat_path)
    parallel_plates=staticmethod(parallel_plates)
    spectrum=staticmethod(spectrum)
    wave_field=staticmethod(wave_field)
    tonal_frequencies=staticmethod(tonal_frequencies)
    repeatability=staticmethod(repeatability)
    propagate_uncertainty=staticmethod(propagate)
    energy_uncertainty=staticmethod(energy_uncertainty)

    @staticmethod
    def hardware_experiment(*args,**kwargs):
        from ..simulation.hardware_experiments import run_hardware
        return run_hardware(*args,**kwargs)

    differentiate=staticmethod(differentiate)
    integrate=staticmethod(quadrature)
    integrate_midpoints=staticmethod(integrate_midpoints)
    solve=staticmethod(solve_ivp)
    compare_thermal=staticmethod(compare_thermal)
    time_to_threshold=staticmethod(time_to_threshold)
    errors=staticmethod(metrics)
    convergence=staticmethod(convergence_study)
    sensitivity=staticmethod(sensitivity_study)
    stability=staticmethod(linear_stability)
    moving_average=staticmethod(moving_average)
    exponential_filter=staticmethod(exponential_filter)
    gaussian_noise=staticmethod(add_gaussian_noise)

    @staticmethod
    def compare_energy_policies(*args,**kwargs):
        from ..optimization.eco import compare_policies
        return compare_policies(*args,**kwargs)

    @staticmethod
    def cooling(*args,**kwargs):
        from .cooling import simulate_cooling
        return simulate_cooling(*args,**kwargs)

    @staticmethod
    def calibrate(*args,**kwargs):
        from .calibration import fit_thermal
        return fit_thermal(*args,**kwargs)

    @staticmethod
    def coupled_thermal(*args,**kwargs):
        from .coupled_thermal import simulate_coupled
        return simulate_coupled(*args,**kwargs)
