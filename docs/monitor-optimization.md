# Recolha: otimização com cadências e proveniência temporal

Uma recolha aquecida perfilada neste Windows identificou `Process.status()` como gargalo: 97 chamadas consumiram aproximadamente 345 ms de um total de 414 ms. A consulta Windows de suspensão percorre informação nativa e era repetida em cada ciclo.

Foi introduzido um cache apenas do estado, por `(PID, data de criação)`, com validade máxima de 5 s antes da próxima tentativa. Cada linha expõe `status_sampled_at` (Unix, segundos) e `status_age_s`. CPU, memória RSS, I/O, nome, utilizador e permissões continuam consultados em cada recolha. Uma segunda recolha aquecida perfilada, sem atualização de estado vencida, demorou aproximadamente 44 ms (30 ms processos e 14 ms métricas globais). Estes dois perfis curtos não são um benchmark emparelhado, não controlam carga externa e não incluem a média dos ciclos de atualização de 5 s.

O primeiro ciclo e os ciclos em que muitos estados vencem podem continuar lentos. O cache reduz trabalho repetido, mas não transforma valores antigos em medições novas. Suspensões/continuações podem demorar até ao ciclo de atualização de estado a aparecer na lista. O controlo efetuado na mesma instância invalida o estado do PID; `ProcessService.invalidate_status(pid)` permite que o controlador invalide o cache do fornecedor através do seu canal de recolha, sem qualquer alteração adicional do processo.

`process_iter()` mantém objetos e datas de criação em cache. Antes de reutilizar qualquer estado/I/O local, `is_running()` verifica a identidade do processo; um PID reutilizado é omitido nesse ciclo e volta com objeto novo num ciclo posterior. Os caches são podados aos processos acessíveis da recolha atual. O catálogo de tipos Windows também rejeita associação de um PID cuja criação seja posterior à fotografia do catálogo.

Swap, temperatura CPU e frequência CPU têm cadência de 2 s; para cada um há timestamp `*_sampled_at` e idade `*_age_s`. Uma falha ou sensor não disponível produz `None`, incluindo `swap_used`, sem conservar silenciosamente um valor anterior. A ausência também é memorizada por 2 s para evitar repetir consultas não suportadas. CPU por núcleo, RAM global e contadores disco/rede continuam por recolha. A idade refere-se ao instante da recolha; o consumidor pode calcular idade atual usando o timestamp Unix.

Cadências são configuráveis por código: `ProcessService(status_interval_s=5)` e `Monitor(auxiliary_interval_s=2)`. Valor zero desativa o cache correspondente. Estas opções não pedem privilégios administrativos.

Os testes dedicados verificam idade e validade, CPU sempre consultada, PID reutilizado, poda, invalidação explícita e pós-controlo, falhas de sensores, ausência distinta de zero e intervalos inválidos. O isolamento da recolha num processo (implementado pelo controlador) trata separadamente a contenção de GIL das chamadas nativas.
