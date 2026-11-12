# InProcess

Aplicação desktop autónoma em Python, psutil e PySide6: monitorização real de processos e laboratório de Modelação Computacional de Sistemas Físicos. O projeto existente foi melhorado sem remover a API de consulta e simulação.

## Abrir no Windows

Pode abrir pelo atalho **InProcess** (`InProcess.lnk`) na pasta do projeto. Usa o ícone fornecido e inicia a aplicação sem uma janela de consola Python. O comando abaixo continua disponível.

Na pasta do projeto, no PowerShell:

```powershell
.\.venv\Scripts\expecto.exe
```

Se ainda não existir ambiente virtual:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m expecto_process_manager
```

Não é necessário ativar o ambiente virtual. Requer Python 3.11+ de 64 bits. Para as versões completas do ambiente Windows testado, instalar `requirements-lock.txt` e depois `pip install --no-deps -e .`.

Linux, numa sessão gráfica:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/expecto
```

O Qt pode requerer bibliotecas de sistema adicionais. A pipeline em `.github/workflows/tests.yml` prepara testes offscreen em Windows e Ubuntu; a sua existência não significa que Linux já tenha sido validado.

## Interface

O design segue a referência clara e azul: barra lateral compacta de 206 px, cartões arredondados, superfícies brancas, pesquisa central e estados discretos de hover/seleção em toda a aplicação. O tema claro é o padrão; o escuro continua disponível em Definições. Cliques não desenham contornos de foco nativos; a navegação por teclado mantém uma indicação subtil. A janela conserva os controlos de minimizar, maximizar/restaurar, fechar, arrastar e redimensionar. Ícones de executáveis Windows são extraídos em segundo plano e guardados em cache.

A tipografia usa **Segoe UI Variable** quando disponível, com famílias de texto e títulos adequadas ao sistema. Os grupos expansíveis mostram os ícones reais das aplicações; quando o sistema não fornece um ícone, apresentam um símbolo genérico. A janela, o atalho e os novos relatórios usam a marca **InProcess**. O módulo Python e o comando legado `expecto` mantêm-se compatíveis; novas instalações também disponibilizam `inprocess`.

Largura **e altura** ajustam a densidade: tamanho de letra, linhas, ícones, controlos e espaçamentos. Os painéis laterais recolhem quando falta espaço; em janelas baixas, o laboratório usa um seletor compacto de categorias. A escala tem um limite de legibilidade e o conteúdo extenso mantém deslocamento. Foram removidos os três botões de estilo Apple e o bloco entre pesquisa e definições. A imagem original está em `interface/assets/expecto.png`, com ICO em sete tamanhos para Windows.

O **Laboratório** está visível na barra lateral. Cinco cartões agrupam os modelos térmicos, energia/circuitos/arrefecimento, sinais/vibrações/dinâmica, calibração e ULTRA ECO; os botões abaixo dos cartões dão acesso aos modelos de cada categoria. No modelo térmico, os modos Simulação, Validação e Experiência mantêm resultados e parâmetros; **Dados e exportação** reúne importação, ficheiros e relatórios. Veja a [pré-visualização](data/design/laboratory.png).

Atalhos: `Ctrl+L` laboratório, `Ctrl+J` análise, `Ctrl+,` definições e `Ctrl+K` pesquisa. A pesquisa global reconhece nomes como `térmico`, `calibração`, `acústica` e `ULTRA ECO`. A pesquisa local de processos mantém os filtros de nome/PID/utilizador. `Ctrl+G` conserva o acesso legado à gravitação, fora da navegação principal. A engrenagem abre Definições.

