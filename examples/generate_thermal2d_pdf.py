"""Reproducible academic report for InProcess Thermal Field 2D (SIMULATED).

Run with PYTHONPATH=src and reportlab installed.
"""
from pathlib import Path
import argparse
import math
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,Flowable

from expecto_process_manager.physics.heat_2d import (
    HeatPlate2D,solve_heat_2d,heat_2d_grid_study,
)

NAVY=colors.HexColor("#14233B")
BLUE=colors.HexColor("#246DE4")
TEAL=colors.HexColor("#078F88")
MUTED=colors.HexColor("#536477")


class FieldImage(Flowable):
    def __init__(self,frame,minimum,maximum,title):
        Flowable.__init__(self)
        self.frame=frame
        self.minimum=minimum
        self.maximum=maximum
        self.title=title
        self.width=450
        self.height=208

    def draw(self):
        painter=self.canv
        painter.setFillColor(NAVY)
        painter.setFont("Helvetica-Bold",10)
        painter.drawString(6,198,self.title)
        ny=len(self.frame)
        nx=len(self.frame[0])
        dx=344/nx
        dy=151/ny
        bottom=32
        left=40
        span=max(self.maximum-self.minimum,1e-12)
        for row_idx,row in enumerate(self.frame):
            for col,temp in enumerate(row):
                t=max(0,min(1,(temp-self.minimum)/span))
                if t<.5:
                    z=t*2
                    color=colors.Color((21+20*z)/255,(95+125*z)/255,(190-38*z)/255)
                else:
                    z=(t-.5)*2
                    color=colors.Color((41+210*z)/255,(220-104*z)/255,(152-108*z)/255)
                painter.setFillColor(color)
                painter.rect(left+col*dx,bottom+(ny-1-row_idx)*dy,dx+.05,dy+.05,stroke=0,fill=1)
        painter.setStrokeColor(MUTED)
        painter.rect(left,bottom,nx*dx,ny*dy,stroke=1,fill=0)
        painter.setFont("Helvetica",8)
        painter.setFillColor(MUTED)
        painter.drawString(left,13,"X (m) →")
        painter.drawRightString(left+nx*dx,13,"campo de temperaturas")
        painter.drawString(391,158,f"{self.maximum:.1f} C")
        painter.drawString(391,33,f"{self.minimum:.1f} C")


