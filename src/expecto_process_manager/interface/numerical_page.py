"""Safe preset numerical experiments, prepared entirely outside the GUI thread."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import time

from PySide6.QtCore import Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGridLayout, QHBoxLayout, QHeaderView, QLabel, QPushButton, QScrollArea,
    QSpinBox, QTableView, QVBoxLayout, QWidget,
)

from .charts import Plot
from .workers import Tasks
from ..core.metrics import export_csv
from ..physics.numerical import differentiate, integrate_midpoints, quadrature, solve_ivp
from ..physics.numerical.signals import add_gaussian_noise, moving_average
from ..physics.numerical.validation import convergence_study, linear_stability, metrics

MAX_INTERVALS = 20_000
MAX_PREVIEW = 1500
METHOD_NAMES = {"euler": "Euler explícito", "heun": "Euler melhorado · Heun", "rk4": "Runge–Kutta de 4.ª ordem"}
DERIVATIVE_NAMES = {"forward": "Diferença progressiva", "backward": "Diferença regressiva", "central": "Diferença centrada"}
QUADRATURE_NAMES = {"left": "Retângulos à esquerda", "right": "Retângulos à direita", "midpoint": "Pontos médios", "trapezoid": "Trapézios", "simpson": "Simpson composto"}
PRESET_NAMES = {"square": "f(t) = t²", "sine": "f(t) = sin(t)", "decay": "f(t) = exp(−t)"}


@dataclass
class NumericalExperiment:
    config: dict
    times: list[float]
    series: dict[str, list[float]]
    error_series: dict[str, list[float]]
    convergence: dict[str, list[tuple[float, float]]]
    results_table: list[dict]
    report: str
    provenance: str = "SIMULATED"
    input_series: dict[str, list[float]] = field(default_factory=dict)
    diagnostic_series: dict[str, list[float]] = field(default_factory=dict)
    preview_times: list[float] = field(default_factory=list)
    preview_series: dict[str, list[float]] = field(default_factory=dict)
    preview_errors: dict[str, list[float]] = field(default_factory=dict)
    preview_inputs: dict[str, list[float]] = field(default_factory=dict)
    preview_diagnostics: dict[str, list[float]] = field(default_factory=dict)
    context: dict = field(default_factory=dict)


def _check(token):
    if token is not None:
        token.check()


def _finite(value, name):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} deve ser um número finito.") from error
    if not math.isfinite(number):
        raise ValueError(f"{name} deve ser um número finito.")
    return number


def _configuration(parameters):
    config = {"mode": "derivatives", "preset": "square", "start": 0., "end": 2., "intervals": 100,
              "noise_sigma": 0., "seed": 42, "filter_window": 5, "ode_model": "decay", "coefficient": 1.,
              "initial": 1., "initial_velocity": 0., "dt": .05}
    config.update(parameters)
    if config["mode"] not in ("derivatives", "integration", "ode"):
        raise ValueError("Escolha Derivadas, Integração ou EDO.")
    if config["preset"] not in PRESET_NAMES:
        raise ValueError("Escolha um dos exemplos predefinidos; não se executam expressões de texto.")
    for name in ("start", "end", "noise_sigma", "coefficient", "initial", "initial_velocity", "dt"):
        config[name] = _finite(config[name], name)
    if config["end"] <= config["start"] or not math.isfinite(config["end"] - config["start"]):
        raise ValueError("O limite final deve ser maior que o inicial, com intervalo finito.")
    intervals = config["intervals"]
    if isinstance(intervals, bool) or not isinstance(intervals, int) or not 4 <= intervals <= MAX_INTERVALS:
        raise ValueError(f"Escolha entre 4 e {MAX_INTERVALS} intervalos.")
    if config["mode"] == "integration" and intervals % 2:
        raise ValueError("Simpson composto requer um número par de intervalos.")
    if config["noise_sigma"] < 0 or isinstance(config["seed"], bool) or not isinstance(config["seed"], int):
        raise ValueError("O ruído requer σ não negativo e uma semente inteira.")
    window = config["filter_window"]
    if isinstance(window, bool) or not isinstance(window, int) or not 1 <= window <= 101 or window % 2 == 0:
        raise ValueError("A janela do filtro deve ser ímpar, entre 1 e 101.")
    if config["mode"] == "ode":
        if config["ode_model"] not in ("decay", "oscillator"):
            raise ValueError("Escolha decaimento ou oscilador.")
        if config["coefficient"] < 0 or config["ode_model"] == "oscillator" and config["coefficient"] == 0:
            raise ValueError("Use a ≥ 0 para decaimento ou ω > 0 para o oscilador.")
        if config["dt"] <= 0 or (config["end"] - config["start"]) / config["dt"] > MAX_INTERVALS:
            raise ValueError(f"Escolha Δt positivo que não exceda {MAX_INTERVALS} passos na trajetória principal.")
    return config


def _grid(start, end, intervals):
    times = [start + (end - start) * i / intervals for i in range(intervals)] + [end]
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError("Intervalos demasiado pequenos para a escala do domínio.")
    return times


def _preset(name):
    """Closed catalogue: function, first/second derivative and primitive."""
    if name == "square":
        return lambda t: t * t, lambda t: 2 * t, lambda t: 2., lambda t: t**3 / 3
    if name == "sine":
        return math.sin, math.cos, lambda t: -math.sin(t), lambda t: -math.cos(t)
    if name == "decay":
        return lambda t: math.exp(-t), lambda t: -math.exp(-t), lambda t: math.exp(-t), lambda t: -math.exp(-t)
    raise ValueError("Função predefinida desconhecida.")


def _sample(function, times, token):
    values = []
    try:
        for index, t in enumerate(times):
            if index % 256 == 0:
                _check(token)
            value = function(t)
            if not math.isfinite(value):
                raise ValueError("O exemplo excedeu o domínio numérico finito.")
            values.append(value)
    except OverflowError as error:
        raise ValueError("O exemplo excedeu o domínio numérico; reduza o intervalo.") from error
    return values


def _result_row(name, value, exact, elapsed, error=None, **extra):
    absolute = abs(value - exact)
    return {"method": name, "value": value, "exact": exact, "absolute_error": absolute,
            "relative_error": absolute / abs(exact) if exact != 0 else None,
            "rmse": error["rmse"] if error else None,
            "maximum_error": error["maximum"] if error else absolute,
            "elapsed_ms": elapsed, **extra}


def _table_report(rows):
    lines = []
    for row in rows:
        relative = "indefinido (referência nula)" if row["relative_error"] is None else f"{row['relative_error']:.6g}"
        text = f"{row['method']}: valor final {row['value']:.10g}; referência {row['exact']:.10g}; erro absoluto final {row['absolute_error']:.6g}; erro relativo {relative}"
        if row["rmse"] is not None:
            text += f"; RMSE de toda a trajetória {row['rmse']:.6g}; erro máximo {row['maximum_error']:.6g}"
        lines.append(text + f"; tempo local do método {row['elapsed_ms']:.4g} ms.")
    return lines


def _derivatives(config, token):
    times = _grid(config["start"], config["end"], config["intervals"])
    function, first, second, _ = _preset(config["preset"])
    clean, reference, reference_second = (_sample(fn, times, token) for fn in (function, first, second))
    observations = add_gaussian_noise(clean, config["noise_sigma"], config["seed"])
    _check(token)
    series, errors, rows = {}, {}, []
    for method, name in DERIVATIVE_NAMES.items():
        _check(token)
        start = time.perf_counter()
        values = differentiate(times, observations, method)
        elapsed = (time.perf_counter() - start) * 1000
        error = metrics(values, reference)
        series[name], errors[name] = values, error["absolute"]
        rows.append(_result_row(name, values[-1], reference[-1], elapsed, error, quantity="primeira derivada"))
    series["Referência analítica · primeira derivada"] = reference
    inputs = {"Função sem ruído": clean}
    if config["noise_sigma"] > 0:
        filtered = moving_average(observations, config["filter_window"])
        inputs.update({"Observação sintética com ruído": observations, "Média móvel centrada": filtered})
        start = time.perf_counter()
        filtered_derivative = differentiate(times, filtered, "central")
        elapsed = (time.perf_counter() - start) * 1000
        name = "Diferença centrada · sinal filtrado"
        error = metrics(filtered_derivative, reference)
        series[name], errors[name] = filtered_derivative, error["absolute"]
        rows.append(_result_row(name, filtered_derivative[-1], reference[-1], elapsed, error, quantity="primeira derivada"))
    start = time.perf_counter()
    second_values = differentiate(times, observations, "central", order=2)
    elapsed = (time.perf_counter() - start) * 1000
    second_error = metrics(second_values, reference_second)
    rows.append(_result_row("Diferença centrada · segunda derivada", second_values[-1], reference_second[-1], elapsed, second_error, quantity="segunda derivada"))
    diagnostics = {"Segunda derivada numérica": second_values, "Referência analítica · segunda derivada": reference_second}
    h = (times[-1] - times[0]) / config["intervals"]
    report = ["EXPERIÊNCIA DE DERIVAÇÃO NUMÉRICA — SIMULATED.",
              f"Exemplo seguro: {PRESET_NAMES[config['preset']]}; domínio [{times[0]:g}, {times[-1]:g}], {config['intervals']} intervalos, h = {h:.8g}. Variáveis adimensionais; não são leituras de hardware.",
              "Diferença progressiva: [f(t+h)−f(t)]/h; regressiva: [f(t)−f(t−h)]/h. Ambas são de primeira ordem em malha uniforme.",
              "Diferença centrada: [f(t+h)−f(t−h)]/(2h), de segunda ordem no interior uniforme. Nos extremos usa um polinómio quadrático unilateral; as diferenças progressiva/regressiva usam a secante oposta no extremo indisponível.",
              "Segunda derivada centrada: [f(t+h)−2f(t)+f(t−h)]/h²; nos extremos desloca-se o stencil de três pontos. A ordem nos extremos é geralmente inferior à ordem interior.",
              f"Ruído gaussiano sintético independente: σ = {config['noise_sigma']:g}, semente = {config['seed']}. Para a derivada centrada interior a variância do ruído é σ²/(2h²), e para a segunda derivada é 6σ²/h⁴: reduzir h pode aumentar o efeito do ruído.",
              f"Quando existe ruído, a média móvel usa {config['filter_window']} amostras, é centrada e não causal, e encurta a janela nos extremos. Pode introduzir viés; não recupera exatamente o sinal original."]
    report.extend(_table_report(rows))
    return NumericalExperiment(config, times, series, errors, {}, rows, "\n\n".join(report), input_series=inputs, diagnostic_series=diagnostics)


def _integration(config, token):
    times = _grid(config["start"], config["end"], config["intervals"])
    function, _, _, primitive = _preset(config["preset"])
    values = _sample(function, times, token)
    midpoints = [(a / 2 + b / 2) for a, b in zip(times, times[1:])]
    middle = _sample(function, midpoints, token)
    reference = _sample(lambda t: primitive(t) - primitive(times[0]), times, token)
    exact, rows, series, errors = reference[-1], [], {}, {}
    for method, name in QUADRATURE_NAMES.items():
        _check(token)
        start = time.perf_counter()
        integral = integrate_midpoints(times, middle) if method == "midpoint" else quadrature(times, values, method)
        elapsed = (time.perf_counter() - start) * 1000
        rows.append(_result_row(name, integral, exact, elapsed, quantity="integral definida"))
        if method == "simpson":
            continue  # Odd prefixes do not satisfy composite Simpson's contract.
        cumulative = [0.]
        for index, (a, b) in enumerate(zip(times, times[1:])):
            if index % 256 == 0:
                _check(token)
            height = {"left": values[index], "right": values[index + 1], "midpoint": middle[index],
                      "trapezoid": values[index] / 2 + values[index + 1] / 2}[method]
            cumulative.append(cumulative[-1] + (b - a) * height)
        if not all(math.isfinite(value) for value in cumulative):
            raise ValueError("A integral acumulada excedeu o domínio numérico.")
        series[name] = cumulative
        errors[name] = metrics(cumulative, reference)["absolute"]
    series["Referência analítica · integral acumulada"] = reference
    report = ["EXPERIÊNCIA DE INTEGRAÇÃO NUMÉRICA — SIMULATED.",
              f"Exemplo: {PRESET_NAMES[config['preset']]}; domínio [{times[0]:g}, {times[-1]:g}], {config['intervals']} intervalos uniformes (número par). Integral exata F(b)−F(a) = {exact:.12g}. Variáveis adimensionais.",
              "Retângulos à esquerda e à direita usam os extremos correspondentes de cada intervalo. Trapézios usam a média das duas alturas. Pontos médios usam f((a+b)/2) efetivamente avaliada no exemplo; não se substitui essa amostra pela média dos extremos.",
              "Simpson composto: h/3 × [f₀ + fₙ + 4Σfᵢ com i ímpar + 2Σfᵢ com i par interior], aplicável nesta malha uniforme com número par de intervalos.",
              "As curvas acumuladas mostram retângulos, pontos médios, trapézios e referência. Simpson é apresentado na tabela para a integral completa: os prefixos com número ímpar de intervalos não satisfazem o seu contrato.",
              "Ordem global esperada para funções suaves: retângulos O(h), pontos médios e trapézios O(h²), Simpson O(h⁴). Uma função particular pode ser integrada exatamente até arredondamento."]
    report.extend(_table_report(rows))
    return NumericalExperiment(config, times, series, errors, {}, rows, "\n\n".join(report), input_series={"Função integrada f(t)": values})


def _ode(config, token):
    start, end, step, coefficient = config["start"], config["end"], config["dt"], config["coefficient"]
    initial, velocity = config["initial"], config["initial_velocity"]
    oscillator = config["ode_model"] == "oscillator"
    if oscillator:
        function = lambda _t, state: [state[1], -coefficient * coefficient * state[0]]
        initial_state = [initial, velocity]
        exact = lambda t: [initial * math.cos(coefficient * (t - start)) + velocity / coefficient * math.sin(coefficient * (t - start)),
                           -initial * coefficient * math.sin(coefficient * (t - start)) + velocity * math.cos(coefficient * (t - start))]
    else:
        function = lambda _t, state: -coefficient * state[0]
        initial_state = initial
        exact = lambda t: [initial * math.exp(-coefficient * (t - start))]
    rows, convergence, convergence_details = [], {}, {}
    series, errors, diagnostics = {}, {}, {}
    times, reference = [], []
    for method, name in METHOD_NAMES.items():
        _check(token)
        clock = time.perf_counter()
        solution = solve_ivp(function, initial_state, (start, end), step, method, token)
        elapsed = (time.perf_counter() - clock) * 1000
        times = solution.times
        reference_states = [exact(t) for t in times]
        reference = [state[0] for state in reference_states]
        values = [state[0] for state in solution.values]
        error = metrics(values, reference)
        series[name], errors[name] = values, error["absolute"]
        if oscillator:
            diagnostics[name] = [state[1] for state in solution.values]

        def final_state(h, method=method, calculated=solution):
            # The convergence grid includes the displayed step. Reuse its
            # endpoint instead of integrating the identical trajectory twice.
            state = calculated.values[-1] if h == step else solve_ivp(function, initial_state, (start, end), h, method, token).values[-1]
            return [state[0], state[1] / coefficient] if oscillator else state

        endpoint = exact(end)
        target = [endpoint[0], endpoint[1] / coefficient] if oscillator else endpoint
        convergence_rows = convergence_study(final_state, target, [step * 4, step * 2, step, step / 2], token)
        convergence[name] = [(row.step, row.rmse) for row in convergence_rows]
        convergence_details[name] = [{"dt": row.step, "error": row.rmse, "observed_order": row.observed_order} for row in convergence_rows]
        rows.append(_result_row(name, values[-1], reference[-1], elapsed, error,
                                observed_order=convergence_rows[-1].observed_order, quantity="posição x" if oscillator else "estado y"))
    series["Referência analítica"] = reference
    if oscillator:
        diagnostics["Referência analítica · velocidade"] = [exact(t)[1] for t in times]
    report = ["EXPERIÊNCIA DE EQUAÇÕES DIFERENCIAIS — SIMULATED.",
              f"Domínio temporal [{start:g}, {end:g}] s; Δt nominal = {step:g} s, {len(times)-1} passos. O último passo é encurtado para terminar exatamente no instante final.",
              (f"Oscilador sem amortecimento: x′ = v; v′ = −ω²x; ω = {coefficient:g} rad/s; x(t₀) = {initial:g}, v(t₀) = {velocity:g}. Referência independente: x = x₀ cos(ωτ) + (v₀/ω) sin(ωτ), v = −ωx₀ sin(ωτ) + v₀ cos(ωτ), τ=t−t₀."
               if oscillator else f"Decaimento: y′ = −ay; a = {coefficient:g} s⁻¹; y(t₀) = {initial:g}. Referência independente: y(t) = y₀ exp[−a(t−t₀)]."),
              "Euler explícito usa uma avaliação da derivada; Heun corrige a previsão de Euler com a média das inclinações inicial/final; RK4 usa quatro avaliações e pesos 1/6, 1/3, 1/3, 1/6. As ordens globais esperadas para problemas suaves e passos estáveis são 1, 2 e 4.",
              "Convergência: passos 4Δt, 2Δt, Δt e Δt/2, comparando o mesmo instante final. A ordem observada é log(Egrosso/Efino)/log(hgrosso/hfino); erro nulo/arredondamento pode tornar essa ordem indefinida ou pouco representativa.",
              ("No oscilador, a convergência usa RMSE das componentes [x, v/ω] no instante final, com a mesma escala de posição. A tabela e o gráfico de erro usam apenas a posição x ao longo de toda a trajetória. Não há dados de sensores. Euler explícito não conserva energia no oscilador sem amortecimento."
               if oscillator else "No decaimento, a convergência compara o estado escalar final. A tabela também mede RMSE e erro máximo ao longo da trajetória. Não há dados de sensores.")]
    if not oscillator:
        for method, name in METHOD_NAMES.items():
            stability = linear_stability(coefficient, step, method)
            report.append(f"Estabilidade de {name}: |R(−aΔt)| = {stability.amplification:.6g}; {'dentro da região de estabilidade' if stability.stable else 'na fronteira ou fora da região de estabilidade'} para o passo nominal.")
    report.extend(_table_report(rows))
    for name, records in convergence_details.items():
        report.append(f"Convergência · {name}: " + "; ".join(f"h={row['dt']:.6g}, erro final={row['error']:.6g}, ordem={row['observed_order']:.4g}" if row["observed_order"] is not None else f"h={row['dt']:.6g}, erro final={row['error']:.6g}, ordem indefinida" for row in records) + ".")
    result = NumericalExperiment(config, times, series, errors, convergence, rows, "\n\n".join(report), diagnostic_series=diagnostics)
    result.context["convergence_details"] = convergence_details
    return result


def calculate_numerical(parameters, token=None) -> NumericalExperiment:
    """Worker entry point; preserve full arrays and prepare bounded plot data."""
    _check(token)
    config = _configuration(dict(parameters))
    result = {"derivatives": _derivatives, "integration": _integration, "ode": _ode}[config["mode"]](config, token)
    _check(token)
    count = len(result.times)
    stride = max(1, math.ceil((count - 1) / (MAX_PREVIEW - 1)))
    indices = list(range(0, count, stride))
    if indices[-1] != count - 1:
        indices.append(count - 1)
    result.preview_times = [result.times[index] for index in indices]
    for original, preview in ((result.series, result.preview_series), (result.error_series, result.preview_errors),
                              (result.input_series, result.preview_inputs), (result.diagnostic_series, result.preview_diagnostics)):
        for name, values in original.items():
            _check(token)
            preview[name] = [values[index] for index in indices]
    result.context.update({"provenance": "SIMULATED", "parameters": dict(config),
                           "origin_declaration": "Funções e condições iniciais ilustrativas; referências analíticas independentes, sem medições reais.",
                           "units": {"domain": "s" if config["mode"] == "ode" else "adimensional", "state": "unidade arbitrária", "compute_time": "ms"},
                           "full_samples": count, "display_samples": len(indices),
                           "relative_error_zero_reference": "indefinido; representado por None",
                           "timing_scope": "uma execução local por método, excluindo interface, referência, convergência e relatório; não é um benchmark"})
    result.report += "\n\nOs tempos são observações de uma execução local, excluindo interface, referência, estudo de convergência e relatório; não constituem um benchmark. Erros relativos com referência nula são indefinidos. Os gráficos limitam a apresentação a 1500 pontos; os resultados e exportações preservam todas as amostras."
    _check(token)
    return result


def export_numerical(path, result, token):
    """Export full trajectories, with the configuration captured at execution."""
    rows = []
    groups = (("value", result.series), ("error_abs", result.error_series), ("input", result.input_series), ("diagnostic", result.diagnostic_series))
    for index, t in enumerate(result.times):
        if index % 256 == 0:
            _check(token)
        row = {"t": t, "provenance": result.provenance, **result.config}
        for prefix, series in groups:
            row.update({f"{prefix}::{name}": values[index] for name, values in series.items()})
        if result.config["mode"] == "integration":
            row.update({f"whole_domain_integral::{record['method']}": record["value"] for record in result.results_table})
        rows.append(row)
    export_csv(path, rows, token)


class NumericalPage(QWidget):
    result_ready = Signal(object)

    def __init__(self, tasks=None):
        super().__init__()
        self.tasks = tasks or Tasks(self)
        self.job = None
        self.result = self.experiment = None
        self.result_context = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        title = QLabel("Métodos numéricos · exemplos verificáveis")
        title.setObjectName("title")
        layout.addWidget(title)
        note = QLabel("SIMULATED · funções predefinidas, referências analíticas e erros calculados. Os exemplos não executam código introduzido pelo utilizador.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        body = QHBoxLayout(content)
        controls = QWidget()
        controls.setMinimumWidth(260)
        controls.setMaximumWidth(360)
        self.form = form = QFormLayout(controls)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.mode = QComboBox()
        for label, value in (("A · Derivadas", "derivatives"), ("B · Integração", "integration"), ("C · Equações diferenciais", "ode")):
            self.mode.addItem(label, value)
        form.addRow("Experiência", self.mode)
        self.preset = QComboBox()
        for name, label in PRESET_NAMES.items():
            self.preset.addItem(label, name)
        form.addRow("Função ilustrativa", self.preset)
        self.ode_model = QComboBox()
        self.ode_model.addItem("Decaimento · y′ = −ay", "decay")
        self.ode_model.addItem("Oscilador · sistema (x, v)", "oscillator")
        form.addRow("Modelo EDO", self.ode_model)
        self.fields = {}
        for name, label, value, low, high, decimals in (
            ("start", "Limite inicial", 0, -1000, 1000, 6),
            ("end", "Limite final", 2, -1000, 1000, 6),
            ("dt", "Passo Δt (s)", .05, .000001, 1000, 6),
            ("coefficient", "a (s⁻¹) / ω (rad/s)", 1, 0, 1000, 6),
            ("initial", "Estado inicial y₀ / x₀", 1, -10000, 10000, 5),
            ("initial_velocity", "Velocidade inicial v₀", 0, -10000, 10000, 5),
            ("noise_sigma", "Desvio do ruído σ", 0, 0, 1000, 6),
        ):
            field = QDoubleSpinBox()
            field.setDecimals(decimals)
            field.setRange(low, high)
            field.setValue(value)
            self.fields[name] = field
            form.addRow(label, field)
        self.intervals = QSpinBox()
        self.intervals.setRange(4, MAX_INTERVALS)
        self.intervals.setSingleStep(2)
        self.intervals.setValue(100)
        form.addRow("Intervalos (par para Simpson)", self.intervals)
        self.seed = QSpinBox()
        self.seed.setRange(0, 2**31 - 1)
        self.seed.setValue(42)
        form.addRow("Semente reprodutível", self.seed)
        self.filter_window = QSpinBox()
        self.filter_window.setRange(1, 101)
        self.filter_window.setSingleStep(2)
        self.filter_window.setValue(5)
        form.addRow("Janela ímpar da média móvel", self.filter_window)
        self.run = QPushButton("Calcular e comparar")
        self.run.setObjectName("primary")
        self.run.clicked.connect(self.execute)
        form.addRow(self.run)
        self.cancel_button = QPushButton("Cancelar cálculo")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel)
        form.addRow(self.cancel_button)
        self.export_button = QPushButton("Exportar séries CSV")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export)
        form.addRow(self.export_button)
        body.addWidget(controls, 1)
        right = QVBoxLayout()
        grid = QGridLayout()
        self.plots = [Plot("Resultado e referência", "Valor", x_title="t"), Plot("Erro absoluto", "Erro", x_title="t"),
                      Plot("Sinal de entrada / convergência", "Valor", x_title="t"), Plot("Segunda derivada / velocidade", "Valor", x_title="t")]
        for index, plot in enumerate(self.plots):
            grid.addWidget(plot, index // 2, index % 2)
        right.addLayout(grid, 1)
        self.table = QTableView()
        self.table.setMinimumHeight(180)
        self.table.setMaximumHeight(245)
        self.table.setWordWrap(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table_model = QStandardItemModel(self)
        self.table.setModel(self.table_model)
        right.addWidget(self.table)
        body.addLayout(right, 3)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        self.summary = QLabel("Escolha A, B ou C. O cálculo e a preparação dos gráficos decorrem em segundo plano.")
        self.summary.setObjectName("muted")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.ode_model.currentIndexChanged.connect(self._mode_changed)
        self._mode_changed()

    def _mode_changed(self):
        mode = self.mode.currentData()
        ode = mode == "ode"
        for widget, visible in ((self.preset, not ode), (self.ode_model, ode), (self.intervals, not ode),
                                (self.fields["dt"], ode), (self.fields["coefficient"], ode), (self.fields["initial"], ode),
                                (self.fields["initial_velocity"], ode and self.ode_model.currentData() == "oscillator"),
                                (self.fields["noise_sigma"], mode == "derivatives"), (self.seed, mode == "derivatives"),
                                (self.filter_window, mode == "derivatives")):
            self.form.setRowVisible(widget, visible)

    def execute(self):
        if not self.run.isEnabled():
            return
        parameters = {name: field.value() for name, field in self.fields.items()}
        parameters.update(mode=self.mode.currentData(), preset=self.preset.currentData(), ode_model=self.ode_model.currentData(),
                          intervals=self.intervals.value(), seed=self.seed.value(), filter_window=self.filter_window.value())
        self.run.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.export_button.setEnabled(False)
        self.summary.setText("A calcular métodos, referências, erros e relatório em segundo plano…")
        self.job = self.tasks.start(lambda token: calculate_numerical(parameters, token), self.display, self.failed)

    def cancel(self):
        if self.job:
            self.job.token.cancel()

    def failed(self, message):
        self.job = None
        self.run.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.export_button.setEnabled(self.result is not None)
        self.summary.setText(message)

    def display(self, result):
        self.result = self.experiment = result
        self.result_context = result.context
        self.job = None
        self.run.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.export_button.setEnabled(True)
        mode = result.config["mode"]
        first_title = {"derivatives": "Primeira derivada e referência analítica", "integration": "Integral acumulada e referência analítica", "ode": "Estado e referência analítica"}[mode]
        self._plot(0, first_title, "Valor", "Tempo (s)" if mode == "ode" else "t", result.preview_times, result.preview_series)
        self._plot(1, "Erro absoluto · comparação com a referência", "Erro absoluto", "Tempo (s)" if mode == "ode" else "t", result.preview_times, result.preview_errors)
        if result.convergence:
            times = [step for step, _ in next(iter(result.convergence.values()))]
            curves = {name: [error for _, error in rows] for name, rows in result.convergence.items()}
            self._plot(2, "Convergência · erro no mesmo instante final", "Erro final", "Passo Δt (s)", times, curves)
        else:
            self._plot(2, "Sinal de entrada e ruído declarado", "f(t)", "t", result.preview_times, result.preview_inputs)
        self._plot(3, "Velocidade e referência" if mode == "ode" else "Segunda derivada e referência", "v" if mode == "ode" else "d²f/dt²", "Tempo (s)" if mode == "ode" else "t", result.preview_times, result.preview_diagnostics)
        self.plots[3].setVisible(bool(result.diagnostic_series))
        headers = ["Método", "Valor final", "Referência", "Erro absoluto", "RMSE", "Tempo (ms)"]
        self.table_model.clear()
        self.table_model.setHorizontalHeaderLabels(headers)
        for row in result.results_table:
            values = [row["method"], row["value"], row["exact"], row["absolute_error"], row["rmse"], row["elapsed_ms"]]
            items = [QStandardItem(value if isinstance(value, str) else "—" if value is None else f"{value:.6g}") for value in values]
            for item in items:
                item.setToolTip(item.text())
            self.table_model.appendRow(items)
        self.table.resizeRowsToContents()
        self.summary.setText(f"SIMULATED · {len(result.times)} amostras completas · {len(result.preview_times)} pontos por curva na apresentação · {len(result.results_table)} métodos/quantidades. Resultados detalhados preparados para o relatório.")
        self.result_ready.emit(result)

    def _plot(self, index, title, unit, x_title, times, series):
        plot = self.plots[index]
        plot.title_label.setText(title)
        plot.x_axis.setTitleText(x_title)
        plot.y_axis.setTitleText(unit)
        plot.update_series(times, series)
        plot.x_axis.setLabelFormat("%.5g")
        plot.y_axis.setLabelFormat("%.5g")
        if series:
            # A nearly constant derivative must not autoscale floating-point
            # roundoff into a large apparent oscillation or 15-digit labels.
            low, high = plot.y_axis.min(), plot.y_axis.max()
            scale = max(abs(low), abs(high))
            if scale and high - low < scale * 1e-8:
                middle = low / 2 + high / 2
                pad = max(scale * .02, 1e-12)
                plot.y_axis.setRange(middle - pad, middle + pad)

    def export(self):
        if self.result is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exportar séries numéricas completas", "numerical-series.csv", "CSV (*.csv)")
        if path:
            result = self.result
            self.tasks.start(lambda token: export_numerical(path, result, token),
                             lambda _: self.summary.setText("Séries completas e configuração usada exportadas; origem SIMULATED."),
                             lambda message: self.summary.setText(message))
