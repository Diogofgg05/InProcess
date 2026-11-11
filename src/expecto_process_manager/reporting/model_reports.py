"""Model-specific, Qt-free scientific reports with explicit provenance."""
from dataclasses import asdict, is_dataclass

from .document import Curve, Figure, ScientificReport, Table
from ..physics.integration import cumulative
from ..physics.numerical.validation import metrics


COLORS = ("#2176c1", "#9756b6", "#1c946b", "#d48b18")


def _finish(report, context):
    context = context or {}
    report.metadata.update(context.get("metadata", {}))
    if context.get("provenance") is not None:
        report.metadata["Proveniência declarada da entrada"] = context["provenance"]
    return report


def _parameters(context):
    context = context or {}
    value = context.get("config", context.get("parameters", {}))
    return asdict(value) if is_dataclass(value) else dict(value or {})


def gravity_report(experiment, context=None) -> ScientificReport:
    config = experiment.config
    report = ScientificReport(
        "Gravitação Newtoniana · comparação de integradores", "gravity", "SIMULATED",
        "Determinar como o método e o passo temporal afetam uma órbita sob uma força central e avaliar os erros de posição e conservação.",
        parameters=[("Massa central M", config.central_mass, "kg"), ("Massa de teste m", config.body_mass, "kg"),
                    ("Raio inicial R", config.radius, "m"), ("Velocidade inicial / circular", config.velocity_factor, "1"),
                    ("Velocidade circular", config.circular_speed, "m/s"), ("Período circular", config.period, "s"),
                    ("Duração", config.duration, "s"), ("Passo nominal", config.dt, "s")],
        equations=["r″ = −GM r / |r|³", "E = m|v|²/2 − GMm/|r|", "Lz = m(x vy − y vx)",
                   "Órbita circular: x = R cos(ωt), y = R sin(ωt), ω = √(GM/R³)"],
        assumptions=["Massa central pontual e fixa; corpo de teste sem recuo da massa central.",
                     "Movimento plano, sem atmosfera, colisões, superfície de impacto ou relatividade.",
                     "As trajetórias são geradas matematicamente; não são observações orbitais."],
        methods=["Euler explícito atualiza posição e velocidade com o estado anterior; é de primeira ordem e pode acumular deriva de energia.",
                 "Euler simplético atualiza primeiro a velocidade e depois a posição; é de primeira ordem e conserva a estrutura geométrica da força central.",
                 "Velocity Verlet usa a força nos dois extremos do passo e tem segunda ordem para forças suaves.",
                 "A malha respeita a duração final por encurtamento do último intervalo. Os diagnósticos usam todas as amostras, antes da redução gráfica."],
        limitations=["Conservação numérica de energia ou momento angular não demonstra, por si, precisão da posição.",
                     "O limite de passos protege os recursos e não garante estabilidade. Passos grandes podem produzir trajetórias sem significado físico.",
                     "O centro singular é protegido numericamente; esta proteção não constitui um modelo de colisão.",
                     "A massa de teste altera E e Lz, mas não a aceleração nesta aproximação; massas comparáveis exigem outro modelo."],
        reproduction=["Reproduzir com physics.gravity.run_gravity(GravityConfig(**parâmetros)); todos os valores de entrada estão na tabela.",
                      "Comparar passos menores mantendo as mesmas condições iniciais e a mesma duração; não alterar a física ao estudar convergência."],
        technical_notes=experiment.report,
    )
    orbits, energy_curves, momentum_curves, error_curves = [], [], [], []
    rows, position_scores = [], {}
    for i, (method, trajectory) in enumerate(experiment.trajectories.items()):
        color = COLORS[i % len(COLORS)]
        orbits.append(Curve(method, [x/1000 for x in trajectory.x], [y/1000 for y in trajectory.y], color))
        energy0, momentum0 = trajectory.energy[0], trajectory.angular_momentum[0]
        energy_error = metrics(trajectory.energy, [energy0]*len(experiment.times))
        momentum_error = metrics(trajectory.angular_momentum, [momentum0]*len(experiment.times))
        characteristic = config.mu*config.body_mass/config.radius
        relative_energy = energy_error["maximum"]/abs(energy0) if abs(energy0) > 1e-12*characteristic else None
        rmse = maximum = None
        if trajectory.position_error is not None:
            position = metrics(trajectory.position_error, [0]*len(trajectory.position_error))
            rmse, maximum = position["rmse"], position["maximum"]
            position_scores[method] = rmse
            error_curves.append(Curve(method, experiment.times, [e/1000 for e in trajectory.position_error], color))
        rows.append((method, energy_error["maximum"], relative_energy, momentum_error["maximum"], rmse, maximum))
        energy_curves.append(Curve(method, experiment.times, [e-energy0 for e in trajectory.energy], color))
        momentum_curves.append(Curve(method, experiment.times, [v-momentum0 for v in trajectory.angular_momentum], color))
    if experiment.reference_x is not None:
        orbits.append(Curve("Referência circular independente", [x/1000 for x in experiment.reference_x],
                            [y/1000 for y in experiment.reference_y], COLORS[3]))
    report.tables.append(Table("Erros e conservação nas trajetórias completas",
                               ("Método", "Máx. |ΔE| (J)", "Máx. |ΔE|/|E₀|", "Máx. |ΔLz| (kg·m²/s)",
                                "RMSE posição (m)", "Máx. erro posição (m)"), rows))
    report.figures.extend([
        Figure("Órbitas com escalas espaciais iguais", "x (km)", "y (km)", orbits, True),
        Figure("Deriva de energia mecânica", "Tempo (s)", "E − E₀ (J)", energy_curves),
        Figure("Deriva de momento angular", "Tempo (s)", "Lz − Lz₀ (kg·m²/s)", momentum_curves),
    ])
    if error_curves:
        report.figures.append(Figure("Erro de posição face à órbita circular", "Tempo (s)", "Erro absoluto (km)", error_curves))
        best = min(position_scores, key=position_scores.get)
        report.interpretation.append(f"Neste ensaio, {best} apresentou o menor RMSE de posição ({position_scores[best]:.6g} m). Esta comparação vale para os parâmetros e a duração apresentados.")
        report.interpretation.append("O fator de velocidade igual a 1 permite uma referência circular independente. A diferença de posição mede erro numérico relativamente a essa solução do mesmo modelo.")
    else:
        report.interpretation.append("A velocidade inicial não corresponde à condição circular. Não se usa uma órbita circular como referência incorreta nem se apresenta RMSE de posição sem referência independente.")
    report.interpretation.append("Aumentar ou reduzir E ou Lz numa dinâmica idealmente conservativa revela defeitos da discretização; erros próximos de zero devem ser interpretados à luz do arredondamento.")
    report.limitations.append("Quando E₀ está próximo de zero, o erro relativo de energia fica indefinido; a tabela conserva o erro absoluto em joules.")
    if experiment.convergence:
        report.tables.append(Table("Refinamento do passo para a referência circular", ("Passo (s)", "Método", "RMSE posição (m)"),
                                   [(step, method, error) for step, values in experiment.convergence for method, error in values.items()]))
        report.interpretation.append("O refinamento verifica convergência no intervalo amostrado; alguns refinamentos podem ser omitidos pelo limite de custo da análise automática.")
    return _finish(report, context)


