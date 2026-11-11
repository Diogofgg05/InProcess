from .document import ScientificReport,Table,Curve,Figure


def numerical_report(experiment,context=None):
    mode=experiment.config['mode']
    titles={'derivatives':'Derivadas, ruído e filtragem','integration':'Integração numérica de funções conhecidas','ode':'Equações diferenciais · comparação de métodos'}
    report=ScientificReport(titles[mode],'numerical','SIMULATED',
        'Validar os algoritmos em funções com referência analítica antes de interpretar dados de sensores ou previsões físicas.')
    labels={'mode':'Tipo de experiência','preset':'Função de referência','start':'Início do domínio','end':'Fim do domínio',
            'intervals':'Número de intervalos','noise_sigma':'Desvio padrão do ruído','seed':'Semente aleatória',
            'filter_window':'Largura da média móvel','ode_model':'Equação diferencial','coefficient':'Coeficiente a ou ω',
            'initial':'Estado inicial','initial_velocity':'Derivada inicial','dt':'Passo interno'}
    units={'start':'s' if mode=='ode' else '1','end':'s' if mode=='ode' else '1',
           'coefficient':'s⁻¹','dt':'s','initial':'1','initial_velocity':'s⁻¹','filter_window':'amostras',
           'noise_sigma':'unidade do sinal'}
    report.parameters=[(labels.get(key,key),value,units.get(key,'—')) for key,value in experiment.config.items()]
    report.assumptions=['As funções de teste são conhecidas e não são medições de hardware.',
                        'Os resultados completos são usados nas métricas; a representação gráfica é reduzida sem alterar os dados de exportação.',
                        'Malhas e extremos são tratados explicitamente; não se inventam amostras nos pontos médios.']
    report.equations=['Progressiva: f′i ≈ (fi+1 − fi)/(ti+1 − ti)',
                     'Regressiva: f′i ≈ (fi − fi−1)/(ti − ti−1)',
                     'Centrada uniforme: f′i ≈ (fi+1 − fi−1)/(2h)',
                     'Segunda derivada uniforme: f″i ≈ (fi+1 − 2fi + fi−1)/h²',
                     'Trapézios: I ≈ Σ (ti+1 − ti)(fi+1 + fi)/2',
                     'EDO: y′ = f(t,y); Euler: yn+1 = yn + h f(tn,yn)']
    report.methods=['Diferenças finitas usam os pontos efetivamente disponíveis. A implementação central usa interpolação quadrática em malhas não uniformes; os extremos têm stencils unilaterais.',
                    'Retângulos à esquerda/direita, pontos médios genuínos, trapézios e Simpson são comparados com uma primitiva conhecida. Simpson requer um número par de intervalos uniformes.',
                    'Euler, Heun e RK4 são implementados diretamente com uma, duas e quatro avaliações da derivada. A função aceita um vetor de estados e não executa expressões de texto.',
                    'Mede-se o tempo do método nesta execução. Valores próximos do arredondamento não justificam interpretar uma ordem assintótica como universal.']
    rows=[]
    for row in experiment.results_table:
        rows.append(tuple(row.get(key) for key in ('method','value','exact','absolute_error','relative_error','rmse','maximum_error','elapsed_ms')))
    report.tables.append(Table('Comparação com a referência analítica',
                        ('Método','Valor final','Referência','Erro absoluto final','Erro relativo final','RMSE','Erro máximo','Tempo (ms)'),rows))
    colors=['#2176c1','#9756b6','#1c946b','#d48b18','#a35722']
    def curves(mapping):
        return [Curve(name,experiment.times,values,colors[i%len(colors)]) for i,(name,values) in enumerate(mapping.items())]
    x_label='Tempo (s)' if mode=='ode' else 'Variável independente (adimensional)'
    report.figures=[Figure('Solução ou derivadas comparadas',x_label,'Resultado (adimensional)',curves(experiment.series)),
                    Figure('Erro absoluto contra a referência',x_label,'Erro absoluto',curves(experiment.error_series))]
    if experiment.diagnostic_series:
        report.figures.append(Figure('Diagnóstico adicional','Variável independente (adimensional)','Grandeza adimensional',curves(experiment.diagnostic_series)))
    if experiment.convergence:
        convrows=[]
        for method,values in experiment.convergence.items():
            convrows.extend((method,h,error) for h,error in values)
        report.tables.append(Table('Convergência no mesmo instante final',('Método','Passo','Erro final'),convrows))
    report.interpretation=['O erro é conhecido porque existe uma solução analítica independente neste ensaio. Esta confirmação matemática não calibra um sensor real.',
                           'O efeito de reduzir o passo depende do truncamento, do arredondamento e do ruído. A derivação pode piorar mesmo quando a malha fica mais fina.',
                           'As ordens esperadas para problemas suaves são 1 para Euler, 2 para Heun e 4 para RK4. Funções especiais ou erros quase nulos podem ocultar essas ordens.']
    report.limitations=['As funções de derivação/integração usam variáveis adimensionais para isolar o algoritmo. Nos exemplos EDO, o tempo é em segundos, o estado é adimensional e a sua derivada tem unidade s⁻¹. Ao aplicar a T, P, x ou v, devem ser atribuídas as unidades físicas correspondentes.',
                        'Um filtro pode reduzir ruído e introduzir viés ou atraso. A média móvel centrada não é um filtro causal para controlo em tempo real.',
                        'As condições de estabilidade dependem da equação; as do decaimento linear não devem ser aplicadas universalmente a qualquer sistema.']
    report.reproduction=['Repetir com a configuração e semente indicadas. Funções personalizadas são fornecidas como callables Python à API científica, nunca por eval na interface.']
    report.technical_notes=experiment.report
    report.metadata.update((context or {}).get('metadata',{}))
    return report
