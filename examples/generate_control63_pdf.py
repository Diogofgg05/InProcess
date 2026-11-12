"""Reproducible academic report for InProcess 6.3 (SIMULATED).

Run with PYTHONPATH=src and reportlab installed. All data are generated
from the same P/PI/PID plant; no energy or fan measurements are claimed.
"""
from pathlib import Path
import argparse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,Flowable

from expecto_process_manager.physics.control_lab63 import (
    ControlScenario,compare_controllers,gain_sensitivity,
)

DARK=colors.HexColor("#17263E")
BLUE=colors.HexColor("#2468CF")
TEAL=colors.HexColor("#008B84")
PURPLE=colors.HexColor("#9452D7")
MUTED=colors.HexColor("#53647B")


class ControlChart(Flowable):
    def __init__(self,series,title,ylabel):
        Flowable.__init__(self)
        self.series,self.title,self.ylabel=series,title,ylabel
        self.width=470
        self.height=200

    def draw(self):
        c=self.canv
        x0,y0,w,h=48,28,380,120
        xx=[t for name,points,color in self.series for t,v in points]
        yy=[v for name,points,color in self.series for t,v in points]
        xmin,xmax=min(xx),max(xx)
        ymin,ymax=min(yy),max(yy)
        pad=max((ymax-ymin)*.07,.01)
        ymin-=pad
        ymax+=pad
        c.setFont("Helvetica-Bold",10)
        c.setFillColor(DARK)
        c.drawString(4,185,self.title)
        c.setFont("Helvetica",7)
        for n in range(5):
            y=y0+n*h/4
            c.setStrokeColor(colors.HexColor("#DCE4EE"))
            c.line(x0,y,x0+w,y)
            c.setFillColor(MUTED)
            c.drawRightString(x0-4,y-2,f"{ymin+(ymax-ymin)*n/4:.2f}")
        c.setStrokeColor(MUTED)
        c.line(x0,y0,x0+w,y0)
        c.line(x0,y0,x0,y0+h)
        c.setFillColor(MUTED)
        c.drawCentredString(x0+w/2,9,"Tempo (s)")
        for idx,(name,samples,color) in enumerate(self.series):
            c.setStrokeColor(color)
            c.setLineWidth(1.45)
            path=c.beginPath()
            # <= 1500 points per line; downsample only for rendering.
            stride=max(1,len(samples)//900)
            for j,(t,v) in enumerate(samples[::stride]):
                px=x0+w*(t-xmin)/(xmax-xmin or 1)
                py=y0+h*(v-ymin)/(ymax-ymin)
                if j==0:path.moveTo(px,py)
                else:path.lineTo(px,py)
            c.drawPath(path)
            c.setFont("Helvetica",8)
            c.setFillColor(color)
            c.drawString(18+idx*145,165,name)


def build(output):
    scenario=ControlScenario()
    results=compare_controllers(scenario)
    sensitivity=gain_sensitivity(scenario)
    assert all(abs(r.metrics.energy_balance_residual_j)<1e-6 for r in results.values())
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name="cTitle",parent=styles["Title"],fontSize=22,leading=27,
                              textColor=DARK,spaceAfter=18))
    styles.add(ParagraphStyle(name="cHead",parent=styles["Heading2"],fontSize=13,leading=18,
                              textColor=BLUE,spaceBefore=11,spaceAfter=8))
    styles.add(ParagraphStyle(name="cText",parent=styles["BodyText"],fontSize=9.1,leading=13.3,
                              textColor=DARK,spaceAfter=9))
    styles.add(ParagraphStyle(name="cEq",parent=styles["BodyText"],fontName="Courier",
                              fontSize=8.4,leading=12,textColor=TEAL,spaceAfter=10))
    story=[Spacer(1,34)]
    def title(t):story.append(Paragraph(t,styles["cTitle"]))
    def head(t):story.append(Paragraph(t,styles["cHead"]))
    def p(t):story.append(Paragraph(t,styles["cText"]))
    def eq(t):story.append(Paragraph(t,styles["cEq"]))
    def table(rows,widths):
        data=[[Paragraph(str(v),styles["cText"]) for v in row] for row in rows]
        t=Table(data,colWidths=widths,repeatRows=1,hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#EAF1FB")),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F5F8FD")]),
            ("GRID",(0,0),(-1,-1),.35,colors.HexColor("#DCE4EE")),
            ("VALIGN",(0,0),(-1,-1),"TOP"),
            ("TOPPADDING",(0,0),(-1,-1),6),
            ("BOTTOMPADDING",(0,0),(-1,-1),4),
        ]))
        story.append(t)
    def footer(c,doc):
        c.setStrokeColor(colors.HexColor("#DCE4EE"))
        c.line(42,34,A4[0]-42,34)
        c.setFont("Helvetica",8)
        c.setFillColor(MUTED)
        c.drawString(42,22,"InProcess | Modelacao Computacional de Sistemas Fisicos")
        c.drawRightString(A4[0]-42,22,f"Pagina {doc.page}")

    title("InProcess 6.3 | Advanced Control Laboratory")
    p("<b>Modelacao e controlo termico P, PI e PID: perturbacoes, limitacao de atuador e validacao numerica</b>")
    p("Relatorio academico gerado automaticamente | novembro de 2026 | "
      "SIMULATED. Nao contem medicoes reais de sensores, consumo eletrico ou ventoinhas.")
    head("Resumo")
    p("Compara-se o comportamento de tres reguladores aplicados ao mesmo modelo "
      "termico acoplado CPU–dissipador e atuador de primeira ordem. "
      "A perturbacao de potencia ocorre numa janela temporal fixa. "
      "O controlador PID usa derivada na medicao, filtro de primeira ordem, "
      "saturacao e anti-windup do integrador.")
    head("Objetivos para a unidade curricular")
    table([
        ["Conceito","Implementacao"],
        ["EDO acopladas","CPU, dissipador e dinamica do atuador"],
        ["Controlo em realimentacao","P, PI e PID com ganhos ajustaveis"],
        ["Perturbacoes e respostas","Degrau finito de potencia termica"],
        ["Analise quantitativa","IAE, ITAE, erro final, pico e saturacao"],
        ["Verificacao","Balanco de energia e limites de atuador"],
        ["Sensibilidade","Variacao simultanea dos ganhos em ±25%"],
    ],[190,315])
    story.append(PageBreak())

    head("1. Modelo termico e dinamica")
    eq("Cdie dTdie/dt = P(t) - Gi(Tdie-Tsink)")
    eq("Csink dTsink/dt = Gi(Tdie-Tsink) - [G0+Gfan*u](Tsink-Ta)")
    eq("tau_fan du/dt = comando - u,    0 <= comando,u <= 1")
    p("A potencia P(t) toma o valor de base exceto na janela definida, "
      "na qual recebe uma perturbacao adicional. A velocidade/fracção de "
      "atuador nao e tratada como potencia eletrica. As leis usadas "
      "representam um modelo de capacidades termicas concentradas.")
    table([
        ["Parametro","Valor ilustrativo"],
        ["Cdie; Csink","120 J/K; 280 J/K"],
        ["Gi; G0; Gfan","6; 1,2; 2 W/K"],
        ["Tau do atuador","3 s"],
        ["Ambiente; alvo","24 C; 47 C"],
        ["Potencia base; perturbacao","55 W; +35 W"],
        ["Janela da perturbacao","100 a 180 s"],
        ["Duracao; passo de integracao","300 s; 0,2 s"],
    ],[235,270])
    head("2. Estrutura de controlo")
    eq("e = Tmedida - Talvo")
    eq("P: cmd=clip(Kp*e,0,1)")
    eq("PI: cmd=clip(Kp*e + Ki*integral(e),0,1)")
    eq("PID: cmd=clip(Kp*e + Ki*integral(e) + Kd*dTf/dt,0,1)")
    p("Tf representa a medicao de temperatura filtrada; o termo derivativo "
      "nao reage diretamente a alteracoes abruptas do valor de referencia. "
      "A integracao anti-windup e condicional quando o comando esta saturado "
      "e limitada em magnitude.")
    story.append(PageBreak())

    head("3. Resposta da temperatura durante perturbacoes")
    color_map={"P":BLUE,"PI":TEAL,"PID":PURPLE}
    story.append(ControlChart([
        (mode,list(zip(trace.times_s,trace.die_c)),color_map[mode])
        for mode,trace in results.items()],
        "Temperatura do CPU (sistema simulado)","Temperatura (C)"))
    story.append(ControlChart([
        (mode,list(zip(trace.times_s,trace.fan_fraction)),color_map[mode])
        for mode,trace in results.items()],
        "Resposta do atuador/ventoinha (fracao)","Fracao"))
    p("A mesma potencia de entrada e o mesmo modelo termico sao usados "
      "na comparacao. O esforco de atuacao nao equivale ao consumo eletrico "
      "da ventoinha e nao se deduz poupança energetica real.")
    head("4. Metricas de desempenho")
    eq("IAE = integral(|e(t)| dt)")
    eq("ITAE = integral(t*|e(t)| dt)")
    table([
        ["Metrica","P","PI","PID"],
        ["Temperatura maxima (C)",*[f"{results[k].metrics.peak_die_c:.3f}" for k in results]],
        ["Erro final (C)",*[f"{results[k].metrics.final_abs_error_c:.3f}" for k in results]],
        ["IAE (C s)",*[f"{results[k].metrics.iae_c_s:.1f}" for k in results]],
        ["Fan medio (0..1)",*[f"{results[k].metrics.fan_mean_fraction:.3f}" for k in results]],
        ["Saturacao (%)",*[f"{100*results[k].metrics.saturated_fraction:.1f}" for k in results]],
    ],[155,115,115,115])
    story.append(PageBreak())

    head("5. Estabilidade e segurança do modelo")
    p("As trajetorias sao finitas e a saturacao limita o comando ao "
      "intervalo [0,1]. Isto permite verificar limites operacionais "
      "na janela simulada, mas NAO prova estabilidade assintotica "
      "da malha fechada. Uma validacao formal exigiria linearizacao, "
      "analise de polos/autovalores e margens de estabilidade.")
    eq("Delta U = integral(Ptermica - Qambiente) dt")
    table([
        ["Controlador","Residuo da conservacao (J)","Acomodacao observada (s)"],
        *[[name,f"{result.metrics.energy_balance_residual_j:.3e}",
           ("nao observada" if result.metrics.observed_settling_s is None
            else f"{result.metrics.observed_settling_s:.3f}")]
          for name,result in results.items()],
    ],[115,190,200])
    head("6. Sensibilidade dos ganhos PID")
    table([
        ["Multiplicador dos ganhos","IAE (C s)","Pico (C)","Saturacao (%)"],
        *[[f"{row['gain_factor']:.2f}",
           f"{row['iae_c_s']:.3f}",f"{row['peak_c']:.3f}",
           f"{100*row['saturation']:.1f}"] for row in sensitivity],
    ],[140,125,115,125])
    p("Variacoes de ganhos nao constituem um algoritmo de sintonia "
      "otima; representam apenas um estudo de sensibilidade "
      "reproduzivel. A derivada filtrada e um compromisso entre "
      "resposta rapida e atenuacao de ruido.")
    story.append(PageBreak())

    head("7. Limitacoes e proximo trabalho")
    p("O modelo usa capacidades termicas concentradas, potencia "
      "hipotetica, ganhos arbitrarios e ruido deterministico opcional. "
      "Nao sao recolhidas RPM reais, consumo eletrico do atuador, "
      "temperatura da sala ou potencia termica efetivamente dissipada. "
      "Uma futura comparacao experimental requer identificacao dos "
      "parametros, incerteza dos sensores, series de validacao independentes, "
      "analise de estabilidade local e testes de robustez a perturbacoes.")
    head("8. Reprodutibilidade")
    eq("python -m pytest tests/test_control_lab63.py -q")
    eq("PYTHONPATH=src python examples/generate_control63_pdf.py")
    p("O laboratorio apresenta os tres controladores no mesmo grafico "
      "e disponibiliza exportacao JSON/CSV. Nao altera processos, "
      "politicas energeticas ou controladores de ventoinha reais.")
    head("Conclusao")
    p("A extensao 6.3 acrescenta realimentacao, filtragem, saturacao "
      "e estudo de resposta a perturbacoes, permitindo justificar "
      "os efeitos de P, PI e PID na fisica termica. "
      "A validacao de software nao equivale a validacao experimental.")
    doc=SimpleDocTemplate(str(output),pagesize=A4,leftMargin=45,rightMargin=45,
                          topMargin=47,bottomMargin=51,
                          title="InProcess 6.3 - Advanced Control Laboratory")
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return output


if __name__=="__main__":
    arg=argparse.ArgumentParser()
    arg.add_argument("--output",type=Path,
                     default=Path("docs/relatorios/InProcess_Advanced_Control_Lab_6_3.pdf"))
    params=arg.parse_args()
    print(build(params.output))
