# InProcess 7.1 / 7.2 — laboratório de desempenho e prioridades seguras

## 7.1 — Protocolo de medição comparativa

A aplicação mede recursos efetivamente observados em **ensaios reais**; não preenche uma tabela artificial de vitória perante Windows ou Linux. O protocolo usa uma tarefa de CPU determinística lançada pelo Python, sem shell, executada nas mesmas condições em cada cenário: sem monitor (BASELINE), InProcess, Gestor de Tarefas do Windows 11 ou GNOME System Monitor no Linux.

1. Registar CPU, RAM, versão do SO e Python, alimentação, temperatura, carga concorrente e intervalo de amostragem. A fingerprint de hardware/ambiente é um filtro preliminar, não garante equivalência térmica.
2. Iniciar apenas um monitor de cada vez; o utilizador fornece manualmente o PID de cada monitor externo. Repetir idealmente pelo menos cinco ensaios por cenário e alternar a ordem A–B–B–A, anotando-a.
3. Utilizar as mesmas iterações da tarefa de referência. Guardar cada execução bruta com sucesso/timeout, identidade do observador, duração, CPU do monitor (% de um núcleo lógico), pico RSS amostrado (MiB), número de amostras e a cadência do amostrador.
4. O filho que executa a tarefa de referência não é incluído no custo do observador InProcess, mesmo que seja seu descendente. Isto evita confundir a tarefa com o monitor que a lançou.
5. Comparar resultados com a mesma fingerprint e hash de tarefa. Analisar medianas, dispersão e impacto no tempo da tarefa; resultados com timeout ou erro não são equivalentes.
6. Não interpretar a cadência do amostrador como frequência real de atualização da GUI ou como latência de clique. Para essas métricas, preparar instrumentação separada e idêntica para cada ferramenta. Não estimar joules a partir de CPU% e RAM.
7. Testes Windows e Linux são grupos diferentes; a troca do próprio sistema operativo impede uma comparação A/B estritamente controlada de ferramentas nativas.

### Windows PowerShell

Depois de abrir os observadores e identificar os seus PIDs:

~~~powershell
.\.venv\Scripts\python.exe examples\benchmark_observers71.py --label BASELINE --repetitions 5 --output benchmarks\baseline.json
.\.venv\Scripts\python.exe examples\benchmark_observers71.py --label INPROCESS --observer-pid 12345 --repetitions 5 --output benchmarks\inprocess.json
.\.venv\Scripts\python.exe examples\benchmark_observers71.py --label WINDOWS_TASK_MANAGER --observer-pid 56789 --repetitions 5 --output benchmarks\windows.json
.\.venv\Scripts\python.exe examples\benchmark_observers71.py --compare benchmarks\baseline.json benchmarks\inprocess.json benchmarks\windows.json
~~~

Os PIDs 12345 e 56789 são exemplos: substituir pelos verdadeiros. Não manter InProcess nem outros monitores abertos durante BASELINE.

### Linux

~~~bash
.venv/bin/python examples/benchmark_observers71.py --label BASELINE --repetitions 5 --output benchmarks/base-linux.json
.venv/bin/python examples/benchmark_observers71.py --label INPROCESS --observer-pid 12345 --repetitions 5 --output benchmarks/inprocess-linux.json
.venv/bin/python examples/benchmark_observers71.py --label GNOME_SYSTEM_MONITOR --observer-pid 56789 --repetitions 5 --output benchmarks/gnome-linux.json
.venv/bin/python examples/benchmark_observers71.py --compare benchmarks/base-linux.json benchmarks/inprocess-linux.json benchmarks/gnome-linux.json
~~~

## 7.2 — Controlo temporário e reversível de prioridades

A GUI exige introdução do PID, pré-visualização do nome, utilizador e identidade de criação, autorização numa caixa de seleção **e** uma segunda confirmação antes de executar. Os dados são revalidados imediatamente antes de alterar o processo.

- Protege a própria aplicação, os antecessores, nomes críticos do SO, outros utilizadores e PIDs reservados.
- Windows: apenas classe NORMAL para BELOW_NORMAL; restaura NORMAL após a sessão.
- Linux: apenas nice=0 para nice=5 e só quando o InProcess **já corre como root**, por ser necessária permissão para restaurar nice=0. Não eleva privilégios. **Não é recomendado executar toda a aplicação gráfica como root**: para utilizadores normais o laboratório recusa a mudança e continua a permitir análise.
- Sessão máxima de 15 segundos, identidade de PID validada, cancelamento cooperativo e reposição confirmada quando possível. Se a prioridade for alterada por outro interveniente, não a sobrescreve.
- Um crash, encerramento forçado ou perda de energia **pode impedir a restauração**. Por isso a reposição automática não é garantida após falhas do processo; o utilizador deve confirmar no gestor nativo.
- Não suspende, termina, congela serviços ou altera planos de energia. Reduzir prioridade não demonstra poupança energética, e não se apresenta como gestão autónoma de CPU/RAM.

## Reprodutibilidade e lacunas

Os testes 7.2 usam processos falsos (mocks), sem alterar prioridades reais durante CI. Os testes 7.1 lançam somente tarefas de referência criadas pelo próprio benchmark e terminam apenas esses filhos em timeout.

~~~bash
python -m pytest tests/test_benchmarks71.py tests/test_priority72.py -q
~~~

Funcionalidades futuras: medição instrumental de latência de clique, séries sincronizadas de potência elétrica, watchdog independente para recuperação após crash, helper Linux com privilégio mínimo, comparação contrabalançada automática e estudos com confiança estatística adequada. **Nenhuma delas foi implementada na versão atual.**
