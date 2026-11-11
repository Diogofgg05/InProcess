# EXPECTO Physical Systems Lab 5.0

## Diagnóstico técnico antes das alterações

Auditoria local em 11 de novembro de 2026: **300 testes passaram em 7,58 s** no ambiente Windows/Python 3.12 existente. Não foi necessário instalar dependências.

O laboratório já tinha duas camadas numéricas: as APIs térmicas históricas e `physics/numerical`, com derivadas, quadraturas, EDO vetorial, Euler/Heun/RK4, comparação térmica, convergência, estabilidade e sinais. A experiência térmica comparava realmente os três integradores com uma referência analítica por intervalos de potência retida à esquerda. Não era apenas uma interface. Mantiveram-se essas APIs e os seus testes.

A calibração existente verificava a identificabilidade de C/k e separava temporalmente treino e validação. Existiam também CPU/GPU acoplados, arrefecimento hipotético e comparação de tarefas NORMAL/ECO/ULTRA ECO. Estes módulos foram reutilizados.

Lacunas encontradas: unidades dimensionais sem corrente elétrica e sem conversões; ausência de RC/RL, dinâmica de ventoinha, vibrações, ondas e FFT; navegação com gravitação/queda livre sem ligação ao hardware; relatório académico anterior sem as dez experiências agora pedidas. Os módulos antigos de AGV/compressor e gravitação foram preservados como exemplos históricos.

## Matriz C1–C9

| Conteúdo | Base anterior | Implementação atual e validação |
|---|---|---|
| C1 — medida | Energia, origem dos dados, dimensões térmicas | Dimensão elétrica; conversões SI; resolução, repetibilidade, incerteza da média; propagação com covariância validada; incerteza da energia por trapézios. Testes dimensionais e de limites físicos. |
| C2 — rotação | Sem modelo de ventoinha | `FanRotor`: Newton, arrasto linear/quadrático, aceleração, momento angular, energia, equilíbrio. Referência linear analítica e convergência 1/2/4. |
| C3 — vibrações | Ausente | `Oscillator`: quatro regimes livres, força harmónica, energia e resposta estacionária em frequência. Referências independentes para regimes livres e transiente forçado, incluindo ressonância ideal não amortecida. |
| C4 — acústica | Ausente | Onda plana 1D incidente/refletida; interferência; extensão com atenuação identificada. FFT radix-2 local com janela, Nyquist e amplitude corrigida. Verificação da EDP e tom sintético. |
| C5 — eletricidade | Integração de potência | Lei de Ohm, três formas de potência Joule, RC com tensão inicial arbitrária/carga/descarga, placas paralelas ideais. Referência analítica, balanço energético e convergência. |
| C6 — eletromagnetismo | Ausente | RL e energia magnética; `FanMotor` com Ke=Kt em SI, contraeletromotriz e perdas. Teste independente da identidade de potência eletromecânica. |
| C7 — calor | Modelo concentrado, calibração e CPU/GPU | Preservados; restrição ao zero absoluto; condução 1D estacionária e convecção em série; motor alimenta condutância térmica por hipótese explícita. Dez experiências dão prioridade ao CPU. |
| C8 — não linear | Arrefecimento dependente de comando temporal | `ThermalFeedback`: saturação proporcional, dinâmica do atuador e perturbação periódica; equilíbrio e Jacobiano local. Extensão académica sem alegações de caos. |
| C9 — métodos | Motor genérico já funcional | Reutilizado nos modelos novos; limite adicional de valores de estado; estudos de convergência, erros, conservação, FFT, observações em tempos não uniformes e benchmark de três repetições. |

## Organização e utilização

`Ctrl+L` abre o laboratório. A janela principal e os serviços de processos não foram redesenhados.

- **A — Termodinâmica:** experiência CPU, calibração, CPU/GPU, condução/convecção.
- **B — Circuitos:** RC e RL; exportação das correntes, tensões e energias.
- **C — Arrefecimento:** rotação e motor eletromecânico acoplado a um nó térmico.
- **D — Vibrações e acústica:** vibração livre/forçada, resposta em frequência, ondas e análise de sinais locais.
- **E — Dinâmica não linear:** realimentação proporcional saturada e atraso de resposta do atuador.
- **F — Métodos e validação:** página numérica existente e análise de ruído/derivadas.
- **G — Energia / ULTRA ECO:** tarefas equivalentes, energia, duração, desempenho e restrições existentes.

