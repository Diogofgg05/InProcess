"""Executable scientific validation, synthetic data and SI units only."""
from pathlib import Path
from expecto_process_manager.physics.gravity import GravityConfig,run_gravity,free_fall_euler
from expecto_process_manager.core.metrics import export_csv


def main():
    directory=Path('data')
    directory.mkdir(exist_ok=True)
    experiment=run_gravity(GravityConfig())
    (directory/'gravity-validation.txt').write_text(experiment.report,encoding='utf-8')
    result=free_fall_euler()
    rows=[dict(time_s=t,height_m=y,velocity_m_s=v,reference_height_m=ref,
               height_error_m=abs(y-ref),provenance='simulado')
          for t,y,v,ref in zip(result.times,result.heights,result.velocities,result.reference_heights)]
    export_csv(directory/'free-fall-example.csv',rows)
    maximum=max(row['height_error_m'] for row in rows)
    print('Dados simulados: relatório orbital em data/gravity-validation.txt')
    print(f'Queda livre: erro máximo {maximum:.9g} m; previsão g*T*dt/2 = {9.80665*4*.01/2:.9g} m')
    print('CSV completo em data/free-fall-example.csv')


if __name__=='__main__': main()