- **Processos:** pastas expansíveis por executável e utilizador, com total de CPU/memória e PID individuais ao expandir. O agrupamento não presume relações pai-filho do SO. A caixa **Lista de processos** mantém a vista individual. Pesquisa, filtros e ordenação numérica funcionam em ambas. Os totais permanecem indisponíveis se faltar uma medição. Botão direito num processo individual: detalhes, suspender, continuar ou terminar com confirmação; uma pasta não termina vários processos. Botão direito no cabeçalho: escolha de colunas. CPU 100% representa um núcleo lógico; a soma pode ultrapassar 100%. Memória agrupada soma valores por processo, incluindo possíveis páginas partilhadas. Disco por processo representa contadores de I/O do SO. Rede/GPU por processo indisponíveis aparecem como `—`.
- **Desempenho:** CPU global/por núcleo, RAM utilizada/disponível, swap, temperatura CPU quando suportada, disco/rede globais. Taxas em MiB/s não são percentagens de ocupação/capacidade.
- **Histórico:** atualização em direto, cartões de resumo (amostras, média/pico CPU e período), filtro temporal, ordenação e exportação CSV. A seleção e a posição de leitura são preservadas ao inserir novas amostras. Não é um arquivo de consumo por aplicação; os dados desta sessão permanecem em memória.
- **Aplicações de arranque:** inventário de leitura. Windows: registo Run e pastas Startup. Linux: XDG autostart. Não cobre todos os mecanismos de arranque e não altera entradas.
- **Utilizadores:** sessões reportadas pelo sistema, não todas as contas existentes.
- **Serviços:** consulta de serviços Windows ou unidades systemd Linux, sem alterações. Falhas de acesso são apresentadas.

Aplicações de arranque, utilizadores e serviços atualizam automaticamente enquanto a respetiva página está aberta (30, 10 e 15 s). Não existem botões de atualização manual nem consultas concorrentes da mesma página. Serviços removidos ou inacessíveis são omitidos com indicação da quantidade, sem interromper os restantes. O hardware usa atualização automática com cache de 10 minutos; os temporizadores param ao sair da página. A monitorização apresenta os gráficos sem os antigos parágrafos técnicos; os detalhes continuam nos tooltips.
- **Laboratório científico:** setores de termodinâmica, energia/circuitos, dinâmica do arrefecimento, vibrações/acústica, realimentação, métodos e ULTRA ECO. RC, RL, rotação e vibrações com referências analíticas; experiências assíncronas, comparação com CSV e exportação científica. Gravitação/queda livre mantêm código e APIs, mas estão ocultas da navegação principal. Consulte [a auditoria e a matriz C1–C9](docs/physical-lab-5.md).
- **Análise científica:** derivadas, ruído/filtragem, gráfico log-log, ordens observadas, RMSE e comparação de quadraturas.
- **Definições:** três secções — **Preferências**, **Dados e relatórios** e **Sistema** — com cartões adaptáveis à janela. Tema claro/escuro, amostragem 250–10 000 ms, limite de histórico e estimativa do período conservado. Exportações, importação e relatórios continuam acessíveis. As alterações são guardadas automaticamente em `data/preferences.ini`.

Filtros de aplicações/serviços são aproximações explícitas: Windows usa PIDs de janelas visíveis e serviços com cache de 10 s; Linux usa associações cgroup a unidades `.service` e `app-*.scope`. Não constituem uma classificação universal. Processos de tipo desconhecido permanecem em Todos. Processos sem permissões para obter os campos obrigatórios são omitidos.

A primeira leitura CPU é aquecimento (`—`). Taxas requerem dois contadores válidos. A barra de estado indica o intervalo realmente decorrido e a duração de recolha: um intervalo configurado de 250 ms não garante recolhas a cada 250 ms num computador lento.

Em ecrãs pequenos, os cartões laterais são ocultados e continuam disponíveis os gráficos de Desempenho. Tabelas e laboratório permitem deslocamento. A monitorização permanece independente dos gráficos térmicos.

## Experiências reproduzíveis

1. Abra Laboratório científico e configure T inicial, Ta, P, C, k, duração, passo, ruído e semente.
2. Execute; consulte os gráficos e a página Análise científica.
3. **Guardar experiência** cria JSON com versão, unidades, parâmetros, origem da potência, métodos e resultados.
4. **Reabrir** valida a versão/unidades e refaz os cálculos a partir da configuração, sem tratar os resultados guardados como observações reais.
5. **Exportar resultados CSV** grava as séries com proveniência; para reproduzir integralmente, guarde também o JSON.

