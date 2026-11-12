"""Rebuild the Physics Lab 6 academic PDF from numerical experiments.

Requires reportlab; all inputs and results are simulated, not calibrated.
Run: PYTHONPATH=src python examples/generate_lab6_pdf.py
"""
from pathlib import Path
import math
import argparse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Flowable
from reportlab.lib.enums import TA_LEFT

from expecto_process_manager.physics.physical_lab6 import (
    HeatSlab, solve_heat, heat_convergence, heat_sensitivity, fan_comparison,
)

NAVY=colors.HexColor("#14243A")
BLUE=colors.HexColor("#2368D9")
TEAL=colors.HexColor("#0A8F8B")
MUTED=colors.HexColor("#536478")


class Lines(Flowable):
    def __init__(self, series, title, x_label="Tempo (s)", y_label="Temperatura (C)"):
        Flowable.__init__(self)
        self.series=series
        self.title=title
        self.x_label=x_label
        self.y_label=y_label
        self.width=465
        self.height=202

    def draw(self):
        c=self.canv
        left,bottom,width,height=50,33,390,125
        xs=[x for name,points,color in self.series for x,y in points]
        ys=[y for name,points,color in self.series for x,y in points]
        xmin,xmax=min(xs),max(xs)
        ymin,ymax=min(ys),max(ys)
        if ymax==ymin: ymax+=1
        pad=(ymax-ymin)*.05
        ymin-=pad
        ymax+=pad
        c.setFont("Helvetica-Bold",10)
        c.setFillColor(NAVY)
        c.drawString(4,183,self.title)
        c.setFont("Helvetica",7)
        c.setFillColor(MUTED)
        for idx in range(5):
            y=bottom+height*idx/4
            c.setStrokeColor(colors.HexColor("#E1E7F0"))
            c.line(left,y,left+width,y)
            c.drawRightString(left-5,y-2,f"{ymin+(ymax-ymin)*idx/4:.2f}")
        c.setStrokeColor(MUTED)
        c.line(left,bottom,left,bottom+height)
        c.line(left,bottom,left+width,bottom)
        c.drawCentredString(left+width/2,12,self.x_label)
        for i,(name,points,color) in enumerate(self.series):
            c.setFillColor(color)
            c.setStrokeColor(color)
            c.setLineWidth(1.65)
            path=c.beginPath()
            for j,(x,y) in enumerate(points):
                px=left+(x-xmin)/max(xmax-xmin,1e-12)*width
                py=bottom+(y-ymin)/(ymax-ymin)*height
                if j==0:path.moveTo(px,py)
                else:path.lineTo(px,py)
            c.drawPath(path)
            c.drawString(12+i*145,165,name)


