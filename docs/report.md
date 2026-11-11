# Estrutura do relatório académico

1. **Introdução e motivação:** monitorização de sistemas e ligação à modelação física.
2. **Objetivos:** requisitos funcionais, científicos e critérios verificáveis.
3. **Fundamentos físicos e matemáticos:** balanço energético, capacidade térmica e dissipação.
4. **Formulação dos modelos:** equação diferencial, hipóteses, unidades e solução de referência.
5. **Métodos numéricos:** Euler, diferenças finitas e quadraturas; estabilidade e ordem.
6. **Arquitetura do software:** módulos, threads, adaptação de plataforma e API.
7. **Implementação em Python:** psutil, PySide6, validação e tratamento de exceções.
8. **Experiências e resultados:** separar ensaios sintéticos de medições reais; registar sistema operativo, CPU, RAM, versões, carga, data e parâmetros. Exportar os CSV originais. Incluir gráficos com título, legenda, unidades e origem.
9. **Validação e análise de erros:** tabelar Δt de 0,01 a 1 s, erro máximo e RMSE; estimar ordem com log(Eh/Eh/2)/log(2); estudar ruído com várias sementes e σ; comparar energia com integrais exatas.
10. **Limitações:** sensores indisponíveis, parâmetros não calibrados, incerteza experimental, simplificações térmicas e influência da recolha no sistema.
11. **Conclusões:** relacionar apenas os resultados efetivamente obtidos com os objetivos.
12. **Desenvolvimentos futuros:** calibração, potência instrumentada, persistência e adaptação ao EXPECTO/SO próprio.

## Protocolo proposto para medições reais

Medir o consumo do próprio programa em repouso e com a mesma carga controlada, durante o mesmo intervalo, para frequências de amostragem de 250, 1000 e 5000 ms. Repetir pelo menos três vezes e reportar média e dispersão. Comparar com outro gestor usando a mesma metodologia. Não preencher tabelas de resultados antes de executar os ensaios. A ferramenta de benchmark fornecida mede apenas a recolha em modo API; o ensaio completo do GUI e a comparação entre aplicações continuam por executar.

## Implementação e evidência disponíveis

A aplicação usa a organização descrita em `architecture.md`. O laboratório permite guardar/reabrir experiências JSON, importar potência CSV com retenção à esquerda e obter gráficos de convergência log-log com estimativa de ordem. São mantidas as unidades, sementes e distinção entre entrada importada e temperatura simulada.

As medições reais de desempenho da implementação estão em `../benchmark-results.json` e `../benchmark-gui-results.json`; a interpretação e os limites constam de `validation.md`. O benchmark GUI offscreen não é uma avaliação de interação real nem uma comparação com outros gestores.

Para completar o relatório, executar os ensaios controlados propostos, incluir resultados numéricos exportados e figuras correspondentes, e discutir o pico de atraso observado no ciclo de eventos. Não transformar os parâmetros térmicos ilustrativos em valores experimentais calibrados.

## Novos ensaios numéricos disponíveis

- Gravitação: massa central pontual fixa, estado circular inicial, comparação de Euler explícito, Euler simplético e Velocity Verlet. Estudar passos 20, 10, 5 e 2,5 s e reportar ordem observada, RMSE de posição, energia e momento angular. A referência circular é independente da recorrência numérica. Não representa órbitas medidas.
- Queda livre: altura inicial 100 m, velocidade inicial zero, g = 9,80665 m/s², duração 4 s. Comparar passos 0,1, 0,05 e 0,01 s. O erro final de altura esperado para passo uniforme é g·T·dt/2 e a deriva de energia específica é g²·T·dt/2. Não existe chão/impacto no modelo.
- Desempenho: substituir conclusões antigas sobre fluidez pelos ensaios em `performance.md`. Apresentar também o aumento de memória/CPU ao isolar a recolha; não comparar apenas o processo da GUI omitindo o auxiliar.

`python examples/gravity_demo.py` gera `data/gravity-validation.txt` e `data/free-fall-example.csv` com resultados sintéticos reproduzíveis. O relatório final deve distinguir esses resultados dos ensaios reais de desempenho do programa.
