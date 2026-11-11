# Motor numérico e identificação térmica

O código científico em `physics/numerical`, `physics/calibration.py` e
`physics/coupled_thermal.py` funciona sem interface gráfica, sensores, IA, NumPy
ou privilégios administrativos. Trabalha com números reais finitos e rejeita
tempos repetidos ou decrescentes. Os resultados calculados não demonstram, por
si só, o comportamento térmico do computador onde a aplicação está instalada.

## 1. Derivadas e ruído

```python
from expecto_process_manager.physics.numerical.derivatives import differentiate

t = [0, 0.1, 0.3, 0.8, 1.0]
y = [time**2 for time in t]
first = differentiate(t, y, method="central", order=1)   # 2t
second = differentiate(t, y, method="central", order=2) # 2
```

`forward` e `backward` usam dois pontos na primeira derivada: são de primeira
ordem em malhas uniformes. No extremo sem vizinho disponível usam a diferença
unilateral oposta. `central` usa a derivada do interpolador quadrático local de
três pontos, com fórmulas unilaterais quadráticas nas extremidades. Com apenas
duas amostras usa a secante comum. A segunda derivada requer três amostras e
usa interpolação quadrática, deslocando o stencil nos extremos. É de segunda
ordem no interior de uma malha uniforme, geralmente de primeira ordem numa
malha irregular e nas extremidades unilaterais. Não se aplica a fórmula de
passo uniforme a dados não uniformes.

Para ruído independente com desvio padrão σ, a diferença centrada uniforme
tem desvio padrão σ/(√2 h). Reduzir h pode, portanto, aumentar o erro do ruído
mesmo quando reduz o erro de truncatura. `signals.add_gaussian_noise` usa uma
semente inteira, por omissão 0. `moving_average` usa uma janela ímpar centrada,
com janelas recortadas nas extremidades: é um filtro não causal para análise
posterior. `exponential_filter` é causal e usa α entre 0 e 1, excluindo 0.
Filtrar pode reduzir o ruído e introduzir distorção ou atraso; não recupera
automaticamente o sinal físico desconhecido. Não se adicionou uma dependência
apenas para implementar o filtro opcional Savitzky–Golay.

## 2. Integração e unidades

`quadrature(times, values, method)` aceita `left`, `right`, `trapezoid` e
`simpson`. Os três primeiros aceitam intervalos não uniformes. Simpson 1/3
composto exige um número par de intervalos uniformes; não altera ou elimina
amostras para satisfazer a condição.

`integrate_midpoints(edges, mid_values)` exige uma amostra genuína no ponto
médio de cada intervalo. A média de dois valores extremos é a altura do
trapézio, não uma medição no ponto médio. Por isso `quadrature` não aceita a
opção `midpoint` sobre amostras dos extremos.

Se o eixo temporal está em s e a potência em W, o resultado está em J. Dividir
por 3600 converte J em Wh. A mesma quadratura pode integrar velocidade em m/s
para obter deslocamento em m. A biblioteca não infere unidades de números
isolados: o chamador deve validar as colunas e manter coerência dimensional.

## 3. Problemas de valor inicial

```python
from expecto_process_manager.physics.numerical.ode import solve_ivp

result = solve_ivp(lambda t, state: -state[0], 1.0, (0.0, 1.0), 0.1, "rk4")
print(result.times[-1], result.values[-1][0])
```

`solve_ivp(function, initial, t_span, dt, method="euler", token=None)` aceita
estado inicial escalar ou vetorial. O callable recebe sempre `(tempo, lista)`;
pode devolver um escalar num problema unidimensional ou uma sequência com a
mesma dimensão do estado. `ODEResult.values` é sempre uma lista de vetores.
`method` aceita `euler`, `heun` e `rk4`; os algoritmos estão implementados
diretamente, sem delegar a um solver externo. Para y′ = f(t,y):

* Euler: yₙ₊₁ = yₙ + h f(tₙ,yₙ).
* Heun: preditor y* = yₙ + h f(tₙ,yₙ), seguido da média das inclinações nos
  extremos inicial e previsto.
* RK4: média ponderada de quatro inclinações, nos tempos t, t+h/2, t+h/2 e t+h.

O último intervalo é encurtado para terminar no instante pedido. O limite é
200000 passos por resolução. Um `token` com método `check()` permite
cancelamento antes de cada avaliação da EDO. Estados não finitos, dimensões
inconsistentes e passos menores que a resolução do tempo são rejeitados. Não
há execução de expressões de texto fornecidas pela interface. As ordens
globais esperadas 1, 2 e 4 pressupõem soluções suficientemente suaves; eventos
e descontinuidades não alinhados exigem tratamento específico do modelo.

## 4. Modelo térmico e comparação de métodos

A conservação da energia fornece acumulação = entrada − dissipação:

> C dT/dt = Pth − k(T − Ta).

C está em J/K, k em W/K e Pth em W. Diferenças em °C têm o mesmo valor numérico
que diferenças em K. Para potência e ambiente constantes, Teq = Ta + P/k e
τ = C/k; a solução independente é T(t)=Teq+(T₀−Teq)exp(−t/τ).

`compare_thermal(initial, ambient, power, capacity, dissipation, duration, dt)`
devolve tempos comuns, temperaturas para os três métodos, referência
analítica e explicação física. `time_to_threshold` devolve o primeiro instante
em que uma temperatura alvo é atingida, 0 se já é a inicial e `None` quando
não é atingida em tempo finito. Um alvo igual ao equilíbrio é assintótico.

