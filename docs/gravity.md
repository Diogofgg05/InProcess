# Laboratório gravitacional

Este módulo é independente de sensores e da interface. Todos os resultados são simulados e usam unidades SI: posição em m, tempo em s, massa em kg, velocidade em m/s, energia em J e momento angular em kg·m²/s. `G = 6,67430×10⁻¹¹ m³ kg⁻¹ s⁻²` é tratado como constante, sem propagação da sua incerteza.

## Modelo e hipóteses

Um corpo de teste move-se no plano em torno de uma massa central **pontual e fixa**:

`r'' = −GM r / |r|³`.

A condição inicial é `r(0)=(R,0)` e `v(0)=(0, f√(GM/R))`, onde f é o fator de velocidade. A massa do corpo não altera a aceleração; multiplica a energia e o momento angular apresentados. Não se modelam recuo da massa central, atmosfera, relatividade, colisões físicas ou uma superfície terrestre. Para massas comparáveis é necessário um modelo baricêntrico de dois corpos.

O raio não é uma altitude: é a distância ao ponto central. Os valores predefinidos de massa e raio são ilustrativos de uma órbita terrestre idealizada, não dados experimentais do computador.

## Métodos comparados

- **Euler explícito:** `r[n+1]=r[n]+h v[n]`, `v[n+1]=v[n]+h a(r[n])`. É de primeira ordem e pode ganhar energia secularmente, fazendo crescer a órbita.
- **Euler simplético (kick-drift):** `v[n+1]=v[n]+h a(r[n])`, `r[n+1]=r[n]+h v[n+1]`. É de primeira ordem; a atualização central conserva Lz até arredondamento, embora a energia não seja exatamente conservada.
- **Velocity Verlet:** `r[n+1]=r[n]+h v[n]+h² a[n]/2`, `v[n+1]=v[n]+h(a[n]+a[n+1])/2`. É de segunda ordem para a força suave. Com passo adequado, apresenta tipicamente erro de energia limitado/oscilatório, mas isso não é uma garantia para passos grandes ou encontros próximos.

O último intervalo é encurtado para terminar na duração pedida. Um máximo de 100 000 passos limita o custo; esse limite não certifica estabilidade ou resolução física. O algoritmo rejeita estados não finitos e passos que atinjam ou atravessem a vizinhança numérica da singularidade central. Essa proteção não representa colisão com uma superfície.

Quando o passo nominal excede a duração, o estudo de convergência começa no passo efetivo igual à duração, para que os refinamentos alterem realmente a malha. A ordem não é estimada quando o RMSE fica abaixo de uma tolerância conservadora de arredondamento relativa ao raio inicial.

## Diagnósticos e referência

`E = m|v|²/2 − GMm/r`, `Lz = m(x vy − y vx)`.

São apresentados os desvios em relação aos valores iniciais. O erro relativo de energia é indefinido quando E₀ é nula ou numericamente próxima de zero; não deve ser substituído por zero. Para `f=1`, a solução circular independente é `x=R cos(ωt)`, `y=R sin(ωt)`, `ω=√(GM/R³)`. Nesse caso existe RMSE de posição contra a referência e estudo de convergência em h, h/2 e h/4. Os refinamentos automáticos são omitidos se excederem 20 000 passos cada; a trajetória principal mantém o limite de 100 000.

Fora de `f=1`, o programa apresenta conservação de energia/momento angular, mas **não** compara a posição com uma órbita circular incorreta e não declara erro contra uma solução exata que não calculou. Uma órbita elíptica, parabólica ou hiperbólica pode ser fisicamente adequada conforme a energia, mas o passo deve resolver a passagem pelo periastro.

## Queda livre uniforme

`free_fall_euler()` implementa Euler explícito com `y` positivo para cima, `v'=-g` e `y'=v`. A referência é `y(t)=y₀+v₀t−gt²/2`, `v(t)=v₀−gt`, válida para g constante e sem resistência do ar. Não há solo ou impacto: y negativa significa uma coordenada abaixo de y=0. Para passos uniformes, o erro final de posição de Euler é `+g T h/2`, enquanto a velocidade fica exata até arredondamento.

## API

```python
from expecto_process_manager.physics.gravity import GravityConfig, run_gravity, free_fall_euler

experiment = run_gravity(GravityConfig(dt=10, duration=10800))
print(experiment.report)
verlet = experiment.trajectories['Velocity Verlet']
fall = free_fall_euler(height=100, duration=4, dt=.01)
```

Os testes comparam referências independentes, ordens de convergência de aproximadamente 1/1/2, conservação de momento angular, erro de energia, singularidade, parâmetros inválidos, cancelamento e independência da trajetória face à massa do corpo de teste. Estes testes validam a implementação numérica, não constituem validação experimental de um sistema físico real.
