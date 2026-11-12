"""Generate a PDF of ACTUAL captured benchmark trials. Never invent measurements.

Example:
  python examples/report_benchmark73_pdf.py benchmarks/baseline.json \
      benchmarks/inprocess.json -o benchmarks/benchmark-results.pdf

Requires reportlab. Reports validation failures instead of fabricated ranks.
"""
import argparse
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,Paragraph,Table,TableStyle,Spacer,Flowable
)

from expecto_process_manager.optimization.benchmarks71 import BenchmarkTrial
from expecto_process_manager.optimization.statistics73 import analyse_benchmarks


class DurationBars(Flowable):
    def __init__(self,stats):
        Flowable.__init__(self)
        self.stats=stats
        self.width=480
        self.height=210

    def draw(self):
        c=self.canv
        c.setFont("Helvetica-Bold",11)
        c.drawString(5,195,"Medianas de duração da tarefa (segundos)")
        largest=max(stat.median_duration_s for stat in self.stats)
        x0,width=152,286
        for i,stat in enumerate(self.stats):
            y=162-i*35
            c.setFont("Helvetica",8)
            c.setFillColor(colors.HexColor("#34465A"))
            c.drawRightString(x0-8,y,stat.label.replace("_"," ")[:23])
            c.setFillColor(colors.HexColor("#2572D6"))
            c.rect(x0,y-2,width*stat.median_duration_s/max(largest,1e-12),
                   16,fill=1,stroke=0)
            c.setFillColor(colors.HexColor("#24364A"))
            c.drawString(x0+width*stat.median_duration_s/max(largest,1e-12)+4,
                         y+2,f"{stat.median_duration_s:.4f}")
        c.setFont("Helvetica",7)
        c.drawString(5,8,"Dados importados de ensaios JSON; sem inferência sobre potência elétrica.")


def build(inputs,output):
    trials=[]
    for filename in inputs:
        raw=json.loads(Path(filename).read_text(encoding="utf-8"))
        trials.extend(BenchmarkTrial(**row) for row in raw["trials"])
    study=analyse_benchmarks(trials)
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name="bx",parent=styles["BodyText"],
                              fontSize=9,leading=13,spaceAfter=8))
    styles.add(ParagraphStyle(name="bh",parent=styles["Heading2"],
                              textColor=colors.HexColor("#2465CF"),spaceAfter=8))
    story=[]
    def p(s):story.append(Paragraph(str(s),styles["bx"]))
    def h(s):story.append(Paragraph(s,styles["bh"]))
    story.append(Paragraph("InProcess 7.3 — Resultados experimentais",styles["Title"]))
    p("Relatório gerado apenas dos ensaios JSON fornecidos. Não demonstra "
      "eficiência energética, calibração dos sensores nem latência de cliques.")
    h("Rastreabilidade e comparação")
    p(f"Ficheiros de origem: {len(inputs)}; execuções: {len(trials)}.")
    p(f"Comparação metodologicamente admissível pelos filtros básicos: "
      f"<b>{study.comparable}</b>.")
    if study.reasons:
        p("Motivos de recusa: "+"; ".join(study.reasons))
    h("Duração e recursos do monitor")
    rows=[["Cenário","N","Mediana tarefa (s)","P95 tarefa (s)","CPU monitor (% núcleo)"]]
    for s in study.stats:
        rows.append([s.label,str(s.n),f"{s.median_duration_s:.4f}",
                     f"{s.p95_duration_s:.4f}",
                     "-" if s.median_observer_cpu_core_pct is None
                     else f"{s.median_observer_cpu_core_pct:.3f}"])
    if len(rows)==1:
        p("Sem ensaios válidos para estatísticas.")
    else:
        data=[[Paragraph(str(x),styles["bx"]) for x in row] for row in rows]
        table=Table(data,colWidths=[128,32,115,110,122],repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#E9F2FC")),
            ("GRID",(0,0),(-1,-1),.4,colors.HexColor("#CFDEEF")),
            ("VALIGN",(0,0),(-1,-1),"TOP")
        ]))
        story.append(table)
        story.append(Spacer(1,16))
        story.append(DurationBars(study.stats))
    h("Sobrecarga perante baseline")
    if not study.impacts:
        p("Não há impactos publicáveis: faltam ensaios comparáveis suficientes.")
    for r in study.impacts:
        p(f"{r.label}: diferença mediana {r.slowdown_pct:.3f}%; "
          f"intervalo bootstrap descritivo 95% "
          f"[{r.difference_ci95_pct[0]:.3f}%, {r.difference_ci95_pct[1]:.3f}%].")
    h("Limitações")
    p("O bootstrap não emparelhado não corrige mudanças de temperatura, "
      "carga concorrente ou diferentes sistemas operativos. O RSS é "
      "amostrado e pode contabilizar páginas partilhadas. A latência "
      "de input/renderização, potência elétrica e energia NÃO FORAM MEDIDAS "
      "pelo protocolo. Repetir e contrabalançar a ordem dos ensaios.")
    pdf=SimpleDocTemplate(str(output),pagesize=A4,
                          leftMargin=43,rightMargin=43,topMargin=48,bottomMargin=48,
                          title="InProcess 7.3 — Benchmark real")
    pdf.build(story)
    return output


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("trials",nargs="+",type=Path)
    parser.add_argument("-o","--output",type=Path,
                        default=Path("benchmarks/inprocess-real-results.pdf"))
    args=parser.parse_args()
    print(build(args.trials,args.output))
