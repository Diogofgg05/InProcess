"""Identifiable thermal fitting with disjoint holdout data and no new dependencies.

The exact interval model assumes zero-order-held thermal power, fixed ambient
temperature and positive constant C and k. Sensor electrical power is not
automatically the thermal power entering this model.
"""
from collections.abc import Sequence
from dataclasses import dataclass
import math

from .numerical._validation import finite_result, finite_values, samples
from .numerical.derivatives import differentiate
from .numerical.ode import CancellationToken
from .numerical.validation import ErrorMetrics, metrics

MAX_SAMPLES = 20_000
MAX_CONDITION = 1e6


@dataclass(frozen=True)
class ThermalSeries:
    """Times in seconds on one common origin, temperatures °C, thermal powers W."""
    times: Sequence[float]
    temperatures: Sequence[float]
    powers: Sequence[float]


@dataclass(frozen=True)
class CalibrationEvaluation:
    times: list[float]
    observed: list[float]
    predicted: list[float]
    residuals: list[float]
    errors: ErrorMetrics
    residual_mean: float
    residual_std: float
    residual_lag1: float | None


@dataclass(frozen=True)
class CalibrationResult:
    capacity: float
    dissipation: float
    time_constant: float
    method: str
    condition_number: float
    training: CalibrationEvaluation
    validation: CalibrationEvaluation
    report: str


def _series(data: ThermalSeries, minimum: int) -> ThermalSeries:
    times, temperatures = samples(data.times, data.temperatures, minimum=minimum)
    _, powers = samples(times, data.powers, minimum=minimum)
    if min(temperatures) < -273.15:
        raise ValueError('Temperatura abaixo do zero absoluto.')
    if any(power < 0 for power in powers):
        raise ValueError("As potências térmicas de aquecimento devem ser não negativas.")
    return ThermalSeries(times, temperatures, powers)


def predict_zoh(
    times: Sequence[float], powers: Sequence[float], initial: float,
    ambient: float, capacity: float, dissipation: float,
) -> list[float]:
    """Exact interval propagation: P_i applies on [t_i,t_(i+1)[, not interpolated."""
    x, p = samples(times, powers)
    initial, ambient, capacity, dissipation = finite_values([initial, ambient, capacity, dissipation], "parâmetros térmicos")
    if capacity <= 0 or dissipation <= 0:
        raise ValueError("C e k devem ser positivos.")
    if min(initial,ambient) < -273.15:
        raise ValueError('Temperatura abaixo do zero absoluto.')
    if any(value < 0 for value in p):
        raise ValueError("As potências térmicas de aquecimento devem ser não negativas.")
    result = [initial]
    rate = dissipation / capacity
    for a, b, power in zip(x, x[1:], p):
        exponent = -rate * (b - a)
        decay = math.exp(exponent)
        fraction = -math.expm1(exponent)
        temperature = ambient + (result[-1] - ambient) * decay + (power / dissipation) * fraction
        result.append(finite_result(temperature))
    return result


def _condition(first: list[float], second: list[float]) -> float:
    """2-norm condition of two log-parameter sensitivity columns."""
    scale = max(max(abs(value) for value in first), max(abs(value) for value in second))
    if scale == 0 or not math.isfinite(scale):
        raise ValueError("Os parâmetros não são identificáveis: não existe excitação térmica suficiente.")
    a = math.fsum((value / scale) ** 2 for value in first)
    c = math.fsum((value / scale) ** 2 for value in second)
    b = math.fsum((x / scale) * (y / scale) for x, y in zip(first, second))
    largest = (a + c + math.hypot(a - c, 2 * b)) / 2
    determinant = a * c - b * b
    if largest <= 0 or determinant <= 0:
        raise ValueError("C e k não são identificáveis independentemente: matriz sem posto completo.")
    smallest = determinant / largest
    condition = math.sqrt(largest / smallest)
    if not math.isfinite(condition) or condition > MAX_CONDITION:
        raise ValueError("C e k não são identificáveis com fiabilidade: ajuste mal condicionado.")
    return condition


