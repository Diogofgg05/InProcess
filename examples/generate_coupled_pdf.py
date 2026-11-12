"""Generate the academic PDF from reproducible, simulated multi-physics models.

Usage:
  python examples/generate_coupled_pdf.py --output docs/relatorios/InProcess_Modelos_Fisicos_Acoplados.pdf
Requires reportlab. No real hardware is probed and no OS settings are changed.
"""
import argparse
import math
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                               TableStyle, PageBreak, Flowable, KeepTogether)

from expecto_process_manager.physics.coupled_models import TwoNodeThermal, BatteryThermalRC
from expecto_process_manager.physics.numerical.ode import solve_ivp

BLUE = colors.HexColor("#1555AB")
DARK = colors.HexColor("#14213B")
MUTED = colors.HexColor("#526376")
TEAL = colors.HexColor("#138B83")


class CurvePlot(Flowable):
    """Pure-vector plot; no matplotlib or raster dependencies."""
    def __init__(self, title, series, x_max, labels, y_min=None, y_max=None):
        Flowable.__init__(self)
        self.width, self.height = 470, 176
        self.title, self.series, self.x_max = title, series, x_max
        self.labels, self.y_min, self.y_max = labels, y_min, y_max

    def draw(self):
        c = self.canv
        x0, y0, w, h = 44, 28, 399, 116
        values = [v for _, points, _ in self.series for _, v in points]
        bottom = min(values) if self.y_min is None else self.y_min
        top = max(values) if self.y_max is None else self.y_max
        span = (top - bottom) or 1.0
        bottom -= .06 * span
        top += .06 * span
        c.setFillColor(DARK)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(0, self.height-14, self.title)
        c.setStrokeColor(colors.HexColor("#DAE1ED"))
        c.setLineWidth(.5)
        for n in range(5):
            yy = y0 + n*h/4
            c.line(x0, yy, x0+w, yy)
            c.setFillColor(MUTED)
            c.setFont("Helvetica", 7)
            c.drawRightString(x0-5, yy-2, f"{bottom+(top-bottom)*n/4:.2f}")
        c.setStrokeColor(MUTED)
        c.line(x0,y0,x0,y0+h)
        c.line(x0,y0,x0+w,y0)
        c.setFillColor(MUTED)
        c.drawCentredString(x0+w/2, 7, f"Tempo (s), 0 a {self.x_max:g}")
        for i, (name, samples, color) in enumerate(self.series):
            c.setStrokeColor(color)
            c.setLineWidth(1.7)
            path = c.beginPath()
            for j, (t,v) in enumerate(samples):
                xx = x0 + w*t/self.x_max
                yy = y0 + h*(v-bottom)/(top-bottom)
                if j==0: path.moveTo(xx,yy)
                else: path.lineTo(xx,yy)
            c.drawPath(path)
            c.setFont("Helvetica", 7)
            c.setFillColor(color)
            c.drawString(55+i*140, self.height-30, name)


def _page(c,doc):
    c.setStrokeColor(colors.HexColor("#D8E1ED"))
    c.line(42,36,A4[0]-42,36)
    c.setFont("Helvetica",8)
    c.setFillColor(MUTED)
    c.drawString(43,24,"InProcess | Modelacao Computacional de Sistemas Fisicos")
    c.drawRightString(A4[0]-43,24,f"Pagina {doc.page}")


