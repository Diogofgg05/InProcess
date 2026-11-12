"""Reproducible academic PDF: numerical physics 6.1.

No sensors or energy measurements. Run with PYTHONPATH=src and reportlab.
"""
import argparse
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Flowable
from reportlab.pdfbase.pdfmetrics import stringWidth

from expecto_process_manager.physics.physical_lab6 import HeatSlab
from expecto_process_manager.physics.heat_implicit import (
    solve_heat_61, temporal_order_study, spatial_order_study,
)

DARK = colors.HexColor("#17253A")
BLUE = colors.HexColor("#2368D9")
TEAL = colors.HexColor("#078D88")
MUTED = colors.HexColor("#65768C")


class Plot(Flowable):
    def __init__(self, curves, title, ylabel, xlabel="Tempo (s)"):
        Flowable.__init__(self)
        self.width = 480
        self.height = 185
        self.curves, self.title, self.ylabel, self.xlabel = curves, title, ylabel, xlabel

    def draw(self):
        c = self.canv
        lx, by, w, h = 56, 30, 385, 110
        xs = [x for name, points, color in self.curves for x, y in points]
        ys = [y for name, points, color in self.curves for x, y in points]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        pad = max((y1-y0)*.08, 1e-12)
        y0 -= pad
        y1 += pad
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(DARK)
        c.drawString(5, 174, self.title)
        c.setFont("Helvetica", 7)
        for i in range(5):
            yy = by + h*i/4
            c.setStrokeColor(colors.HexColor("#E0E8F2"))
            c.line(lx, yy, lx+w, yy)
            c.setFillColor(MUTED)
            c.drawRightString(lx-6, yy-2, f"{y0+(y1-y0)*i/4:.4g}")
        c.setStrokeColor(MUTED)
        c.line(lx, by, lx+w, by)
        c.line(lx, by, lx, by+h)
        c.drawCentredString(lx+w/2, 13, self.xlabel)
        for index, (name, samples, color) in enumerate(self.curves):
            c.setStrokeColor(color)
            c.setLineWidth(1.6)
            path = c.beginPath()
            for i, (x, y) in enumerate(samples):
                xx = lx + w*(x-x0)/(x1-x0 or 1)
                yy = by + h*(y-y0)/(y1-y0)
                if not i:
                    path.moveTo(xx,yy)
                else:
                    path.lineTo(xx,yy)
            c.drawPath(path)
            c.setFont("Helvetica", 7)
            c.setFillColor(color)
            c.drawString(12+index*125, 157, name)