Potência CSV requer `time_s,power_w`. Colunas opcionais `time_unit,power_unit` só aceitam `s,W`. Valores finitos, tempos crescentes, potência não negativa, até 200 001 amostras e ficheiro até 10 MiB. Exemplo sintético em `data/power-example.csv`. A origem importada é não verificada. A simulação usa retenção à esquerda (ZOH), com tempos relativos ao início; a duração tem de estar coberta pelos dados. A temperatura resultante continua a ser simulada.

## Testes e benchmarks

A otimização da interface foi medida com 600 processos sintéticos e ensaios de recolha real: [resultados antes/depois e limitações](docs/sidebar-optimization.md). Na carga sintética, a mediana da atualização agrupada passou de 89,76 para 16,27 ms. A frequência de recolha não foi reduzida para obter este resultado.

As **dez experiências físicas prioritárias**, com verificações quantitativas e relatório offline, podem ser executadas sem abrir a interface:

```powershell
.\.venv\Scripts\python.exe examples\physical_lab.py
```

Resultado: [relatório científico 5.0](reports/physical-lab-5/physical-suite.html), CSV e JSON reproduzíveis. Todos os dados de demonstração são sintéticos; não representam medições do hardware. O botão **10 experiências** nas novas páginas executa o mesmo código em segundo plano.

```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python examples\api_demo.py
.\.venv\Scripts\python examples\benchmark.py --samples 5 --repetitions 3
$env:QT_QPA_PLATFORM='offscreen'
.\.venv\Scripts\python examples\benchmark_gui.py --duration 10 --interval 1000
.\.venv\Scripts\python examples\compare_performance.py --repetitions 3 --duration 8 --directory data/comparison-new
Remove-Item Env:QT_QPA_PLATFORM
```

Execute benchmarks separados de testes e outras cargas controláveis. O benchmark API mede recolhas consecutivas, não o consumo em repouso. O GUI mede CPU, pico amostrado de RAM e intervalos de um timer de 25 ms, incluindo arranque; não mede diretamente latência de cliques. Mostra recursos da GUI e o agregado GUI + coletor real + lançador Windows do ambiente virtual. CPU é expressa em percentagem de um núcleo, podendo exceder 100%. `--backend thread` permite comparar a recolha sem isolamento; o padrão é `process`. Repita com `--interval 250`, `1000` e `5000`, indicando ficheiros de saída diferentes com `--output`.

O comparador alterna os modos e mantém os ficheiros brutos. Os ensaios locais já realizados estão em `data/perf-thread-*.json`, `data/perf-process-*.json` e `data/performance-comparison.json`. Em três repetições de 8 s, a média dos maiores intervalos GUI passou de 413,6 para 55,4 ms. A memória agregada aumentou cerca de 29 MiB e o CPU total também aumentou; o objetivo do isolamento é reduzir bloqueios da interface, não esconder o custo do auxiliar. Consulte `docs/performance.md`.

Capturas reais dos testes/benchmark: `data/interface-preview.png`, `data/laboratory-preview.png`, `data/dashboard-preview.png`. Nenhum teste termina processos de terceiros. Mocks verificam as operações e a confirmação.

Na tabela e nos cartões compactos são usadas unidades decimais MB/GB (10⁶/10⁹ bytes); a página Desempenho mantém as unidades binárias indicadas nos eixos. Mb/s significa megabits por segundo. Os números e o sistema operativo apresentados são reais, pelo que diferem dos valores ilustrativos da fotografia. GPU e percentagens de ocupação de disco/rede sem sensor não são inventadas para imitar a referência.

## API e arquitetura