def build_report(output):
    cpu = TwoNodeThermal()
    battery = BatteryThermalRC()
    cpu_init = (30.,26.)
    battery_init = (.85,0.,25.)
    cpu_sol = solve_ivp(cpu.rhs,cpu_init,(0.,240.),.5,"rk4")
    battery_sol = solve_ivp(battery.rhs,battery_init,(0.,120.),.2,"rk4")
    cpu_ref = [cpu.exact(t,cpu_init)[0] for t in cpu_sol.times]
    battery_ref = [battery.exact(t,battery_init) for t in battery_sol.times]
    cpu_n = [cpu.observables(y)["cpu_temp_c"] for y in cpu_sol.values]
    bat_n = [battery.observables(y)["terminal_voltage_v"] for y in battery_sol.values]
    cpu_err = math.sqrt(sum((a-b)**2 for a,b in zip(cpu_n,cpu_ref))/len(cpu_n))
    bat_err = math.sqrt(sum((a-b)**2 for a,b in zip(bat_n,battery_ref))/len(bat_n))
    if not cpu_err < 1e-4 or not bat_err < 1e-4:
        raise AssertionError("Numerical results disagree with independent reference.")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(str(output), pagesize=A4, rightMargin=46,leftMargin=46,
                            topMargin=48,bottomMargin=49, title="InProcess - Modelos fisicos acoplados",
                            author="Projeto InProcess | Relatorio academico reproduzivel")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="IPTitle",parent=styles["Title"],fontSize=22,leading=28,
                              textColor=DARK,spaceAfter=16))
    styles.add(ParagraphStyle(name="IPSub",parent=styles["Normal"],fontSize=11,leading=17,
                              textColor=MUTED,spaceAfter=11))
    styles.add(ParagraphStyle(name="IPBody",parent=styles["BodyText"],fontSize=9.4,leading=14.1,
                              spaceAfter=9,textColor=DARK))
    styles.add(ParagraphStyle(name="IPH",parent=styles["Heading2"],fontSize=13.5,leading=18,
                              spaceBefore=15,spaceAfter=9,textColor=BLUE))
    styles.add(ParagraphStyle(name="IPEq",parent=styles["BodyText"],fontName="Courier",fontSize=8.5,
                              leading=13,spaceAfter=10,textColor=DARK))
    S=[]
    def para(t):S.append(Paragraph(t,styles["IPBody"]))
    def head(t):S.append(Paragraph(t,styles["IPH"]))
    def eq(t):S.append(Paragraph(t,styles["IPEq"]))
    def tbl(rows,widths=None):
        data=[[Paragraph(str(v),styles["IPBody"]) for v in row] for row in rows]
        t=Table(data,colWidths=widths,repeatRows=1,hAlign="LEFT")
        t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#EAF1FA")),
          ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F5F8FC")]),
          ("GRID",(0,0),(-1,-1),.35,colors.HexColor("#D5DFEA")),
          ("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),8),
          ("RIGHTPADDING",(0,0),(-1,-1),8),("TOPPADDING",(0,0),(-1,-1),7),
          ("BOTTOMPADDING",(0,0),(-1,-1),5)]))
        S.append(t)

    S.append(Spacer(1,45))
    S.append(Paragraph("InProcess",styles["IPTitle"]))
    S.append(Paragraph("Laboratorio de Modelacao Computacional de Sistemas Fisicos",styles["IPSub"]))
    S.append(Paragraph("<b>Relatorio tecnico - Modelos fisicos acoplados e validacao numerica</b>",styles["IPSub"]))
    para("Versao do estudo: 5.1 | Data: novembro de 2026 | Estado: resultados de simulacao "
         "reproduzivel. Nao foram feitas medicoes de sensores, ensaios de hardware ou "
         "medicoes reais de energia. Sem autor/numero mecanografico presumidos.")
    S.append(Spacer(1,16))
    head("Resumo")
    para("O InProcess integra a monitorizacao de processos com um laboratorio computacional. "
         "Esta extensao incorpora dois modelos acoplados de relevancia direta ao hardware: "
         "(i) transferencia termica CPU-dissipador-ambiente com duas capacitancias e "
         "(ii) bateria equivalente de Thevenin com estado de carga, polarizacao RC e perdas termicas. "
         "A resolucao usa Euler, Heun e Runge-Kutta de quarta ordem (RK4) e inclui "
         "solucoes analiticas independentes para as grandezas principais.")
    head("Pergunta e objetivos")
    para("Como traduzir leis de conservacao em EDO de primeira ordem, integrando energia e "
         "transferencia de calor sem confundir grandezas simuladas com telemetria real? "
         "Objetivos: formular os sistemas, comparar integradores, testar balancos e "
         "interpretar limites de validade. Esta entrega nao demonstra que o InProcess "
         "reduz consumo energetico num computador real.")
    head("1. Conteudos programaticos e metodologia")
    tbl([["Conteudo","Aplicacao no projeto"],["Leis de conservacao","Balancos de energia termica, quimica e eletrica"],
         ["Equacoes diferenciais","Sistemas de 2 e 3 variaveis de estado"],
         ["Integracao numerica","Euler, Heun, RK4 e estudo da discretizacao"],
         ["Validacao","Referencias analiticas, erros RMSE e energia residual"],
         ["Analise critica","Dominios fisicos, condicoes iniciais e limites de sensores"]],
        [190,320])
    S.append(PageBreak())

    head("2. Modelo termico CPU - dissipador")
    para("Considera-se uma capacitancia termica associada ao die do CPU (C1) e outra "
         "associada ao dissipador (C2), ligadas por condutancia Gi; a transferencia "
         "para o ambiente e representada por Ga. Por conservacao de energia:")
    eq("C1 dT1/dt = P - Gi (T1 - T2)")
    eq("C2 dT2/dt = Gi (T1 - T2) - Ga (T2 - Ta)")
    para("Para potencia P e ambiente Ta constantes, o equilibrio e:")
    eq("T2eq = Ta + P/Ga;    T1eq = T2eq + P/Gi")
    tbl([["Parametro","Valor ilustrativo"],["C1; C2","120 J/K; 280 J/K"],
         ["Gi; Ga","6 W/K; 1,2 W/K"],["P; Ta","70 W; 24 graus Celsius"],
         ["T1(0); T2(0)","30; 26 graus Celsius"]],
         [220,290])
    para("O modelo e linear e admite solucao fechada por autovalores reais da matriz "
         "de transferencia. Essa referencia e calculada independentemente do RK4; "
         "o equilibrio nao representa o valor real ou o limite seguro de um CPU.")
    cpu_p = [(t,v) for t,v in zip(cpu_sol.times,cpu_n)]
    cpu_a = [(t,v) for t,v in zip(cpu_sol.times,cpu_ref)]
    S.append(CurvePlot("Temperatura do CPU: referencia vs RK4",
                       [("RK4",cpu_p,BLUE),("Analitica",cpu_a,TEAL)],240,"s"))
    para(f"Resultado numerico: Tcpu(240 s) = {cpu_n[-1]:.4f} graus Celsius; "
         f"RMSE perante solucao fechada = {cpu_err:.3e} graus Celsius. "
         f"Equilibrio previsto = {cpu.equilibrium[0]:.3f} graus Celsius. "
         "Os valores sao apenas hipoteticos.")
    head("Balanco de energia e interpretacao")
    eq("d[C1(T1-Ta)+C2(T2-Ta)]/dt = P - Ga(T2-Ta)")
    para("O fluxo interno Gi(T1-T2) cancela ao somar as duas equacoes. "
         "Assim nao se conta a mesma potencia termica duas vezes. A validacao "
         "analitica do balanco e uma verificacao da implementacao, nao do hardware.")
    S.append(PageBreak())

    head("3. Bateria: modelo equivalente RC e aquecimento")
    para("O modelo de Thevenin utiliza estado de carga s, tensao de polarizacao u e "
         "temperatura T. A corrente I e positiva na descarga; Q representa a carga "
         "nominal em coulombs; R0 as perdas ohmicas e Rp/Cp a polarizacao:")
    eq("Q ds/dt = -I                (Q = 3600 * capacidade_Ah)")
    eq("Cp du/dt = I - u/Rp")
    eq("Cth dT/dt = I^2 R0 + u^2/Rp - k(T-Ta)")
    eq("Vterminal = Voc(s) - I R0 - u")
    para("O termo Voc(s) e uma aproximacao linear idealizada entre 10,0 e 12,6 V "
         "(nao representa uma curva experimental de uma bateria de computador). "
         "A solucao fechada do estado de carga e da polarizacao permite verificar "
         "a tensao terminal independentemente do integrador.")
    tbl([["Parametro","Valor ilustrativo"],["Capacidade; corrente","4 Ah; 2 A"],
         ["R0; Rp; Cp","0,07 ohm; 0,04 ohm; 1500 F"],
         ["Cth; k; Ta","120 J/K; 0,55 W/K; 25 graus Celsius"],
         ["SOC(0); u(0); T(0)","0,85; 0 V; 25 graus Celsius"]],
         [230,280])
    bat_p = [(t,v) for t,v in zip(battery_sol.times,bat_n)]
    bat_a = [(t,v) for t,v in zip(battery_sol.times,battery_ref)]
    S.append(CurvePlot("Tensao terminal: referencia vs RK4",
                       [("RK4",bat_p,BLUE),("Analitica",bat_a,TEAL)],120,"s"))
    para(f"Resultado numerico: V(120 s) = {bat_n[-1]:.6f} V; "
         f"RMSE = {bat_err:.3e} V; estado de carga final = {battery_sol.values[-1][0]:.5f}. "
         "Nao foi medida qualquer bateria real.")
    head("Balanco energetico")
    eq("d(Equim + Epol + Eterm)/dt = -I * Vterminal - k(T-Ta)")
    para("Equim e a integral da tensao em circuito aberto face ao estado de carga; "
         "Epol = Cp*u^2/2; Eterm = Cth*(T-Ta). O calor gerado pelas "
         "resistencias aparece como energia termica, conservando o balanco "
         "global do modelo. A energia descarregada nao equivale automaticamente "
         "a energia na tomada.")
    S.append(PageBreak())

    head("4. Metodos numericos e verificacoes")
    para("As EDO sao resolvidas com passo fixo e tempo final alinhado. "
         "Euler tem erro global de ordem 1; Heun de ordem 2; RK4 de ordem 4 "
         "no regime de solucoes suficientemente suaves e passos estaveis. "
         "Um passo numerico pequeno nao melhora a validade de parametros fisicos.")
    tbl([["Experiencia","Passo","Grandeza","RMSE RK4"],
         ["Dois nos termicos","0,5 s","Temperatura CPU",f"{cpu_err:.3e} graus C"],
         ["Bateria RC","0,2 s","Tensao terminal",f"{bat_err:.3e} V"]],
        [150,75,150,135])
    para("A verificacao automatica requer convergencia face a referencias "
         "independentes e coerencia dos balancos. Foram mantidos testes "
         "de erros de parametros, dominios fisicos e exportacao com proveniencia.")
    head("5. Reprodutibilidade")
    eq("python -m pytest tests/test_coupled_models.py -q")
    eq("python examples/generate_coupled_pdf.py --output docs/relatorios/InProcess_Modelos_Fisicos_Acoplados.pdf")
    para("O projeto identifica cada experiencia como SIMULATED e guarda "
         "metadados com parametros, unidades SI, condicoes iniciais e metodos. "
         "Os relatorios sao recalculados por codigo versionado; para reproduzir "
         "os valores deve usar-se a mesma revisao Git e a mesma configuracao.")
    head("6. Limitacoes e trabalho futuro")
    para("Os parametros nao foram calibrados com sensores reais; a potencia termica "
         "do CPU nao foi medida. O segundo modelo usa curva Voc(s) linear, corrente "
         "constante e uma unica dinamica RC: nao considera envelhecimento, "
         "histerese, dependencia de temperatura ou tensoes de celulas individuais. "
         "Futuro: repeticoes experimentais, incerteza de sensores, identificacao "
         "de parametros, validacao em treino/teste separados e comparacao "
         "de energia por tarefa com fronteiras equivalentes.")
    head("Bibliografia e apoio")
    para("OpenStax, University Physics Vol. 2, circuitos RC/RL e energia "
         "(https://openstax.org/books/university-physics-volume-2).")
    para("NREL, Battery Models, equivalent-circuit and thermal modelling "
         "(https://www.nrel.gov/transportation/battery-models). "
         "As referencias fundamentam ideias gerais, nao certificam os "
         "parametros ilustrativos do InProcess.")
    para("<b>Conclusao:</b> os novos sistemas mostram uma aplicacao "
         "tecnicamente fundamentada de equacoes diferenciais, conservacao "
         "de energia e integracao numerica a fenomenos de hardware. "
         "A validade experimental permanece uma fase distinta.")
    doc.build(S,onFirstPage=_page,onLaterPages=_page)
    return output


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,
                        default=Path("docs/relatorios/InProcess_Modelos_Fisicos_Acoplados.pdf"))
    args=parser.parse_args()
    print(build_report(args.output))
