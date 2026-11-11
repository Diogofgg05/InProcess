# Defesa oral — 10 minutos

O relatório executável está em `reports/academic-final.html`. Regenerar com `.venv\Scripts\python examples\generate_academic_report.py`; o gerador não abre Qt nem recolhe hardware. As oito experiências físicas são sintéticas. O inventário anterior de hardware e os tempos reais de execução das chamadas estão identificados separadamente. Não há resultados instrumentais de potência ou temperatura nem poupanças reais demonstradas.

## 0:00–1:00 — Questão e âmbito

“Pretendo estudar se modelos térmicos e integração da potência permitem comparar energia para a mesma tarefa. A entrega verifica a biblioteca com referências conhecidas. A aplicação ao computador real precisa ainda de instrumentação e validação independente.”

Apresentar H1–H5 da secção 4. H2 e a componente algorítmica de H3 têm evidência matemática; H1, H4 e H5 não têm confirmação experimental neste PC. Uma classificação depende da avaliação e da grelha oficial, que não foi fornecida.

## 1:00–2:15 — Dedução física

Escrever de memória: acumulação = entrada − dissipação. Com `dU=C dT` e dissipação linear, `C T′ = Pth − k(T−Ta)`. Mostrar as unidades: `(J/K)(K/s)=W`. Explicar o nó concentrado e a temperatura representativa. `Pth` é potência térmica assumida; CPU% e TDP não são um wattímetro.

Derivar `θ=T−Ta−Pth/k`, depois `θ′=−(k/C)θ`. Daí `T=Teq+(T0−Teq)e^(−t/τ)`, `Teq=Ta+Pth/k` e `τ=C/k`. No ensaio principal, Teq=44,5 °C e τ=50 s, por escolha dos parâmetros.

## 2:15–3:30 — Euler, Heun e RK4

Escrever `T[n+1]=T[n]+h(Pth−k(T[n]−Ta))/C`. Explicar que o código calcula os estágios diretamente, conserva todos os estados e encurta o último intervalo.

Mostrar a experiência 1. Euler usa uma inclinação, Heun duas e RK4 quatro. Mostrar a experiência 3 e explicar as ordens observadas e os limites de arredondamento. Os custos em ms são chamadas realmente cronometradas, sem repetição estatística; não são medidas de energia.

## 3:30–4:15 — Estabilidade e arrefecimento

Para `θ′=−aθ`, Euler tem fator `R=1−ah`. Exigir `|R|<1`, obtendo `0<h<2C/k`. Para os parâmetros principais, a fronteira é 100 s; estabilidade não garante precisão. Não confundir h interno com intervalo dos sensores.

Na experiência 2, duplicar C duplica τ; duplicar k reduz τ a metade. Alterar Ta muda o equilíbrio. Não se inferiu uma relação entre RPM e k nem se controlaram ventoinhas.

## 4:15–5:15 — Energia, quadraturas e perfis

Escrever `E=∫Pdt`, `1 Wh=3600 J` e `eficiência=trabalho concluído/E`. Mostrar 50 W × 10 s = 500 J e a integral de x². O ponto médio usa amostras no meio; Simpson exige espaçamento uniforme e número par de intervalos.

Mostrar a experiência 7: NORMAL 600 J em 10 s; ECO 675 J em 15 s apesar dos 45 W; ULTRA ECO 500 J em 20 s. Com prazo de 18 s, ULTRA ECO não é admissível. Dizer claramente que são cenários sintéticos e que o sistema operativo não foi alterado.

## 5:15–6:15 — Ruído e derivadas

Mostrar a experiência 5 com semente 42. Para ruído independente de desvio σ, a derivada centrada tem desvio `σ/(√2 h)`. A segunda derivada amplifica por `1/h²`. Derivar esta expressão pela soma das variâncias de duas amostras independentes.

A média móvel reduz variância neste ensaio, mas pode distorcer transientes; a versão centrada não é causal e usa dados futuros. Comparar sempre as mesmas amostras interiores, explicitando as bordas excluídas.