```python
from expecto_process_manager.plugin_api import Manager
from expecto_process_manager.simulation.experiments import ExperimentConfig

manager = Manager()
processes = manager.list_processes()
cpu = manager.get_cpu_usage()
memory = manager.get_memory_usage()
result = manager.simulate_temperature(
    initial_temperature=40, ambient_temperature=22,
    power=45, duration=120, dt=0.1,
)
joules = manager.calculate_energy(times=result.times, powers=result.powers)
experiment = manager.run_experiment(ExperimentConfig(seed=123))
```

As chamadas originais mantêm-se. CPU de processos recém-observados passa a `None` durante aquecimento; `get_cpu_usage()` mantém a semântica não bloqueante do psutil (primeira leitura é baseline). Alterações de processos estão separadas em `ProcessService.control`, exigindo autorização explícita do chamador.

`MonitoringProvider` permite substituir as consultas de monitorização. `PsutilProvider` é a implementação inicial. Por padrão, `ProcessSamplingThread` comunica com um auxiliar Python de leitura, isolando do GIL da GUI as chamadas nativas lentas. Fornecedores injetados por código continuam suportados por `SamplingThread`. `Tasks` gere ficheiros e cálculos com cancelamento cooperativo. O fecho para o auxiliar que a própria aplicação criou; nunca termina processos de terceiros para otimizar o sistema. Sem `waitForDone()` na thread GUI. Tabelas preservam o modelo quando os PIDs não mudam; gráficos reutilizam eixos/séries e limitam a representação a cerca de 1500 pontos, sem reduzir os dados exportados.

CPU, RAM e I/O são consultados em cada recolha. Estado de processos tem cache de até 5 s, invalidado após uma ação confirmada; swap, frequência e temperatura são consultados a cada 2 s. Timestamps e idades constam dos CSV/tooltips/detalhes. Valores indisponíveis continuam distintos de zero. Definições mostra a duração de recolha e P95 do timer interno de 16 ms; não equivale à latência de cliques nem ao tempo de um quadro gráfico.

Veja `docs/architecture.md`, `docs/science.md`, `docs/validation.md` e `docs/report.md`.

A lista de processos conserva o snapshot mais recente enquanto outra página está selecionada e atualiza a vista ao regressar. A chegada de ícones não recalcula os grupos. Medições e limitações: [atualizações por página e ícones](docs/page-activity-optimization.md).

## Euler, gravitação e queda livre

Abra **Ctrl+G** ou Laboratório científico → **Gravitação · órbitas**. O modelo usa massa central fixa e pontual, `r'' = −GM r / |r|³`, em SI. Compare Euler explícito, Euler simplético e Velocity Verlet: órbitas com escalas espaciais iguais, erro de posição, energia e momento angular. O caso circular (`v/v_circular = 1`) tem referência analítica independente e estudo de convergência; para outras velocidades não se apresenta uma referência circular incorreta. Presets circulares, elípticos e de escape são hipóteses sintéticas, sem atmosfera ou impacto. Configurações JSON são reabertas recalculando os resultados; CSV contém trajetórias completas dos três métodos.

No separador **Queda livre · Euler**, configure altura, velocidade inicial, g, duração e passo. A referência é `y = y0 + v0*t − g*t²/2`, `v = v0 − g*t`; compare erro e energia específica em J/kg. A integração pode prosseguir abaixo da origem: não é modelado um chão ou colisão. Diminuir o passo deve reduzir o erro de altura de primeira ordem.

```python
from expecto_process_manager.plugin_api import Manager
from expecto_process_manager.physics.gravity import GravityConfig

manager = Manager()
orbits = manager.simulate_gravity(GravityConfig(duration=10800, dt=10))
fall = manager.simulate_free_fall(height=100, gravity=9.80665, duration=4, dt=0.01)
```

Veja `docs/gravity.md` para fórmulas, hipóteses, convergência e limitações. Capturas integradas: `data/gravity-integrated-preview.png` e `data/free-fall-integrated-preview.png`.

## Limitações científicas

O coletor geral não mede potência do CPU nem converte utilização em watts. Existe aquisição opcional de temperatura e potência elétrica da GPU através de `examples/capture_sensors.py`, com origem, domínios e integridade registados. C e k continuam ilustrativos até existir calibração física adequada. A referência analítica é por intervalo para o forçamento retido; não corrige saltos não alinhados com o passo. Erro relativo em Celsius depende da origem da escala. Ruído é sintético e reprodutível.