Os índices legados foram preservados para não quebrar APIs e testes. Os separadores de gravitação e queda livre estão ocultos e não se tornam novamente visíveis quando são construídos. O acesso programático antigo continua possível.

Nas páginas B/C/D/E, selecionar um modelo repõe a respetiva configuração ilustrativa. Introduzir parâmetros com ponto decimal, incluindo notação científica (`1e-5`). O estado inicial mostra as unidades e a ordem das componentes. A execução resolve **os três métodos**; a caixa de grandeza permite observar corrente, rotação, potência, energia ou temperatura conforme o modelo. A curva de ressonância é estacionária e não se confunde com o transiente temporal.

Os modos de simulação, experiência e validação distinguem a origem dos resultados. Para comparar observações, executar primeiro a simulação e usar **Experiência · importar observações**. A importação compara o canal físico principal, sem ajustar parâmetros automaticamente. A calibração térmica continua na sua página própria. Nas extensões de campos, a verificação é pelas equações; os campos sintéticos não são medições de componentes reais.

## Equações e interpretação

### CPU e dissipação

O balanço `C T′ = Pth − k(T−Ta)` resulta da primeira lei: potência recebida menos potência cedida iguala a taxa de armazenamento `d(CT)/dt`. Para C, k, Ta e P constantes:

`Teq=Ta+P/k`, `τ=C/k`, `T(t)=Teq+(T0−Teq) exp(−t/τ)`.

Com P=45 W, C=180 J/K, k=1,2 W/K, Ta=25 °C e T0=30 °C: **Teq=62,5 °C; τ=150 s; T(120 s)=47,8968086662 °C**. O critério de Euler é `0<Δt<2C/k`. Passo pequeno controla erro de discretização; não calibra o modelo físico.

Condução e convecção em série têm a **mesma** potência: `Rcond=d/(kt A)`, `Rconv=1/(hA)`, `Q=(Tchip−Ta)/(Rcond+Rconv)`. A superfície é `Ts=Ta+Q Rconv`; o perfil na parede é linear. O relatório verifica `−kt A dT/dx = hA(Ts−Ta)`. Não se somam estas duas potências, pois representam a mesma energia em duas partes do caminho.

### Circuitos e ventoinha

Kirchhoff no RC: `Vs=Ri+Vc` e `i=C Vc′`, logo `Vc′=(Vs−Vc)/(RC)`. A referência geral é `Vc=Vs+(V0−Vs) exp(−t/RC)`; `Ec=CVc²/2`.

No RL: `Li′=Vs−Ri`, `i=Vs/R+(i0−Vs/R) exp(−Rt/L)` e `EL=Li²/2`. Resistências são estritamente positivas nestes modelos, que não representam saturação, ESR ou um VRM comutado.

Newton no rotor: `Jω′=τmotor−bω−cω|ω|`. O arrasto sempre retira energia: `Pdrag=bω²+c|ω|³`. `L=Jω`; a conservação exige binário resultante nulo. Para rotação sem perdas nem binário, ω e L conservam-se. Para b>0 e c=0, a resposta exponencial tem `τrot=J/b` e `ωeq=τmotor/b`. O estado inicial pode representar desaceleração com binário zero.

No motor: `Li′=V−Ri−Kω`, `Jω′=Ki−bω−cω|ω|`. Usar a mesma constante K em SI preserva `Kωi=Kiω`, cancelando a transferência interna no balanço:

`d( Li²/2 + Jω²/2 )/dt = Vi − Ri² − bω² − c|ω|³`.

O CPU recebe uma entrada térmica própria Pth; não recebe automaticamente perdas do motor. A relação de arrefecimento `k=k0+β|ω|` é declaradamente hipotética e não inferida de RPM. Sem dados, não há controlo ou calibração da ventoinha física.

### Vibrações e som

