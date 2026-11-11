# Fundamentos científicos

A auditoria, matriz C1–C9, derivações dos circuitos/motores/vibrações/ondas, hipóteses e limites da versão 5.0 estão em [physical-lab-5.md](physical-lab-5.md). As APIs térmicas e numéricas descritas abaixo foram preservadas.

O modelo concentrado é `C dT/dt = P(t) − k(T − Ta)`. T e Ta em °C, C em J/°C, k em W/°C e P em W. Considera um único corpo de temperatura uniforme, ambiente constante, dissipação linear e parâmetros invariantes. Não modela controlo de ventoinhas, frequência/tensão, distribuição espacial ou resistência térmica variável.

Para potência constante, `Teq = Ta + P/k`, `τ = C/k` e `T(t) = Teq + (T0 − Teq) exp(−t/τ)`. O programa usa esta solução em cada intervalo para a mesma potência constante à esquerda usada por Euler. Nos cenários com saltos, a referência é exata para a força amostrada, não para saltos que ocorram no interior de um passo. O estudo de convergência usa potência constante para isolar o erro numérico.

Euler explícito: `T[n+1] = T[n] + h(P[n] − k(T[n] − Ta))/C`. O último intervalo pode ser menor para chegar à duração pedida. O fator de amplificação do erro é `1 − hk/C`, pelo que a estabilidade exige `0 < hk/C < 2`. Para resposta sem oscilações, `hk/C ≤ 1`. O erro global esperado é O(h), o local O(h²), em forçamentos suaves.

Erro absoluto: `|Tn − Tref|`. Erro relativo: `|Tn − Tref| / |Tref|`, indefinido para referência nula. A escala Celsius torna este erro dependente da origem; para interpretação física de erros relativos de temperatura usar Kelvin. RMSE: raiz da média dos quadrados das diferenças. RMSE entre duas soluções sintéticas valida o algoritmo, não a fidelidade física ao computador.

Derivação: diferenças centrais de segunda ordem no interior, com pesos de três pontos também válidos para passos não uniformes. As extremidades usam diferenças unilaterais de primeira ordem. Para h uniforme, `(T[i+1] − T[i−1])/(2h)`. Ruído independente de variância σ² produz variância `σ²/(2h²)` na derivada central. A média móvel de sete pontos reduz flutuações, mas pode distorcer transições e tem janelas assimétricas nos extremos. A largura física da janela depende do passo.

Energia: integral de P no tempo. Retângulos à esquerda (O(h)), trapézios (O(h²)) e Simpson composta (O(h⁴) para funções suficientemente suaves). Simpson só é aceite para intervalos uniformes em número par. Saltos invalidam as hipóteses de suavidade; trapézios/Simpson interpolam os valores adjacentes aos saltos, enquanto retângulos à esquerda correspondem ao forçamento retido usado na simulação. Energia acumulada nos gráficos usa trapézios; 1 Wh = 3600 J. Potência térmica e potência elétrica não são sinónimos sem hipóteses adicionais.

Os testes usam energia constante exata, integral de t² = 1/3 em [0,1], equilíbrio térmico, solução analítica e convergência de Euler. Não se apresentam observações sintéticas como medições. O CSV importado é de origem não verificada. Valores medidos de CPU/RAM não implicam que o modelo térmico tenha sido calibrado.