A estabilidade de Euler exige 0 < h k/C < 2. A fronteira h k/C = 2 é marginal
e não dissipa o erro. Estabilidade não garante precisão. `linear_stability`
avalia o polinómio de amplificação do método para y′ = −a y. O passo interno
de integração é independente do intervalo entre leituras de sensores.

## 5. Calibração de C e k com validação separada

```python
from expecto_process_manager.physics.calibration import fit_thermal, predict_zoh

# Experiência inteiramente SIMULATED, com parâmetros conhecidos.
times = [i * 0.5 for i in range(401)]
powers = [45.0] * len(times)
temperatures = predict_zoh(times, powers, 30, 22, 100, 2)
fit = fit_thermal(times, temperatures, powers, ambient=22)
print(fit.capacity, fit.dissipation, fit.validation.errors["rmse"])
```

`fit_thermal(times, temperatures, powers, ambient, *, method="integral_zoh",
validation=None, token=None)` reserva obrigatoriamente dados para validação.
Por omissão separa os primeiros 70% para treino e os últimos 30% para
validação, com um mínimo de oito e quatro amostras respetivamente. Não
partilha amostras nem intervalos entre os conjuntos. Se se fornecer
`validation=ThermalSeries(times, temperatures, powers)`, as duas séries devem
usar a mesma origem temporal e janelas fechadas estritamente disjuntas.
O limite total é 20000 amostras.

O método principal assume potência térmica mantida no valor esquerdo em cada
intervalo, Pᵢ, e usa a propagação exata:

> θᵢ₊₁ = exp(−bhᵢ) θᵢ + g Pᵢ [1−exp(−bhᵢ)], b=k/C, g=1/k, θ=T−Ta.

Para cada b positivo, g é obtido por mínimos quadrados. Uma pesquisa de 81
pontos em log(b) e até 64 refinamentos de secção áurea identifica o mínimo
com parâmetros positivos; C=k/b. Trata-se de uma otimização unidimensional
limitada, não de uma garantia universal para qualquer sinal físico. As
previsões de avaliação propagam o modelo a partir da primeira temperatura
de cada conjunto, sem reinicializar a cada observação. Essa condição inicial
é fornecida, não prevista, e é excluída das métricas.
Ruído nas temperaturas dos dois extremos também pode introduzir viés no
ajuste a um passo; a solução exata do intervalo não elimina erros dos sensores.

A alternativa `method="derivative"` estima dT/dt por diferenças centradas e
ajusta dT/dt=aP−b(T−Ta), com C=1/a e k=b/a. Exclui as derivadas unilaterais dos
extremos. A derivação amplifica ruído e a regressão com variáveis ruidosas
pode ter viés; não se presume que esta alternativa seja adequada a degraus.

A biblioteca rejeita temperaturas constantes, matrizes sem posto completo,
parâmetros não positivos e Jacobianos de sensibilidades em log(C),log(k) com
condicionamento superior a 10⁶. Uma excursão térmica ≤10⁻⁶ °C é tratada como
insuficiente. Com P=0 só o quociente k/C pode ser identificado: devolver C e k
separados seria uma falsa precisão. São devolvidos MAE, RMSE, erro máximo,
resíduos observado−previsto, média, desvio padrão populacional e
autocorrelação de ordem 1. Não se calculam intervalos de confiança sem um
modelo estatístico adequado.

Uma divisão temporal é um holdout; não é uma repetição experimental
independente. O utilizador deve fornecer a origem das amostras e as condições
de controlo experimental. Potência elétrica de um package não se transforma
automaticamente em potência térmica deste nó. Um bom ajuste pode ocultar
erro de sensor, ambiente incorreto ou alterações das ventoinhas.

## 6. Extensão CPU/GPU

`CoupledThermalConfig` define Ta, Cc, Cg, kc, kg e kcg.
`simulate_coupled(config, initial_cpu=40, initial_gpu=35, cpu_power=45,
gpu_power=60, duration=120, dt=.1, method="rk4", token=None)` resolve:

> Cc Tc′ = Pc − kc(Tc−Ta) − kcg(Tc−Tg)
>
> Cg Tg′ = Pg − kg(Tg−Ta) + kcg(Tc−Tg).

C deve ser positivo; k pode ser zero para estudar um sistema isolado. Ao
somar os balanços, o acoplamento cancela exatamente: só transfere energia
entre nós. O resultado inclui curvas analíticas independentes para kcg=0,
energia recebida, transferência líquida ao ambiente, variação da energia
armazenada e resíduo de balanço. Para kcg≠0 as curvas independentes comparam
outro modelo físico e não representam o erro numérico. As energias são
integradas com os mesmos estágios das temperaturas: a conservação é um teste
de consistência, não uma referência independente de exatidão.

## 7. Validação executável

```powershell
.venv\Scripts\python -m pytest -q tests/test_numerical_engine.py tests/test_calibration.py tests/test_coupled.py
```

Os testes cobrem os requisitos A–I: derivada de t², integral de x², y′=−y,
50 W×10 s=500 J, referência térmica, estabilidade, ruído, balanço energético
e rejeição de calibração subidentificável. Incluem ordens de convergência
1/2/4, malhas não uniformes, extremos, cancelamento, limites de passos,
validação disjunta, ajuste com ruído e conservação interna CPU/GPU. São
experiências sintéticas ou analíticas, sem resultados de sensores inventados.