def free_fall_report(presentation, context=None) -> ScientificReport:
    result = getattr(presentation, "result", presentation)
    parameters = getattr(presentation, "parameters", _parameters(context))
    gravity = parameters.get("gravity")
    height_errors = metrics(result.heights, result.reference_heights)
    velocity_errors = metrics(result.velocities, result.reference_velocities)
    report = ScientificReport(
        "Queda livre · Euler e solução analítica", "free_fall", "SIMULATED",
        "Avaliar a aproximação de Euler à queda livre sob gravidade uniforme, separando erro numérico de altura e velocidade.",
        parameters=[("Altura inicial", result.heights[0], "m"), ("Velocidade inicial", result.velocities[0], "m/s"),
                    ("Aceleração g", gravity, "m/s²"), ("Duração", result.times[-1]-result.times[0], "s"),
                    ("Passo nominal", parameters.get("dt"), "s")],
        equations=["y′ = v; v′ = −g", "yₙ₊₁ = yₙ + h vₙ; vₙ₊₁ = vₙ − h g",
                   "y(t) = y₀ + v₀t − gt²/2; v(t) = v₀ − gt", "Energia específica e = v²/2 + gy"],
        assumptions=["Eixo vertical positivo para cima; g constante e não negativo; ausência de arrasto.",
                     "Sem chão nem impacto: alturas negativas representam posições abaixo da origem escolhida.",
                     "Todos os valores são simulados; a solução analítica é uma referência do mesmo modelo ideal."],
        methods=["Euler explícito integra o sistema posição/velocidade com o mesmo passo e ajusta o último intervalo à duração.",
                 "O erro absoluto, MAE, RMSE e máximo usam as séries completas. O erro relativo é indefinido quando a referência vale zero.",
                 "Para g constante, a velocidade de Euler é exata até arredondamento; o erro global da altura é de primeira ordem no passo."],
        tables=[Table("Erros face à solução analítica", ("Grandeza", "MAE", "RMSE", "Máximo", "Unidade"),
                      [("Altura", height_errors["mae"], height_errors["rmse"], height_errors["maximum"], "m"),
                       ("Velocidade", velocity_errors["mae"], velocity_errors["rmse"], velocity_errors["maximum"], "m/s")])],
        figures=[Figure("Altura e referência independente", "Tempo (s)", "Altura (m)",
                        [Curve("Euler", result.times, result.heights, COLORS[0]), Curve("Analítica", result.times, result.reference_heights, COLORS[3])]),
                 Figure("Velocidade e referência independente", "Tempo (s)", "Velocidade (m/s)",
                        [Curve("Euler", result.times, result.velocities, COLORS[0]), Curve("Analítica", result.times, result.reference_velocities, COLORS[3])]),
                 Figure("Erro absoluto de altura", "Tempo (s)", "Erro absoluto (m)", [Curve("Euler", result.times, height_errors["absolute"])])],
        interpretation=[f"O RMSE da altura é {height_errors['rmse']:.6g} m; o da velocidade é {velocity_errors['rmse']:.6g} m/s. São erros matemáticos face à solução analítica, não incertezas de sensores.",
                        "Euler usa a velocidade do início de cada intervalo. Sob aceleração descendente constante, isso produz uma altura acima da referência, com diferença acumulada g·Σh²/2."],
        limitations=["A energia é específica, em J/kg; não se inventa uma massa para apresentar energia total.",
                     "O modelo de g uniforme deixa de ser adequado para grandes variações de altitude; o modelo não descreve impacto nem resistência do ar."],
        reproduction=["Executar physics.gravity.free_fall_euler com os parâmetros apresentados e repetir com metade do passo, mantendo a duração.",
                      "A comparação é determinística e não contém ruído sintético nem medições reais."],
    )
    if gravity is not None:
        energy = [v*v/2+gravity*y for y, v in zip(result.heights, result.velocities)]
        initial_energy = result.velocities[0]**2/2+gravity*result.heights[0]
        drift = metrics(energy, [initial_energy]*len(energy))
        report.figures.append(Figure("Energia específica e conservação", "Tempo (s)", "Energia específica (J/kg)",
                                     [Curve("Euler", result.times, energy), Curve("Referência constante", result.times, [initial_energy]*len(energy), COLORS[3])]))
        report.tables.append(Table("Conservação", ("Diagnóstico", "Valor", "Unidade"), [("Máx. |e−e₀|", drift["maximum"], "J/kg")]))
    else:
        report.limitations.append("O valor de g não acompanhou o resultado; não se reconstruiu a energia nem se assumiu uma aceleração por omissão.")
    return _finish(report, context)


