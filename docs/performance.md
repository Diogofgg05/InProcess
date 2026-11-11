# Desempenho: duração de recolha e resposta da interface

A otimização atual da lista agrupada e da barra lateral, com resultados antes/depois e os limites dos ensaios, está em [sidebar-optimization.md](sidebar-optimization.md). A comparação abaixo documenta o isolamento anterior do coletor e não deve ser confundida com os novos resultados.

O perfil Windows identificou consultas `Process.status()` caras. A recolha agora mantém estado por identidade `(PID,created)` durante até 5 s e sensores auxiliares durante 2 s, com timestamps/idades. CPU, RAM e I/O continuam consultados por amostra. Detalhes em `monitor-optimization.md`.

Chamadas nativas que retêm o GIL podem bloquear a interface apesar de ocorrerem numa thread. O padrão passou para um coletor Python separado, sem Qt. O canal JSON só aceita pedidos de leitura. Um leitor QThread envia snapshots para a GUI; o histórico só é retido no processo da GUI. Ao fechar, apenas esse auxiliar e o seu lançador são parados. PID e data de criação identificam o auxiliar, incluindo o Python real por trás do redirecionador do ambiente virtual Windows.

Modelos Qt evitam reset quando a sequência de identidades não muda. Eixos e séries dos gráficos são persistentes. Pré-visualizações científicas são preparadas nos trabalhadores e limitadas a 1500 pontos.

## Comparação local

Windows 11, Python 3.12, Qt offscreen. Três execuções de 8 s por modo, intervalo solicitado de 1000 ms, arranque incluído. Foram executados primeiro os três ensaios em thread e depois os três isolados. A ferramenta fornecida alterna os modos em novos ensaios para reduzir efeitos de ordem. A carga exterior não foi totalmente controlada. Não são garantias de desempenho noutros sistemas.

| Estatística: média entre ensaios | Thread + caches | Processo + caches |
|---|---:|---:|
| Maior intervalo do timer GUI | 413,6 ms | 55,4 ms |
| P95 do intervalo do timer GUI | 41,0 ms | 38,1 ms |
| Duração de recolha | 179,2 ms | 193,4 ms |
| CPU agregado, percentagem de um núcleo | 19,7% | 24,1% |
| Pico amostrado de RSS agregado | 92,5 MiB | 121,4 MiB |

O maior intervalo médio diminuiu 86,6%, enquanto P95 mudou pouco. O isolamento não acelerou a recolha nesta comparação; reduziu os picos de bloqueio GUI. Há custo adicional de cerca de 29 MiB e maior CPU agregado. O timer alvo é de 25 ms e o intervalo entre eventos não mede diretamente latência de cliques, FPS ou tempo de apresentação no ecrã. Os números das linhas P95/máximo são médias de estatísticas por ensaio, não um P95 agrupado de todos os eventos.

Resultados brutos: `data/perf-thread-1.json` a `3`, `data/perf-process-1.json` a `3`; síntese em `data/performance-comparison.json`.

Dois ensaios exploratórios revelaram problemas da própria instrumentação. `data/probe-overhead/` enumerava toda a árvore de processos a cada 25 ms, acrescentando custo excessivo. `data/launcher-probe/` contava o pequeno redirecionador venv Windows em vez do Python real para recursos do coletor. Esses ficheiros foram preservados, mas excluídos da comparação final. O ensaio inicial `data/performance-before-isolation.json` também não é um A/B controlado com esta versão.

## Reprodução

```powershell
.\.venv\Scripts\python examples\compare_performance.py --repetitions 3 --duration 8 --directory data/comparison-new
```

Para resumir os ensaios existentes sem executar novamente:

```powershell
.\.venv\Scripts\python examples\compare_performance.py --reuse --directory data
```

Amostragem a 250 ms é permitida, mas não garante essa cadência se o sistema estiver lento. Não há fila de amostras atrasadas a acumular para cumprir artificialmente a frequência. Linux, interação real, cargas grandes e execuções longas continuam a precisar de validação.
