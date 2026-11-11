# Evidência experimental e robustez — InProcess

Verificação local em 11 de novembro de 2026. Os ficheiros originais estão em `data/validation/`; `summary.json` é calculado por `examples/summarize_validation.py`. Os ensaios não substituem uma campanha de instrumentação nem garantem tempos máximos de resposta.

## Aquisição física disponível

Não foram encontrados sensores de temperatura/potência do CPU acessíveis nesta configuração Windows, nem um CSV externo fornecido pelo utilizador. Não se converteram percentagens de CPU em watts.

Foi possível recolher temperatura e potência da NVIDIA GeForce RTX 3050 Ti Laptop GPU, através de `nvidia-smi`, em duas sessões distintas de 120 segundos, com 60 amostras por sessão. Os manifestos incluem identificador de aquisição, origem, relógio UTC, duração, domínios, erros e SHA-256 do CSV.

| Sessão | Temperatura indicada | Potência elétrica indicada | Erros de aquisição |
|---|---:|---:|---:|
| `gpu-session` | 51–54 °C | 6,18–14,40 W | 0 |
| `gpu-validation` | 51–56 °C | 4,27–11,34 W | 0 |

São leituras do dispositivo reportadas pelo driver, sem calibração externa ou incerteza conhecida. A temperatura refere-se à GPU e a potência à placa; não são temperatura/potência do CPU. A resposta temporal da potência depende da arquitetura/driver e pode incluir médias. Consulte a [documentação oficial do NVIDIA System Management Interface](https://docs.nvidia.com/deploy/nvidia-smi/index.html).

A segunda sessão coincidiu com o ensaio de carga do CPU. O trabalho gráfico exterior e a ventilação não foram controlados. Os intervalos da tabela descrevem essas sessões; não demonstram aquecimento máximo, segurança térmica ou causalidade entre carga e temperatura.

## Calibração com dados independentes

`physics/experimental_validation.py` liga as aquisições ao ajuste térmico existente. Verifica a integridade do CSV, valores finitos, tempos crescentes, domínios consistentes, identificadores distintos, ficheiros distintos e janelas de aquisição disjuntas. Não permite reutilizar a própria sessão como validação independente.

A avaliação destas duas sessões está em `experimental-evaluation.json`, com estado **NOT_EVALUATED**: falta temperatura ambiente medida/declarada e uma hipótese explícita sobre a conversão entre potência elétrica da placa e entrada térmica no modelo. Não foram ajustados C ou k com um ambiente inventado.

Uma temperatura ambiente declarada e `--allow-electrical-proxy` permitem um estudo **EXPLORATORY**, incluindo erros e resíduos numa segunda sessão. Esse modo nunca apresenta `physical_validation=true`. Identificadores e hashes evitam reutilização acidental ou alteração do CSV sem deteção; não certificam o instrumento, a identidade física de uma GPU ou a autenticidade do manifesto.

Para uma validação física do CPU, é necessário adquirir temperatura do CPU e potência correspondente ao domínio modelado, medir o ambiente, documentar a incerteza/atraso dos sensores e controlar as condições de ventilação. Treino e validação devem usar aquisições separadas com excitação suficiente. Depois do ajuste, avaliar RMSE, erro máximo, condicionamento e estrutura dos resíduos; um bom ajuste numérico pode continuar a ter parâmetros fisicamente incorretos.

## Carga e criação/saída de processos

`validation_soak.py` executou uma sessão Windows de 180 s configurados, com 183,83 s totais incluindo preparação/encerramento. Usa recolha real a 1000 ms, dois auxiliares com duty alvo de 50% de um núcleo cada e dois processos curtos a cada cinco segundos. Alterna Processos, Desempenho, Histórico e Definições a cada 20 s, incluindo ordenação por CPU e expansão de grupos ao regressar a Processos.

Foram criados 70 auxiliares próprios: dois de carga e 68 de curta duração. Todos terminaram com código zero; 69 processos trabalhadores foram observados nos snapshots, sujeitos à cadência de amostragem. Houve 175 recolhas e nenhuma falha reportada pelo coletor. Nenhuma operação de controlo foi aplicada a processos de terceiros.

| Medição | Resultado |
|---|---:|
| Timer de 25 ms, mediana após aquecimento | 25,01 ms |
| Timer de 25 ms, P95 após aquecimento | 26,57 ms |
| Timer de 25 ms, P99 após aquecimento | 108,11 ms |
| Timer de 25 ms, máximo após aquecimento | 458,07 ms |
| CPU da GUI, percentagem de um núcleo | 19,57% |
| Aplicação dos processos, mediana / máximo | 12,27 / 96,24 ms |
| Atualização dos gráficos, mediana / máximo | 21,01 / 78,01 ms |
| Atualização do histórico, mediana / máximo | 1,26 / 3,10 ms |

O aquecimento excluído das estatísticas do timer externo é de 20 s. CPU refere-se apenas ao processo da GUI; não inclui coletor, lançadores ou auxiliares. A memória amostrada da GUI caiu cerca de 54,9 MiB entre as medianas das dez primeiras/últimas amostras após aquecimento; libertação/paginação de memória impede interpretar isto como prova de ausência de fugas.

Três minutos permitem observar mais ciclos que os ensaios anteriores de oito segundos. Continuam a faltar sessões de horas, repetições controladas, ensaios com mais núcleos e campanhas noutros computadores. Durante a execução decorreram aquisição NVIDIA, preparação de dependências Linux e verificações curtas; a carga exterior não foi isolada. Este ensaio não é uma comparação causal antes/depois nem é diretamente comparável às tabelas anteriores.

## Picos de resposta

`LatencyTrace` conserva buffers limitados de callbacks e intervalos de timer. Os registos brutos permitem relacionar os atrasos com atualização de processos, gráficos, histórico, cartões e pedidos de ícones. A versão final também mede navegação e aplicação dos ícones; estas duas medições adicionais foram introduzidas depois da sessão de 180 s e não constam dessa sessão.

O timer interno de 16 ms registou 108 intervalos de pelo menos 80 ms; 77 não sobrepuseram nenhum dos callbacks instrumentados nessa sessão. O maior intervalo interno foi 2293,86 ms durante o arranque/preparação do ensaio. Os registos internos incluem arranque e encerramento, enquanto a coluna de máximo do timer externo exclui os primeiros 20 s e termina antes do encerramento. Não se devem misturar estas estatísticas.

Um callback sobreposto a um pico não demonstra que o causou. A cobertura não inclui toda a pintura Qt, o gestor de janelas, chamadas nativas, agendamento do SO ou carga externa. Os picos não foram eliminados, e nenhum destes timers mede diretamente latência de cliques.

## Sistemas operativos e reprodução

Foram executados testes reais em Windows 11/Python 3.12 e Ubuntu WSL/Python 3.14, com psutil 7.2.2 e PySide6 6.10.1. Versões e resultados estão em `*-environment.json` e `*-tests.xml`. WSL usa o mesmo computador e um kernel Microsoft; não representa outro equipamento, Linux nativo ou avaliação visual interativa. O primeiro ensaio Linux emitiu apenas um aviso de permissões da cache partilhada com Windows; os testes passaram.

Resultados finais: **397 testes aprovados em Windows**; **396 aprovados e um ignorado em Linux** (extração nativa de ícones específica de Windows). Os novos testes cobrem proveniência, integridade, separação das aquisições, dados inválidos, limites do diagnóstico e 30 ciclos de alteração/reordenação de centenas de processos, incluindo reutilização de PID e preservação da seleção. Uma repetição Windows sob carga falhou por esperar por todas as tarefas, incluindo extração nativa de ícones; o teste de confirmação passou a isolar essa dependência, mantendo a cobertura nativa num teste separado. A suíte Windows completa voltou a passar.

A CI está preparada para Windows e Ubuntu com Python 3.12 e 3.14 e preservação dos relatórios JUnit. Não se afirma execução remota desta matriz nesta sessão.

```powershell
# Escolher pastas novas para não substituir aquisições anteriores.
.\.venv\Scripts\python.exe examples\capture_sensors.py --duration 120 --interval 2 --output data\validation\gpu-new-training
.\.venv\Scripts\python.exe examples\capture_sensors.py --duration 120 --interval 2 --output data\validation\gpu-new-holdout
.\.venv\Scripts\python.exe examples\validate_experiment.py --training data\validation\gpu-new-training\manifest.json --validation data\validation\gpu-new-holdout\manifest.json --output data\validation\new-evaluation.json

$env:QT_QPA_PLATFORM='offscreen'
.\.venv\Scripts\python.exe examples\validation_soak.py --duration 180 --workers 2 --duty 0.5 --output data\validation\soak-new
.\.venv\Scripts\python.exe -m pytest -q --junitxml=data\validation\windows-tests.xml
.\.venv\Scripts\python.exe examples\summarize_validation.py
```

O ensaio de carga é explícito, limitado a dois trabalhadores e 50% de duty por trabalhador no harness. Não altera frequências, serviços, prioridades ou processos externos. Para ensaios Linux separados usar `-o cache_dir=.pytest_cache_linux`; não executar benchmarks em simultâneo com a suíte de testes se se pretende comparar desempenho.

## O que ainda impede uma avaliação máxima fundamentada

Há agora aquisição real da GPU com proveniência, duas sessões independentes, análise temporal de picos, carga/churn reais e execução de testes em dois sistemas. Permanecem por demonstrar a calibração física do CPU, estabilidade durante horas, atribuição e redução dos piores picos, experiência interativa/DPI e funcionamento em equipamentos diferentes. A classificação académica continua dependente da grelha e da avaliação do docente.