`x′=v`, `v′=(F0 cos Ωt−cv−kx)/m` derivam de Newton. `ω0=√(k/m)`, `ζ=c/(2√mk)` e `E=mv²/2+kx²/2`. Para F0=0, `E′=−cv²`; com excitação há trabalho externo. O pico de deslocamento estacionário ocorre em `ωr=ω0√(1−2ζ²)` apenas para `ζ<1/√2`. Sem amortecimento, a ressonância exata não tem amplitude estacionária finita; o resultado é identificado como indefinido e não exportado como infinito.

`frot=RPM/60`, `fpassagem=Npás frot`. Estas frequências sugerem hipóteses a comparar com instrumentação; não comprovam ressonância nem avaria.

A extensão acústica usa `p=A cos ω(t−x/c)+rA cos ω(t−(2L−x)/c)`, solução de `p_tt=c²p_xx`. r é o coeficiente de reflexão de pressão em x=L. A atenuação exponencial é uma **extensão com perdas**, não uma solução da mesma EDP sem perdas. As hipóteses são pequenas perturbações, meio homogéneo e propagação 1D; o modelo não calcula o campo acústico tridimensional de uma caixa real.

A FFT remove DC e admite janela Hann ou retangular, corrigindo o ganho coerente. Usa exatamente N amostras uniformes, N potência de dois entre 8 e 65536; rejeita truncagem ou reamostragem implícita. Resolução `Δf=fs/N`; Nyquist `fs/2`. Frequências esperadas ≥ Nyquist geram aviso. Não é possível demonstrar ausência de aliasing apenas a partir de amostras. A amplitude tem a unidade de entrada, sem dB SPL calibrados.

### Realimentação

`CT′=P+A sin(2πft)−(k0+βu)(T−Ta)`; `τu u′=clip(Kp(T−Talvo),0,1)−u`. τu representa resposta de primeira ordem, **não atraso puro**. O equilíbrio é encontrado pelo balanço de potência; traço e determinante do Jacobiano classificam a estabilidade local em potência constante. A saturação não é diferenciável na fronteira, que é sinalizada. O modelo não implementa controlador com histerese ou atraso puro. Não se apresentam estes casos como concluídos nem se chama caos a uma oscilação.

## Medida, unidades e origem

`units.convert` suporta J/Wh, W/mW, °C/K, grandezas elétricas e RPM/rad/s/Hz. Conversões entre frequências cíclicas e angulares exigem `rotational=True`, porque uma frequência acústica arbitrária não define RPM. Temperaturas absolutas abaixo de 0 K são rejeitadas. Diferenças térmicas usam K, numericamente equivalentes a diferenças em °C. O sistema dimensional cobre massa, comprimento, tempo, temperatura e corrente, suficientes para os modelos implementados.

`measurement.repeatability` calcula média, desvio padrão amostral e incerteza da média com resolução uniforme de arredondamento `resolução/√12`. Repetibilidade não mede exatidão nem erro sistemático. `propagate` usa `u_f²=gᵀΣg` e verifica simetria, diagonal e positividade semidefinida da covariância. `energy_uncertainty` combina pesos dos trapézios com erros de potência independentes e tempos exatos. Erros sistemáticos comuns exigem covariância; não desaparecem por aumentar a amostragem.

Os novos modelos não leem sensores. Observações importadas mantêm **IMPORTED_UNVERIFIED**: a unidade declarada não certifica a calibração de um instrumento. Um sensor de utilização CPU não mede automaticamente potência, vibração, tensão ou corrente. Resultados calculados continuam **SIMULATED** mesmo quando comparados com dados importados.

## Importação e reprodução

CSV comum para observações: `time_s,value,unit`, separador vírgula, ponto decimal. Exemplos de unidade: `V` no RC, `A` no RL, `rad/s` no rotor/motor, `m` na vibração, `°C` na realimentação e `Pa` na análise acústica. Tempos relativos à condição inicial do modelo; não se desloca a origem silenciosamente. Limites: 8 MiB e 50001 amostras; FFT tem a restrição adicional de potência de dois. Para dados em RPM, converter explicitamente antes de comparar o canal angular em rad/s.

O comparador resolve RK4 nos tempos realmente observados, incluindo intervalos não uniformes, sem interpolar as medições. A condição inicial é fornecida, não ajustada. Uma comparação assim não substitui calibração, repetições independentes ou análise da incerteza instrumental.