GPU não integrada no fornecedor geral atual; a aquisição experimental NVIDIA é separada. Temperatura do CPU indisponível via psutil neste Windows. Persistência automática de histórico, instalador binário, calibração física e comparação experimental com outros gestores continuam por implementar/realizar. A suíte foi executada em Windows e Ubuntu via WSL; testes offscreen não substituem avaliação visual interativa, DPI elevados ou validação noutro computador. Consulte [evidência experimental e robustez](docs/validation-evidence.md) para dados reais, carga/churn e análise dos picos.

## Monitorização adaptativa e segurança dos processos

Quando a janela do InProcess está **minimizada**, a frequência de recolha passa automaticamente para, no mínimo, **3000 ms** (ou mantém o intervalo escolhido pelo utilizador, se for superior). O histórico continua a ser recolhido, mas as vistas ocultas deixam de ser redesenhadas e o timer de diagnóstico da interface fica suspenso. Ao restaurar a janela, regressa à cadência configurada em Definições. Este mecanismo reduz trabalho desnecessário, **não constitui uma medição de poupança energética** e não altera as políticas do sistema operativo.

Para evitar perda de trabalho e instabilidade, as operações manuais de suspensão/terminação recusam o próprio InProcess, o processo que o iniciou, os seus antecessores acessíveis e uma lista conservadora de processos críticos do sistema operativo. A verificação de reutilização de PID e a confirmação do utilizador continuam ativas. Estas proteções são complementares às permissões do SO e não garantem proteção contra todas as interrupções possíveis. O motor ULTRA ECO continua a **comparar** perfis, sem os aplicar automaticamente.

Os ficheiros de execução temporários do pytest e os resultados locais de testes deixam de ser versionados; os relatórios científicos reproduzíveis e respetivos dados em `reports/` e `data/` são preservados.

## ECO Advisor — poupança mínima e atraso máximo

No Laboratório → Energia / ULTRA ECO, o InProcess apresenta um parecer
independente da simples escolha de menor energia. O utilizador define a
**poupança mínima** e o **atraso máximo**, em percentagem relativamente ao
perfil NORMAL. São calculados joules, Wh, redução relativa e diferença
de duração. Os resultados são registados no relatório científico.

Quando NORMAL não pode ser usado como referência ou as tarefas não são
comparáveis, o parecer é inconclusivo. Quando nenhuma alternativa cumpre os
limites, recomenda manter NORMAL. É uma decisão de **análise/DRY RUN**:
não aplica alterações ao sistema operativo, não demonstra poupança
experimental e não transforma o projeto num otimizador autónomo.
Veja [energia e limites do método](docs/energy-eco.md).

## Indicadores inteligentes de atividade (InProcess Insights)

Na página Processos, o InProcess destaca discretamente até dois processos
com CPU ou memória residente persistentemente elevadas. Só apresenta o aviso
após três amostras consecutivas; compara PID e data de criação, evita picos
isolados e remove os avisos quando os valores normalizam. Não monitoriza
novos sensores, não transforma CPU% em watts e não atua sobre processos.

As regras conservadoras iniciais são ≥85% de um núcleo lógico ou RSS
≥max(768 MiB, 20% RAM total). O aviso não constitui diagnóstico de
avaria ou desperdício. Consulte [monitorização](docs/monitor-optimization.md).

## InProcess Insights + ECO Advisor

A página Energia / ULTRA ECO mostra agora o **contexto de atividade dos processos
recolhido pelo gestor**, sem executar uma segunda monitorização. Quando existem
observações de CPU/RAM persistentemente elevados, apresenta um aviso de carga
ativa e recomenda cautela na comparação experimental de energia. A ausência de
alertas não comprova que o sistema esteja em repouso.