def _jacobian_condition(data: ThermalSeries, ambient: float, capacity: float, dissipation: float) -> float:
    first, second = [], []
    rate = dissipation / capacity
    for left, right, temperature, power in zip(data.times, data.times[1:], data.temperatures, data.powers):
        h = right - left
        exponent = -rate * h
        decay = math.exp(exponent)
        heat_gain = power / dissipation
        sensitivity_c = decay * rate * h * (temperature - ambient - heat_gain)
        sensitivity_k = -sensitivity_c - heat_gain * (-math.expm1(exponent))
        first.append(finite_result(sensitivity_c))
        second.append(finite_result(sensitivity_k))
    return _condition(first, second)


def _fit_exact(data: ThermalSeries, ambient: float, token: CancellationToken | None) -> tuple[float, float]:
    # Variable projection: for each b=k/C>0 the gain g=1/k is a linear
    # least-squares parameter. Search log(b), then refine the best grid bracket.
    steps = [b - a for a, b in zip(data.times, data.times[1:])]
    theta = [finite_result(value - ambient) for value in data.temperatures]
    power_scale = max(data.powers[:-1])
    if power_scale <= 0:
        raise ValueError("Com P=0 apenas k/C é identificável; não é possível separar C de k.")
    temp_scale = max(1.0, max(abs(value) for value in theta))
    low = 1e-6 / (data.times[-1] - data.times[0])
    high = 30 / min(steps)
    if low <= 0 or not math.isfinite(high):
        raise ValueError("A escala temporal dos dados não permite um ajuste numérico fiável.")
    lower, upper = math.log(low), math.log(high)

    def objective(log_rate: float) -> tuple[float, float]:
        if token is not None:
            token.check()
        rate = math.exp(log_rate)
        sources, targets = [], []
        for i, h in enumerate(steps):
            exponent = -rate * h
            fraction = -math.expm1(exponent)
            sources.append((data.powers[i] / power_scale) * fraction)
            targets.append((theta[i + 1] / temp_scale) - math.exp(exponent) * (theta[i] / temp_scale))
        denominator = math.fsum(value * value for value in sources)
        if denominator == 0:
            return math.inf, 0.0
        gain_scaled = math.fsum(x * y for x, y in zip(sources, targets)) / denominator
        if gain_scaled <= 0 or not math.isfinite(gain_scaled):
            return math.inf, 0.0
        residual = math.fsum((y - gain_scaled * x) ** 2 for x, y in zip(sources, targets)) / len(sources)
        gain = (temp_scale / power_scale) * gain_scaled
        return residual, gain

    points = [lower + (upper - lower) * i / 80 for i in range(81)]
    grid = [objective(point) for point in points]
    best = min(range(len(grid)), key=lambda i: grid[i][0])
    if not math.isfinite(grid[best][0]) or best in (0, len(grid) - 1):
        raise ValueError("Não existe um mínimo físico identificável dentro da escala temporal observada.")
    a, b = points[best - 1], points[best + 1]
    ratio = (math.sqrt(5) - 1) / 2
    c, d = b - ratio * (b - a), a + ratio * (b - a)
    fc, fd = objective(c), objective(d)
    for _ in range(64):
        if fc[0] < fd[0]:
            b, d, fd = d, c, fc
            c = b - ratio * (b - a)
            fc = objective(c)
        else:
            a, c, fc = c, d, fd
            d = a + ratio * (b - a)
            fd = objective(d)
    log_rate = (a + b) / 2
    _, gain = objective(log_rate)
    if gain <= 0:
        raise ValueError("O ajuste não produziu parâmetros positivos.")
    dissipation = finite_result(1 / gain)
    capacity = finite_result(dissipation / math.exp(log_rate))
    return capacity, dissipation


