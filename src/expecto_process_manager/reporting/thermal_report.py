from dataclasses import asdict
from .document import ScientificReport,Table,Figure,Curve
from ..physics.validation import errors


def thermal_report(experiment,context=None):
    c=experiment.config
    r=experiment.simulation
    report=ScientificReport('Dinâmica térmica e integração de energia','thermal','SIMULATED',
        'Estudar como uma capacidade térmica equivalente armazena energia e como a dissipação para o ambiente determina o aquecimento e arrefecimento. Comparar erro numérico e energia, sem inferir watts da utilização CPU.')
    report.parameters=[('Temperatura inicial',c.initial,'°C'),('Temperatura ambiente',c.ambient,'°C'),
                       ('Potência nominal',c.power,'W'),('Capacidade térmica C',c.capacity,'J/K'),
                       ('Dissipação k',c.dissipation,'W/K'),('Duração',c.duration,'s'),('Passo interno',c.dt,'s'),
                       ('Desvio padrão do ruído',c.noise,'°C'),('Semente',c.seed,'—'),('Cenário',c.scenario,'—'),
                       ('Origem da potência',c.provenance,'—'),('Constante de tempo C/k',c.capacity/c.dissipation,'s'),
                       ('Equilíbrio nominal Ta+P/k',c.ambient+c.power/c.dissipation,'°C')]
    report.equations=['Acumulação = entrada − dissipação',
                     'C · dT/dt = Pth(t) − k(T − Ta)',
                     'Tn+1 = Tn + Δt [Pn − k(Tn − Ta)]/C',
                     'T(t) = Ta + P/k + (T0 − Ta − P/k) exp(−kt/C)',
                     'Eentrada = ∫ P(t) dt; 1 Wh = 3600 J',
                     'ΔU = C(Tfinal − Tinicial); Eentrada − Edissipada = ΔU']
    report.assumptions=['Modelo concentrado com uma temperatura representativa; C e k constantes e positivos.',
                        'Potência térmica e temperatura ambiente consideradas conhecidas ou assumidas. Diferenças em °C e K têm o mesmo valor.',
                        'A potência de entrada é mantida constante à esquerda em cada intervalo (ZOH). A referência analítica é exata para esse forçamento discretizado.',
                        'A potência elétrica de um sensor não é automaticamente igual à potência térmica exata do modelo.']
    report.methods=['Euler explícito calcula o novo estado a partir da taxa no início do intervalo. O erro global esperado é de primeira ordem para o problema suave.',
                    'Heun usa uma previsão de Euler e a média das taxas inicial e prevista; RK4 combina quatro avaliações. Potência mantida constante em cada passo evita comparar forçamentos diferentes nos saltos.',
                    'A integração da potência por trapézios fornece o gráfico de energia. Nos saltos, interpolação linear e retenção à esquerda representam hipóteses distintas.',
                    'A derivação centrada amplifica ruído: para erros independentes de variância σ², a variância da derivada é σ²/(2Δt²). A média móvel reduz ruído mas pode suavizar transições.']
    solutions=getattr(experiment,'method_solutions',{}) or {'Euler':r.temperatures}
    rows=[]
    for name,values in solutions.items():
        metric=errors(values,r.reference)
        rows.append((name,metric['rmse'],metric['maximum'],getattr(experiment,'method_timings',{}).get(name)))
    report.tables.append(Table('Erros contra a referência por intervalo',('Método','RMSE (°C)','Máximo (°C)','Tempo do cálculo (s)'),rows))
    ein=sum((r.times[i+1]-r.times[i])*r.powers[i] for i in range(len(r.times)-1))
    stored=c.capacity*(r.reference[-1]-r.reference[0])
    report.tables.append(Table('Balanço térmico da referência ZOH',('Grandeza','Valor','Unidade'),
                               [('Energia térmica de entrada',ein,'J'),('Variação da energia interna',stored,'J'),
                                ('Energia cedida ao ambiente (com sinal)',ein-stored,'J'),
                                ('Energia integrada por trapézios',experiment.energy[-1],'J'),
                                ('Energia integrada por trapézios',experiment.energy[-1]/3600,'Wh')]))
    colors=['#2176c1','#8f50c4','#199363']
    curves=[Curve(name,r.times,values,colors[i%3]) for i,(name,values) in enumerate(solutions.items())]
    curves.append(Curve('Referência analítica ZOH',r.times,r.reference,'#ba801c'))
    report.figures=[Figure('Temperatura e métodos','Tempo (s)','Temperatura (°C)',curves),
                    Figure('Potência de entrada','Tempo (s)','Potência térmica (W)',[Curve('Amostras de entrada',r.times,r.powers)]),
                    Figure('Energia acumulada','Tempo (s)','Energia (J)',[Curve('Trapézios',r.times,experiment.energy)]),
                    Figure('Derivadas e ruído','Tempo (s)','Taxa (°C/s)',[Curve(n,r.times,v,colors[i]) for i,(n,v) in enumerate(zip(('Sinal sem ruído','Sinal ruidoso','Sinal filtrado'),experiment.derivatives))])]
    report.tables.append(Table('Convergência de Euler a potência constante',('Passo (s)','RMSE (°C)'),experiment.convergence))
    study=getattr(experiment,'method_convergence',{})
    if study:
        all_rows=[]
        conv_fig=[]
        cost_fig=[]
        for i,(method,trials) in enumerate(study.items()):
            valid=[row for row in trials if row['rmse'] is not None]
            all_rows.extend((method,row['dt'],row['rmse'],row['maximum'],row['seconds'],row['order'],row.get('omitted_reason')) for row in trials)
            conv_fig.append(Curve(method,[row['dt'] for row in valid],[row['rmse'] for row in valid],colors[i%3]))
            cost_fig.append(Curve(method,[row['seconds'] for row in valid],[row['rmse'] for row in valid],colors[i%3]))
        report.tables.append(Table('Refinamento e custo por método',('Método','Passo (s)','RMSE (°C)','Máximo (°C)','Tempo (s)','Ordem observada','Omissão'),all_rows))
        report.figures.append(Figure('Erro versus passo interno','Passo Δt (s)','RMSE (°C)',conv_fig))
        report.figures.append(Figure('Erro versus tempo de processamento','Tempo do integrador (s)','RMSE (°C)',cost_fig))
    report.interpretation=[f'A constante de tempo é {c.capacity/c.dissipation:.6g} s. Ao fim de uma constante de tempo, a distância ao equilíbrio do modelo constante reduz-se por um fator exp(−1).',
                           'A energia dissipada pode ter sinal negativo se o ambiente aquecer um corpo mais frio. O balanço deve ser interpretado com a convenção entrada positiva.',
                           'Um passo estável não garante precisão. Para Euler é necessário 0 < Δt < 2C/k; a resposta é monótona quando Δt·k/C ≤ 1.',
                           'O RMSE aqui compara soluções numéricas e referência matemática. Não demonstra que C/k descrevem este computador.']
    report.limitations=['C e k não são parâmetros calibrados do hardware por omissão. Ventoinhas, DVFS, geometria e outros caminhos térmicos não são modelados.',
                        'O erro relativo em Celsius depende da origem da escala; referências nulas tornam a divisão indefinida.',
                        'Nenhuma potência real é inferida de CPU%. Dados CSV permanecem de origem não verificada se não existir instrumentação declarada.']
    report.reproduction=['Guardar/reabrir a configuração JSON preserva parâmetros, ruído e semente; CSV contém os estados.',
                         'O passo interno da simulação é independente da frequência real de amostragem dos sensores.']
    report.technical_notes=experiment.report
    report.metadata.update(context or {})
    return report