**O novo contexto não é uma medição de potência.** CPU e RAM não são convertidos
em watts e as diferenças de J/Wh e os pareceres da comparação continuam a
depender apenas das séries de potência fornecidas. Os snapshots não estão
necessariamente sincronizados com essas séries. Nenhum processo ou plano
energético é alterado por esta funcionalidade. Consulte
[limites da comparação](docs/energy-eco.md).

## Laboratório académico: novos modelos acoplados e PDF

Dois novos modelos físicos estão integrados no mesmo laboratório PySide6:

- **CPU e dissipador (2 nós térmicos):** duas equações diferenciais acopladas com capacidade do CPU e dissipador, transferência de calor pela interface e convecção para o ambiente. O balanço energético e a solução fechada permitem comparar Euler, Heun e RK4.
- **Bateria eletrotérmica (3 estados):** estado de carga, circuito de polarização RC e aquecimento por perdas ohmicas. Inclui tensão terminal, balanço de energia, domínio SOC e referência analítica para a tensão sob corrente constante.

Estes modelos são **SIMULATED**. Todos os parâmetros são ilustrativos, não estão calibrados contra o hardware do computador e não alteram serviços, ventoinhas, bateria ou políticas energéticas.

**[Relatório académico em PDF — Modelos Físicos Acoplados](docs/relatorios/InProcess_Modelos_Fisicos_Acoplados.pdf)**

Reproduzir o PDF a partir do código e parâmetros versionados:

```bash
python -m pip install 'reportlab>=4,<5'
PYTHONPATH=src python examples/generate_coupled_pdf.py --output docs/relatorios/InProcess_Modelos_Fisicos_Acoplados.pdf
python -m pytest tests/test_coupled_models.py -q
```

No Windows PowerShell, executar `$env:PYTHONPATH = "src"` antes do comando Python caso ainda não tenha sido instalado o pacote. O gerador produz gráficos vetoriais, equações, referências analíticas, valores numéricos e limitações. A validação de software não substitui medições físicas nem verificação académica da adequação do relatório.

## Physical Systems Lab 6.0 — EDP, estabilidade, sensibilidade e controlo

O laboratório integra uma página nova, **A · Modelação térmica 1D e controlo**, com três experiências:

1. **Equação do calor 1D**: modelo de difusão transiente com fronteiras a temperatura ambiente, condição inicial senoidal, Euler explícito em diferenças finitas (espaço centrado), solução analítica independente e resíduos discretos de conservação de energia.
2. **Convergência e sensibilidade**: quatro passos temporais/valores de Fourier, comparação RMSE com solução contínua, estudo de difusividade a 80%, 100% e 120%, com material e geometria configurados na interface. O erro espacial limita a inferência de ordem temporal.
3. **Controlo térmico do CPU-dissipador**: sistema de dois nós térmicos, atuador de primeira ordem e regulador PI com saturação e anti-windup; comparação com ventilação fixa, sem controlar a ventoinha real nem estimar potência elétrica pela fração do atuador.

**[Relatório académico PDF 6.0](docs/relatorios/InProcess_Physical_Systems_Lab_6.pdf)**, gerado de forma reproduzível pelo script [generate_lab6_pdf.py](examples/generate_lab6_pdf.py). O relatório inclui equações, gráficos, estabilidade, balanço, erros, sensibilidade e limitações. Os parâmetros são hipotéticos e os resultados são identificados como **SIMULATED**, não medidos.

```bash
python -m pytest tests/test_physical_lab6.py -q
python -m pip install 'reportlab>=4,<5'
PYTHONPATH=src python examples/generate_lab6_pdf.py --output docs/relatorios/InProcess_Physical_Systems_Lab_6.pdf
```

Em PowerShell: `$env:PYTHONPATH='src'` antes de executar o gerador, ou instalar o projeto com `pip install -e .`. A física simulada não é prova de eficiência energética real; são necessários sensores calibrados, dados independentes e incerteza experimental para essa afirmação.


## Physical Systems Lab 6.1 — métodos implícitos e convergência independente