def energy_report(comparison, context=None) -> ScientificReport:
    sources = sorted({run.provenance for run in comparison.runs})
    provenance = " / ".join(sources)
    report = ScientificReport(
        "Energia por tarefa · comparação de perfis", "energy", provenance,
        "Comparar a energia necessária para concluir a mesma tarefa em NORMAL, ECO e ULTRA ECO, respeitando as restrições declaradas.",
        parameters=[("Tarefa", comparison.runs[0].task_id or "não identificada", ""),
                    ("Trabalho por tarefa", comparison.runs[0].work_units, comparison.runs[0].work_label)],
        equations=["E = ∫ P(t) dt", "Etrap = Σ (Pᵢ + Pᵢ₊₁)(tᵢ₊₁ − tᵢ)/2", "1 Wh = 3600 J",
                   "Eficiência = trabalho concluído / energia consumida"],
        assumptions=["Instantes em segundos e potência explícita em watts; a utilização de CPU não é convertida em potência.",
                     "A comparação requer a mesma tarefa, a mesma unidade e quantidade de trabalho concluído e proveniências de potência compatíveis.",
                     "Computador, carga de fundo, fronteira de potência e condições experimentais devem ser comparáveis; estes requisitos não são certificados pelo CSV."],
        methods=["Os trapézios usam os intervalos reais, incluindo amostragem não uniforme. A potência média é energia dividida pela duração.",
                 "Os limites de duração e temperatura filtram os perfis admissíveis. Sem uma série térmica, não é possível confirmar um limite térmico.",
                 "Entre perfis comparáveis e admissíveis escolhe-se a menor energia; em empate usa-se a menor duração. Não se aplica nenhuma configuração ao sistema operativo."],
        tables=[Table("Consumo e admissibilidade", ("Perfil", "Origem potência", "Duração (s)", "Energia (J)", "Energia (Wh)",
                                                     "Potência média (W)", "T máxima (°C)", "Trabalho/J", "Admissível", "Motivo"),
                      [(row.policy, row.provenance, row.duration, row.energy_j, row.energy_wh, row.average_power,
                        row.max_temperature, row.efficiency, row.feasible, "; ".join(row.reasons) or "Condições satisfeitas") for row in comparison.rows]),
                Table("Metadados declarados por perfil", ("Perfil", "Tarefa", "Trabalho", "Unidade", "Concluído", "Origem térmica"),
                      [(run.policy, run.task_id, run.work_units, run.work_label, run.work_completed,
                        run.temperature_provenance or "UNKNOWN") for run in comparison.runs])],
        limitations=["Importar números não demonstra que um sensor os mediu; MEASURED é uma declaração do fornecedor dos dados.",
                     "Potência elétrica e potência térmica têm significados distintos. A origem da temperatura é independente da origem da potência.",
                     "O intervalo analisado não inclui energia anterior ou posterior, nem perdas fora da fronteira de medição.",
                     "Não foram calculados intervalos de confiança, repetibilidade, incerteza de sensores ou significância estatística da diferença."],
        reproduction=["Usar optimization.eco.PolicyRun e compare_policies com os mesmos dados, tarefa, trabalho e restrições.",
                      "CSV de potência: time_s,power_w e, opcionalmente, temperature_c; os metadados de tarefa e origem são fornecidos separadamente."],
        technical_notes=comparison.report,
    )
    config = _parameters(context)
    for key, label, unit in (("max_duration", "Prazo máximo", "s"), ("max_temperature", "Limite térmico", "°C")):
        if key in config:
            report.parameters.append((label, config[key] if config[key] is not None else "sem limite", unit))
    powers, energies, temperatures = [], [], []
    for i, run in enumerate(comparison.runs):
        time = [t-run.times[0] for t in run.times]
        color = COLORS[i % len(COLORS)]
        if run.powers is not None:
            powers.append(Curve(run.policy, time, run.powers, color))
            # Normalize before the legacy cumulative trapezoid so adding two
            # individually finite powers cannot overflow its intermediate sum.
            scale = max(run.powers)
            accumulated = ([2*v*scale for v in cumulative(run.times, [p/scale/2 for p in run.powers])]
                           if scale else [0.0]*len(run.times))
            energies.append(Curve(run.policy, time, accumulated, color))
        if run.temperatures is not None:
            temperatures.append(Curve(run.policy, time, run.temperatures, color))
    report.figures.extend([Figure("Potência por perfil", "Tempo decorrido (s)", "Potência (W)", powers),
                           Figure("Energia acumulada por tarefa", "Tempo decorrido (s)", "Energia (J)", energies)])
    if temperatures:
        report.figures.append(Figure("Temperaturas fornecidas, sem inferência de sensores", "Tempo decorrido (s)", "Temperatura (°C)", temperatures))
    if comparison.recommendation:
        source_label = "no cenário simulado" if sources == ["SIMULATED"] else "nos dados fornecidos"
        report.interpretation.append(f"O perfil de menor energia admissível {source_label} é {comparison.recommendation}. A recomendação compara os ensaios e não aplica uma política ao computador.")
    else:
        reason = " ".join(comparison.reasons) or "Nenhum perfil satisfez todas as restrições."
        report.interpretation.append("Sem recomendação: "+reason)
    normal = next((row for row in comparison.rows if row.policy == "NORMAL"), None)
    if comparison.comparable and normal is not None and normal.energy_j is not None and normal.energy_j > 0:
        report.tables.append(Table("Diferença para NORMAL na mesma tarefa", ("Perfil", "Eperfil − Enormal (J)", "Redução relativa de energia"),
                                   [(row.policy, row.energy_j-normal.energy_j, (normal.energy_j-row.energy_j)/normal.energy_j)
                                    for row in comparison.rows if row.energy_j is not None]))
    report.interpretation.append("Uma potência menor pode exigir uma duração maior e resultar em mais energia. O valor em joules por tarefa é a comparação relevante para o trabalho declarado.")
    if "SIMULATED" in sources:
        report.interpretation.append("Os dados SIMULATED ilustram o método; não demonstram poupança real nem desempenho deste computador.")
    return _finish(report, context)


