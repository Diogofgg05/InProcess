# Estado de validação — atualização EXPECTO

## Atualização de otimização e modelos gravitacionais

104 testes passaram na validação da integração. A execução final está em `test-results.txt`. Foram acrescentados testes de órbitas/Euler/Verlet/convergência, queda livre, ficheiros gravitacionais, caches e idades, IPC de leitura, encerramento do auxiliar real, preservação dos objetos dos gráficos e API. Capturas integradas dos separadores orbitais e de queda livre foram revistas visualmente.

A recolha isolada é agora o padrão; o formato de tabelas, os controlos e o laboratório térmico foram mantidos. Novo A/B com três ensaios por modo: maior intervalo médio do timer GUI 413,6 → 55,4 ms, com mais memória e CPU agregados. Medição e limitações completas em `performance.md` e `data/performance-comparison.json`; não confundir redução de picos de atraso com aceleração da recolha, menor consumo total ou latência de cliques.

Os modelos gravitacionais são inteiramente sintéticos. A referência orbital só é aplicada ao caso circular; queda livre usa g constante sem chão/impacto. Não há validação experimental de gravidade ou calibração de sensores. Linux continua sem execução real neste ambiente.

## Evidência local das revisões anteriores

Windows 11, Python 3.12.10. Baseline anterior: 24 testes. A suíte ampliada cobre matemática, experiências, ficheiros, cancelamento, inventários e GUI; consultar `test-results.txt` para a execução mais recente. Capturas Processos/Laboratório foram inspecionadas visualmente, incluindo correção de escalas dos gráficos e colunas da tabela.

Revisão visual mais recente: 55 testes aprovados em 10,42 s. Foram adicionadas verificações das dimensões da composição (1536×1024; sidebar 267 px; barra 60 px; recursos 381 px; linhas 49 px; resumo 103 px), extração real de ícones HICON Windows e controlos de maximizar/restaurar/fechar. Os testes de margem de redimensionamento são executados offscreen: o arrasto e o redimensionamento interativo com rato num ambiente gráfico real permanecem por validar manualmente. A equivalência pixel a pixel à fotografia não foi demonstrada; conteúdo medido e disponibilidade de sensores diferem, por definição, dos valores ilustrativos.

O benchmark da nova composição está em `benchmark-gui-reference-design.json`. `data/dashboard-preview.png` é a sua captura, com dados reais. Os números na tabela seguinte pertencem ao ensaio anterior e permanecem identificados como tal; não se deve atribuí-los à revisão visual mais recente.

Testes de GUI verificam pesquisa, filtros, ordenação numérica, seleção persistente, confirmação recusada/aceite com serviço mock, preferências, ocultação dos cartões em janela pequena e encerramento durante simulação. Os testes de experiências verificam reprodução da configuração/semente, potência importada ZOH com referência independente, CSV inválido, limites de ficheiro e preservação de exportação cancelada. Ruído/filtragem é testado com três sementes e três intensidades.

Nenhum teste suspende ou termina processos de terceiros. Testes Linux de inventários com mocks não constituem execução no Linux. A pipeline Windows/Ubuntu foi preparada, mas não foi executada neste ambiente.

## Benchmarks reais

Executados separadamente dos testes. Os ficheiros JSON são os resultados brutos, específicos desta máquina e carga.

| Ensaio | Resultado |
|---|---|
| API final, 3 repetições × 3 recolhas consecutivas | média 350,8 ms/recolha; desvio entre médias 46,8 ms |
| GUI offscreen, intervalo 1000 ms, incluindo arranque | 10 recolhas em 10,05 s; média de recolha 479,7 ms |
| GUI CPU | 4,56 s CPU em 10,05 s = 45,4% de um núcleo lógico |
| GUI RAM | pico amostrado de 80 687 104 bytes (aprox. 77 MiB) |
| Timer GUI de 25 ms | intervalo P95 47,8 ms; máximo 468,1 ms |

`benchmark-before-optimization.json` guarda um ensaio API anterior à antecipação da verificação de permissões: média 1,182 s/recolha. Os ensaios não são emparelhados nem controlam toda a carga externa; a diferença não é uma garantia universal de melhoria.

O pico de atraso e o consumo de recolha permanecem relevantes. APIs nativas Windows/psutil e contenção do GIL podem atrasar o ciclo de eventos mesmo quando a chamada ocorre numa thread trabalhadora. Avaliar isolamento por processo e redução de frequência de métricas caras é uma possível melhoria futura. A amostragem configurada de 250 ms não garante essa cadência.

## Matriz final

| Área | Estado |
|---|---|
| Novo design escuro, tema claro, tabela e cartões medidos | Implementado; capturas offscreen verificadas |
| Recolha persistente, baselines e valores ausentes | Implementado; testes locais |
| Cancelamento e encerramento sem espera bloqueante GUI | Implementado; chamadas nativas já iniciadas aguardam conclusão |
| Experiências JSON, CSV validado e potência importada | Implementado; reprodução testada |
| Matemática, convergência log-log e ordem observada | Implementado; referências sintéticas testadas |
| Arranque, serviços, utilizadores | Inventários de leitura; cobertura específica de cada plataforma |
| Tipos aplicação/serviço/processo | Identificação aproximada, explicitada na interface |
| Preferências | Persistidas em INI; histórico permanece em memória |
| Linux e DPI elevados | Suíte executada em Ubuntu WSL; DPI/interação e Linux nativo ainda por validar |
| Potência elétrica medida, GPU e calibração física | Aquisição NVIDIA separada disponível; calibração física do CPU pendente |
| Comparação experimental com gestores externos | Não realizada |
| Instalador binário e relatório final preenchido | Não entregues; estrutura e protocolo disponíveis |

Não se declara conclusão de todas as fases académicas nem se atribui uma classificação. Os resultados térmicos continuam sintéticos; as medições do computador não validam experimentalmente o modelo térmico.

Ver [Evidência experimental e robustez](validation-evidence.md) para as aquisições reais da GPU, os 180 s de carga/churn, registos dos picos e resultados locais Windows/Linux. Estes dados ampliam a validação operacional, mantendo explícita a ausência de calibração física do CPU.
