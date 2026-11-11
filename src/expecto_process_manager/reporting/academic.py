"""Reproducible academic experiments and a 21-section, offline final report.

All physical experiments here are synthetic. perf_counter durations are actual
local timings of numerical calls, not measurements of CPU power or temperature.
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html import escape
from importlib.metadata import PackageNotFoundError, version
import json
import math
import os
from pathlib import Path
import platform
import tempfile
from time import perf_counter

from .document import Curve, Figure, ScientificReport, Table
from .model_reports import calibration_report, coupled_report, energy_report
from .render import CSS, figure_html, number
from ..core.cancellation import Cancellation
from ..optimization.eco import compare_policies, synthetic_policy_runs
from ..physics.calibration import fit_thermal, predict_zoh
from ..physics.coupled_thermal import CoupledThermalConfig, simulate_coupled
from ..physics.numerical.derivatives import differentiate
from ..physics.numerical.integration import integrate_midpoints, quadrature
from ..physics.numerical.ode import solve_ivp
from ..physics.numerical.signals import add_gaussian_noise, moving_average
from ..physics.numerical.thermalcomparison import compare_thermal, time_to_threshold
from ..physics.numerical.validation import linear_stability, metrics
from ..physics.thermal_model import ThermalModel


COLORS = ("#2176c1", "#9756b6", "#1c946b", "#d48b18")
METHODS = ("euler", "heun", "rk4")
STEPS = (1., .5, .1, .05, .01)


@dataclass
class AcademicExperiments:
    generated_at: str
    software_version: str
    runtime: str
    experiments: list[ScientificReport]
    checks: list[tuple[str, bool, str]]
    thermal_rows: list[tuple]
    hardware: dict | None
    hardware_path: str | None
    total_elapsed: float


def _thermal_report(result, power, initial, step, title):
    report = ScientificReport(
        title, "thermal", "SIMULATED",
        "Comparar a evolução de uma temperatura representativa com a solução analítica do balanço térmico concentrado.",
        parameters=[("T₀", initial, "°C"), ("Ta", 22, "°C"), ("Pth", power, "W"),
                    ("C", 100, "J/K"), ("k", 2, "W/K"), ("Duração", 120, "s"), ("Δt", step, "s")],
        equations=["C T′ = Pth − k(T−Ta)", "T(t) = Teq + (T₀−Teq)e^(−t/τ)", "Teq = Ta + Pth/k; τ = C/k"],
        assumptions=["Temperatura uniforme equivalente, coeficientes e potência constantes, ambiente fixo.",
                     "Parâmetros introduzidos como hipótese; não são uma calibração do hardware inventariado."],
        methods=["Euler, Heun e RK4 são implementados diretamente em Python. A referência analítica não utiliza os estados numéricos."],
        tables=[Table("Erro nas séries completas", ("Método", "MAE (°C)", "RMSE (°C)", "Máximo (°C)", "T final (°C)"),
                      [(method.upper(), error["mae"], error["rmse"], error["maximum"], values[-1])
                       for method, values in result.solutions.items() for error in [metrics(values, result.reference)]])],
        figures=[Figure("Temperatura e referência", "Tempo (s)", "Temperatura (°C)",
                        [Curve(method.upper(), result.times, values, COLORS[i]) for i, (method, values) in enumerate(result.solutions.items())]
                        +[Curve("Analítica", result.times, result.reference, COLORS[3])]),
                 Figure("Erro absoluto ao longo do tempo", "Tempo (s)", "Erro absoluto (°C)",
                        [Curve(method.upper(), result.times, metrics(values, result.reference)["absolute"], COLORS[i])
                         for i, (method, values) in enumerate(result.solutions.items())])],
        interpretation=[f"A solução tende para {22+power/2:g} °C com constante de tempo de 50 s. O valor final analítico é {result.reference[-1]:.8g} °C.",
                        "Diferenças entre os métodos são erros de discretização do mesmo modelo; não são diferenças entre sensores."],
        limitations=["Uma referência analítica valida o algoritmo para estas hipóteses, mas não valida experimentalmente o comportamento de um processador."],
        reproduction=["Repetir compare_thermal com os parâmetros tabelados; não é necessário qualquer sensor."],
    )
    return report


def run_academic_experiments(hardware_path=None, token: Cancellation | None = None) -> AcademicExperiments:
    token = token or Cancellation()
    token.check()
    began = perf_counter()
    warm = compare_thermal(40, 22, 45, 100, 2, 120, .1, token)
    experiments = [_thermal_report(warm, 45, 40, .1, "Experiência 1 · aquecimento simulado")]

    cooling_rows, cooling_curves = [], []
    cooling_cases = ((100, 2, 22), (200, 2, 22), (100, 4, 22), (100, 2, 30))
    for i, (capacity, dissipation, ambient) in enumerate(cooling_cases):
        trial = compare_thermal(70, ambient, 0, capacity, dissipation, 120, .1, token)
        cooling_rows.append((capacity, dissipation, ambient, capacity/dissipation, trial.reference[-1],
                             time_to_threshold(70, ambient, 0, capacity, dissipation, 35)))
        cooling_curves.append(Curve(f"C={capacity}, k={dissipation}, Ta={ambient}", trial.times, trial.solutions["rk4"], COLORS[i]))
    experiments.append(ScientificReport(
        "Experiência 2 · arrefecimento e parâmetros físicos", "cooling", "SIMULATED",
        "Estudar como capacidade, dissipação e ambiente alteram a descida de temperatura sem potência de aquecimento.",
        parameters=[("Temperatura inicial", 70, "°C"), ("Potência", 0, "W"), ("Duração", 120, "s"), ("Passo", .1, "s")],
        equations=["T(t) = Ta + (T₀−Ta)e^(−kt/C)", "τ = C/k", "t(T*) = −τ ln[(T*−Ta)/(T₀−Ta)]"],
        assumptions=["Sem aquecimento, com parâmetros e ambiente constantes; o limiar deve ser atingível no modelo."],
        methods=["RK4 é comparado à solução analítica. Os tempos de limiar da tabela são analíticos e podem exceder a janela gráfica."],
        tables=[Table("Sensibilidade física e tempo até 35 °C", ("C (J/K)", "k (W/K)", "Ta (°C)", "τ (s)", "T(120 s) (°C)", "Tempo até 35 °C (s)"), cooling_rows)],
        figures=[Figure("Arrefecimento em quatro condições assumidas", "Tempo (s)", "Temperatura (°C)", cooling_curves)],
        interpretation=["Duplicar C duplica a constante de tempo; duplicar k reduz essa constante a metade. Alterar Ta muda a temperatura final de equilíbrio.",
                        "Os valores de k representam cenários assumidos de dissipação, sem inferir uma relação entre RPM e transferência térmica."],
        limitations=["Não se mediram ventoinhas, geometrias nem coeficientes do computador; não se controlam ventoinhas."],
        reproduction=["Usar T₀=70 °C, P=0 W e cada triplo (C,k,Ta) tabelado."],
    ))

    thermal_rows, convergence = [], {method: [] for method in METHODS}
    for step in STEPS:
        token.check()
        trial = compare_thermal(40, 22, 45, 100, 2, 120, step, token)
        model = ThermalModel(22, 100, 2)
        for method in METHODS:
            started = perf_counter()
            timed = solve_ivp(lambda _time, state: model.rate(state[0], 45), 40, (0, 120), step, method, token)
            elapsed = perf_counter()-started
            error = metrics(trial.solutions[method], trial.reference)
            previous = convergence[method][-1] if convergence[method] else None
            order = None
            if previous and min(previous[1], error["rmse"]) > 1e-12*max(trial.reference):
                order = math.log(previous[1]/error["rmse"])/math.log(previous[0]/step)
            convergence[method].append((step, error["rmse"], error["maximum"], elapsed))
            stability = linear_stability(.02, step, method)
            thermal_rows.append((step, method.upper(), len(timed.times)-1, error["rmse"], error["maximum"], elapsed*1000, order, stability.amplification))
    stability_curves = []
    for i, step in enumerate((80., 110.)):
        demonstration = solve_ivp(lambda _time, state: -.02*state[0], 1, (0, 1100), step, "euler", token)
        stability_curves.append(Curve(f"Euler h={step:g} s", demonstration.times, [value[0] for value in demonstration.values], COLORS[i]))
    experiments.append(ScientificReport(
        "Experiência 3 · convergência, estabilidade e custo", "convergence", "SIMULATED · tempos de execução locais medidos",
        "Determinar o efeito do passo sobre o erro e o custo de integrar o mesmo modelo térmico.",
        parameters=[("Passos", ", ".join(map(str, STEPS)), "s"), ("C/k", 50, "s"), ("Limite de estabilidade Euler", 100, "s")],
        equations=["Euler: R(z)=1+z, z=−kh/C", "Estabilidade absoluta: |R(−kh/C)|<1 ⇒ 0<h<2C/k",
                   "Ordem observada p = ln(Eh/Eh′) / ln(h/h′)"],
        assumptions=["Mesmo estado inicial, duração, potência e referência analítica em todas as malhas."],
        methods=["Cada erro usa toda a trajetória na respetiva malha. A ordem é uma estimativa a partir de RMSE temporal; não se comparam diretamente vetores de tamanhos diferentes.",
                 "O tempo em ms é uma chamada real ao resolvedor, medida com perf_counter; exclui renderização e análise do erro, mas inclui o controlo de cancelamento.",
                 "Não se estima ordem quando os erros se aproximam do limiar de arredondamento de 10⁻¹² vezes a escala de temperatura."],
        tables=[Table("Estudo de passo — uma execução cronometrada por combinação", ("h (s)", "Método", "Intervalos", "RMSE (°C)", "Máximo (°C)", "Tempo (ms)", "Ordem observada", "|R|"), thermal_rows)],
        figures=[Figure("Convergência do erro máximo", "log₁₀(h/s)", "log₁₀(erro máximo/°C)",
                        [Curve(method.upper(), [math.log10(row[0]) for row in rows], [math.log10(max(row[2], 1e-16)) for row in rows], COLORS[i])
                         for i, (method, rows) in enumerate(convergence.items())]),
                 Figure("Erro e tempo de processamento da chamada", "Tempo de execução (ms)", "RMSE (°C)",
                        [Curve(method.upper(), [row[3]*1000 for row in rows], [row[1] for row in rows], COLORS[i])
                         for i, (method, rows) in enumerate(convergence.items())]),
                 Figure("Demonstração de estabilidade em θ′=−0,02θ, θ₀=1 K", "Tempo (s)", "Desvio θ (K)", stability_curves)],
        interpretation=["Euler apresenta erro de primeira ordem no regime estável; Heun usa duas avaliações e RK4 quatro por passo, obtendo ordens superiores antes do arredondamento.",
                        "Todos os passos estudados estão abaixo de 100 s, mas estabilidade não significa que o erro seja suficientemente pequeno para qualquer aplicação.",
                        "Na demonstração separada, h=80 s gera oscilações amortecidas, enquanto h=110 s amplifica oscilações artificiais. Não são medições nem comportamento térmico real.",
                        "Os tempos dependem da carga concorrente, do intérprete e do estado da máquina. Uma única chamada não suporta conclusões estatísticas de desempenho."],
        limitations=["O passo interno da simulação não é a frequência de um sensor. Diminuir h aumenta custo e não corrige erros do modelo ou ruído experimental."],
        reproduction=["Reexecutar o gerador para obter novos tempos reais; pequenas diferenças de tempo são esperadas."],
    ))

    integration_rows = []
    edges = [i/10 for i in range(11)]
    for label, times, values, midpoint_values, exact in (
            ("50 W durante 10 s", list(range(11)), [50.]*11, [50.]*10, 500.),
            ("∫₀¹ x² dx", edges, [x*x for x in edges], [((a+b)/2)**2 for a,b in zip(edges, edges[1:])], 1/3)):
        for method in ("left", "right", "midpoint", "trapezoid", "simpson"):
            started = perf_counter()
            value = integrate_midpoints(times, midpoint_values) if method == "midpoint" else quadrature(times, values, method)
            elapsed = perf_counter()-started
            integration_rows.append((label, method, value, exact, abs(value-exact), elapsed*1e6))
    experiments.append(ScientificReport(
        "Experiência 4 · integração e energia", "quadrature", "SIMULATED",
        "Validar quadraturas com potência constante e uma função polinomial de integral conhecida.",
        equations=["E=∫Pdt; 50 W × 10 s = 500 J = 0,138888… Wh", "∫₀¹ x² dx = 1/3"],
        assumptions=["Amostragem uniforme com 10 intervalos; o ponto médio usa valores realmente avaliados no meio de cada intervalo."],
        methods=["Retângulos à esquerda e direita, ponto médio, trapézios e Simpson 1/3 composto são executados sobre os dados declarados.",
                 "Simpson só é aplicado com intervalos uniformes e em número par. O seu resultado exato para x² decorre da ordem de exatidão polinomial."],
        tables=[Table("Quadraturas executadas", ("Caso", "Método", "Resultado", "Exato", "Erro absoluto", "Tempo chamada (µs)"), integration_rows)],
        figures=[Figure("Potência sintética constante", "Tempo (s)", "Potência (W)", [Curve("P=50 W", list(range(11)), [50.]*11)])],
        interpretation=["Todas as regras integram exatamente a potência constante até arredondamento. Para x², os erros dos retângulos não desaparecem numa malha finita e Simpson é exato até arredondamento.",
                        "Energia em joules mede a área sob P(t); os valores de x² constituem um teste matemático adimensional, não uma medição energética."],
        limitations=["A diferença entre regras não é, por si, uma estimativa da incerteza de um wattímetro."],
        reproduction=["Usar 11 extremos de intervalo e 10 avaliações reais nos pontos médios."],
    ))

    times = [i*.01 for i in range(1001)]
    clean = [22+t*t for t in times]
    noisy = add_gaussian_noise(clean, .05, seed=42)
    filtered = moving_average(noisy, 11)
    derivative_reference = [2*t for t in times]
    signal_rows, derivative_curves, second_curves = [], [], []
    derivative_errors = {}
    interior = slice(10, -10)
    for i, (name, signal) in enumerate((("Sem ruído", clean), ("Ruído σ=0,05 °C", noisy), ("Média móvel 11", filtered))):
        derivative = differentiate(times, signal)
        second = differentiate(times, signal, order=2)
        first_error = metrics(derivative[interior], derivative_reference[interior])
        second_error = metrics(second[interior], [2.]*len(second[interior]))
        derivative_errors[name] = first_error["rmse"]
        signal_rows.append((name, first_error["rmse"], first_error["maximum"], second_error["rmse"]))
        derivative_curves.append(Curve(name, times, derivative, COLORS[i]))
        second_curves.append(Curve(name, times, second, COLORS[i]))
    experiments.append(ScientificReport(
        "Experiência 5 · derivadas e ruído", "signals", "SIMULATED",
        "Testar diferenças finitas num sinal de temperatura conhecido e observar o efeito do ruído e da filtragem.",
        parameters=[("Passo de amostragem", .01, "s"), ("Desvio do ruído gaussiano", .05, "°C"), ("Semente", 42, ""), ("Janela média móvel", 11, "amostras")],
        equations=["T(t)=22 °C+(1 °C/s²)t²; T′=(2 °C/s²)t; T″=2 °C/s²", "T′ᵢ≈(Tᵢ₊₁−Tᵢ₋₁)/(2h)",
                   "σ(derivada centrada) = σruído/(√2 h)", "σ(segunda derivada) = √6 σruído/h²"],
        assumptions=["Ruído gaussiano independente, aditivo, de média zero. O polinómio é um sinal de teste, sem afirmar que um CPU aquece quadraticamente."],
        methods=["Diferenças centradas com polinómio local de três pontos e segunda derivada; extremos usam fórmulas unilaterais.",
                 "Média móvel centrada de 11 amostras, não causal; métricas excluem dez amostras de cada extremo para não misturar efeitos de fronteira."],
        tables=[Table("Erros nas mesmas amostras interiores", ("Sinal", "RMSE T′ (°C/s)", "Máximo T′ (°C/s)", "RMSE T″ (°C/s²)"), signal_rows)],
        figures=[Figure("Sinal original, ruidoso e filtrado", "Tempo (s)", "Temperatura sintética (°C)",
                        [Curve("Original", times, clean, COLORS[0]), Curve("Ruidoso", times, noisy, COLORS[1]), Curve("Filtrado", times, filtered, COLORS[2])]),
                 Figure("Primeira derivada", "Tempo (s)", "Taxa (°C/s)", derivative_curves+[Curve("Analítica", times, derivative_reference, COLORS[3])]),
                 Figure("Segunda derivada", "Tempo (s)", "Variação da taxa (°C/s²)", second_curves)],
        interpretation=["A subtração de amostras ruidosas seguida de divisão por h amplia as flutuações. A segunda derivada contém h² no denominador e é ainda mais sensível.",
                        "A média móvel reduz a variância desta experiência, mas altera o sinal. Um filtro causal introduziria atraso; a média centrada usa informação futura e pode distorcer transientes."],
        limitations=["A semente torna o ensaio repetível; não transforma o ruído sintético num modelo calibrado de um sensor real."],
        reproduction=["Usar semente 42, σ=0,05 °C, passo 0,01 s e exatamente a mesma janela e seleção interior."],
    ))

    fit_times = [i*.5 for i in range(401)]
    fit_powers = [45.]*len(fit_times)
    fit_temperatures = predict_zoh(fit_times, fit_powers, 30, 22, 100, 2)
    fitted = fit_thermal(fit_times, fit_temperatures, fit_powers, 22, token=token)
    calibration = calibration_report(fitted, {"provenance": "SIMULATED", "ambient": 22})
    calibration.title = "Experiência 6 · calibração em dados sintéticos e holdout"
    calibration.tables.insert(0, Table("Recuperação dos parâmetros geradores", ("Parâmetro", "Verdade sintética", "Estimativa", "Unidade"),
                                        [("C", 100, fitted.capacity, "J/K"), ("k", 2, fitted.dissipation, "W/K")]))
    calibration.interpretation.append("A recuperação dos parâmetros conhecidos verifica o estimador em dados gerados pelo próprio modelo; não constitui calibração experimental do CPU.")
    experiments.append(calibration)

    comparison = compare_policies(synthetic_policy_runs(), max_duration=18, token=token)
    energy = energy_report(comparison, {"config": {"max_duration": 18, "max_temperature": None}})
    energy.title = "Experiência 7 · energia por tarefa e restrições"
    unconstrained = compare_policies(synthetic_policy_runs(), token=token)
    energy.interpretation.append(f"Sem prazo, o menor consumo sintético é {unconstrained.recommendation}. Com prazo de 18 s, ULTRA ECO deixa de ser admissível e a recomendação é {comparison.recommendation}.")
    experiments.append(energy)

    coupled_config = CoupledThermalConfig()
    coupled_results = {method: simulate_coupled(coupled_config, duration=120, dt=.1, method=method, token=token) for method in METHODS}
    coupled = coupled_report(coupled_results["rk4"], {"config": {**asdict(coupled_config), "dt": .1}})
    coupled.title = "Experiência 8 · sistema térmico CPU/GPU"
    coupled.tables.append(Table("Comparação dos três métodos no sistema acoplado", ("Método", "CPU final (°C)", "GPU final (°C)", "Máximo resíduo (J)"),
                                 [(method.upper(), result.cpu_temperatures[-1], result.gpu_temperatures[-1], max(abs(v) for v in result.balance_residual))
                                  for method, result in coupled_results.items()]))
    experiments.append(coupled)

    decay_coarse = solve_ivp(lambda _t, y: -y[0], 1, (0, 1), .1, "euler", token)
    decay_fine = solve_ivp(lambda _t, y: -y[0], 1, (0, 1), .05, "euler", token)
    rejected_reason = ""
    try:
        cooling = predict_zoh(list(range(40)), [0.]*40, 70, 22, 100, 2)
        fit_thermal(list(range(40)), cooling, [0.]*40, 22, token=token)
    except ValueError as error:
        rejected_reason = str(error)
    clean_derivative_error = derivative_errors["Sem ruído"]
    checks = [
        ("A · derivada t²", clean_derivative_error < 1e-9, f"RMSE centrada interior={clean_derivative_error:.6g} °C/s"),
        ("B · integral x²", abs(quadrature(edges, [x*x for x in edges], "simpson")-1/3) < 1e-12, "Simpson comparado a 1/3"),
        ("C · Euler y′=−y", abs(decay_fine.values[-1][0]-math.exp(-1)) < abs(decay_coarse.values[-1][0]-math.exp(-1)), "Erro final diminui ao passar de 0,1 a 0,05 s"),
        ("D · energia constante", quadrature([0, 10], [50, 50]) == 500, "50 W × 10 s = 500 J"),
        ("E · referência térmica", metrics(warm.solutions["rk4"], warm.reference)["maximum"] < 1e-8, "RK4 comparado à solução exponencial"),
        ("F · estabilidade", linear_stability(1, 1.9).stable and not linear_stability(1, 2.1).stable, "Euler estável para h=1,9; instável para h=2,1 em y′=−y"),
        ("G · amplificação do ruído", derivative_errors["Ruído σ=0,05 °C"] > clean_derivative_error, "RMSE da derivada ruidosa excede o da derivada limpa"),
        ("H · balanço de energia", max(abs(v) for v in coupled_results["rk4"].balance_residual) < 1e-7, "Consistência do balanço no sistema acoplado"),
        ("I · identificabilidade", bool(rejected_reason), rejected_reason or "A calibração deveria ter sido rejeitada"),
    ]
    if not all(passed for _, passed, _ in checks):
        raise ValueError("Falha na geração académica: "+", ".join(name for name, passed, _ in checks if not passed))
    hardware = None
    if hardware_path is not None:
        target = Path(hardware_path)
        if target.exists():
            if target.stat().st_size > 2*1024*1024:
                raise ValueError("Inventário prévio excede 2 MiB.")
            with target.open(encoding="utf-8-sig") as stream:
                hardware = json.load(stream)
            if not isinstance(hardware, dict) or not isinstance(hardware.get("items"), list):
                raise ValueError("Inventário prévio inválido.")
    try:
        software_version = version("expecto-process-manager")
    except PackageNotFoundError:
        software_version = "não instalada; consultar pyproject.toml"
    token.check()
    return AcademicExperiments(datetime.now(timezone.utc).isoformat(), software_version,
                               f"Python {platform.python_version()} · {platform.system()}", experiments, checks,
                               thermal_rows, hardware, str(hardware_path) if hardware_path else None, perf_counter()-began)


def _table(table):
    return "<h3>"+escape(table.title)+"</h3><table><thead><tr>"+"".join("<th>"+escape(str(v))+"</th>" for v in table.headers)+"</tr></thead><tbody>"+"".join(
        "<tr>"+"".join("<td>"+escape(number(v))+"</td>" for v in row)+"</tr>" for row in table.rows)+"</tbody></table>"


def _paragraphs(*texts):
    return "".join("<p>"+escape(text)+"</p>" for text in texts)


def _experiment(report):
    content = ["<article><h3>"+escape(report.title)+"</h3><p class='tag'>"+escape(report.provenance)+"</p>", _paragraphs(report.problem)]
    content.append(_table(Table("Parâmetros", ("Parâmetro", "Valor", "Unidade"), report.parameters)))
    for title, texts in (("Hipóteses", report.assumptions), ("Métodos", report.methods)):
        content.append("<h4>"+title+"</h4>"+_paragraphs(*texts))
    content.extend("<div class='equation'>"+escape(eq)+"</div>" for eq in report.equations)
    content.extend(_table(table) for table in report.tables)
    content.extend(figure_html(figure) for figure in report.figures)
    content.append("<h4>Interpretação</h4>"+_paragraphs(*report.interpretation))
    content.append("<h4>Limitações e reprodução</h4>"+_paragraphs(*report.limitations, *report.reproduction))
    content.append("</article>")
    return "".join(content)


def render_academic_report(data: AcademicExperiments) -> str:
    """Render exactly the 21 requested academic sections and eight experiments."""
    sections = []
    def section(index, title, html):
        sections.append(f'<section id="sec-{index}"><h2>{index}. '+escape(title)+"</h2>"+html+"</section>")
    section(1, "Resumo", _paragraphs(
        "O InProcess Physical Systems Lab aplica conservação da energia, equações diferenciais e métodos numéricos ao estudo térmico e energético de computadores. Este relatório foi gerado por oito experiências efetivamente executadas com dados sintéticos identificados.",
        "Euler, Heun e RK4 são comparados à solução analítica; estudam-se convergência, quadraturas, ruído, identificação térmica com holdout, energia por tarefa e acoplamento CPU/GPU. Os tempos de execução apresentados foram medidos nesta geração.",
        "Não foram recolhidas aqui medições físicas de potência ou temperatura. O inventário prévio do computador identifica o contexto de execução, sem constituir validação experimental dos modelos."))
    section(2, "Introdução e motivação", _paragraphs(
        "Um monitor de processos fornece observáveis computacionais. Um laboratório físico exige formular um modelo, explicitar unidades e hipóteses, calcular previsões e confrontá-las com uma referência ou com medições independentes.",
        "O projeto preserva a monitorização e acrescenta um motor matemático independente da interface. A aplicação energética é uma oportunidade para estudar compromissos entre duração, dissipação e consumo, sem concluir poupança a partir de CPU% ou RAM livre."))
    section(3, "Problema científico", _paragraphs(
        "É possível modelar o comportamento térmico e energético de um computador e identificar configurações que reduzam energia sem comprometer significativamente o desempenho?",
        "Neste estado do trabalho, a resposta experimental permanece em aberto. É possível verificar algoritmos e estudar cenários assumidos; demonstrar a adequação ao computador requer instrumentação, tarefas controladas e repetições."))
    hypotheses = Table("Hipóteses, método e critério de avaliação", ("Hipótese", "Método proposto", "Critério", "Estado da evidência"), [
        ("H1: modelo de primeira ordem aproxima TCPU", "Medir Pth/temperatura sincronizadas, ajustar C/k e reservar outra sessão", "RMSE do holdout, resíduos e incerteza compatíveis com objetivo previamente definido", "Apenas recuperação sintética; sem validação experimental"),
        ("H2: reduzir h melhora Euler no regime estável", "Experiência 3 com cinco passos e mesma referência analítica", "Erro decrescente e ordem próxima de 1 antes de arredondamento", "Validação algorítmica nesta geração"),
        ("H3: integrar potência estima energia", "Experiência 4 com integrais conhecidas; depois comparar a wattímetro", "Convergência/exatidão nos casos de referência; erro instrumental em experiência real", "Quadraturas validadas; aplicação instrumental por executar"),
        ("H4: políticas diferem em J por mesma tarefa", "Executar tarefa equivalente por perfil, em ordem controlada e repetida", "Diferença de energia superior à incerteza, respeitando prazo e temperatura", "Apenas cenário sintético; sem poupança real demonstrada"),
        ("H5: menor potência não implica melhor eficiência", "Comparar integral e duração, mantendo trabalho concluído", "Identificar o efeito do tempo sobre J por tarefa", "Contraexemplo sintético calculado; sem conclusão experimental sobre este PC"),
    ])
    section(4, "Objetivos e hipóteses", _paragraphs("Os objetivos são formular, implementar, validar e interpretar. Os critérios experimentais devem ser definidos antes de recolher os dados; não se inventa um limite de aceitação oficial da unidade curricular.")+_table(hypotheses))
    section(5, "Fundamentação física", _paragraphs(
        "A primeira lei relaciona acumulação e fluxos de energia. Uma capacidade térmica equivalente C associa variações de temperatura a variações de energia interna. A lei linear de arrefecimento usa k(T−Ta) como fluxo líquido para o ambiente.",
        "W equivale a J/s, C tem unidade J/K e k tem unidade W/K. Diferenças em kelvin e em graus Celsius são numericamente iguais; temperaturas absolutas não são intercambiáveis em todas as leis físicas.")
        +"<div class='equation'>[C dT/dt] = (J/K)(K/s) = J/s = W = [Pth] = [k(T−Ta)]</div>")
    section(6, "Dedução matemática dos modelos", _paragraphs(
        "Partindo de dU/dt = potência de entrada − potência dissipada e assumindo dU=C dT com C constante, obtém-se C dT/dt = Pth − k(T−Ta). A aproximação concentrada substitui a distribuição espacial por uma temperatura representativa.",
        "Com Pth e Ta constantes, desloca-se a variável para θ=T−Ta−Pth/k. A EDO passa a θ′=−(k/C)θ e a sua integração dá a solução exponencial.")
        +"<div class='equation'>T(t)=Ta+Pth/k+(T₀−Ta−Pth/k)e^(−kt/C); Teq=Ta+Pth/k; τ=C/k</div>"
        +_paragraphs("No sistema CPU/GPU há dois balanços e uma transferência interna comum. O mesmo fluxo sai de um nó e entra no outro; por isso cancela ao somar as equações."))
    section(7, "Equações diferenciais", _paragraphs(
        "O modelo de um nó é um problema de valor inicial T′=f(t,T). A versão acoplada tem estado (Tc,Tg,Eentrada,Eambiente); as energias são integradas com os mesmos estágios das temperaturas.")
        +"<div class='equation'>Cc Tc′=Pc−kc(Tc−Ta)−kcg(Tc−Tg)<br>Cg Tg′=Pg−kg(Tg−Ta)+kcg(Tc−Tg)</div>"
        +_paragraphs("A solução com kcg=0 é referência exata dos nós independentes. Para kcg≠0, a diferença para as curvas independentes é uma diferença de modelos, não erro numérico."))
    section(8, "Métodos numéricos", _paragraphs(
        "Euler usa uma inclinação no início do intervalo e tem erro global de primeira ordem. Heun corrige a previsão usando a média de duas inclinações e tem segunda ordem. RK4 combina quatro estágios e tem quarta ordem para problemas suficientemente suaves.")
        +"<div class='equation'>Euler: yₙ₊₁=yₙ+h f(tₙ,yₙ)<br>Heun: k₁=f(tₙ,yₙ); k₂=f(tₙ+h,yₙ+h k₁); yₙ₊₁=yₙ+h(k₁+k₂)/2<br>RK4: yₙ₊₁=yₙ+h(k₁+2k₂+2k₃+k₄)/6</div>"
        +_paragraphs("Retângulos, ponto médio, trapézios e Simpson aproximam áreas; derivadas usam diferenças locais. Simpson exige uniformidade e número par de intervalos, e o ponto médio exige amostras avaliadas nessa posição."))
    section(9, "Implementação em Python", _paragraphs(
        "physics/numerical contém diferenças finitas, quadraturas, resolvedor EDO, sinais e validação. thermal_model, calibration e coupled_thermal representam a física. core/energy e optimization/eco calculam consumos e comparações de leitura. reporting transforma resultados em HTML/SVG sem depender de Qt.",
        "O resolvedor constrói a malha, calcula os estágios e guarda cada estado; não chama SciPy. Limites de amostras e cancelamento cooperativo controlam o custo. A interface prepara resumos limitados, conservando os dados completos para exportação e métricas.")
        +"<pre>def passo_euler(t, estado, h, derivada):\n    inclinacao = derivada(t, estado)\n    return [y + h*dy for y, dy in zip(estado, inclinacao)]\n\n# Formulação térmica usada pelo algoritmo:\ndef taxa_termica(T, Pth, C, k, Ta):\n    return (Pth - k*(T-Ta))/C</pre>"
        +_paragraphs("O excerto exprime as equações; a implementação executada está nos módulos do repositório e valida entradas, dimensão, valores finitos e duração final."))
    section(10, "Metodologia experimental", _paragraphs(
        "Experiências 1–8: aquecimento; arrefecimento; convergência/custo; integração; derivadas e ruído; calibração; energia por tarefa; sistema CPU/GPU. Os parâmetros geradores e a semente são fixos. A calibração reserva uma janela temporal disjunta, sem utilizar o holdout no ajuste.",
        "Para a fase real: fixar tarefa/dados e critério de conclusão, instrumentar a mesma fronteira de potência, medir Ta, sincronizar relógios, estabilizar as condições iniciais, controlar carga de fundo, repetir em ordem alternada e registar configuração e incerteza. Reservar sessões independentes para validação.",
        "Não se escolhe um perfil por menor CPU% nem se compara uma tarefa incompleta a uma tarefa concluída. Limites de duração e temperatura devem ser definidos previamente."))
    instrument_html = _paragraphs(
        "SIMULATED designa séries geradas pelas equações; ESTIMATED designa parâmetros ou grandezas inferidas; MEASURED exige uma origem instrumental explícita. Um CSV isolado permanece de origem não verificada até documentação adequada.",
        "Neste relatório, potência e temperatura físicas do computador estão indisponíveis. O inventário abaixo foi recolhido anteriormente no Windows e não foi atualizado por este gerador. Modelo de CPU, GPU ou TDP não fornecem uma potência medida.")
    if data.hardware:
        collected = data.hardware.get("collected_at")
        try:
            stamp = datetime.fromtimestamp(float(collected), timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError, OSError):
            stamp = "não informado"
        instrument_html += _paragraphs(f"Inventário prévio: {data.hardware_path}; collected_at={collected}; instante UTC={stamp}; plataforma declarada={data.hardware.get('platform', 'UNKNOWN')}.")
        instrument_html += _table(Table("Inventário de hardware previamente declarado", ("Categoria", "Grandeza", "Valor reportado", "Origem"),
                                        [(item.get("category", ""), item.get("name", ""), item.get("value", ""), item.get("source", "UNKNOWN"))
                                         for item in data.hardware["items"] if isinstance(item, dict)]))
    else:
        instrument_html += _paragraphs("Não foi fornecido um inventário prévio; não se inventa uma configuração de hardware.")
    section(11, "Dados e instrumentação", instrument_html)
    section(12, "Resultados da simulação", "".join(_experiment(report) for report in data.experiments))
    section(13, "Resultados experimentais", _paragraphs(
        "Não há resultados experimentais de potência, temperatura física ou consumo energético por tarefa nesta entrega. O inventário de hardware é informação de contexto; os tempos perf_counter são observações do tempo de execução das chamadas numéricas.",
        "Não foram executados perfis reais NORMAL/ECO/ULTRA ECO no sistema operativo. Os perfis calculados são inteiramente sintéticos e nenhuma configuração foi alterada.",
        "H1, H4 e H5 não recebem confirmação experimental. H2 e a componente algorítmica de H3 recebem evidência matemática reproduzível. A validação instrumental de H3 permanece por realizar."))
    section(14, "Validação matemática", _table(Table("Verificações realmente executadas durante esta geração", ("Verificação", "Resultado", "Evidência"),
                                                                   [(name, "Passou" if passed else "Falhou", evidence) for name, passed, evidence in data.checks]))
        +_paragraphs("Estas verificações foram avaliadas pelo gerador antes de escrever o relatório. Não equivalem a executar a suite pytest completa nem certificam experiências físicas. Executar python -m pytest para a validação de regressões do repositório."))
    section(15, "Análise de erros", _paragraphs(
        "O erro absoluto é |previsão−referência|; MAE é a média desses módulos e RMSE a raiz da média dos seus quadrados. O erro relativo fica indefinido quando a referência vale zero. Os valores são calculados antes da redução gráfica.",
        "Distinguem-se erro de truncatura, arredondamento, erro de modelo e incerteza experimental. A comparação sintética conhece a verdade geradora; uma medição real não a fornece automaticamente. Ruído e filtragem alteram a derivada e podem introduzir viés.",
        "O holdout mede a previsão numa janela não usada no ajuste, excluindo a condição inicial fornecida. Resíduos estruturados ou autocorrelacionados podem revelar dinâmica omitida; um RMSE pequeno em dados do próprio modelo não valida a física do hardware."))
    section(16, "Convergência e estabilidade", _paragraphs(
        "Para o modo térmico θ′=−(k/C)θ, Euler é absolutamente estável se 0<h<2C/k. Com C=100 J/K e k=2 W/K, a fronteira é 100 s; todos os cinco passos de 1 a 0,01 s estão no interior do regime estável.",
        "A ordem observada usa RMSE temporal sobre cada malha e é omitida junto ao piso de arredondamento. RK4 pode atingir esse piso antes de Euler; reduzir mais o passo pode aumentar custo sem produzir melhoria útil.",
        "Os tempos locais medidos não foram repetidos ou corrigidos de carga concorrente e não são um benchmark de hardware. O relatório mostra os valores observados, sem prometer uma redução de milissegundos reproduzível."))
    section(17, "Otimização energética", _paragraphs(
        "No exemplo, NORMAL consome 600 J em 10 s; ECO consome 675 J em 15 s, embora a potência desça de 60 para 45 W. ULTRA ECO usa 500 J em 20 s, mas falha um prazo de 18 s. O melhor perfil depende das restrições e do trabalho concluído.",
        "Os valores resultam das integrais dos cenários declarados. Não são poupanças medidas neste computador. As recomendações são de leitura, sem suspender processos ou modificar políticas energéticas.",
        "Uma aplicação futura exige repetir a mesma tarefa com energia medida na mesma fronteira e demonstrar uma diferença superior à incerteza, preservando prazo e condições térmicas."))
    provisional = Table("Matriz provisória: requisitos deste prompt, experiências e evidência", ("Requisito do projeto", "Experiência", "Evidência nesta entrega", "Pendente"), [
        ("Balanço e solução analítica", "1–2", "Equações, unidades, tabelas e curvas", "Confrontação com sensores"),
        ("Euler/Heun/RK4 e convergência", "1, 3", "Cinco passos, erros, ordens e custos locais", "Precisão requerida pela aplicação real"),
        ("Integração e energia", "4, 7", "500 J e integral 1/3; J por tarefa", "Energia instrumental e incerteza"),
        ("Derivadas, ruído e filtros", "5", "Semente 42 e métricas nas mesmas amostras", "Modelo de ruído dos sensores"),
        ("Identificabilidade e holdout", "6", "C/k recuperados; rejeição com P=0; janelas disjuntas", "Calibração e validação experimental"),
        ("Sistema CPU/GPU", "8", "Balanços, cancelamento interno e comparação de modelos", "Parâmetros físicos observados"),
        ("Qualidade e reprodutibilidade", "1–8", "Código executável, verificações A–I e HTML/SVG offline", "Enunciado/grelha oficial e relatório de pytest da entrega"),
    ])
    section(18, "Discussão crítica", _paragraphs(
        "A grelha oficial de avaliação não foi fornecida. A matriz seguinte é uma correspondência provisória com os requisitos do prompt, não uma rubrica oficial, e não permite prometer uma classificação.",
        "AGV e compressor são referências metodológicas independentes: integrar velocidade produz distância, integrar pressão em volume produz trabalho e integrar potência em tempo produz energia. Não são o foco da aplicação principal.")+_table(provisional))
    section(19, "Limitações", _paragraphs(
        "Sem potência e temperatura físicas sincronizadas não é possível validar o modelo térmico do PC, calibrar C/k reais ou demonstrar poupança dos perfis. O inventário contém disponibilidade e fontes declaradas, sem resolver a ausência de instrumentação.",
        "Um nó concentrado omite a distribuição espacial; dois nós continuam a ser uma simplificação. k constante não representa controlo de ventoinhas, variação de contacto ou convecção não linear. A conversão entre potência elétrica e térmica não foi calibrada.",
        "Não foram quantificadas incerteza instrumental, repetibilidade ou significância estatística. O holdout sintético pertence ao mesmo gerador e não é uma nova sessão física. As figuras SVG são reduzidas para visualização pelo renderer, mantendo os dados completos no cálculo."))
    section(20, "Conclusões e trabalho futuro", _paragraphs(
        "A implementação traduz conservação da energia em algoritmos Python e verifica-os com referências conhecidas. As oito experiências geradas mostram como passo, método, ruído, parâmetros e restrições afetam os resultados.",
        "H2 é suportada no regime numérico testado e H3 tem a componente de quadratura verificada. H1, H4 e H5 permanecem sem confirmação experimental neste computador; os cenários sintéticos apenas demonstram como poderiam ser avaliadas.",
        "O próximo passo científico é preparar instrumentação e tarefas controladas, registar incerteza e ambiente, reservar sessões independentes e comparar perfis com repetições. Só depois faz sentido calibrar políticas físicas ou alegar poupança real."))
    section(21, "Bibliografia", "<ul>"
        '<li><a href="https://openstax.org/details/books/university-physics-volume-2">OpenStax, University Physics, Volume 2</a>: primeira lei, calor e termodinâmica; apoio aos balanços, sem transcrição de texto.</li>'
        '<li><a href="https://www.nist.gov/pml/owm/metric-si">NIST, Sistema Internacional de Unidades</a>: coerência dimensional e unidades.</li>'
        '<li><a href="https://docs.scipy.org/doc/scipy/reference/generated/scipy.integrate.solve_ivp.html">SciPy, solve_ivp</a>: referência para a formulação de problemas de valor inicial; SciPy não é usado como resolvedor neste projeto.</li>'
        '<li><a href="https://psutil.io/">Documentação oficial psutil</a>: monitorização, interfaces e limitações por plataforma; não fornece universalmente potência ou temperatura.</li></ul>')
    metadata = _table(Table("Registo desta execução", ("Metadado", "Valor"), [
        ("Gerado em UTC", data.generated_at), ("Versão do pacote", data.software_version), ("Ambiente de execução", data.runtime),
        ("Tempo total do gerador numérico, antes da renderização (s)", data.total_elapsed),
        ("Instrumentação energética/térmica física", "Indisponível; experiências SIMULATED"),
        ("Comando de reprodução", ".venv/Scripts/python examples/generate_academic_report.py"),
    ]))
    toc = "<nav><h2>Conteúdo</h2><ol>"+"".join(f'<li><a href="#sec-{i}">Secção {i}</a></li>' for i in range(1, 22))+"</ol></nav>"
    return ('<!doctype html><html lang="pt"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>InProcess · relatório académico final</title><style>'+CSS+
            'article{border-top:2px solid #dbe3ed;margin-top:34px;padding-top:12px}h4{font-size:16px;margin-bottom:6px}nav ol{columns:3}section{scroll-margin-top:20px}</style></head><body><main>'
            '<header><p class="muted">Projeto de Modelação Computacional de Sistemas Físicos</p><h1>InProcess Physical Systems Lab</h1>'
            '<p class="tag">Experiências físicas SIMULATED · custos numéricos cronometrados · inventário prévio separado</p></header>'
            +metadata+toc+"".join(sections)+"</main></body></html>")


def generate_academic_report(path, hardware_path=None, token: Cancellation | None = None) -> str:
    """Execute, validate and atomically write the actual academic artifact."""
    data = run_academic_experiments(hardware_path, token)
    html = render_academic_report(data)
    if token:
        token.check()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, delete=False) as stream:
            temporary = stream.name
            stream.write(html)
        if token:
            token.check()
        os.replace(temporary, target)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    return str(target.resolve())
