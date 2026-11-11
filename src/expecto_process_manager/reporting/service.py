from dataclasses import dataclass
from pathlib import Path
from .context import experiment_metadata
from .render import save_report,render_report
from .thermal_report import thermal_report
import json


@dataclass(frozen=True)
class GeneratedReport:
    path: str
    preview_html: str
    title: str


def generate_report(kind,result,context,output_directory,token):
    token.check()
    if kind=='thermal':
        report=thermal_report(result)
    elif kind=='numerical':
        from .numerical_report import numerical_report
        report=numerical_report(result,context)
    else:
        from .model_reports import gravity_report,free_fall_report,energy_report,calibration_report,coupled_report
        builders={'gravity':gravity_report,'free-fall':free_fall_report,'energy':energy_report,
                  'calibration':calibration_report,'coupled':coupled_report}
        if kind not in builders: raise ValueError('Tipo de relatório desconhecido.')
        report=builders[kind](result,context)
    report.metadata.update(experiment_metadata(context.get('metadata',{})))
    path=save_report(Path(output_directory)/f'latest-{kind}.html',report,token)
    token.check()
    return GeneratedReport(path,render_report(report,figures=False),report.title)


def generate_university_report(output_directory,token):
    from .academic import generate_academic_report
    from ..core.hardware import get_cached_hardware
    directory=Path(output_directory)
    directory.mkdir(parents=True,exist_ok=True)
    hardware=get_cached_hardware()
    hardware_path=None
    if hardware:
        hardware_path=directory/'hardware-context.json'
        hardware_path.write_text(json.dumps(hardware.as_dict(),ensure_ascii=False,indent=2),encoding='utf-8')
    token.check()
    return generate_academic_report(directory/'academic-final.html',hardware_path,token)
