# Arquitetura

- `core/models.py`: contratos de processos tipados, mantendo mapas públicos.
- `core/providers.py`: protocolo MonitoringProvider e fornecedor psutil inicial.
- `core/sampling_process.py`: auxiliar de leitura com protocolo JSON versionado; não importa Qt nem aceita ações de controlo de processos.
- `core/monitoring.py`: snapshots, baselines por thread e taxas com relógio monotónico.
- `core/processes.py`: leituras e controlo separado com autorização e identidade PID/data de criação.
- `core/inventory.py`, `platforms/catalog.py`: consultas de arranque/serviços/sessões e classificação aproximada por SO.
- `core/metrics.py`: CSV validado e exportação atómica.
- `core/cancellation.py`: token cooperativo sem dependência Qt.
- `physics/`: métodos numéricos independentes de GUI e sensores.
- `simulation/experiments.py`: configuração imutável, validação, execução, análise e persistência JSON versionada.
- `interface/workers.py`: recolha persistente e tarefas geridas; resultados enviados por sinais Qt.
- `interface/process_collector.py`: leitura IPC e ciclo de vida do auxiliar isolado; identifica o Python real e o lançador Windows, preservando a identidade antes de parar o auxiliar criado pela aplicação.
- `interface/`: páginas, modelos Qt, tema, ícones vetoriais e cartões com séries medidas.
- `interface/window_chrome.py`: barra de janela própria, controlos funcionais e menu de ferramentas científicas; margens exteriores iniciam redimensionamento nativo.
- `interface/delegates.py`: desenho de navegação, primeira coluna e cabeçalho conforme a referência, mantendo seleção, acessibilidade e ordenação dos modelos Qt.
- `interface/process_icons.py`: extração assíncrona de ícones de executáveis Windows como QImage; conversão para QPixmap apenas na thread GUI, cache limitado a 256 nomes. Fallback vetorial quando o ícone é inacessível; outros sistemas usam QIcon.fromTheme.
- `plugin_api/`: contratos originais e execução de experiências.
- `physics/gravity.py`: comparação Newtoniana central com Euler explícito/simplético/Verlet e queda livre uniforme, sem dependências da interface.
- `interface/gravity_page.py`, `free_fall_page.py`: parâmetros, gráficos e ficheiros dos novos separadores; preparação científica fora da GUI.

A thread GUI só prepara configurações pequenas e apresenta resultados. Cálculos científicos, leitura/escrita de ficheiros e inventários correm fora dela. A apresentação ainda percorre séries para gráficos (até ~1500 pontos visíveis) e aplica filtros/ordenação aos processos; medir o custo com muitos milhares de processos é trabalho futuro.

O cancelamento é verificado entre etapas e a cada 256 passos Euler ou linhas CSV. Bibliotecas de serialização e chamadas nativas do sistema não são interrompidas a meio. O encerramento desativa novas ações, solicita cancelamento/paragem e verifica periodicamente a conclusão. Não usa espera bloqueante na thread GUI.

O fornecedor abstrato cobre consultas de métricas/processos. O controlo autorizado e os inventários continuam como serviços separados, a adaptar quando for integrado outro sistema operativo. Não há dependência de um assistente IA.
