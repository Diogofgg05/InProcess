"""InProcess Physics Lab 6.2 — conservative, explicit, transient 2-D heat.

Finite-volume, cell-centered discretization of
    rho*c*dT/dt = div(k*grad T) + q
on a thin rectangular plate. An optional central inclusion uses a separate
thermal conductivity and volumetric heat capacity. Internal face
conductances use harmonic-mean conductivity. External boundaries can be
Dirichlet (fixed ambient), convection (Robin, including half-cell series
resistance), or insulated (zero heat flux).

The timestep criterion is a conservative POSITIVITY/PASSIVITY bound:
    dt <= min_i(C_i / sum_j G_ij)
(including boundary conductance). It is stricter than some linear stability
bounds but prevents an explicit conduction step from overshooting solely due
to diffusion. This is SIMULATED hardware-inspired physics, never sensors.
"""
from dataclasses import dataclass, replace
from math import ceil, exp, fsum, hypot, isfinite, pi, sin, sqrt
from typing import Literal


Boundary = Literal["dirichlet", "convection", "insulated"]


@dataclass(frozen=True)
class HeatPlate2D:
    length_x_m: float = .10
    length_y_m: float = .08
    thickness_m: float = .003
    nx: int = 25
    ny: int = 21
    matrix_k_w_m_k: float = 160.0
    inclusion_k_w_m_k: float = 18.0
    matrix_volumetric_capacity_j_m3_k: float = 2_400_000.0
    inclusion_volumetric_capacity_j_m3_k: float = 1_700_000.0
    inclusion: bool = True
    boundary: Boundary = "convection"
    convection_h_w_m2_k: float = 25.0
    ambient_c: float = 25.0
    initial_peak_c: float = 65.0
    source_w: float = 6.0

    def __post_init__(self):
        for name in ("length_x_m", "length_y_m", "thickness_m",
                     "matrix_k_w_m_k", "inclusion_k_w_m_k",
                     "matrix_volumetric_capacity_j_m3_k",
                     "inclusion_volumetric_capacity_j_m3_k"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value <= 0:
                raise ValueError(f"{name}: parâmetro físico positivo e finito obrigatório.")
        for name in ("ambient_c", "initial_peak_c", "convection_h_w_m2_k", "source_w"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
                raise ValueError(f"{name}: valor finito obrigatório.")
        if self.ambient_c < -273.15 or self.initial_peak_c < self.ambient_c:
            raise ValueError("Temperaturas abaixo do zero absoluto ou pico inferior ao ambiente.")
        if self.convection_h_w_m2_k < 0 or self.source_w < 0:
            raise ValueError("Convecção e fonte de calor não podem ser negativas.")
        if type(self.nx) is not int or type(self.ny) is not int or not (7 <= self.nx <= 81 and 7 <= self.ny <= 81):
            raise ValueError("Malha entre 7 e 81 células por direção.")
        if type(self.inclusion) is not bool or self.boundary not in ("dirichlet", "convection", "insulated"):
            raise ValueError("Configuração de material ou fronteira inválida.")

    @property
    def dx(self):
        return self.length_x_m / self.nx

    @property
    def dy(self):
        return self.length_y_m / self.ny

    @property
    def alpha_matrix(self):
        return self.matrix_k_w_m_k / self.matrix_volumetric_capacity_j_m3_k

    def exact(self, x_m: float, y_m: float, t_s: float) -> float:
        """Continuum single-sine eigenmode, for homogeneous/no-source/Dirichlet."""
        if self.inclusion or self.source_w != 0 or self.boundary != "dirichlet":
            raise ValueError("Referência analítica só para material uniforme, sem fonte e com Dirichlet.")
        if not (0 <= x_m <= self.length_x_m and 0 <= y_m <= self.length_y_m and t_s >= 0):
            raise ValueError("Coordenadas ou tempo fora do domínio.")
        if not all(isfinite(v) for v in (x_m, y_m, t_s)):
            raise ValueError("Coordenadas ou tempo não finitos.")
        return (self.ambient_c + (self.initial_peak_c-self.ambient_c)
                * sin(pi*x_m/self.length_x_m)*sin(pi*y_m/self.length_y_m)
                * exp(-self.alpha_matrix*pi*pi
                      * (1/self.length_x_m**2+1/self.length_y_m**2)*t_s))


@dataclass(frozen=True)
class HeatFieldResult:
    times_s: tuple[float, ...]
    frames_c: tuple[tuple[tuple[float, ...], ...], ...]  # frame[row_y][column_x]
    dx_m: float
    dy_m: float
    dt_s: float
    conservative_limit_s: float
    fourier_x: float
    fourier_y: float
    initial_j: float
    final_j: float
    heat_input_j: float
    boundary_loss_j: float
    balance_residual_j: float
    min_c: float
    max_c: float
    rmse_exact_c: float | None
    origin: str = "SIMULATED"


def _harmonic(a, b):
    return 2*a*b/(a+b)


def _network(model: HeatPlate2D):
    nx, ny = model.nx, model.ny
    dx, dy, depth = model.dx, model.dy, model.thickness_m
    size = nx*ny
    k = [0.0]*size
    cap = [0.0]*size
    sources = [0.0]*size
    hot = []

    for j in range(ny):
        y = (j+.5)/ny
        for i in range(nx):
            x = (i+.5)/nx
            pos = j*nx+i
            insert = model.inclusion and .32 <= x <= .68 and .30 <= y <= .70
            conductivity = model.inclusion_k_w_m_k if insert else model.matrix_k_w_m_k
            volumetric_capacity = (model.inclusion_volumetric_capacity_j_m3_k if insert
                                   else model.matrix_volumetric_capacity_j_m3_k)
            k[pos] = conductivity
            cap[pos] = volumetric_capacity*dx*dy*depth
            if .42 <= x <= .58 and .40 <= y <= .60:
                hot.append(pos)
    if not hot:
        hot=[(ny//2)*nx+(nx//2)]
    for pos in hot:
        sources[pos] = model.source_w/len(hot)

    neighbors = [[] for _ in range(size)]
    boundary_g = [0.0]*size
    vertical_face = depth*dy
    horizontal_face = depth*dx

    def edge(i, j, area, distance):
        g = _harmonic(k[i],k[j])*area/distance
        neighbors[i].append((j,g))
        neighbors[j].append((i,g))

    for j in range(ny):
        for i in range(nx):
            pos=j*nx+i
            if i+1<nx:
                edge(pos,pos+1,vertical_face,dx)
            if j+1<ny:
                edge(pos,pos+nx,horizontal_face,dy)

            def conductance(area, half_dx):
                if model.boundary == "insulated":
                    return 0.0
                if model.boundary == "dirichlet":
                    return k[pos]*area/half_dx
                if model.convection_h_w_m2_k == 0:
                    return 0.0
                return area/(half_dx/k[pos]+1/model.convection_h_w_m2_k)

            if i==0:
                boundary_g[pos] += conductance(vertical_face,dx/2)
            if i==nx-1:
                boundary_g[pos] += conductance(vertical_face,dx/2)
            if j==0:
                boundary_g[pos] += conductance(horizontal_face,dy/2)
            if j==ny-1:
                boundary_g[pos] += conductance(horizontal_face,dy/2)

    limit = min(
        cap[p]/(sum(g for _,g in neighbors[p])+boundary_g[p])
        for p in range(size)
    )
    return neighbors, boundary_g, cap, sources, limit


def solve_heat_2d(model: HeatPlate2D | None = None, *, duration_s: float = 6.0,
                  dt_s: float | None = None, token=None) -> HeatFieldResult:
    model = model if model is not None else HeatPlate2D()
    if (isinstance(duration_s, bool) or not isinstance(duration_s,(int,float))
            or not isfinite(duration_s) or duration_s<=0):
        raise ValueError("Duração positiva e finita obrigatória.")
    neighbors,boundary_g,capacity,sources,limit = _network(model)
    requested = limit*.85 if dt_s is None else dt_s
    if (isinstance(requested,bool) or not isinstance(requested,(int,float))
            or not isfinite(requested) or requested<=0):
        raise ValueError("Passo temporal positivo e finito obrigatório.")
    if requested > limit*(1+1e-12):
        raise ValueError("Passo térmico 2D viola o limite explícito de monotonicidade.")
    steps = ceil(duration_s/requested)
    cells=model.nx*model.ny
    if steps>30000 or steps*cells>2_500_000:
        raise ValueError("Orçamento de tempo/malha excedido; reduza duração ou resolução.")
    h = duration_s/steps
    ta = model.ambient_c
    state = [
        ta+(model.initial_peak_c-ta)*sin(pi*(i+.5)/model.nx)*sin(pi*(j+.5)/model.ny)
        for j in range(model.ny) for i in range(model.nx)
    ]
    initial_j = fsum(c*(value-ta) for c,value in zip(capacity,state))
    loss_j = 0.0
    input_j = 0.0
    time_samples=[0.0]
    stride=max(1,ceil(steps/24))

    def grid_flat(values):
        return tuple(tuple(values[j*model.nx:(j+1)*model.nx]) for j in range(model.ny))

    frames=[grid_flat(state)]
    for step in range(1,steps+1):
        if token is not None and step%32==0:
            token.check()
        loss_j += h*fsum(g*(state[p]-ta) for p,g in enumerate(boundary_g))
        input_j += h*fsum(sources)
        nxt = []
        for pos,temp in enumerate(state):
            flow = fsum(g*(state[other]-temp) for other,g in neighbors[pos])
            flow -= boundary_g[pos]*(temp-ta)
            flow += sources[pos]
            new_temp = temp+h*flow/capacity[pos]
            if not isfinite(new_temp) or new_temp < -273.15:
                raise ValueError("Temperatura simulada divergente ou inferior ao zero absoluto.")
            nxt.append(new_temp)
        state=nxt
        if step==steps or step%stride==0:
            time_samples.append(h*step)
            frames.append(grid_flat(state))
    if token is not None:
        token.check()
    final_j = fsum(c*(value-ta) for c,value in zip(capacity,state))
    exact_errors = None
    if not model.inclusion and model.source_w==0 and model.boundary=="dirichlet":
        err = [
            (state[j*model.nx+i] -
             model.exact((i+.5)*model.dx,(j+.5)*model.dy,duration_s))
            for j in range(model.ny) for i in range(model.nx)
        ]
        exact_errors = sqrt(fsum(e*e for e in err)/len(err))
    minimum=min(min(row) for frame in frames for row in frame)
    maximum=max(max(row) for frame in frames for row in frame)
    return HeatFieldResult(
        tuple(time_samples),tuple(frames),model.dx,model.dy,h,limit,
        model.alpha_matrix*h/model.dx**2,model.alpha_matrix*h/model.dy**2,
        initial_j,final_j,input_j,loss_j,
        final_j-initial_j-input_j+loss_j,
        minimum,maximum,exact_errors,
    )


def heat_2d_grid_study(model: HeatPlate2D | None = None, *, duration_s=2.0,
                       token=None) -> list[dict]:
    """Grid-refinement RMSE for analytically supported uniform Dirichlet case.

    Repeats nx,ny=9,13,17,25 and uses 0.5 of the conservative time limit.
    Both spatial and temporal errors change, so no standalone spatial order
    is claimed. Results are convergence evidence, not physical validation.
    """
    base=model if model is not None else HeatPlate2D()
    comparison = replace(base,inclusion=False,source_w=0.,boundary="dirichlet")
    rows=[]
    for n in (9,13,17,25):
        if token is not None: token.check()
        trial=replace(comparison,nx=n,ny=n)
        out=solve_heat_2d(trial,duration_s=duration_s,
                          dt_s=None,token=token)
        rows.append({
            "nx":n,"ny":n,"dx_m":out.dx_m,"dy_m":out.dy_m,
            "dt_s":out.dt_s, "rmse_c":out.rmse_exact_c,
            "energy_balance_j":out.balance_residual_j,
        })
    return rows
