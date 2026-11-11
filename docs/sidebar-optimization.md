# Barra lateral e otimização da interface — InProcess

Verificação local em 11 de novembro de 2026, Windows 11, Python 3.12, Qt offscreen.

## Alterações

A barra lateral usa uma seleção azul suave com indicador vertical, ícones mais discretos, separadores entre monitorização, laboratório e definições. As Definições estão diretamente acessíveis no menu. Os pixmaps dos ícones são reutilizados numa cache limitada a 96 entradas; o resto do design foi preservado.

O profiling encontrou sobretudo custo nas notificações do modelo hierárquico de processos. As alterações ao motor da interface foram:

- Agregar sinais produzidos pela mesma atualização num único processamento dos grupos.
- Emitir uma notificação para o intervalo de grupos, em vez de uma por pasta.
- Notificar as linhas filhas apenas nas pastas expandidas; os valores das pastas fechadas continuam atualizados e aparecem corretamente ao expandir.
- Adiar a reconstrução da vista agrupada quando a lista individual está ativa; ao regressar, aplicar o snapshot mais recente.
- Agrupar e ordenar diretamente os registos Python, evitando milhares de criações de `QModelIndex` para o mesmo trabalho.
- Evitar a ordenação dinâmica da lista individual quando essa vista está oculta. A ordenação e os filtros da vista ativa mantêm-se funcionais.
- Comparar valores de ordenação diretamente nos registos, preservando a ordenação numérica e os valores indisponíveis.
- Ignorar reaplicações de densidade quando tamanho, página, tema e páginas construídas não mudaram.

A cadência de amostragem de 1000 ms e o coletor real não foram alterados. Não se reduziram leituras para produzir artificialmente tempos menores. As operações sobre processos continuam a usar PID e data de criação; selecionar uma pasta não executa uma operação em massa.

Uma melhoria posterior adia as atualizações visuais de Processos enquanto outra página está selecionada e evita reconstruir grupos por alterações de ícones. Os resultados, o custo de regressar à página e as limitações estão em [Atualizações por página e ícones](page-activity-optimization.md).

## Ensaio determinístico de atualização

600 processos sintéticos, 60 nomes de executável, 30 atualizações medidas em cada vista. Cada atualização mede a aplicação dos novos registos e o processamento dos eventos Qt. A geração dos dados, consultas ao SO, extração de ícones nativos e construção inicial da página estão fora desse intervalo. O profiling foi executado separadamente, por acrescentar overhead.

| Vista | Mediana antes | Mediana depois | Redução | P95 antes → depois |
|---|---:|---:|---:|---:|
| Grupos fechados | 89,76 ms | 16,27 ms | 81,9% | 147,28 → 28,00 ms |
| Dez pastas expandidas | 80,98 ms | 20,14 ms | 75,1% | 111,91 → 45,47 ms |
| Ordenada por CPU | 141,49 ms | 19,71 ms | 86,1% | 251,07 → 36,38 ms |
| Lista individual | 76,03 ms | 22,53 ms | 70,4% | 129,47 → 31,66 ms |

São medições de uma carga fixa, não de todas as possíveis árvores de processos. A sequência conserva os PID e usa variações determinísticas de valores; não caracteriza churn intenso de processos nem todas as reordenações possíveis. Não são FPS, latência de cliques ou medições de potência elétrica.

No profiling das mesmas quatro vistas, dez atualizações por vista, as chamadas à função de criação de índices hierárquicos passaram de 315160 para 10240. O tempo acumulado de `update_rows`, incluindo overhead do profiler, passou de 4,451 s para 0,375 s. Estes tempos de profiling não foram usados nas percentagens da tabela.

## Aplicação com recolha real

Três ensaios de oito segundos antes e três depois, com o mesmo fornecedor isolado e intervalo configurado de 1000 ms. Incluem as primeiras recolhas e renderizações após mostrar a janela, não uma medição completa do tempo de lançamento. Todos os resultados finais foram conservados, incluindo o pior pico.

| Média das estatísticas de cada ensaio | Antes | Depois |
|---|---:|---:|
| CPU da GUI, % de um núcleo lógico | 14,20% | 10,60% |
| CPU agregado GUI + coletor/lançador, % de um núcleo | 37,12% | 30,88% |
| Pico amostrado de memória agregado | 130,79 MiB | 131,07 MiB |
| Duração média de recolha | 226,66 ms | 194,33 ms |
| P95 dos intervalos do timer GUI de 25 ms | 38,82 ms | 37,66 ms |
| Média do maior intervalo por ensaio | 67,10 ms | 85,14 ms |
| Pior intervalo observado nos três ensaios | 70,48 ms | 110,00 ms |

O CPU médio da GUI ficou 25,3% mais baixo nestes ensaios. A memória manteve-se praticamente igual. O pior pico não melhorou e houve uma execução com 110 ms. Portanto, estes dados não demonstram eliminação de bloqueios ocasionais ou uma latência máxima garantida.

A carga exterior, caches do sistema e a cadência de temporizadores Windows não estão controladas. A redução observada no tempo de recolha não é atribuída diretamente às alterações do frontend, pois o algoritmo de recolha permaneceu igual. São ensaios locais curtos; estabilidade prolongada, máquinas diferentes e interação real continuam a precisar de validação.

## Artefactos e reprodução

Os dados completos estão em `data/sidebar-optimization/`:

- `ui-before.json` e `ui-after.json`: todos os tempos das atualizações sintéticas.
- `profile-before.json` e `profile-after.json`: diagnóstico separado com profiling.
- `before-1.json` a `before-3.json` e `after-1.json` a `after-3.json`: seis ensaios reais finais.
- `summary.json`: síntese calculada automaticamente a partir desses ficheiros.
- `ui-after-first.json`: execução intermédia, anterior à remoção da ordenação da vista oculta; não integra a comparação final.

```powershell
$env:QT_QPA_PLATFORM='offscreen'
.\.venv\Scripts\python.exe examples\benchmark_ui_updates.py --updates 30 --output data\ui-new.json
.\.venv\Scripts\python.exe examples\benchmark_gui.py --duration 8 --backend process --output data\gui-new.json
.\.venv\Scripts\python.exe examples\summarize_ui_optimization.py
.\.venv\Scripts\python.exe -m pytest -q
```

O último comando passou com **380 testes em 17,84 s**. Os novos testes verificam notificações reduzidas, atualização de dados em pastas fechadas, filtros dependentes de novas medições e recuperação da vista agrupada após ficar oculta.

## Avaliação técnica indicativa

**18/20 como projeto académico**, sem substituir a grelha do docente. O projeto combina monitorização real, modelos físicos explícitos, validação numérica, testes extensos, relatórios reproduzíveis e uma interface utilizável. A otimização agora tem evidência antes/depois.

Essas lacunas passaram a ter verificação adicional: duas aquisições reais da GPU, um ensaio de 180 s com carga e criação/saída de 70 auxiliares, registo dos picos e execução da suíte em Windows e Ubuntu via WSL. Os dados e o protocolo estão em [Evidência experimental e robustez](validation-evidence.md).

A avaliação máxima ainda exige calibração física do CPU com sensores/ambiente conhecidos, sessões de horas, investigação dos piores picos e validação em equipamentos diferentes. As medições da GPU não validam o modelo do CPU; WSL usa o mesmo hardware. A simulação sintética, os testes aprovados e a aquisição real têm alcances diferentes, explicitados no relatório.