def calibration_report(result, context=None) -> ScientificReport:
    context = context or {}
    source = context.get("provenance", "UNKNOWN")
    report = ScientificReport(
        "Calibração térmica · identificação de C e k", "calibration", f"ESTIMATED · entrada {source}",
        "Estimar capacidade e dissipação térmicas de um modelo concentrado e testar a previsão num intervalo temporal reservado, sem reutilizar os dados de ajuste.",
        parameters=[("Capacidade estimada C", result.capacity, "J/K"), ("Dissipação estimada k", result.dissipation, "W/K"),
                    ("Constante de tempo τ = C/k", result.time_constant, "s"),
                    ("Número de condição do Jacobiano", result.condition_number, "1")],
        equations=["C dT/dt = Pth − k(T − Ta)", "τ = C/k",
                   "Tᵢ₊₁ = Ta + (Tᵢ − Ta)e^(−kΔtᵢ/C) + (Pᵢ/k)(1 − e^(−kΔtᵢ/C))",
                   "Matriz de sensibilidade Jᵢⱼ = ∂Tᵢ₊₁ / ∂log(θⱼ), θ = (C,k)",
                   "Regressão alternativa: T′ = aPth + b(Ta−T), C=1/a, k=b/a", "Resíduo r = Tobservada − Tprevista"],
        assumptions=["C e k positivos e constantes; ambiente fixo e modelo de temperatura uniforme.",
                     "A potência térmica é mantida constante ao valor esquerdo em cada intervalo (ZOH). Potência elétrica não é automaticamente potência térmica.",
                     "A proveniência da entrada é declarada pelo utilizador. CSV sem verificação mantém origem UNKNOWN; os parâmetros ajustados são ESTIMATED."],
        methods=["O método integral_zoh minimiza erros de previsão a um passo com projeção do ganho 1/k, procura em log(k/C) e refinamento unidimensional.",
                 "A alternativa derivative ajusta derivadas numéricas; é mais sensível a ruído e erros nas variáveis, sobretudo em mudanças de potência.",
                 "O condicionamento em log(C), log(k) testa a independência local das duas colunas da matriz de sensibilidade. Sem posto completo, C e k não podem ser separados.",
                 "Treino e holdout ocupam janelas sem sobreposição. A temperatura inicial de cada janela é fornecida e excluída das métricas, não apresentada como previsão."],
        limitations=["Arrefecimento com P=0 identifica apenas a razão k/C; equilíbrio térmico ou excitação insuficiente não identificam os dois parâmetros independentemente.",
                     "Um número de condição aceitável não elimina erro de modelo, viés, ruído correlacionado ou falta de calibração dos sensores.",
                     "O holdout temporal reduz reutilização de amostras, mas não equivale a uma repetição experimental independente.",
                     "Não são fornecidos intervalos de confiança para C e k; um bom ajuste não prova que o modelo descreve toda a física do computador."],
        reproduction=["Executar physics.calibration.fit_thermal com a mesma série de treino, ambiente, método e validação reservada.",
                      "Preservar o referencial temporal comum, as unidades °C/s/W e a divisão temporal; não escolher o holdout com base no erro final."],
        technical_notes=result.report,
    )
    parameters = _parameters(context)
    ambient = context.get("ambient", parameters.get("ambient"))
    if ambient is not None:
        report.parameters.append(("Ambiente Ta", ambient, "°C"))
    else:
        report.limitations.append("A temperatura ambiente não acompanhou o objeto de resultado; deve ser preservada com os dados para reprodução completa.")
    report.parameters.append(("Método de ajuste", result.method, ""))
    rows, temperature_curves, residual_curves = [], [], []
    for i, (label, evaluation) in enumerate((("Treino", result.training), ("Validação reservada", result.validation))):
        rows.append((label, len(evaluation.times), evaluation.times[0], evaluation.times[-1], evaluation.errors["mae"],
                     evaluation.errors["rmse"], evaluation.errors["maximum"], evaluation.residual_mean,
                     evaluation.residual_std, evaluation.residual_lag1))
        temperature_curves.extend([Curve(label+" · entrada", evaluation.times, evaluation.observed, COLORS[2*i]),
                                   Curve(label+" · previsão", evaluation.times, evaluation.predicted, COLORS[2*i+1])])
        residual_curves.append(Curve(label, evaluation.times, evaluation.residuals, COLORS[i]))
    report.tables.append(Table("Avaliação por janela, excluindo a condição inicial", ("Janela", "Amostras", "Início (s)", "Fim (s)",
                                                                                   "MAE (°C)", "RMSE (°C)", "Máximo (°C)",
                                                                                   "Média resíduo (°C)", "Desvio resíduo (°C)", "Autocorrelação lag 1"), rows))
    report.figures.extend([Figure("Temperaturas fornecidas e previsões", "Tempo (s)", "Temperatura (°C)", temperature_curves),
                           Figure("Resíduos por janela", "Tempo (s)", "Observada − prevista (°C)", residual_curves)])
    report.interpretation.append(f"O ajuste estimou τ = {result.time_constant:.6g} s. A constante de tempo expressa a rapidez de resposta deste modelo, não a frequência nem a capacidade elétrica do processador.")
    report.interpretation.append(f"O RMSE reservado é {result.validation.errors['rmse']:.6g} °C, face a {result.training.errors['rmse']:.6g} °C no treino. A conclusão é limitada às janelas e hipóteses fornecidas.")
    if result.condition_number > 1e3:
        report.interpretation.append("O condicionamento elevado indica forte sensibilidade dos parâmetros; mais excitação térmica e ensaios independentes são necessários antes de uma interpretação física robusta.")
    else:
        report.interpretation.append("O condicionamento passou o critério numérico do estimador; isto suporta identificabilidade local, sem certificar o modelo físico.")
    report.interpretation.append("Resíduos com média persistente ou autocorrelação podem indicar viés, dinâmica omitida ou ruído estruturado. Autocorrelação indefinida com variância nula não deve ser apresentada como zero medido.")
    return _finish(report, context)