No Laboratório > **A · Modelação térmica 1D e controlo**, selecionar
**6.1 · Métodos numéricos implícitos e convergência**. O seletor de método
permite comparar Euler explícito, Euler implícito (Backward Euler) e
Crank–Nicolson, mantendo a mesma geometria e difusividade térmica. A
interface distingue também os parâmetros da barra térmica dos parâmetros
do controlador PI, eliminando campos irrelevantes em cada modo.

A implementação em \`physics/heat_implicit.py\` utiliza um sistema
tridiagonal resolvido em O(N), sem formar matrizes densas. O esquema
explícito exige **Fo ≤ 0,5**; Euler implícito é L-estável e Crank–Nicolson
é A-estável, mas pode oscilar para passos muito grandes. São verificados
fluxos nas fronteiras e balanço de energia de acordo com a quadratura de
cada esquema.

O laboratório calcula:
- **Ordem temporal observada** comparando o estado central à solução
  **semidiscreta exata**, evitando confundir erro espacial com temporal;
  espera-se ordem 1 para Euler e 2 para Crank–Nicolson.
- **Ordem espacial observada** comparando o modo próprio semidiscreto
  à solução da EDP contínua, sem erro de passo temporal; espera-se ordem 2
  para diferenças espaciais centradas.
- **RMSE** relativamente à solução contínua e resíduos discretos de energia,
  sempre com parâmetros, SI e origem **SIMULATED**.

Os resultados são didáticos e não atestam aquecimento, consumo ou poupança
reais do computador. Não é efetuada qualquer atuação sobre processos,
ventoinhas ou políticas energéticas.

**[Relatório PDF 6.1](docs/relatorios/InProcess_Numerical_Physics_6_1.pdf)**.
Recriar o PDF localmente:

\`\`\`bash
python -m pip install 'reportlab>=4,<5'
PYTHONPATH=src python examples/generate_lab61_pdf.py
python -m pytest tests/test_heat_implicit.py tests/test_heat_implicit_gui.py -q
\`\`\`

Para PowerShell, definir \`$env:PYTHONPATH='src'\` antes do gerador.


## InProcess 6.2 — Thermal Field 2D (modelação física computacional)

A nova página **Laboratório → Modelo térmico → Campo térmico 2D** usa um
modelo transiente bidimensional baseado na conservação da energia.
A resolução é explícita por volumes finitos (malha de centros de células)
e inclui:

- Dois materiais com condutividade e capacidade calorífica volumétrica
  diferentes (material central opcional); fluxos entre materiais com média
  harmónica da condutividade.
- Fonte de calor local em watts, geometria e resolução configuráveis.
- Fronteiras de temperatura fixa (Dirichlet), convecção (Robin, com
  resistência da meia célula) e isolamento (Neumann sem fluxo).
- Restrição explícita conservativa de passo por célula
  \`dt <= min(C_i/(Σ G_faces + G_fronteira))\`, incluindo limite
  de nós e de trabalho total.
- Mapa térmico em cores e seletor temporal, implementados em PySide6;
  exportação das temperaturas para CSV e dos metadados para JSON.
- Balanço global \`ΔU = E_fonte - E_perdas\` com resíduo
  de conservação, assim como comparação contra solução analítica para
  material homogéneo sem fonte e fronteiras Dirichlet.
- Estudo de refinamento de malha com erro RMSE. Como a escolha
  do passo temporal depende da malha, este estudo não pretende
  isolar uma ordem de convergência puramente espacial.

**[Relatório académico PDF 6.2](docs/relatorios/InProcess_Thermal_Field_2D_6_2.pdf)**

Reprodução:

\`\`\`bash
python -m pytest tests/test_heat_2d.py -q
python -m pip install 'reportlab>=4,<5'
PYTHONPATH=src python examples/generate_thermal2d_pdf.py
\`\`\`

Tudo é **SIMULATED**: o mapa não é uma termografia real e
as propriedades/material/fonte não estão calibrados contra um CPU ou GPU
físico. Nenhuma ventoinha, processo ou política energética é modificada.