def build(output):
    model = HeatSlab(nodes=21)
    duration = 4.0
    step = .2
    results = {
        method: solve_heat_61(model,duration_s=duration,dt_s=step,method=method)
        for method in ("explicit","backward_euler","crank_nicolson")
    }
    temporal = {
        method: temporal_order_study(model,duration_s=duration,method=method)
        for method in results
    }
    spatial = spatial_order_study(model,duration_s=duration)
    for value in results.values():
        assert abs(value.balance_error_j) < 1e-7
    assert 0.75 < temporal["explicit"][-1]["observed_order"] < 1.25
    assert 0.75 < temporal["backward_euler"][-1]["observed_order"] < 1.25
    assert 1.8 < temporal["crank_nicolson"][-1]["observed_order"] < 2.2
    assert 1.8 < spatial[-1]["observed_order"] < 2.2

    output = Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="reportTitle",parent=styles["Title"],fontSize=22,leading=27,
                              textColor=DARK,spaceAfter=20))
    styles.add(ParagraphStyle(name="reportHead",parent=styles["Heading2"],fontSize=13,leading=18,
                              textColor=BLUE,spaceBefore=12,spaceAfter=8))
    styles.add(ParagraphStyle(name="reportBody",parent=styles["BodyText"],fontSize=9.1,leading=13.4,
                              textColor=DARK,spaceAfter=9))
    styles.add(ParagraphStyle(name="reportCode",parent=styles["BodyText"],fontName="Courier",
                              fontSize=8.3,leading=12,textColor=TEAL,spaceAfter=8))
    story = [Spacer(1,36)]
    def para(t): story.append(Paragraph(t,styles["reportBody"]))
    def title(t): story.append(Paragraph(t,styles["reportTitle"]))
    def head(t): story.append(Paragraph(t,styles["reportHead"]))
    def eq(t): story.append(Paragraph(t,styles["reportCode"]))
    def table(rows,widths):
        data = [[Paragraph(str(value),styles["reportBody"]) for value in row] for row in rows]
        t=Table(data,colWidths=widths,repeatRows=1,hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#EAF1FB")),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F5F8FD")]),
            ("GRID",(0,0),(-1,-1),.35,colors.HexColor("#D9E2EC")),
            ("VALIGN",(0,0),(-1,-1),"TOP"),
            ("TOPPADDING",(0,0),(-1,-1),5),
            ("BOTTOMPADDING",(0,0),(-1,-1),3),
        ]))
        story.append(t)
    def pages(canvas,doc):
        canvas.setStrokeColor(colors.HexColor("#DDE6F0"))
        canvas.line(42,35,A4[0]-42,35)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica",8)
        canvas.drawString(42,23,"InProcess | Modelacao Computacional de Sistemas Fisicos")
        canvas.drawRightString(A4[0]-42,23,f"Pagina {doc.page}")

    title("InProcess 6.1 | Numerical Physics")
    para("<b>Euler explicito, Euler implicito e Crank-Nicolson para a equacao do calor 1D</b>")
    para("Relatorio cientifico de simulacao reproduzivel | novembro 2026 | SIMULATED. "
         "Sem dados experimentais, calibração de sensores ou atuação sobre o computador.")
    head("Resumo e objetivo")
    para("O InProcess 6.1 estuda discretizacoes da difusao termica e introduz dois esquemas "
         "implicitos, resolvidos por algoritmo tridiagonal O(N), evitando matrizes densas. "
         "O objetivo e comparar estabilidade, conservacao e precisao, isolando as ordens "
         "temporais e espaciais com referencias analiticas distintas.")
    head("1. Modelo e condicoes")
    eq("T_t = alpha * T_xx")
    eq("T(0,t)=T(L,t)=Ta; T(x,0)=Ta + A*sin(pi*x/L)")
    eq("T_cont(x,t)=Ta + A*sin(pi*x/L)*exp(-alpha*(pi/L)^2*t)")
    table([
        ["Parâmetro físico", "Valor ilustrativo"],
        ["L; alpha", "0,04 m; 1e-5 m2/s"],
        ["Condutividade; secção", "180 W/(m K); 0,001 m2"],
        ["Ta; T central inicial", "25 C; 65 C"],
        ["Nós; duração", "21; 4 s"],
        ["Passo comum aos três métodos", "0,2 s"],
    ],[220,285])
    para("Os extremos usam temperatura fixa (Dirichlet). A condição inicial em modo "
         "seno permite uma solução exata da EDP, sem ajuste de parâmetros ao resultado numérico.")
    story.append(PageBreak())
    head("2. Métodos numéricos e estabilidade")
    para("Para a discretização espacial centrada, seja Lh a matriz tridiagonal do "
         "Laplaciano e Fo=alpha*dt/dx². O método theta aplica:")
    eq("(I - theta*Fo*Lh) u[n+1] = (I+(1-theta)*Fo*Lh) u[n]")
    table([
        ["Método","theta","Estabilidade linear","Ordem temporal"],
        ["Euler explícito","0","Fo <= 0,5","1"],
        ["Euler implícito","1","A-estável e L-estável","1"],
        ["Crank–Nicolson","0,5","A-estável; possíveis oscilações","2"],
    ],[145,60,190,110])
    para("A-estabilidade não significa monotonicidade incondicional: Crank–Nicolson "
         "pode produzir oscilações não físicas para passos demasiado grandes. "
         "A resolução dos sistemas tridiagonais é linear no número de nós.")
    curves=[]
    for method,color,label in [
        ("explicit",BLUE,"Euler explicito"),
        ("backward_euler",colors.HexColor("#9552D9"),"Euler implicito"),
        ("crank_nicolson",TEAL,"Crank-Nicolson"),
    ]:
        r=results[method]
        curves.append((label,list(zip(r.times_s,[profile[model.nodes//2]
                          for profile in r.profiles_c])),color))
    story.append(Plot(curves,"Evolucao termica do centro da barra","Temperatura (C)"))
    table([
        ["Método","RMSE vs EDP (C)","Fo real","Resíduo de energia (J)"],
        *[[name, f"{r.rmse_c:.5g}",f"{r.fourier:.4g}",
           f"{r.balance_error_j:.2e}"] for name,r in results.items()],
    ],[130,135,80,160])
    story.append(PageBreak())
    head("3. Ordem de convergência temporal")
    para("Para isolar a convergência temporal, não se usa como referência a EDP contínua, "
         "pois incluiria um erro espacial de ordem O(dx²). Para o modo sinusoidal inicial, "
         "a solução exata do sistema SEMIDISCRETO tem autovalor:")
    eq("lambda_h = -4*alpha/dx^2*sin^2(pi/(2*(N-1)))")
    eq("Tcentro(t)=Ta + A*exp(lambda_h*t)")
    para("A tabela seguinte apresenta a ordem empírica calculada pela razão de erros "
         "em passos sucessivamente divididos por dois.")
    table([
        ["Método","Erro dt=0,2 s","Erro dt=0,025 s","Ordem observada"],
        *[[name,
           f"{rows[0]['error_c']:.4g}",
           f"{rows[-1]['error_c']:.4g}",
           f"{rows[-1]['observed_order']:.3f}"]
          for name,rows in temporal.items()]
    ],[145,120,125,115])
    para("Os valores resultam de cálculos reproduzíveis, não de sensores. A ordem "
         "observada depende de as soluções serem suaves e do regime assintótico.")
    head("4. Ordem de convergência espacial")
    para("A referência semidiscreta é comparada à solução exata contínua, "
         "sem introduzir erro temporal. Refinar N de 11 para 161 permite "
         "examinar a precisão de diferenças espaciais centradas.")
    table([
        ["Nós","dx (m)","Erro central (C)","Ordem"],
        *[[str(row["nodes"]),f"{row['dx_m']:.6g}",
           f"{row['error_c']:.4g}",
           "-" if row["observed_order"] is None else f"{row['observed_order']:.3f}"]
          for row in spatial],
    ],[80,140,160,125])
    story.append(PageBreak())
    head("5. Energia e verificação independente")
    eq("U = rho*c*A*dx * soma(T_i - Ta) [apenas pontos internos]")
    eq("U_final - U_inicial + integral(Q_fronteira dt) = 0")
    para("Os fluxos de fronteira foram integrados com a mesma ponderação theta "
         "do método discreto. O pequeno resíduo demonstra consistência algébrica "
         "do esquema. Não demonstra que os parâmetros ilustrativos correspondam a "
         "um dissipador real.")
    table([
        ["Método","Energia inicial (J)","Energia final (J)","Saída integrada (J)"],
        *[[name,f"{r.energy_initial_j:.4f}",
           f"{r.energy_final_j:.4f}",f"{r.boundary_energy_j:.4f}"]
          for name,r in results.items()]
    ],[130,130,120,125])
    head("6. Reprodutibilidade e limitações")
    eq("python -m pytest tests/test_heat_implicit.py -q")
    eq("PYTHONPATH=src python examples/generate_lab61_pdf.py")
    para("Todas as curvas e tabelas são obtidas pelo motor versionado e por "
         "parâmetros explícitos. Erros experimentais permanecem desconhecidos: "
         "falta medir potência, temperatura ambiente, resposta temporal, "
         "incerteza instrumental e condições de ventilação num computador real.")
    para("Os métodos numéricos 6.1 complementam, e não substituem, o laboratório "
         "6.0: modelos CPU-dissipador, bateria eletrotérmica e controlo PI.")
    head("Conclusão")
    para("A versão 6.1 acrescenta estabilidade, convergência e conservação "
         "como resultados mensuráveis e interpretáveis para a UC. "
         "A separação do erro temporal e espacial permite identificar as "
         "ordens do método sem atribuir incorretamente o erro da grelha ao "
         "integrador temporal. A validação física requer experiências independentes.")
    doc=SimpleDocTemplate(str(output),pagesize=A4,leftMargin=44,rightMargin=44,
                          topMargin=46,bottomMargin=50,
                          title="InProcess 6.1 - Numerical Physics")
    doc.build(story,onFirstPage=pages,onLaterPages=pages)
    return output


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,
                        default=Path("docs/relatorios/InProcess_Numerical_Physics_6_1.pdf"))
    args=parser.parse_args()
    print(build(args.output))
