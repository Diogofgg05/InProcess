"""Build the InProcess academic PDF from its real simulation modules.

Run: python scripts/generate_academic_pdf.py
Dependencies: reportlab and the InProcess Python package.
"""
from datetime import date
from pathlib import Path
import math

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Flowable,
)
from expecto_process_manager.physics.coupled_models import TwoNodeThermal, BatteryThermalRC
from expecto_process_manager.physics.numerical.ode import solve_ivp

DEST = Path("docs/relatorios/InProcess_Modelacao_Sistemas_Fisicos.pdf")
BLUE = colors.HexColor("#1761B9")
DARK = colors.HexColor("#1D2D4B")
LIGHT = colors.HexColor("#EDF4FD")


class Figure(Flowable):
    """Compact vector chart, drawn directly into PDF (no external images)."""

    def __init__(self, title, x, series, unit):
        super().__init__()
        self.title, self.x, self.series, self.unit = title, x, series, unit
        self.width, self.height = 172*mm, 78*mm

    def draw(self):
        c = self.canv
        ox, oy = 24*mm, 16*mm
        w, h = self.width-31*mm, self.height-27*mm
        values = [v for _, serie, _ in self.series for v in serie]
        ymin, ymax = min(values), max(values)
        padding = max(0.01, 0.08*(ymax-ymin))
        ymin -= padding
        ymax += padding
        xmin, xmax = self.x[0], self.x[-1]
        c.setFillColor(DARK)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(3*mm, self.height-5*mm, self.title)
        c.setFont("Helvetica", 7)
        c.setStrokeColor(colors.HexColor("#A7B6C9"))
        c.line(ox,oy,ox,oy+h)
        c.line(ox,oy,ox+w,oy)
        for i in range(5):
            yy=oy+i*h/4
            c.setStrokeColor(colors.HexColor("#E4EAF4"))
            c.line(ox,yy,ox+w,yy)
            c.setFillColor(DARK)
            c.drawRightString(ox-2*mm,yy-2,f"{ymin+i*(ymax-ymin)/4:.2f}")
            c.drawCentredString(ox+i*w/4,oy-5*mm,f"{xmin+i*(xmax-xmin)/4:.0f}")
        c.drawCentredString(ox+w/2,oy-10*mm,"Tempo (s)")
        c.drawString(3*mm,self.height-12*mm,self.unit)
        for n,(name,serie,color) in enumerate(self.series):
            c.setStrokeColor(colors.HexColor(color))
            c.setLineWidth(1.3)
            path=c.beginPath()
            factor=max(1,len(self.x)//600)
            indices=list(range(0,len(self.x),factor))
            if indices[-1]!=len(self.x)-1:indices.append(len(self.x)-1)
            for k,i in enumerate(indices):
                xx=ox+(self.x[i]-xmin)/(xmax-xmin)*w
                yy=oy+(serie[i]-ymin)/(ymax-ymin)*h
                (path.moveTo if k==0 else path.lineTo)(xx,yy)
            c.drawPath(path)
            c.setFont("Helvetica",7)
            c.setFillColor(colors.HexColor(color))
            c.drawString(ox+n*50*mm,self.height-18*mm,name)


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#D7E0EB"))
    canvas.line(20*mm,18*mm,190*mm,18*mm)
    canvas.setFillColor(DARK)
    canvas.setFont("Helvetica",8)
    canvas.drawString(20*mm,13*mm,"InProcess 5.1 | Modelacao Computacional de Sistemas Fisicos")
    canvas.drawRightString(190*mm,13*mm,str(doc.page))
    canvas.restoreState()


def create_pdf(destination=DEST):
    destination=Path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name="InTitle",parent=styles["Title"],fontName="Helvetica-Bold",
                              fontSize=24,leading=29,textColor=DARK,spaceAfter=18))
    styles.add(ParagraphStyle(name="InHeading",parent=styles["Heading2"],fontSize=13,
                              leading=17,spaceBefore=10,spaceAfter=5,textColor=BLUE))
    styles.add(ParagraphStyle(name="InBody",parent=styles["BodyText"],fontSize=9.5,
                              leading=14,spaceAfter=8,textColor=DARK))
    styles.add(ParagraphStyle(name="InEq",parent=styles["BodyText"],fontName="Courier",
                              fontSize=8.2,leading=13,spaceAfter=9,leftIndent=10,
                              backColor=LIGHT,borderPadding=6,textColor=DARK))
    items=[]
    def paragraph(t,style="InBody"):items.append(Paragraph(t,styles[style]))
    def heading(t):paragraph(t,"InHeading")
    def eq(t):paragraph(t,"InEq")
    def table(rows, widths):
        view=Table(rows,colWidths=widths,repeatRows=1,hAlign="LEFT")
        view.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),BLUE),
            ("TEXTCOLOR",(0,0),(-1,0),colors.white),
            ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,LIGHT]),
            ("FONTSIZE",(0,0),(-1,-1),8),
            ("VALIGN",(0,0),(-1,-1),"TOP"),
            ("TOPPADDING",(0,0),(-1,-1),6),
            ("BOTTOMPADDING",(0,0),(-1,-1),6),
        ]))
        items.append(view)

    items.append(Spacer(1,29*mm))
    paragraph("INPROCESS","InTitle")
    heading("Modelos fisicos acoplados no hardware de um computador")
    paragraph("Relatorio tecnico-academico | Modelacao Computacional de Sistemas Fisicos")
    paragraph("Versao 5.1 | Data: "+date.today().strftime("%d/%m/%Y"))
    items.append(Spacer(1,13*mm))
    paragraph("<b>Natureza dos resultados:</b> SIMULATED. Os graficos provem de modelos "
              "matematicos idealizados, nao de sensores fisicos calibrados.")
    paragraph("<b>Objetivo:</b> aprofundar a modelacao com sistemas de equacoes "
              "diferenciais acopladas, conservacao de energia e verificacao de "
              "algoritmos Euler, Heun e Runge-Kutta de quarta ordem.")
    items.append(PageBreak())

    heading("1. Enquadramento na unidade curricular")
    paragraph("O InProcess liga a monitorizacao de processos ao estudo fisico de "
              "energia, calor, corrente eletrica e metodos numericos. As simulacoes "
              "complementam a interface, mas nao controlam o hardware.")
    table([
        ["Conteudo", "Aplicacao concreta"], 
        ["C1 - Grandezas e medida", "Unidades SI, origem de dados e incerteza"],
        ["C2 - Dinamica", "Rotor de ventoinha e momento angular"],
        ["C3 - Vibracoes", "Massa-mola-amortecedor e resposta forçada"],
        ["C4 - Ondas", "Ondas acusticas e transformada FFT"],
        ["C5 - Eletricidade", "Lei de Ohm, resistencia e circuitos RC"],
        ["C6 - Eletromagnetismo", "Circuito RL, bobinas e motor"],
        ["C7 - Termodinamica", "CPU e dissipador; bateria e perdas Joule"],
        ["C8 - Sistemas nao lineares", "Controlo termico com saturacao"],
        ["C9 - Metodos computacionais", "EDOs, quadraturas, erro e convergencia"],
    ],[53*mm,118*mm])
    heading("2. Metodologia")
    paragraph("Para cada modelo: formular leis fisicas, explicitar hipoteses, "
              "definir parametros e condicoes iniciais, integrar as EDOs, comparar "
              "solucoes com referencias analiticas independentes, verificar "
              "balancos energeticos e avaliar a convergencia em funcao do passo h.")

    model=TwoNodeThermal()
    initial=(30.,26.)
    sol=solve_ivp(model.rhs,initial,(0,240),.5,"rk4")
    die=[v[0] for v in sol.values]
    sink=[v[1] for v in sol.values]
    exact=[model.exact(t,initial)[0] for t in sol.times]
    err=max(abs(a-b) for a,b in zip(die,exact))
    items.append(PageBreak())
    heading("3. Modelo fisico acoplado CPU - dissipador")
    paragraph("Dois volumes termicos armazenam calor; a interface conduz calor "
              "do CPU para o dissipador e este troca calor com o ambiente. "
              "A energia transferida pela interface e interna ao sistema.")
    eq("Ccpu dTcpu/dt = P - Gi (Tcpu - Ts)")
    eq("Cs dTs/dt = Gi (Tcpu - Ts) - Ga (Ts - Ta)")
    eq("dE/dt = P - Ga (Ts - Ta)")
    paragraph("Parametros ilustrativos: Ccpu=120 J/K, Cs=280 J/K, Gi=6 W/K, "
              "Ga=1,2 W/K, Ta=24 graus C e P=70 W. Estado inicial: 30 e 26 graus C.")
    paragraph(f"Equilibrio: CPU={model.equilibrium[0]:.3f} graus C; "
              f"dissipador={model.equilibrium[1]:.3f} graus C. "
              f"Aos 240 s: CPU={die[-1]:.3f}, dissipador={sink[-1]:.3f} graus C. "
              f"Erro maximo RK4 vs. referencia analitica: {err:.3g} graus C.")
    items.append(Figure("CPU e dissipador",sol.times,[
        ("CPU RK4",die,"#1761B9"),
        ("Dissipador RK4",sink,"#139B83"),
        ("CPU analitica",exact,"#C9813A")],"Temperatura (graus C)"))
    paragraph("Hipoteses: coeficientes constantes, nos concentrados, regime linear, "
              "potencia conhecida. Sem modelacao 3D, firmware ou leituras reais.")

    b=BatteryThermalRC()
    state=(.85,0.,25.)
    bs=solve_ivp(b.rhs,state,(0,120),.2,"rk4")
    voltage=[b.observables(y)["terminal_voltage_v"] for y in bs.values]
    temp=[y[2] for y in bs.values]
    reference=[b.exact(t,state) for t in bs.times]
    verr=max(abs(a-z) for a,z in zip(voltage,reference))
    items.append(PageBreak())
    heading("4. Bateria: circuito eletrico RC e transferencia de calor")
    paragraph("Circuito equivalente de Thevenin com resistencia interna R0, "
              "ramo de polarizacao Rp-Cp, estado de carga SOC e um no termico.")
    eq("Q ds/dt = -I        ;     Cp du/dt = I - u/Rp")
    eq("Vterminal = OCV(s) - I R0 - u")
    eq("Cth dT/dt = I^2 R0 + u^2/Rp - k (T-Ta)")
    eq("d(Echem+Ecap+Eterm)/dt = -I Vterminal - k (T-Ta)")
    paragraph("Parametros hipoteticos: capacidade 4 Ah, I=2 A, "
              "R0=0,07 ohm, Rp=0,04 ohm, Cp=1500 F, Cth=120 J/K, "
              "k=0,55 W/K e Ta=25 graus C. "
              "A curva OCV(s)=10+2,6s e linear apenas por simplificacao.")
    paragraph(f"Aos 120 s: SOC={bs.values[-1][0]*100:.3f}%, "
              f"tensao terminal={voltage[-1]:.5f} V; "
              f"temperatura={temp[-1]:.3f} graus C. "
              f"Erro maximo de tensao RK4 vs. referencia analitica={verr:.3g} V.")
    items.append(Figure("Tensao de descarga",bs.times,[
        ("RK4",voltage,"#1761B9"),("Analitica",reference,"#C9813A")],"Tensao (V)"))
    paragraph("As perdas resistivas convertem energia eletrica em calor. "
              "A energia no ramo RC e contabilizada de forma independente. "
              "O modelo nao estima saude, seguranca ou autonomia reais da bateria.")

    items.append(PageBreak())
    heading("5. Convergencia dos metodos numericos")
    rows=[["Modelo", "Metodo", "Erro h=4", "Erro h=2", "Erro h=1"]]
    for name,physical,init,value,exact_fn in [
        ("CPU",model,initial,lambda y:y[0],lambda t:model.exact(t,initial)[0]),
        ("Bateria",b,state,lambda y:b.observables(y)["terminal_voltage_v"],lambda t:b.exact(t,state)),
    ]:
        for method in ("euler","heun","rk4"):
            errors=[]
            for h in (4,2,1):
                r=solve_ivp(physical.rhs,init,(0,40),h,method)
                errors.append(abs(value(r.values[-1])-exact_fn(40)))
            rows.append([name,method.upper(),*[f"{e:.4g}" for e in errors]])
    table(rows,[35*mm,29*mm,35*mm,35*mm,37*mm])
    paragraph("Erros absolutos no mesmo instante final, com h sucessivamente "
              "reduzido. O metodo RK4 oferece, em geral, menor erro para um "
              "mesmo passo em EDOs suficientemente regulares. "
              "Precisao numerica nao certifica os parametros fisicos.")
    heading("6. Aplicacao no InProcess")
    paragraph("Os modelos estao disponiveis no Laboratorio, nos grupos Modelo "
              "Termico e Energia. Os utilizadores podem alterar parametros e "
              "condicoes iniciais, executar Euler/Heun/RK4 e exportar CSV, JSON "
              "e relatórios HTML com proveniencia SIMULATED. "
              "As operacoes nao alteram prioridades, processos ou frequencias.")
    heading("7. Limitacoes e trabalho futuro")
    paragraph("Sao necessarias medicoes instrumentais de potencia, temperaturas, "
              "corrente, ambiente e registos independentes para calibrar os "
              "coeficientes. A validacao real deve reservar dados nao usados "
              "na estimacao de parametros e incluir incerteza e repeticoes.")

    items.append(PageBreak())
    heading("8. Reproducibilidade")
    eq('python -m pip install -e \".[dev]\" reportlab')
    eq("python -m pytest tests/test_coupled_models.py -q")
    eq("python scripts/generate_academic_pdf.py")
    paragraph("O documento e produzido a partir de modelos existentes em "
              "src/expecto_process_manager/physics/coupled_models.py. "
              "A origem permanece SIMULATED; nenhuma figura e apresentada "
              "como medicao experimental.")
    heading("9. Referencias e documentacao")
    paragraph("[1] OpenStax, University Physics, Vol. 1, dinamica, energia e "
              "oscilacoes. https://openstax.org/details/books/university-physics-volume-1")
    paragraph("[2] OpenStax, University Physics, Vol. 2, circuitos eletricos, "
              "capacitancia e indutancia. https://openstax.org/details/books/university-physics-volume-2")
    paragraph("[3] NIST, International System of Units (SI). https://physics.nist.gov/cuu/Units/")
    paragraph("[4] Chapra &amp; Canale, Numerical Methods for Engineers, "
              "integracao de equacoes diferenciais.")
    paragraph("[5] Repositorio do projeto InProcess, codigo dos modelos, "
              "testes de regressao e evidencias de GitHub Actions.")
    heading("10. Conclusao")
    paragraph("As duas experiencias ampliam o programa cientifico do InProcess "
              "com sistemas acoplados relevantes para computadores, "
              "verificacoes de energia e referencias analiticas. "
              "A natureza idealizada das simulacoes permanece identificada.")

    doc=SimpleDocTemplate(str(destination),pagesize=A4,
        leftMargin=19*mm,rightMargin=19*mm,topMargin=19*mm,bottomMargin=24*mm,
        title="InProcess - Modelacao Computacional de Sistemas Fisicos",
        author="Projeto InProcess")
    doc.build(items,onFirstPage=footer,onLaterPages=footer)
    print(destination.resolve())
    return destination


if __name__ == "__main__":
    create_pdf()