**Exportar CSV + JSON + relatório** guarda as séries dos três métodos, metadados, hipóteses, unidades, condições iniciais, erros, balanços e gráficos SVG offline. JSON conserva a configuração em `config`; a API pode reproduzir com `run_hardware(HardwareConfig(**payload['config']))`. A origem e as observações comparadas permanecem separadas. A API histórica de guardar/reabrir experiências térmicas mantém-se.

## Dez experiências, testes e desempenho

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe examples\physical_lab.py
```

O segundo comando cria [physical-suite.html](../reports/physical-lab-5/physical-suite.html), JSON dos resultados/verificações e relatórios individuais. Também pode ser executado no botão **10 experiências** das novas páginas.

As dez experiências são: aquecimento CPU; dissipação; energia; RC; rotação da ventoinha; vibração amortecida; ressonância; ruído/derivadas; calibração térmica; ULTRA ECO. RL, motor acoplado e realimentação têm relatórios complementares. As referências analíticas, a identidade de potência eletromecânica, a EDP da onda e os balanços são verificações distintas. Dados sintéticos não validam um componente físico.

Os métodos do motor genérico têm limite de 200000 passos e agora de 2000000 valores de estado armazenados. Nas novas experiências, o limite é 50000 passos por método e 20 s por execução; cancelamento verificado nos estágios do integrador. A validação importada limita-se a 100000 passos/20 s. Os cálculos, importações e exportações são executados nos trabalhadores existentes. Os gráficos reduzem apenas a apresentação; métricas e CSV usam todas as amostras. Não há cache de resultados científicos com risco de parâmetros obsoletos.

O relatório inclui benchmark local RC, 1000 passos, três repetições por método, mediana e tempos individuais, sem GUI/I/O dentro da medição. Não mede consumo elétrico ou desempenho de C++/Rust e não justifica mudar a linguagem. Os testes de interface verificam execução assíncrona, cancelamento e desenhos de resultados; a medição de latência sob carga depende do equipamento.

### Evidência da execução final

Em 11 de novembro de 2026, a suíte completa passou com **360 testes em 15,63 s**, incluindo os 300 testes anteriores. Os 60 testes adicionais cobrem física, importação/exportação, convergência, unidades/incertezas, FFT, campos, relatórios e interface. O comando das dez experiências foi executado depois, sem testes simultâneos, e todas as suas verificações quantitativas passaram.

No benchmark incluído nessa execução, as medianas para 1000 passos RC foram Euler **1,4268 ms**, Heun **2,9829 ms** e RK4 **5,9446 ms**. São tempos locais variáveis, com três repetições e sem medição de energia elétrica. Os tempos brutos e ordens de convergência estão em `reports/physical-lab-5/physical-suite.json`.

A captura da página de rotação foi gerada e inspecionada em `data/physical-lab-5-preview.png`. A validação foi realizada em Windows; não se declara execução em Linux.

## Limites da entrega e validação experimental futura

Não foram realizadas medições físicas de potência, RPM, corrente, pressão sonora ou vibração. Não há aquisição de microfone, gravação de conversas, controlo de ventoinhas nem alterações automáticas de perfis energéticos. CSV local permite usar instrumentação externa. A FFT mantém os dados em memória até nova execução/fecho; só exporta por ação do utilizador.

C4 e C8 são extensões limitadas e explicitamente identificadas. Não há simulação BLDC com comutação, VRM completo, identificação automática de avarias, caos físico demonstrado, controlador com histerese ou atraso puro. As previsões térmicas ilustrativas não são garantias de segurança. A cadeia elétrica → mecânica → condutância térmica é implementada; a cadeia vibração → som relaciona frequências, sem inventar um coeficiente de transmissão medido.

Referências de apoio: [OpenStax — circuitos e energia eletromagnética](https://openstax.org/books/university-physics-volume-2/pages/14-6-rlc-series-circuits), [OpenStax — oscilador amortecido e forçado](https://openstax.org/books/calculus-volume-3/pages/7-3-applications), [University of Michigan — modelo completo de motor](https://web.eecs.umich.edu/~jfr/embeddedctrls/files/Lecture7.pdf). Estas referências apoiam a formulação idealizada; os testes locais verificam a implementação, não certificam o hardware.
