# Energia e comparação de perfis

Esta API é apenas de leitura. Os nomes NORMAL, ECO e ULTRA ECO identificam ensaios fornecidos pelo utilizador ou cenários sintéticos. Não aplicam políticas ao sistema operativo, não controlam processos e não alteram frequências ou limites de potência.

## Cálculo

`core.energy.integrate_power(times, powers)` integra a potência em W pelos trapézios usando os instantes reais em s, mesmo quando o espaçamento não é uniforme. O resultado `EnergyUse` contém `joules`, `watt_hours`, `duration`, `average_power` e `peak_power`. Uma energia de 3600 J corresponde a 1 Wh. A eficiência de uma tarefa é trabalho concluído dividido pela energia, em unidades de trabalho/J; para energia nula, a eficiência fica indefinida.

Não se converte utilização de CPU, frequência, TDP ou percentagens em potência medida. A fronteira de medição deve ser consistente: energia do pacote CPU e energia da tomada não representam a mesma grandeza experimental.

## Contrato de um ensaio

```python
from expecto_process_manager.optimization.eco import PolicyRun, compare_policies

normal = PolicyRun(
    policy="NORMAL", times=[0, 5, 10], powers=[60, 60, 60],
    temperatures=[25, 70, 70], work_units=1, work_label="render completo",
    provenance="SIMULATED", task_id="mesma-cena-v1", work_completed=True,
    temperature_provenance="SIMULATED",
)
eco = PolicyRun(
    policy="ECO", times=[0, 7.5, 15], powers=[45, 45, 45],
    temperatures=[25, 62, 62], work_units=1, work_label="render completo",
    provenance="SIMULATED", task_id="mesma-cena-v1", work_completed=True,
    temperature_provenance="SIMULATED",
)
comparison = compare_policies([normal, eco], max_duration=18, max_temperature=80)
```

Neste exemplo inteiramente sintético, NORMAL usa 600 J e ECO usa 675 J: a menor potência do ECO não compensa o tempo adicional. Não se demonstra poupança real no computador. `synthetic_policy_runs()` acrescenta ULTRA ECO, com 500 J durante 20 s, para demonstrar também a influência de um prazo.

Potência e temperatura têm proveniências independentes. `provenance` aceita `SIMULATED`, `ESTIMATED` ou `MEASURED`; `temperature_provenance` pode ser uma dessas etiquetas ou permanecer não declarada. Estas etiquetas são declarações do utilizador e não certificam sensores. Dados importados não adquirem automaticamente proveniência medida.

O mesmo `task_id`, a mesma unidade/descrição de trabalho, a mesma quantidade positiva de trabalho e `work_completed=True` devem estar presentes em todos os perfis. Caso contrário, a comparação não recomenda. Misturar proveniências de potência ou omitir potência em qualquer perfil também impede recomendar. Um único perfil permite calcular consumo, mas não comparar alternativas.

`EnergyComparison.rows` contém métricas por perfil; `feasible` contém os perfis que satisfazem os limites de duração e temperatura; `recommendation` é o nome do perfil de menor energia admissível ou `None`; `comparable` e `reasons` explicam os bloqueios. Sem temperatura, um perfil não pode satisfazer uma restrição térmica. Sem restrição térmica, a ausência de temperatura não impede comparar energia. Empates de energia usam a menor duração. O relatório em `report` explicita resultados, unidades, origem, hipóteses e limites.

## CSV

`core.energy.load_power_csv(path)` lê `time_s,power_w` e, opcionalmente, `temperature_c`. São obrigatórios pelo menos dois instantes finitos estritamente crescentes e potências finitas não negativas. Se a coluna de temperatura existir, todos os valores devem estar preenchidos. O limite é 16 MiB e 200 001 amostras. Não são aceites cabeçalhos de CPU%, unidades implícitas ou colunas extra.

`optimization.eco.load_policy_csv(path, policy=..., work_units=..., work_label=..., provenance=..., task_id=..., work_completed=True, temperature_provenance=None)` combina a série com metadados explicitamente fornecidos. Usa ponto decimal e separador vírgula. O CSV sozinho não permite saber se a tarefa terminou ou se as medições são equivalentes.

## Limites da interpretação

Uma comparação justa requer a mesma tarefa, computador, configuração, carga de fundo, fronteira de potência e condições experimentais. O cálculo cobre apenas o intervalo fornecido. Não inclui consumo anterior/posterior, calibração, incerteza instrumental, repetição de ensaios nem significância estatística. A recomendação descreve os valores fornecidos; não garante desempenho, segurança térmica ou poupança futura.

Executar `python -m pytest tests/test_energy_eco.py` para verificar energia constante, tempos não uniformes, unidades, restrições, incompatibilidade de tarefas, proveniência, potência ausente, importação e cancelamento.

## Parecer de eficiência com limites configuráveis (ECO Advisor)

A função `optimization.advisor.energy_advice(comparison, min_savings_percent=5,
max_slowdown_percent=25)` analisa a comparação anterior **sem modificar o
sistema operativo**. Usa NORMAL como referência e calcula a diferença de energia
em joules, watt-hora, redução percentual e diferença percentual de duração.
Uma alternativa só é considerada candidata quando a comparação é válida,
NORMAL é admissível, poupa a energia mínima exigida e o atraso não ultrapassa
o limite. Sem uma referência válida, o parecer é inconclusivo.

Na página Energia / ULTRA ECO, os parâmetros «Poupança mínima» e «Atraso máximo»
podem ser configurados. O parecer é apresentado separadamente do perfil
matematicamente menos energético. Assim, o perfil de energia mínima pode ser
rejeitado pelo atraso excessivo. O relatório preserva as duas interpretações.

Exemplo sintético: NORMAL consome 600 J em 10 s, ECO 675 J em 15 s e
ULTRA ECO 500 J em 20 s. Com os limites de 5% de poupança e 25% de atraso,
o parecer aconselha manter NORMAL: apesar de ULTRA ECO gastar menos joules,
demora 100% mais. Com atraso máximo de 100%, ULTRA ECO pode tornar-se
candidato **neste cenário simulado**.

Os resultados são exclusivamente `DRY RUN`: sem alterações de processos,
frequências, prioridades, planos de energia ou dispositivos. A origem
`MEASURED` é declarada pelo utilizador e não garante calibração ou qualidade
experimental. A política recomendada não prova ganhos no hardware real,
nem valida automaticamente limites de segurança térmica.

Testes: `python -m pytest tests/test_eco_advisor.py -q`.

## Contexto de carga real no ECO Advisor

A página do laboratório recebe os avisos já calculados pelo
`ProcessInsights`, quando é criada e sempre que chegam novos snapshots.
O módulo `optimization/workload.py` apresenta três estados:
`NO_SNAPSHOT`, `NO_SUSTAINED_SIGNAL` e `ACTIVE_WORKLOAD`.
O ecrã distingue cargas persistentes de CPU/RAM e deixa claro que não é
possível deduzir watts dessas métricas. Não existe novo sensor, thread ou
processo de monitorização por causa desta funcionalidade.

O contexto serve para alertar que uma comparação energética deve ser feita
em condições experimentais controladas. Os dados de processos são instantâneos:
**não estão sincronizados com os intervalos de potência dos perfis comparados**.
Por isso, o parecer de poupança, os valores em J/Wh, a proveniência e a
admissibilidade térmica não são alterados por avisos de utilização do CPU.
Um alerta de atividade não prova que existe desperdício, nem autoriza terminar
ou suspender processos. Nenhum perfil é aplicado automaticamente.

Testes dedicados: `python -m pytest tests/test_workload_context.py -q`.