## 6:15–7:15 — Calibração e identificabilidade

Mostrar a experiência 6. Os parâmetros são ESTIMATED a partir de entrada SIMULATED. O treino e o holdout não partilham amostras nem intervalos; a temperatura inicial de cada janela é fornecida e excluída das métricas.

Explicar a matriz de sensibilidade em log(C), log(k), o seu condicionamento e a rejeição do arrefecimento com P=0: apenas k/C pode ser identificado. Recuperar C=100 e k=2 do mesmo modelo gerador verifica o estimador e não calibra o CPU real.

## 7:15–8:00 — Conservação no sistema CPU/GPU

Mostrar as duas equações e cancelar `−kcg(Tc−Tg)` com `+kcg(Tc−Tg)`. O acoplamento transfere energia internamente. O resíduo `Eentrada−Eambiente−ΔU` mede consistência do sistema integrado.

Explicar que um resíduo pequeno não prova exatidão independente: as energias usam os mesmos estágios da EDO. As curvas sem acoplamento só são referência exata quando kcg=0.

## 8:00–9:00 — Evidência e limitações

Mostrar a distinção entre inventário de hardware, medições de tempo de execução, dados físicos sintéticos e medições físicas ausentes. Modelo de CPU, GPU, RAM ou frequência não fornece potência térmica calibrada.

Apresentar a matriz provisória da secção 18. Não é uma grelha oficial. Não afirmar aprovação de testes que não tenham sido executados: o gerador executa as verificações A–I; a suite completa exige `python -m pytest` e o respetivo resultado real.

## 9:00–10:00 — Conclusão e próxima experiência

“O contributo demonstrado é uma biblioteca matemática executável, com referências analíticas, validação e relatórios reproduzíveis. A próxima experiência mede a mesma tarefa e fronteira de potência em condições controladas, regista ambiente e incerteza, repete os perfis e reserva sessões independentes para validar o modelo.”

Não prometer poupança, segurança térmica ou classificação. Se faltar tempo, preservar a dedução física, a validação de Euler e a distinção entre simulação e medição.

## Perguntas críticas para ensaiar

1. **Por que razão C tem unidade J/K?** Porque é a variação de energia interna por variação de temperatura na aproximação adotada; inclui componentes efetivos do conjunto térmico, sem corresponder automaticamente à massa do chip.
2. **É possível usar percentagem de CPU como potência?** Apenas num modelo explicitamente estimado e calibrado; não como medição elétrica nem térmica.
3. **RK4 é sempre melhor?** Tem ordem superior em problemas suaves, mas custa mais por passo, não elimina ruído, erros de modelo ou limitações de estabilidade e pode atingir arredondamento.
4. **Um passo mais pequeno melhora um sensor?** Não. h numérico e amostragem física são conceitos distintos; diferenciar dados mais próximos pode amplificar ruído.
5. **Por que não aplicar Simpson a qualquer CSV?** A fórmula composta usada pressupõe intervalos uniformes e número par; reamostrar acrescentaria hipóteses que teriam de ser declaradas.
6. **Um holdout sintético valida o hardware?** Não. Verifica previsão no domínio do gerador; exige-se instrumentação e novas sessões físicas para validar o computador.
7. **Por que não separar C e k em arrefecimento livre?** Com P=0, a curva depende apenas de k/C; há infinitos pares com a mesma constante de tempo.
8. **Menos watts significa poupança?** Depende da duração e do trabalho concluído. O critério é a integral em joules para a mesma tarefa e restrições.
9. **Um balanço de energia com resíduo zero demonstra temperaturas corretas?** Não quando os fluxos e estados são integrados conjuntamente; é consistência algébrica, que deve ser complementada por referência independente e convergência.
10. **O que falta para concluir H1/H4/H5 sobre este PC?** Potência e temperatura sincronizadas, fronteira de medição, ambiente, carga equivalente, repetições, incerteza e validação reservada.