def build(output):
    mixed=HeatPlate2D()
    result=solve_heat_2d(mixed,duration_s=6)
    homogeneous=HeatPlate2D(nx=25,ny=25,inclusion=False,source_w=0,boundary="dirichlet")
    verification=solve_heat_2d(homogeneous,duration_s=2)
    grids=heat_2d_grid_study(duration_s=1)
    insulated=solve_heat_2d(HeatPlate2D(boundary="insulated",source_w=0),duration_s=2)
    assert abs(result.balance_residual_j)<1e-7
    assert abs(verification.balance_residual_j)<1e-7
    assert abs(insulated.balance_residual_j)<1e-7
    assert verification.rmse_exact_c is not None
    assert grids[-1]["rmse_c"] < grids[0]["rmse_c"]

    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name="IPTitle2D",parent=styles["Title"],fontSize=22,leading=27,textColor=NAVY,spaceAfter=18))
    styles.add(ParagraphStyle(name="IPHead2D",parent=styles["Heading2"],fontSize=13,leading=18,textColor=BLUE,spaceBefore=11,spaceAfter=7))
    styles.add(ParagraphStyle(name="IPText2D",parent=styles["BodyText"],fontSize=9.2,leading=13.5,textColor=NAVY,spaceAfter=9))
    styles.add(ParagraphStyle(name="IPEq2D",parent=styles["BodyText"],fontName="Courier",fontSize=8.6,leading=12,textColor=TEAL,spaceAfter=10))
    story=[Spacer(1,30)]
    def title(text):story.append(Paragraph(text,styles["IPTitle2D"]))
    def heading(text):story.append(Paragraph(text,styles["IPHead2D"]))
    def p(text):story.append(Paragraph(text,styles["IPText2D"]))
    def eq(text):story.append(Paragraph(text,styles["IPEq2D"]))
    def table(rows,widths):
        data=[[Paragraph(str(v),styles["IPText2D"]) for v in row] for row in rows]
        obj=Table(data,colWidths=widths,repeatRows=1,hAlign="LEFT")
        obj.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#E9F2FC")),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F4F8FC")]),
            ("GRID",(0,0),(-1,-1),.4,colors.HexColor("#D6E1ED")),
            ("VALIGN",(0,0),(-1,-1),"TOP"),
            ("TOPPADDING",(0,0),(-1,-1),6),
            ("BOTTOMPADDING",(0,0),(-1,-1),4),
        ]))
        story.append(obj)
    def footer(c,doc):
        c.setStrokeColor(colors.HexColor("#D6E1ED"))
        c.line(42,36,A4[0]-42,36)
        c.setFont("Helvetica",8)
        c.setFillColor(MUTED)
        c.drawString(42,23,"InProcess | Modelacao Computacional de Sistemas Fisicos")
        c.drawRightString(A4[0]-42,23,f"Pagina {doc.page}")

    title("InProcess 6.2 | Thermal Field 2D")
    p("<b>Difusao termica transitoria, materiais heterogeneos, conveccao, "
      "conservacao de energia e validacao numerica</b>")
    p("Relatorio academico reproduzivel | novembro 2026 | SIMULATED. "
      "Nenhuma propriedade foi calibrada e nenhuma medicao fisica foi realizada.")
    heading("Resumo")
    p("Esta fase do InProcess utiliza a equacao do calor em duas dimensoes. "
      "A malha de volumes finitos utiliza capacidade termica por celula, "
      "condutancias entre celulas calculadas pela media harmonica da condutividade "
      "e fluxo de fronteira coerente com as leis de Fourier e Newton. "
      "O solver e explicito, conserva energia de forma discreta "
      "e limita o passo pelo criterio de monotonicidade.")
    heading("Objetivos da unidade curricular")
    table([
        ["Conceito","Experiencia computacional"],
        ["EDP de difusao","Temperatura T(x,y,t)"],
        ["Discretizacao espacial","Volumes finitos e faces de materiais diferentes"],
        ["Conservacao","Entrada termica, calor nas fronteiras, energia interna"],
        ["Condicoes de fronteira","Dirichlet, Robin e isolamento"],
        ["Estabilidade","Limite de passo explicito por celula"],
        ["Verificacao","Referencia analitica num caso homogéneo"],
    ],[190,315])
    story.append(PageBreak())

    heading("1. Modelo e discretizacao")
    eq("rho*c * dT/dt = div(k grad T) + q")
    p("A capacidade local e C_i = rho_i*c_i*V_i. Para cada face interna, "
      "a condutancia e G_ij = k_harmonico*A_face/distancia. "
      "Para material isotropico, o fluxo de calor entre celulas "
      "segue a lei de Fourier. Na fronteira com conveccao inclui-se "
      "a resistencia condutiva de meia celula mais a resistencia convectiva.")
    eq("C_i dT_i/dt = sum_j G_ij(T_j-T_i) + Q_i - Gb_i(T_i-Ta)")
    eq("G_harm = 2*k1*k2/(k1+k2)")
    eq("G_Robin = A/(dx/(2*k) + 1/h)")
    p("Fronteiras: Dirichlet fixa Ta na superficie externa; "
      "Robin usa o coeficiente h; Neumann isolado impoe fluxo nulo. "
      "A condicao inicial senoidal e uma hipotese ilustrativa, "
      "nao o mapa real de um componente.")
    table([
        ["Parametro","Valor do caso misto"],
        ["Lx x Ly","0,10 x 0,08 m"],
        ["Espessura","0,003 m"],
        ["Malha","25 x 21 celulas"],
        ["Condutividade matriz/inclusao","160 / 18 W/(m K)"],
        ["Capacidade volumetrica (matriz)","2,4e6 J/(m3 K)"],
        ["Potencia termica local","6 W"],
        ["Conveccao ambiente","25 W/(m2 K)"],
        ["Temperatura ambiente e pico inicial","25 C / 65 C"],
    ],[230,275])
    story.append(PageBreak())

    heading("2. Evolucao do campo térmico")
    p("Visualizacao vetorial diretamente a partir da grelha numerica. "
      "A escala de cores e a mesma nos dois instantes representados; "
      "nao corresponde a uma fotografia termografica do hardware.")
    story.append(FieldImage(result.frames_c[0],result.min_c,result.max_c,
                            "Campo de temperatura inicial (simulado)"))
    story.append(FieldImage(result.frames_c[-1],result.min_c,result.max_c,
                            f"Campo de temperatura a t={result.times_s[-1]:.1f} s"))
    heading("3. Estabilidade e limites")
    p("Um passo explicito suficientemente pequeno garante que cada "
      "atualizacao pode ser expressa por coeficientes nao negativos "
      "na difusao pura. Utiliza-se o limite conservativo "
      "min(C_i/sum G), incluindo perdas de fronteira.")
    eq("dt <= min_i (C_i / (sum_j G_ij + Gb_i))")
    table([
        ["Grandeza","Valor do caso misto"],
        ["Passo efetivo (s)",f"{result.dt_s:.6g}"],
        ["Limite de passo (s)",f"{result.conservative_limit_s:.6g}"],
        ["Fourier X (matriz)",f"{result.fourier_x:.5f}"],
        ["Fourier Y (matriz)",f"{result.fourier_y:.5f}"],
        ["Temperatura máxima (C)",f"{result.max_c:.4f}"],
    ],[230,275])
    story.append(PageBreak())

    heading("4. Balanço discreto de energia")
    eq("U_final-U_inicial = E_fonte-E_perdas")
    p("Os fluxos entre celulas sao simetricos e cancelam na soma global "
      "da energia. O mesmo fluxo de fronteira que entra no esquema "
      "e integrado temporalmente como energia perdida para o ambiente.")
    table([
        ["Grandeza","Resultado numerico"],
        ["U inicial (J)",f"{result.initial_j:.6f}"],
        ["U final (J)",f"{result.final_j:.6f}"],
        ["Entrada termica (J)",f"{result.heat_input_j:.6f}"],
        ["Perdas fronteira (J)",f"{result.boundary_loss_j:.6f}"],
        ["Residuo conservativo (J)",f"{result.balance_residual_j:.3e}"],
    ],[250,255])
    p("O residuo pequeno demonstra a consistencia do esquema de "
      "conservacao, nao a validade experimental dos parametros.")
    heading("5. Referencia analitica")
    p("No caso homogeneo, sem fonte interna e com fronteira "
      "de temperatura fixa, a solucao exata de modo seno e:")
    eq("T=Ta+A*sin(pi*x/Lx)*sin(pi*y/Ly)*exp(-alpha*pi^2*(1/Lx^2+1/Ly^2)*t)")
    p(f"RMSE da simulação homogénea perante a solucao exata: "
      f"{verification.rmse_exact_c:.6g} C, no instante final de 2 s. "
      "A referencia nao se aplica diretamente ao material heterogeneo.")
    heading("6. Refinamento de malha e erro")
    table([
        ["Nx=Ny","dx (m)","RMSE (C)","Resíduo energia (J)"],
        *[[str(row["nx"]),f"{row['dx_m']:.5f}",
           f"{row['rmse_c']:.6g}",f"{row['energy_balance_j']:.2e}"]
          for row in grids],
    ],[90,125,130,160])
    p("O refinamento espacial tambem altera o passo temporal escolhido "
      "pela restricao conservativa, pelo que esta tabela indica "
      "convergencia combinada espacial/temporal: nao se atribui "
      "uma ordem espacial pura a estes erros.")
    story.append(PageBreak())

    heading("7. Interpretacao, limites e desenvolvimento futuro")
    p("O caso misto e um modelo didatico de uma placa fina: "
      "as propriedades de condutividade e capacidade termica "
      "sao valores hipoteticos; nao ha calibracao para CPU, GPU "
      "ou dissipador real. As condicoes de fronteira representam "
      "aproximacoes ideais e a geracao local nao foi medida.")
    p("Para uma evolucao fisica rigorosa seriam necessarias aquisicoes "
      "calibradas de temperatura, fluxo termico e potencia de entrada, "
      "geometria mais fiel, dados independentes de treino/validacao, "
      "estimacao de parametros e incerteza instrumental.")
    heading("8. Reproducibilidade")
    eq("python -m pytest tests/test_heat_2d.py -q")
    eq("PYTHONPATH=src python examples/generate_thermal2d_pdf.py")
    p("Os dados, mapas e indicadores sao produzidos pelo codigo "
      "do InProcess e podem ser exportados para JSON e CSV. "
      "Nao se controlam ventoinhas ou processos e nao se pode "
      "inferir consumo eletrico real a partir de um mapa simulado.")
    heading("Enquadramento")
    p("Incropera et al., Fundamentals of Heat and Mass Transfer, "
      "Wiley; Patankar, Numerical Heat Transfer and Fluid Flow, "
      "Hemisphere. As referencias fornecem enquadramento do metodo, "
      "nao certificam os parametros escolhidos.")
    p("<b>Conclusao:</b> o laboratorio 6.2 acrescenta um campo termico "
      "bidimensional, materiais distintos, condicoes de fronteira e "
      "conservacao verificavel. O estudo continua numerico ate existir "
      "uma campanha experimental independente.")
    doc=SimpleDocTemplate(str(output),pagesize=A4,
                          leftMargin=45,rightMargin=45,
                          topMargin=47,bottomMargin=51,
                          title="InProcess 6.2 Thermal Field 2D")
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return output


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,
                        default=Path("docs/relatorios/InProcess_Thermal_Field_2D_6_2.pdf"))
    args=parser.parse_args()
    print(build(args.output))