def build(output):
    slab=HeatSlab()
    sim=solve_heat(slab,duration_s=4)
    convergence=heat_convergence()
    sensitivity=heat_sensitivity()
    fans=fan_comparison()
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ipTitle",parent=styles["Title"],fontSize=23,leading=29,
                              textColor=NAVY,spaceAfter=20))
    styles.add(ParagraphStyle(name="ipHead",parent=styles["Heading2"],fontSize=14,leading=20,
                              textColor=BLUE,spaceBefore=12,spaceAfter=10))
    styles.add(ParagraphStyle(name="ipText",parent=styles["BodyText"],fontSize=9.3,leading=14.0,
                              textColor=NAVY,spaceAfter=11))
    styles.add(ParagraphStyle(name="ipEq",parent=styles["BodyText"],fontSize=9,leading=14,
                              fontName="Courier",textColor=TEAL,spaceAfter=11))
    story=[]
    def title(t): story.append(Paragraph(t,styles["ipTitle"]))
    def head(t): story.append(Paragraph(t,styles["ipHead"]))
    def p(t): story.append(Paragraph(t,styles["ipText"]))
    def eq(t): story.append(Paragraph(t,styles["ipEq"]))
    def table(rows,widths=None):
        data=[[Paragraph(str(x),styles["ipText"]) for x in row] for row in rows]
        t=Table(data,colWidths=widths,hAlign="LEFT",repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#EAF2FF")),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F5F8FC")]),
            ("GRID",(0,0),(-1,-1),.35,colors.HexColor("#D8E2EE")),
            ("VALIGN",(0,0),(-1,-1),"TOP"),
            ("LEFTPADDING",(0,0),(-1,-1),9),("TOPPADDING",(0,0),(-1,-1),6),
            ("BOTTOMPADDING",(0,0),(-1,-1),4),
        ]))
        story.append(t)
    def page(c,doc):
        c.setStrokeColor(colors.HexColor("#D8E2EE"))
        c.line(40,37,A4[0]-40,37)
        c.setFont("Helvetica",8)
        c.setFillColor(MUTED)
        c.drawString(40,25,"InProcess - Modelacao Computacional de Sistemas Fisicos")
        c.drawRightString(A4[0]-40,25,f"Pagina {doc.page}")

    story.append(Spacer(1,42))
    title("InProcess | Physical Systems Lab 6.0")
    p("<b>Conducao 1D, estabilidade numerica, sensibilidade e arrefecimento adaptativo</b>")
    p("Relatorio academico reproduzivel | novembro de 2026 | Todos os cenarios SIMULATED. "
      "O documento nao apresenta medições de sensores nem validação física de equipamentos.")
    head("Resumo")
    p("Esta extensao converte as leis de Fourier e de conservacao da energia num "
      "problema de difusao transitoria em uma dimensao (EDP), resolvido por "
      "diferencas centrais no espaco e Euler explicito no tempo. A estabilidade "
      "obedece ao numero de Fourier. O estudo compara a solucao a uma referencia "
      "analitica, investiga malhas/passos, alteracoes da difusividade e um "
      "controlador PI que regula o arrefecimento de um modelo CPU-dissipador.")
    head("Objetivos para a UC")
    table([["Conceito","Implementacao e verificacao"],
           ["Transferencia de calor","Equacao do calor 1D e fronteiras Dirichlet"],
           ["EDP e diferencas finitas","Derivada espacial de segunda ordem"],
           ["Estabilidade","Numero de Fourier <= 0,5"],
           ["Energia e conservacao","Energia interna e fluxo perdido nas fronteiras"],
           ["Erros e convergencia","RMSE e erros comparados com solucao independente"],
           ["Controlo e sistemas dinamicos","Dois nos termicos e atuador PI limitado"]],
          [190,315])
    story.append(PageBreak())
    head("1. Problema de condução térmica")
    p("Uma barra equivalente de comprimento L, condutividade k e difusividade alpha "
      "troca calor pelas extremidades mantidas a temperatura Ta. "
      "A temperatura inicial e uma senoide espacial; nao representa dados medidos do CPU.")
    eq("dT/dt = alpha * d2T/dx2,  0 < x < L")
    eq("T(0,t)=T(L,t)=Ta;  T(x,0)=Ta+A*sin(pi*x/L)")
    eq("T_exata(x,t)=Ta+A*sin(pi*x/L)*exp[-alpha*(pi/L)^2*t]")
    p("No ponto interno i, o esquema explicito usa "
      "T_i(n+1)=T_i(n)+Fo*(T_(i-1)-2*T_i+T_(i+1)), "
      "com Fo=alpha*dt/dx^2. A estabilidade linear exige Fo <= 1/2.")
    table([["Parametro","Valor simulado"],
           ["L","0,04 m"],["alpha","1,0e-5 m2/s"],
           ["k; area","180 W/(m K); 0,001 m2"],
           ["Ta; temperatura maxima inicial","25 C; 65 C"],
           ["Nos","21"],["Fo efetivo",f"{sim.fourier:.4f}"]],
          [230,275])
    centers=[profile[slab.nodes//2] for profile in sim.profiles_c]
    reference=[slab.exact(slab.length_m/2,t) for t in sim.times_s]
    story.append(Lines([
        ("Discretizacao",list(zip(sim.times_s,centers)),BLUE),
        ("Analitica",list(zip(sim.times_s,reference)),TEAL),
    ],"Centro da barra: Euler explicito vs referencia"))
    p(f"RMSE em perfis armazenados = {sim.rmse_c:.4g} C; "
      f"erro maximo = {sim.max_error_c:.4g} C. "
      "Inclui erros espacial e temporal.")
    story.append(PageBreak())
    head("2. Balanço de energia")
    p("Na grelha, a energia interna aproximada e a soma das energias dos "
      "volumes interiores, medida relativamente a Ta. "
      "Os fluxos de calor na fronteira usam a mesma aproximacao "
      "que a discretizacao espacial.")
    eq("U = rho*c*A*dx*sum_interior(T_i - Ta)")
    eq("U_final - U_inicial + integral(Q_saida dt) = 0")
    table([["Grandeza","Valor (simulado)"],
           ["Energia inicial",f"{sim.energy_initial_j:.6f} J"],
           ["Energia final",f"{sim.energy_final_j:.6f} J"],
           ["Energia evacuada",f"{sim.boundary_energy_j:.6f} J"],
           ["Residuo discreto",f"{sim.balance_error_j:.6e} J"]],
          [220,285])
    p("A concordancia do balanco comprova consistencia entre o algoritmo e os "
      "fluxos discretos. Nao demonstra que a condutividade ilustrativa "
      "seja a de um dissipador real.")
    head("3. Convergencia de passo temporal")
    table([["Fo efetivo","RMSE (C)","Erro max. (C)"],
           *[[f"{r['actual_fourier']:.3f}",f"{r['rmse_c']:.5g}",
              f"{r['maximum_c']:.5g}"] for r in convergence]],
          [150,180,175])
    p("Como o tamanho da malha espacial se mantem fixo, o erro perante a solucao "
      "continua inclui uma componente de ordem O(dx^2), que nao desaparece "
      "ao reduzir dt. Nao se declara uma ordem temporal observada "
      "a partir desta tabela sem isolar o erro espacial.")
    story.append(PageBreak())
    head("4. Sensibilidade a difusividade termica")
    table([["alpha (m2/s)","Temperatura central (C)","RMSE (C)"],
           *[[f"{r['diffusivity_m2_s']:.7f}",f"{r['center_temperature_c']:.4f}",
              f"{r['rmse_c']:.5g}"] for r in sensitivity]],
          [145,190,170])
    p("Com geometria e fronteiras iguais, maior difusividade provoca "
      "evolucao temporal mais rapida para o equilibrio. O estudo nao estima "
      "alpha a partir do sistema operativo ou de sensores.")
    head("5. Controlo PI do arrefecimento")
    p("O controlador regula um atuador hipotetico u no intervalo [0,1], "
      "com atraso de primeira ordem. A condutancia termica efetiva "
      "para o ambiente cresce com a resposta do ventilador. "
      "O integrador possui limite e anti-windup condicional.")
    eq("C1*dT1/dt = P - Gi*(T1-T2)")
    eq("C2*dT2/dt = Gi*(T1-T2) - (G0+Gfan*u)*(T2-Ta)")
    eq("tau*du/dt = clip(Kp*e+Ki*integral(e),0,1) - u")
    p("Comparou-se a ventilacao fixa a 50% com um PI adaptativo, "
      "sem atuar numa ventoinha real. O codigo nao corresponde "
      "a um controlador PID completo, porque nao inclui termo derivativo.")
    fixed,adaptive=fans["fixed"],fans["adaptive"]
    story.append(Lines([
        ("Vent. fixa",list(zip(fixed.times_s,fixed.die_c)),BLUE),
        ("PI adaptativo",list(zip(adaptive.times_s,adaptive.die_c)),TEAL),
    ],"Temperatura CPU em condicoes simuladas"))
    table([["Indicador","Fixo (50%)","PI adaptativo"],
           ["T CPU final (C)",f"{fixed.last_die_c:.3f}",f"{adaptive.last_die_c:.3f}"],
           ["T CPU max. (C)",f"{fixed.max_die_c:.3f}",f"{adaptive.max_die_c:.3f}"],
           ["Fracao media atuador",f"{fixed.mean_fan_fraction:.3f}",f"{adaptive.mean_fan_fraction:.3f}"]],
          [185,155,165])
    story.append(PageBreak())
    head("6. Limitações, segurança e interpretação")
    p("A difusao 1D usa material homogeneo, dimensoes fixas e "
      "extremidades a temperatura constante. Dissipadores reais incluem "
      "geometria 3D, contactos termicos, conveccao distribuida e radiacao. "
      "O controlador PI nao conhece a curva fisica da ventoinha, "
      "nem o seu consumo eletrico ou ruido. Nenhuma poupança energetica real "
      "e demonstrada pela comparacao de fracoes de atuacao.")
    p("A implementacao distingue simulacao, validacao numerica e validacao "
      "experimental. Para uma futura validacao real, medir T CPU, T ambiente, "
      "potencia associada ao dominio, velocidade da ventoinha e respetivas "
      "incertezas; usar conjuntos independentes para ajuste e validacao.")
    head("7. Reprodutibilidade")
    eq("python -m pytest tests/test_physical_lab6.py -q")
    eq("PYTHONPATH=src python examples/generate_lab6_pdf.py")
    p("O codigo inclui limites de numero de passos e nos, rejeita instabilidade "
      "explícita e permite cancelar calculos. Os resultados da EDP nao usam "
      "sensores do computador; os dados da GUI nao sao usados para inferir watts.")
    head("Bibliografia de enquadramento")
    p("OpenStax, University Physics, conceitos de calor e transferencia termica, "
      "https://openstax.org/subjects/science.")
    p("Crank, J., The Mathematics of Diffusion, Oxford University Press: "
      "formulacao classica de difusao. "
      "As fontes oferecem enquadramento teorico; nao sao fonte dos parametros simulados.")
    p("<b>Conclusao:</b> a extensão 6.0 acrescenta uma EDP física, "
      "estabilidade de discretizacao, conservacao, referencia analitica, "
      "analise de sensibilidade e controlo termico demonstravel. "
      "Os resultados continuam ilustrativos ate a fase de calibracao.")
    doc=SimpleDocTemplate(str(output),pagesize=A4,leftMargin=45,rightMargin=45,
                          topMargin=48,bottomMargin=51,
                          title="InProcess Physical Systems Lab 6.0",
                          author="Projeto InProcess")
    doc.build(story,onFirstPage=page,onLaterPages=page)
    return output


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,
                        default=Path("docs/relatorios/InProcess_Physical_Systems_Lab_6.pdf"))
    args=parser.parse_args()
    print(build(args.output))
