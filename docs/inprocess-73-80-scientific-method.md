# InProcess 7.3–8.0 — evidência científica, segurança e eficiência nativa

> **Estado:** primeira implementação modular, sujeita à validação em hardware real.
> **Não se demonstrou** que o InProcess consome menos energia que Windows 11 ou Linux,
> nem que os modelos físicos estão calibrados para um determinado computador.

## 7.3 — Scientific Benchmark Laboratory

O módulo \`optimization/statistics73.py\` analisa os ensaios já recolhidos
por \`optimization/benchmarks71.py\`. Exige **pelo menos três ensaios bem-sucedidos**
por cenário e, além das verificações anteriores, calcula:

- Média, mediana, desvio-padrão e percentil P95 da duração;
- Mediana de CPU de um núcleo lógico e RSS amostrado do observador;
- Sobrecarga relativa de duração face ao BASELINE;
- Bootstrap determinístico, **não emparelhado**, de 1000 reamostragens
  para um intervalo descritivo de 95% da razão de medianas.

O bootstrap **não corrige** o drift térmico, a falta de contrabalançamento
entre condições nem o facto de se comparar sistemas operativos diferentes.
Sem instrumentos comuns de latência de clique/renderização, esta grandeza
permanece \`NOT_MEASURED\`. A frequência da amostragem não é frequência da GUI.
Nenhum resultado real é pré-preenchido.

Recomenda-se cinco ou mais repetições reais por cenário, alternância de ordem
e registo da temperatura ambiente, modo energético, atualizações, processos de
fundo, condições de alimentação e frequência de atualização das aplicações.
O utilizador deve executar a recolha no próprio PC.

## 7.4 — Crash Watchdog de prioridade

\`optimization/watchdog74.py\` pode ser iniciado como **processo independente**
durante uma sessão autorizada de \`priority72.py\`. O objetivo é repor a prioridade
original quando a GUI desaparece ou o prazo curto expira.

Características:

- Transição estritamente delimitada: Windows NORMAL ↔ BELOW_NORMAL; Linux
  nice 0 ↔ 5 somente com permissões já existentes (não executar GUI como root).
- Verificação de PID, data de criação, utilizador, dono da sessão e valor exato
  de prioridade temporária;
- Se a prioridade tiver sido alterada por outra aplicação, não a sobrescreve;
- O processo auxiliar tenta restaurar no máximo após 20 s, mesmo que a
  interface tenha falhado, desde que o helper continue operacional.

**Limitação crítica:** não é reversão garantida. Falhas de privilégios,
encerramento do helper, sessão terminada, reboot e falha do SO podem impedir
o restauro. Uma aplicação não deve descrever isto como um mecanismo transacional
robusto, sem testes de crash físicos em Windows/Linux. A UI informa o utilizador
e preserva uma segunda via de reposição no processo principal.

## 7.5 — Native Efficiency (apenas tarefas próprias)

O módulo \`optimization/native75.py\` tem uma API **opt-in** para executar uma
**nova tarefa de benchmark** com uma política nativa:

- No Windows, tenta \`SetProcessInformation\` /
  \`ProcessPowerThrottling\` para ativar **EcoQoS no processo filho**
  expressamente criado e autorizado. O processo termina após a tarefa
  ou timeout; não se altera a política global do utilizador.
- No Linux, usa \`systemd-run --user --scope --property=CPUWeight=50\`
  para isolar a tarefa na sessão do utilizador, se systemd estiver disponível.
  \`CPUWeight\` é um **peso relativo de CPU**, não uma percentagem garantida,
  nem um limite de potência. Sem sudo, sem root e sem comandos de shell.

A experiência é opcional e isolada; não altera PIDs escolhidos
arbitrariamente, serviços críticos, ficheiros do sistema ou ventoinhas.
O efeito depende do escalonador, permissões e configuração do computador.
**Não afirmar redução de watts/joules sem sensores.**

Fontes de especificação para validação da API:
- Microsoft — [SetProcessInformation](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-setprocessinformation)
- Microsoft — [PROCESS_POWER_THROTTLING_STATE](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/ns-processthreadsapi-process_power_throttling_state)
- systemd — [resource control / CPUWeight](https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html)

## 7.6 — Energia medida, unidades e proveniência

O módulo \`optimization/energy76.py\` aceita CSV em unidades SI:

\`\`\`csv
time_s,power_w,temperature_c
0,20,25
2,20,26
5,20,27
\`\`\`

O equipamento, o identificador do sensor e o **domínio de potência**
(entrada da tomada, pacote CPU, placa GPU, etc.) são obrigatórios.
A origem por defeito é \`MEASURED_UNVERIFIED\`; importar uma série
não comprova calibração. Os valores de energia são integrados pelo
método trapezoidal:

\`\`\`text
E = sum( (P[k] + P[k+1])/2 * (t[k+1] - t[k]) ) [joules]
Wh = E / 3600
\`\`\`

Para uma potência constante de 20 W durante 5 s, o resultado matemático
é 100 J (0,02778 Wh). Isto é **apenas um exemplo didático**, não um
ensaio energético realizado no InProcess.

A comparação entre perfis exige equipamento, sensor, domínio de potência,
proveniência e **equivalência de trabalho**. Mesmo quando estes coincidem,
são necessários ensaios repetidos e análise de incerteza para concluir
que uma diferença não é ruído instrumental.

## 8.0 — Motor de recomendações com evidência

\`optimization/recommendations80.py\` é um mecanismo de regras
**READ_ONLY** — não é um LLM treinado, nem aprende autonomamente. Se
não houver experiências suficientes/comparáveis, responde
\`INSUFFICIENT_EVIDENCE\`; se houver indícios descritivos de overhead,
sugere **rever a carga**. Para energia, indica um perfil candidato,
sem o aplicar.

**Não existe nenhuma execução automática** de comandos, mudança de
prioridade ou políticas energéticas pelas recomendações.

## Interface

- Página antiga de desempenho 7.1/7.2: apresentação das métricas 7.3 e
  recomendações 8.0; sessões 7.2 com watchdog 7.4 opcional ativado pela UI;
- Página nova de laboratório 7.5/7.6/8.0: experiência nativa limitada
  com confirmação, importação CSV com unidade/sensor, comparação de
  consumo e recomendações somente de leitura;
- Exportação JSON, mantendo proveniência dos dados e avisos.

## Verificação e limites da entrega

\`\`\`bash
python -m pytest tests/test_scientific_73_to_80.py -q
python -m pytest -q
\`\`\`

Os testes de watchdog e sistema nativo usam mocks, para não modificar
as prioridades dos runners da CI. Antes de ativar funções privilegiadas
em produção, executar uma matriz de testes manuais em máquinas de teste:
crash da interface, crash do helper, PID reutilizado, erro de permissão,
processo encerrado antes do prazo, sessões simultâneas e políticas de
segurança do Windows/Linux. A CI não simula essas condições por completo.

## Trabalho futuro

1. Exposição de sensores calibrados com sincronização e unidades verificadas;
2. Latência da interface medida com instrumentação externa comum;
3. Experiências contrabalançadas e estudos com incerteza estatística;
4. Watchdog instalado como serviço de privilégio mínimo auditado;
5. Protocolos de decisão com limites térmicos e avaliação de robustez;
6. Gestão adaptativa **só após** validação experimental e revisão de segurança.


### Relatório PDF gerado diretamente dos teus benchmarks reais

Depois de executar os ensaios 7.1 com Windows ou Linux, produzir
gráficos de duração e estatísticas **sem dados inventados**:

\`\`\`bash
python -m pip install 'reportlab>=4,<5'
python examples/report_benchmark73_pdf.py \
  benchmarks/baseline.json benchmarks/inprocess.json \
  -o benchmarks/benchmark-resultados.pdf
\`\`\`

O relatório usa os JSON originais e apresenta as razões de recusa da
comparação sempre que os ensaios não sejam metodologicamente equivalentes.
**Não** contém gráficos de consumo elétrico ou de latência da GUI, porque
essas medições exigem instrumentos adicionais.