def _fit_derivative(data: ThermalSeries, ambient: float) -> tuple[float, float]:
    # Exclude the one-sided endpoint derivatives; this still differentiates
    # noisy observations and is explicitly described as an approximation.
    derivative = differentiate(data.times, data.temperatures)[1:-1]
    first = list(data.powers[1:-1])
    second = [ambient - value for value in data.temperatures[1:-1]]
    norm_first, norm_second = math.hypot(*first), math.hypot(*second)
    if norm_first == 0:
        raise ValueError("Com P=0 apenas k/C é identificável; C e k não podem ser separados.")
    if norm_second == 0 or not math.isfinite(norm_first + norm_second):
        raise ValueError("Dados insuficientes para identificar C e k.")
    u = [value / norm_first for value in first]
    v = [value / norm_second for value in second]
    correlation = math.fsum(x * y for x, y in zip(u, v))
    determinant = 1 - correlation * correlation
    if determinant <= 1e-12:
        raise ValueError("Os parâmetros não são identificáveis: regressão sem posto completo.")
    scale = max(1.0, max(abs(value) for value in derivative))
    target = [value / scale for value in derivative]
    rhs_u = math.fsum(x * y for x, y in zip(u, target))
    rhs_v = math.fsum(x * y for x, y in zip(v, target))
    coefficient_a = ((rhs_u - correlation * rhs_v) / determinant) * (scale / norm_first)
    coefficient_b = ((rhs_v - correlation * rhs_u) / determinant) * (scale / norm_second)
    if coefficient_a <= 0 or coefficient_b <= 0:
        raise ValueError("A regressão não produziu C e k positivos; reveja o modelo, ruído e excitação.")
    return finite_result(1 / coefficient_a), finite_result(coefficient_b / coefficient_a)


def _evaluate(data: ThermalSeries, ambient: float, capacity: float, dissipation: float) -> CalibrationEvaluation:
    observed = list(data.temperatures)
    predicted = predict_zoh(data.times, data.powers, observed[0], ambient, capacity, dissipation)
    residuals = [value - forecast for value, forecast in zip(observed, predicted)]
    # The initial condition is supplied, not predicted; exclude it from metrics.
    errors = metrics(predicted[1:], observed[1:])
    mean = math.fsum(residuals[1:]) / (len(residuals) - 1)
    centered = [value - mean for value in residuals[1:]]
    variance = math.fsum(value * value for value in centered) / len(centered)
    denominator = math.fsum(value * value for value in centered)
    lag1 = math.fsum(a * b for a, b in zip(centered, centered[1:])) / denominator if denominator > 0 else None
    return CalibrationEvaluation(list(data.times), observed, predicted, residuals, errors, mean, math.sqrt(variance), lag1)


