"""Ten priority experiments with verifiable checks and offline artifacts.

No sensor readings, OS actions, microphone access or hardware probing.
"""
from dataclasses import asdict
from html import escape
import json
import math
from pathlib import Path
from time import perf_counter

from .document import Curve,Figure
from .render import CSS,figure_html,save_report
from .thermal_report import thermal_report
from ..core.cancellation import Cancellation
from ..physics.calibration import fit_thermal,predict_zoh
from ..physics.cooling import simulate_cooling
from ..physics.numerical.derivatives import differentiate
from ..physics.numerical.integration import quadrature
from ..physics.numerical.signals import add_gaussian_noise,moving_average
from ..physics.numerical.validation import metrics,convergence_study
from ..physics.numerical.ode import solve_ivp
from ..physics.hardware_models import RCCircuit
from ..optimization.eco import compare_policies,synthetic_policy_runs
from ..simulation.experiments import ExperimentConfig,run_experiment,save_experiment
from ..simulation.hardware_experiments import HardwareConfig,run_hardware,export_hardware


def generate_physical_suite(directory,token=None):
    token=token or Cancellation()
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    token.check()
    sections,records=[],[]
    def add(number,title,parameters,results,checks,text,figures=(),link=None):
        token.check()
        if not all(checks.values()): raise ValueError(f'Experiência {number}: falhou uma verificação: {checks}')
        records.append(dict(number=number,title=title,origin='SIMULATED',parameters=parameters,results=results,checks=checks))
        sections.append(f'<section><h2>{number}. {escape(title)}</h2><p>SIMULATED · validação numérica/sintética</p><pre>'+escape(text)+'</pre>'+''.join(figure_html(f) for f in figures)+
                        ('<p><a href="'+escape(link,quote=True)+'">Relatório e gráficos completos</a></p>' if link else '')+'</section>')

    config=ExperimentConfig(initial=30,ambient=25,power=45,capacity=180,dissipation=1.2,duration=120,dt=1,noise=.2,seed=42)
    thermal=run_experiment(config,token)
    save_experiment(str(directory/'cpu.json'),thermal,token)
    save_report(directory/'cpu.html',thermal_report(thermal),token)
    reference=62.5-32.5*math.exp(-.8)
    add(1,'Aquecimento do CPU',asdict(config),dict(equilibrium_c=62.5,time_constant_s=150,reference_120s_c=reference,
        errors=thermal.method_errors),dict(reference=abs(thermal.simulation.reference[-1]-reference)<1e-10,
        method_order=thermal.method_errors['RK4']['rmse']<thermal.method_errors['Heun']['rmse']<thermal.method_errors['Euler']['rmse']),
        thermal.report,link='cpu.html')

    cooling_curves,cooling_results=[],[]
    for k,ambient,color in ((1.2,25,'#2176c1'),(2.4,25,'#9756b6'),(1.2,30,'#1c946b')):
        r=simulate_cooling(60,ambient,180,k,0,0,120,.5,token)
        cooling_results.append(dict(dissipation_w_k=k,ambient_c=ambient,final_c=r.temperatures['RK4'][-1],
                                    rmse_c=metrics(r.temperatures['RK4'],r.reference)['rmse']))
        cooling_curves.append(Curve(f'k={k} W/K; Ta={ambient} °C',r.times,r.temperatures['RK4'],color))
    add(2,'Dissipação térmica',dict(initial_c=60,capacity_j_k=180,power_w=0,duration_s=120,dt_s=.5),cooling_results,
        dict(cooling_gain=cooling_results[1]['final_c']<cooling_results[0]['final_c'],
             ambient_effect=cooling_results[2]['final_c']>cooling_results[0]['final_c'],
             analytical_errors=all(row['rmse_c']<1e-8 for row in cooling_results)),
        'C T′=−k(T−Ta). Aumentar k reduz τ=C/k; aumentar Ta reduz o potencial de arrefecimento. Coeficientes hipotéticos, não inferidos de RPM.',
        [Figure('Sensibilidade a k e Ta','Tempo (s)','°C',cooling_curves)])

    times=[i/10 for i in range(101)]
    energies={m:quadrature(times,[50]*101,m) for m in ('left','right','trapezoid','simpson')}
    add(3,'Energia consumida',dict(power_w=50,duration_s=10,dt_s=.1),energies,
        dict(constant_power=all(abs(v-500)<1e-10 for v in energies.values()),polynomial=abs(quadrature([0,.5,1],[0,.25,1],'simpson')-1/3)<1e-14),
        'E=∫Pdt; P=dE/dt. 50 W × 10 s = 500 J = 0,1388889 Wh. Para tarefa equivalente, 40 W × 20 s = 800 J: menor potência pode aumentar energia.\n'+json.dumps(energies))

    for number,key,title in ((4,'rc','Circuito RC'),(5,'rotor','Motor da ventoinha · rotação'),
                             (6,'vibration','Vibração amortecida'),(7,'forced','Ressonância')):
        r=run_hardware(HardwareConfig(key),token)
        export_hardware(r,directory,token)
        checks={'finite_results':all(math.isfinite(o[r.metadata['primary']]) for o in r.observables['rk4'])}
        if r.errors: checks['rk4_reference']=r.errors['rk4']['maximum']<1e-5
        if key=='vibration': checks['energy_decay']=r.observables['rk4'][-1]['stored_j']<r.observables['rk4'][0]['stored_j']
        if key=='forced':
            response=r.frequency_response
            peak_index=max(range(len(response['amplitude_m'])),key=lambda i:response['amplitude_m'][i] or 0)
            checks['peak']=abs(response['frequency_hz'][peak_index]-response['resonance_hz'])<response['natural_hz']/100
        add(number,title,r.metadata,dict(errors=r.errors,balances_j=r.balances,frequency_response=r.frequency_response),checks,r.report,link=key+'.html')

    t=[i*.01 for i in range(1001)]
    clean=[math.sin(2*math.pi*time) for time in t]
    noisy=add_gaussian_noise(clean,.02,42)
    target=[2*math.pi*math.cos(2*math.pi*time) for time in t]
    dclean,dnoisy,dfiltered=[differentiate(t,v) for v in (clean,noisy,moving_average(noisy,7))]
    noise_results={k:metrics(v,target) for k,v in (('clean',dclean),('noisy',dnoisy),('filtered',dfiltered))}
    add(8,'Ruído e derivadas',dict(dt_s=.01,sigma=.02,seed=42,window_samples=7),noise_results,
        dict(noise_amplification=noise_results['noisy']['rmse']>noise_results['clean']['rmse'],
             filtering=noise_results['filtered']['rmse']<noise_results['noisy']['rmse']),
        'Diferenciação central: variância de ruído σ²/(2h²). Média móvel reduz ruído e introduz viés/fase nas transições; janela de 7 pontos.\n'+
        json.dumps({k:{n:e[n] for n in ('mae','rmse','maximum')} for k,e in noise_results.items()}),
        [Figure('Ruído amplificado pela derivada','Tempo (s)','1/s',[Curve('Analítica',t,target),Curve('Derivada ruidosa',t,dnoisy,'#9756b6'),Curve('Derivada filtrada',t,dfiltered,'#1c946b')])])

    t=list(range(601)); powers=[45. if time<250 else 20. for time in t]
    temperatures=predict_zoh(t,powers,30,25,180,1.2)
    fit=fit_thermal(t,temperatures,powers,25,token=token)
    add(9,'Calibração térmica',dict(source='synthetic exact ZOH',capacity_j_k=180,dissipation_w_k=1.2,ambient_c=25,
        times_s=t,power_w=powers),asdict(fit),dict(capacity=abs(fit.capacity-180)<1e-3,
        dissipation=abs(fit.dissipation-1.2)<1e-5,holdout=fit.training.times[-1]<fit.validation.times[0],
        validation_rmse=fit.validation.errors['rmse']<1e-5),fit.report,
        [Figure('Validação temporal separada','Tempo (s)','°C',[
            Curve('Observação sintética',fit.validation.times,fit.validation.observed),Curve('Previsão',fit.validation.times,fit.validation.predicted,'#1c946b')])])

    comparison=compare_policies(synthetic_policy_runs())
    add(10,'ULTRA ECO · tarefas equivalentes',dict(source='synthetic_policy_runs'),
        dict(rows=[asdict(row) for row in comparison.rows],recommendation=comparison.recommendation),
        dict(comparable=comparison.comparable,energy_available=all(row.energy_j is not None for row in comparison.rows)),
        comparison.report+'\nNão altera perfis do SO. Previsões térmicas não calibradas não garantem segurança térmica.')

    # Bounded statistical timing: separate from graph rendering and file output.
    benchmark=[]
    model=RCCircuit()
    for method in ('euler','heun','rk4'):
        timings=[]
        for _ in range(3):
            start=perf_counter(); solve_ivp(model.rhs,0,(0,1),.001,method,token); timings.append(perf_counter()-start)
        rows=convergence_study(lambda h:solve_ivp(model.rhs,0,(0,1),h,method,token).values[-1][0],model.exact(1),[.2,.1,.05],token)
        benchmark.append(dict(method=method,seconds=timings,median_s=sorted(timings)[1],steps=1000,convergence=[asdict(row) for row in rows]))
    for key in ('rl','motor','feedback'):
        export_hardware(run_hardware(HardwareConfig(key),token),directory,token)
    payload=dict(model_version='5.0.0',origin='SIMULATED',experiments=records,benchmark=benchmark,
                 limitations='Sem validação experimental de sensores/hardware; tempos locais não medem energia do PC.')
    (directory/'physical-suite.json').write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
    html='<!doctype html><html lang="pt"><meta charset="utf-8"><title>InProcess · dez experiências físicas</title><style>'+CSS+'</style><body><main><h1>InProcess Physical Systems Lab 5.0</h1><p>Dez experiências reproduzíveis. Todas usam dados sintéticos. Verificações automáticas aprovadas; não constituem validação experimental do hardware.</p>'+''.join(sections)+'<h2>Convergência e benchmark</h2><pre>'+escape(json.dumps(benchmark,indent=2))+'</pre><p>RC com 1000 passos, três repetições por método; sem GUI ou I/O dentro do intervalo medido. Valores completos e metadados em physical-suite.json.</p></main></body></html>'
    target=directory/'physical-suite.html'
    target.write_text(html,encoding='utf-8')
    token.check()
    return target