def coupled_report(result, context=None) -> ScientificReport:
    config = _parameters(context)
    report = ScientificReport(
        "Modelo térmico acoplado · CPU e GPU", "coupled_thermal", "SIMULATED",
        "Simular a troca de calor entre dois nós térmicos e verificar o balanço global de energia, distinguindo acoplamento físico de erro numérico.",
        parameters=[("Temperatura inicial CPU", result.cpu_temperatures[0], "°C"),
                    ("Temperatura inicial GPU", result.gpu_temperatures[0], "°C"),
                    ("Potência térmica CPU", result.cpu_powers[0], "W"), ("Potência térmica GPU", result.gpu_powers[0], "W"),
                    ("Duração", result.times[-1]-result.times[0], "s"), ("Método", result.method.upper(), "")],
        equations=["Cc Tc′ = Pc − kc(Tc−Ta) − kcg(Tc−Tg)", "Cg Tg′ = Pg − kg(Tg−Ta) + kcg(Tc−Tg)",
                   "ΔU = Cc(Tc−Tc₀) + Cg(Tg−Tg₀)", "Eentrada − Eambiente − ΔU = 0",
                   "−kcg(Tc−Tg) + kcg(Tc−Tg) = 0"],
        assumptions=["CPU e GPU são dois nós uniformes com capacidades, dissipações e acoplamento constantes.",
                     "Potências térmicas e ambiente fixos; sem sensores reais, ajuste automático de ventoinhas ou identificação de hardware.",
                     "O acoplamento transfere calor internamente do nó mais quente para o mais frio; não cria energia."],
        methods=[f"O método {result.method.upper()} integra temperaturas e energias nos mesmos estágios da mesma EDO.",
                 "As curvas independentes usam a solução analítica com kcg=0. Com acoplamento diferente de zero, representam outro modelo físico, não a referência exata da solução acoplada.",
                 "O resíduo de balanço testa consistência algébrica. Como as energias são integradas no mesmo sistema, esse resíduo não constitui uma validação independente da precisão."],
        tables=[Table("Balanço no fim do intervalo", ("Grandeza", "Valor", "Unidade"),
                      [("Energia de entrada", result.input_energy[-1], "J"), ("Energia líquida para o ambiente", result.dissipated_energy[-1], "J"),
                       ("Variação de energia armazenada", result.stored_energy[-1], "J"),
                       ("Máximo resíduo absoluto do balanço", max(abs(v) for v in result.balance_residual), "J")]),
                Table("Temperaturas simuladas", ("Nó", "Inicial (°C)", "Final (°C)", "Máxima (°C)"),
                      [("CPU", result.cpu_temperatures[0], result.cpu_temperatures[-1], max(result.cpu_temperatures)),
                       ("GPU", result.gpu_temperatures[0], result.gpu_temperatures[-1], max(result.gpu_temperatures))])],
        figures=[Figure("Temperaturas acopladas e comparação sem acoplamento", "Tempo (s)", "Temperatura (°C)",
                        [Curve("CPU acoplada", result.times, result.cpu_temperatures, COLORS[0]),
                         Curve("GPU acoplada", result.times, result.gpu_temperatures, COLORS[1]),
                         Curve("CPU independente", result.times, result.independent_cpu, COLORS[2]),
                         Curve("GPU independente", result.times, result.independent_gpu, COLORS[3])]),
                 Figure("Energias do sistema de dois nós", "Tempo (s)", "Energia (J)",
                        [Curve("Entrada", result.times, result.input_energy, COLORS[0]),
                         Curve("Ambiente", result.times, result.dissipated_energy, COLORS[1]),
                         Curve("Variação armazenada", result.times, result.stored_energy, COLORS[2])]),
                 Figure("Resíduo do balanço", "Tempo (s)", "Eentrada − Eambiente − ΔU (J)",
                        [Curve("Consistência algébrica", result.times, result.balance_residual)])],
        interpretation=["Ao somar os dois balanços, os termos de acoplamento cancelam exatamente. A soma da energia dos nós só varia por entrada externa e troca com o ambiente.",
                        f"O maior resíduo absoluto é {max(abs(v) for v in result.balance_residual):.6g} J. Um valor pequeno suporta a consistência do balanço implementado, sem provar a exatidão das temperaturas.",
                        "A energia armazenada é uma variação relativamente ao estado inicial. A troca líquida com o ambiente pode ser negativa se um nó estiver mais frio do que o ambiente."],
        limitations=["Nenhuma curva representa temperatura medida da CPU ou GPU deste computador.",
                     "Parâmetros constantes e temperatura uniforme omitem geometria, ventoinhas, contactos térmicos variáveis e distribuição espacial do calor.",
                     "Um passo deve resolver o modo térmico mais rápido. A conservação algébrica não substitui um estudo de convergência nem uma medição independente."],
        reproduction=["Executar physics.coupled_thermal.simulate_coupled com a configuração, método, condições iniciais, potências e duração apresentados.",
                      "Repetir com passos menores. Para comparar erro com as curvas independentes, usar explicitamente kcg=0."],
        technical_notes=result.report,
    )
    for key, label, unit in (("ambient", "Ambiente Ta", "°C"), ("cpu_capacity", "Capacidade CPU", "J/K"),
                              ("gpu_capacity", "Capacidade GPU", "J/K"), ("cpu_dissipation", "Dissipação CPU", "W/K"),
                              ("gpu_dissipation", "Dissipação GPU", "W/K"), ("coupling", "Acoplamento CPU/GPU", "W/K"),
                              ("dt", "Passo nominal", "s")):
        if key in config:
            report.parameters.append((label, config[key], unit))
    if config.get("coupling") == 0:
        cpu_error = metrics(result.cpu_temperatures, result.independent_cpu)
        gpu_error = metrics(result.gpu_temperatures, result.independent_gpu)
        report.tables.append(Table("Validação independente, apenas para kcg=0", ("Nó", "RMSE (°C)", "Máximo (°C)"),
                                   [("CPU", cpu_error["rmse"], cpu_error["maximum"]), ("GPU", gpu_error["rmse"], gpu_error["maximum"])]))
    if not all(key in config for key in ("ambient", "cpu_capacity", "gpu_capacity", "cpu_dissipation", "gpu_dissipation", "coupling")):
        report.limitations.append("A configuração completa C/k/acoplamento não acompanhou o resultado. Não foram inventados parâmetros por omissão; preservar a configuração é necessário para reprodução fiel.")
    return _finish(report, context)
