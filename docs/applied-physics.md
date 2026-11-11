# Exemplos académicos: movimento e compressor

Estes módulos são exemplos independentes da monitorização e não participam na escolha de perfis energéticos. Não controlam dispositivos físicos nem o sistema operativo.

## Movimento AGV

`physics.motion.run_motion(MotionConfig(...))` compara Euler, Heun e RK4 para `x'=v` e `v'=a−b−c v`. As unidades são m, s, m/s, m/s² e s⁻¹ para o atrito linear `c`. Não se trata de um coeficiente de atrito de Coulomb.

A velocidade inicial é não negativa. Uma travagem que chega a zero é localizada dentro do passo por bisseção do avanço numérico; a posição deixa de evoluir nesse instante. A distância de Euler mantém o respetivo erro e não é substituída pela solução exata. Há uma referência analítica independente para aceleração constante, incluindo atrito linear. A condição `dt*c<=1` preserva a velocidade não negativa em Euler; o máximo é 100 000 intervalos.

O resultado disponibiliza `times`, `trajectories`, `reference` e `report`. Cada trajetória contém posições, velocidades, acelerações e, quando ocorre durante a experiência, o tempo e a distância de paragem. Dados simulados não demonstram o desempenho de travagem de um veículo real.

## Compressor

`physics.thermodynamics.analyze_compression(volumes, pressures)` preserva a ordem das amostras. O trabalho pelo gás é `∫p dV` e o trabalho sobre o gás tem o sinal oposto. Volumes em m³ e pressões absolutas em Pa devem ser positivos e finitos. Os trapézios aceitam ramos crescentes, decrescentes ou ciclos. Não se ordenam os volumes, porque isso destruiria o ciclo.

Simpson requer um ramo estritamente monotónico, passo uniforme e número par de intervalos. Um ajuste global `log p = log K − n log V` requer pelo menos três pontos de um único ramo monotónico e bem condicionado. O RMSE é calculado em Pa após o ajuste no domínio logarítmico. Ciclos mantêm o trabalho assinado e não recebem um ajuste global automático.

As referências isotérmica e adiabática reversível são ancoradas no primeiro ponto, pressupõem gás ideal e massa fixa; a referência adiabática usa `gamma=1.4` explicitamente. Não são medições nem uma descrição garantida de um compressor real.

`import_compression_csv(path)` requer exatamente os cabeçalhos `volume_m3,pressure_pa`. O ficheiro deve usar separador vírgula e ponto decimal, até 16 MiB e 100 001 amostras. A origem importada permanece não verificada. `synthetic_compression()` fornece dados explicitamente simulados.

## Verificação

Executar `python -m pytest tests/test_applied_physics.py`. Os testes cobrem o evento de paragem, convergência de Euler, referência com atrito, integração com sinal, Simpson, recuperação de expoente politrópico, ciclos, dados inválidos, importação SI e cancelamento. Não há validação experimental de um AGV ou compressor físico.
