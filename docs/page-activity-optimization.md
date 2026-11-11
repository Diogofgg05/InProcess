# Atualizações por página e ícones — InProcess

Verificação local em 11 de novembro de 2026. Esta alteração reduz o trabalho da lista de processos quando outra página está selecionada e evita recalcular grupos quando chegam apenas ícones.

## Comportamento

- A recolha mantém o intervalo configurado. O histórico e o snapshot completo mais recente continuam disponíveis.
- Enquanto Processos está oculto, a página conserva as linhas mais recentes, sem atualizar/reordenar os modelos Qt em cada recolha.
- Ao regressar, aplica apenas o snapshot mais recente. Preserva filtros, pastas expandidas e a seleção de um processo que conserve PID e data de criação.
- Se o processo desaparecer ou o PID for reutilizado, a seleção anterior não passa automaticamente ao novo processo. Ações sobre a lista oculta não obtêm uma seleção antiga.
- Pedidos novos de extração de ícones só são iniciados com Processos selecionado. Um pedido já iniciado pode concluir em segundo plano.
- A aplicação de ícones notifica apenas a decoração da coluna Nome. Não recalcula filtros, totais ou ordenação dos grupos; respostas vazias não geram notificações.
- Ícones de tema disponíveis em Linux passam a notificar a lista quando são carregados.

Os diagnósticos distinguem `process_snapshot`, enquanto a lista está oculta, de `process_view`, durante a atualização visual. O custo de aplicar dados ao regressar aparece em `page_navigation`.

## Medições

`examples/benchmark_page_activity.py`: 600 processos sintéticos, dez grupos expandidos, ordenação por CPU e 40 atualizações por caso, usando Qt offscreen. Cada tempo inclui a operação e processamento de eventos Qt; geração dos registos/imagens fica fora do intervalo. O caso de ícones entrega 16 imagens geradas por atualização, sem extração nativa.

| Caso, mediana | Antes | Depois | Repetição depois |
|---|---:|---:|---:|
| Processos visível | 36,85 ms | 48,82 ms | 45,01 ms |
| Processos oculto | 16,18 ms | 0,21 ms | 0,25 ms |
| Entrega de ícones | 123,27 ms | 106,73 ms | 114,25 ms |
| Regresso/apresentação, uma observação por execução | 95,16 ms | 108,99 ms | 119,86 ms |

O trabalho repetido com a lista oculta caiu cerca de 98,7% no primeiro par de ensaios. Esse ganho tem um custo: a aplicação dos dados é feita ao regressar à página. Não se trata de aceleração da recolha de sensores ou de todo o programa.

Os tempos da lista visível ficaram mais altos nestas execuções, e a entrega de ícones teve uma melhoria mais modesta e variável. Os ensaios não isolam toda a carga exterior nem demonstram a causa dessa diferença na lista visível. A alteração não apresenta uma melhoria uniforme, nem uma garantia de redução do pior pico. A suíte verifica adicionalmente que uma atualização só de ícones não percorre novamente os filtros nem reconstrói os grupos.

Ficheiros brutos em `data/page-activity/`: `before-offscreen.json`, `after-offscreen.json`, `after-offscreen-repeat.json`. `before.json` é uma observação inicial com plataforma gráfica nativa, anterior ao registo explícito da plataforma no script; não entra na tabela nem nas percentagens. Os relatórios `windows-tests.xml` e `linux-tests.xml` guardam os resultados de regressão desta alteração.

Regressão: **403 testes aprovados em Windows** e **402 aprovados, um ignorado em Ubuntu/WSL**. Os seis novos casos cobrem as duas vistas ao adiar dados, seleção segura após reutilização de PID, chegada de ícones sem novo agrupamento e ligação efetiva destas regras à navegação da janela principal.

```powershell
$env:QT_QPA_PLATFORM='offscreen'
.\.venv\Scripts\python.exe examples\benchmark_page_activity.py --output data\page-activity\new-run.json
.\.venv\Scripts\python.exe -m pytest -q
```

As execuções de teste e benchmark são separadas. Os números anteriores permanecem guardados como observações da implementação anterior; executar o comando agora mede a versão atual.