def fit_thermal(
    times: Sequence[float], temperatures: Sequence[float], powers: Sequence[float], ambient: float,
    *, method: str = "integral_zoh", validation: ThermalSeries | None = None,
    token: CancellationToken | None = None,
) -> CalibrationResult:
    """Fit C,k with an obligatory disjoint validation series.

    Without a separate validation series, reserve the last 30% chronologically
    (at least four samples) and fit the preceding samples (at least eight).
    No samples or intervals are shared. Separate series must use one common
    absolute/relative time origin and have nonoverlapping closed time windows.
    At most 20000 total samples are accepted. Power is held at its left value.
    """
    ambient = finite_values([ambient], "temperaturas ambiente")[0]
    if ambient < -273.15:
        raise ValueError('Ambiente abaixo do zero absoluto.')
    if method not in ("integral_zoh", "derivative"):
        raise ValueError("Escolha integral_zoh ou derivative para a calibração.")
    original = _series(ThermalSeries(times, temperatures, powers), 12 if validation is None else 8)
    if validation is None:
        count = max(4, math.ceil(len(original.times) * .3))
        split = len(original.times) - count
        if split < 8:
            raise ValueError("São necessárias oito amostras de treino e quatro de validação.")
        training = ThermalSeries(original.times[:split], original.temperatures[:split], original.powers[:split])
        holdout = ThermalSeries(original.times[split:], original.temperatures[split:], original.powers[split:])
        split_description = "Separação temporal automática: primeiros 70% para ajuste, últimos 30% para validação (arredondamento e mínimos aplicados)."
    else:
        training = original
        holdout = _series(validation, 4)
        if not (training.times[-1] < holdout.times[0] or holdout.times[-1] < training.times[0]):
            raise ValueError("Treino e validação devem usar janelas temporais disjuntas, sem amostras partilhadas.")
        split_description = "Validação fornecida numa janela temporal separada, sem sobreposição com o treino."
    if len(training.times) + len(holdout.times) > MAX_SAMPLES:
        raise ValueError(f"A calibração aceita no máximo {MAX_SAMPLES} amostras no total.")
    if max(training.temperatures) - min(training.temperatures) <= 1e-6:
        raise ValueError("Temperatura constante: C e k não são identificáveis independentemente.")
    if token is not None:
        token.check()
    capacity, dissipation = _fit_exact(training, ambient, token) if method == "integral_zoh" else _fit_derivative(training, ambient)
    condition = _jacobian_condition(training, ambient, capacity, dissipation)
    train = _evaluate(training, ambient, capacity, dissipation)
    check = _evaluate(holdout, ambient, capacity, dissipation)
    tau = finite_result(capacity / dissipation)
    lines = [
        "Calibração do modelo térmico concentrado — parâmetros ESTIMATED.",
        "C dT/dt = Pth − k(T − Ta), C e k positivos e constantes; temperatura ambiente constante.",
        f"C = {capacity:.8g} J/K; k = {dissipation:.8g} W/K; τ = C/k = {tau:.8g} s; Ta = {ambient:g} °C.",
        f"Método: {method}; condicionamento do Jacobiano em log(C), log(k) = {condition:.6g}.",
        split_description,
        f"Treino: {len(train.times)} amostras [{train.times[0]:g}, {train.times[-1]:g}] s; RMSE = {train.errors['rmse']:.6g} °C; MAE = {train.errors['mae']:.6g} °C; erro máximo = {train.errors['maximum']:.6g} °C.",
        f"Validação: {len(check.times)} amostras [{check.times[0]:g}, {check.times[-1]:g}] s; RMSE = {check.errors['rmse']:.6g} °C; MAE = {check.errors['mae']:.6g} °C; erro máximo = {check.errors['maximum']:.6g} °C.",
        f"Resíduo = observado − previsto. Média de validação = {check.residual_mean:.6g} °C; desvio padrão populacional = {check.residual_std:.6g} °C; autocorrelação de ordem 1 = {check.residual_lag1 if check.residual_lag1 is not None else 'indefinida (variância zero)' }.",
        "As previsões propagam a solução exata por intervalo com P_i constante; a temperatura inicial de cada série é fornecida e excluída das métricas.",
        "O ajuste integral usa mínimos quadrados de previsão a um passo, projeção do ganho 1/k, pesquisa limitada em log(k/C) e refinamento unidimensional.",
        "A origem das amostras deve ser declarada pelo utilizador: estas rotinas não certificam a existência de sensores nem convertem potência elétrica em potência térmica.",
        "Uma separação temporal reduz reutilização de dados, mas não equivale a uma repetição experimental independente. Um bom ajuste não valida sozinho a física nem fornece intervalos de confiança.",
    ]
    if method == "derivative":
        lines.append("Alternativa DERIV: regressão dT/dt = aP − b(T − Ta), C=1/a, k=b/a. Diferenciação e erros nas variáveis amplificam ruído e podem introduzir viés; descontinuidades de potência não são resolvidas por este método.")
    if condition > 1e3:
        lines.append("Atenção: sensibilidade elevada dos parâmetros; maior excitação e repetições experimentais são recomendadas.")
    if token is not None:
        token.check()
    return CalibrationResult(capacity, dissipation, tau, method, condition, train, check, "\n".join(lines))
