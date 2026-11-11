import math
import pytest
from expecto_process_manager.physics.thermal_model import ThermalModel
from expecto_process_manager.physics.euler import simulate
from expecto_process_manager.physics.integration import integrate
from expecto_process_manager.physics.differentiation import derivative,smooth
from expecto_process_manager.physics.validation import errors
from expecto_process_manager.simulation.noise import add_noise


def test_analytic_and_first_order_convergence():
    model = ThermalModel()
    assert model.exact(40,36,100) == pytest.approx(40)
    fine = simulate(model,40,lambda t:80,100,.1)
    coarse = simulate(model,40,lambda t:80,100,1)
    assert fine.reference[-1] == pytest.approx(model.exact(40,80,100))
    ratio = errors(coarse.temperatures,coarse.reference)['rmse']/errors(fine.temperatures,fine.reference)['rmse']
    assert 9 < ratio < 11


def test_endpoint_and_stability():
    result = simulate(ThermalModel(),40,lambda t:45,1,.3)
    assert result.times[-1] == 1
    assert len(result.times) == len(result.temperatures) == len(result.powers)
    with pytest.raises(ValueError):
        simulate(ThermalModel(),40,lambda t:45,200,100)


@pytest.mark.parametrize('method', ['rectangle','trapezoid','simpson'])
def test_constant_energy(method):
    assert integrate([0,1,2],[45,45,45],method) == pytest.approx(90)


def test_integration_reference():
    times = [i/10 for i in range(11)]
    values = [t*t for t in times]
    assert integrate(times,values,'simpson') == pytest.approx(1/3)
    assert abs(integrate(times,values,'trapezoid')-1/3) < abs(integrate(times,values,'rectangle')-1/3)


@pytest.mark.parametrize('times,values,method', [([0,1,1],[0,1,2],'rectangle'),([0,1],[0,1],'simpson'),([0,1,3],[0,1,2],'simpson'),([0,math.nan],[0,1],'trapezoid'),([0,1],[0],'rectangle')])
def test_invalid_integration(times,values,method):
    with pytest.raises(ValueError):
        integrate(times,values,method)


def test_derivative_nonuniform():
    times = [0,.1,.3,1]
    result = derivative(times,[t*t for t in times])
    assert result[1:-1] == pytest.approx([.2,.6])


def test_noise_and_filter():
    times = [i/100 for i in range(1001)]
    clean = [math.sin(t) for t in times]
    noisy = add_noise(clean,.1)
    d = derivative(times,clean)
    assert errors(derivative(times,smooth(noisy)),d)['rmse'] < errors(derivative(times,noisy),d)['rmse']
    assert add_noise(clean,.1) == noisy


def test_invalid_parameters():
    with pytest.raises(ValueError):
        ThermalModel(capacity=0)
    with pytest.raises(ValueError):
        simulate(ThermalModel(),40,lambda t:-1,1,.1)
    assert errors([1],[0])['relative'] == [None]
