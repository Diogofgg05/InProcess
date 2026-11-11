"""Numerical methods independent of the desktop interface and system sensors."""

from .derivatives import differentiate
from .integration import integrate_midpoints, quadrature
from .ode import ODEResult, solve_ivp

__all__ = ["ODEResult", "differentiate", "integrate_midpoints", "quadrature", "solve_ivp"]
