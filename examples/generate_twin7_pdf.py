"""Generate academic Digital Twin 7.0 report from versioned synthetic data.

All estimates are from simulated input only. No measured data are
automatically validated or converted from CPU percentages.
"""
import argparse
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,Flowable
)
from expecto_process_manager.physics.digital_twin7 import (
    synthetic_thermal_series,calibrate_twin,forecast_scenario,
)

DARK=colors.HexColor("#15243A")
BLUE=colors.HexColor("#2169D7")
TEAL=colors.HexColor("#0A8C84")
MUTED=colors.HexColor("#586A7C")


class Chart(Flowable):
    def __init__(self,series,title):
        Flowable.__init__(self)
        self.width,self.height=470,205
        self.series,self.title=series,title

    def draw(self):
        c=self.canv
        left,bottom,w,h=52,29,382,120
        xs=[x for name,data,col in self.series for x,y in data]
        ys=[y for name,data,col in self.series for x,y in data]
        x0,x1=min(xs),max(xs)
        y0,y1=min(ys),max(ys)
        pad=max((y1-y0)*.08,.01)
        y0-=pad
        y1+=pad
        c.setFont("Helvetica-Bold",10)
        c.setFillColor(DARK)
        c.drawString(5,190,self.title)
        c.setFont("Helvetica",7)
        for k in range(5):
            yy=bottom+h*k/4
            c.setStrokeColor(colors.HexColor("#DEE7F1"))
            c.line(left,yy,left+w,yy)
            c.setFillColor(MUTED)
            c.drawRightString(left-4,yy-2,f"{y0+(y1-y0)*k/4:.2f}")
        c.setStrokeColor(MUTED)
        c.line(left,bottom,left+w,bottom)
        c.line(left,bottom,left,bottom+h)
        c.setFillColor(MUTED)
        c.drawCentredString(left+w/2,10,"Tempo (s)")
        for i,(name,data,col) in enumerate(self.series):
            c.setStrokeColor(col)
            c.setLineWidth(1.7)
            path=c.beginPath()
            for k,(x,y) in enumerate(data):
                xx=left+w*(x-x0)/(x1-x0 or 1)
                yy=bottom+h*(y-y0)/(y1-y0)
                if k==0:path.moveTo(xx,yy)
                else:path.lineTo(xx,yy)
            c.drawPath(path)
            c.setFillColor(col)
            c.drawString(13+i*180,165,name)


def build(path):
    series=synthetic_thermal_series()
    report=calibrate_twin(series)
    model=report.model
    val=report.validation
    future=forecast_scenario(series,report,power_w=60,ambient_c=24,horizon_s=120.)
    assert report.origin=="SIMULATED"
    assert model.tau_s>0 and model.resistance_k_w>0 and model.capacity_j_k>0
    output=Path(path)
    output.parent.mkdir(parents=True,exist_ok=True)
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name="dTitle",parent=styles["Title"],fontSize=22,leading=27,textColor=DARK,spaceAfter=17))
    styles.add(ParagraphStyle(name="dHead",parent=styles["Heading2"],fontSize=13,leading=18,textColor=BLUE,spaceBefore=12,spaceAfter=7))
    styles.add(ParagraphStyle(name="dText",parent=styles["BodyText"],fontSize=9.3,leading=13.6,textColor=DARK,spaceAfter=10))
    styles.add(ParagraphStyle(name="dEq",parent=styles["BodyText"],fontName="Courier",fontSize=8.5,leading=12,textColor=TEAL,spaceAfter=9))
    story=[Spacer(1,32)]
    def title(t):story.append(Paragraph(t,styles["dTitle"]))
    def head(t):story.append(Paragraph(t,styles["dHead"]))
    def para(t):story.append(Paragraph(t,styles["dText"]))
    def equation(t):story.append(Paragraph(t,styles["dEq"]))
    def table(rows,widths):
        grid=Table([[Paragraph(str(item),styles["dText"]) for item in row] for row in rows],
                   colWidths=widths,repeatRows=1,hAlign="LEFT")
        grid.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#E9F1FC")),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F5F8FC")]),
            ("GRID",(0,0),(-1,-1),.4,colors.HexColor("#DCE5F0")),
            ("VALIGN",(0,0),(-1,-1),"TOP"),
            ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),4)
        ]))
        story.append(grid)
    def footer(canvas,doc):
        canvas.setStrokeColor(colors.HexColor("#DCE5F0"))
        canvas.line(42,35,A4[0]-42,35)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica",8)
        canvas.drawString(42,23,"InProcess 7.0 | Modelacao Computacional de Sistemas Fisicos")
        canvas.drawRightString(A4[0]-42,23,f"Pagina {doc.page}")

    title("InProcess 7.0 | Thermal Digital Twin")
    para("<b>Identificacao fisica de parametros, treino e validacao temporal, "
         "previsao e limites de confianca</b>")
    para("Relatorio cientifico reproduzivel | novembro de 2026 | "
         "DADOS SINTETICOS (SIMULATED). Nenhum sensor real foi validado.")
    head("Resumo")
    para("Esta experiencia usa um modelo termico de primeira ordem, "
         "equivalente a uma resistencia e capacidade termicas, "
         "para identificar a constante de tempo e prever temperaturas. "
         "A calibracao usa um bloco inicial de dados e a validacao "
         "usa exclusivamente instantes posteriores, com previsao recursiva. "
         "Calculam-se erros, um baseline de persistencia e limites de extrapolacao.")
    head("Objetivos da unidade curricular")
    table([
        ["Matematica e fisica","Aplicacao"],
        ["EDO de primeira ordem","Capacidade e resistencia termicas"],
        ["Modelacao discreta","Solução exata por amostragem ZOH"],
        ["Estimacao de parametros","Minimos quadrados e identificabilidade"],
        ["Validacao independente","Separacao cronologica entre treino e teste"],
        ["Erro experimental","RMSE, MAE, viés, R2 e baseline"],
        ["Previsao","Propagacao futura de temperatura sob entradas hipoteticas"],
    ],[194,312])
    story.append(PageBreak())
    head("1. Modelo termico concentrado")
    equation("C * dT/dt = P(t) - (T-Ta)/R")
    para("Aqui C e a capacidade termica em J/K, R a resistencia termica "
         "em K/W, P a potencia termica em W e Ta a temperatura ambiente. "
         "Quando P e Ta sao constantes no intervalo amostral dt, "
         "a discretizacao de ordem zero e exata:")
    equation("T[k+1]-Ta[k] = a*(T[k]-Ta[k]) + b*P[k]")
    equation("a=exp(-dt/tau), b=R*(1-a), tau=R*C")
    para("Para estimar a,b, faz-se regressao linear de dois parametros "
         "sobre amostras temporais do treino. A solucao so e aceite "
         "se 0&lt;a&lt;1 e b&gt;0. Entradas sem excitação suficiente "
         "sao rejeitadas porque nao identificam parametros univocamente.")
    table([
        ["Propriedade","Estimativa sintetica"],
        ["Passo de amostragem",f"{model.dt_s:.4g} s"],
        ["Resistencia R",f"{model.resistance_k_w:.6f} K/W"],
        ["Capacidade C",f"{model.capacity_j_k:.4f} J/K"],
        ["Constante tau",f"{model.tau_s:.4f} s"],
        ["Coeficiente discreto a",f"{model.a:.8f}"],
        ["Coeficiente discreto b",f"{model.b:.8f}"],
    ],[242,265])
    head("2. Dados e protocolo")
    para("A serie gerada tem 300 observacoes sintéticas com cargas termicas "
         "variaveis e temperatura ambiente tambem variavel. "
         f"O bloco inicial contem {report.train_points} observacoes; "
         f"a validacao avalia {val.points} previsoes posteriores. "
         "Nao existe reordenacao aleatoria nem fuga de temperatura do futuro "
         "para a estimativa do modelo.")
    story.append(PageBreak())
    head("3. Resultados de validação temporal")
    story.append(Chart([
        ("Observação sintética",list(zip(report.validation_times_s,
                                        report.validation_measured_c)),BLUE),
        ("Previsão autónoma",list(zip(report.validation_times_s,
                                    report.validation_predicted_c)),TEAL),
    ],"Validação futura: observacao vs previsão"))
    table([
        ["Indicador","Resultado no holdout"],
        ["RMSE",f"{val.rmse_c:.6g} C"],
        ["MAE",f"{val.mae_c:.6g} C"],
        ["Viés",f"{val.bias_c:.6g} C"],
        ["RMSE persistência",f"{val.persistence_rmse_c:.6g} C"],
        ["Skill vs persistência",str(val.skill_vs_persistence)],
        ["R2",str(val.r_squared)],
        ["P90 empirico de |erro|",f"{val.observed_abs_error_p90_c:.6g} C"],
    ],[250,257])
    para("O P90 e um quantil observado dos erros deste teste e NAO "
         "um intervalo de confianca calibrado. Um resultado com erro "
         "pequeno sobre dados sintéticos não prova qualidade sobre dados reais.")
    head("4. Previsão hipotética")
    story.append(Chart([
        ("Previsão P=60W, Ta=24C",list(zip(*future)),TEAL),
    ],"Cenario sob potência termica constante"))
    para(f"Temperatura simulada no final de 120 s: {future[1][-1]:.5f} C. "
         "Esta previsão é permitida apenas dentro das faixas observadas "
         "de potência e temperatura ambiente no treino.")
    story.append(PageBreak())
    head("5. Identificabilidade, limitações e segurança")
    para("A capacidade e resistencia nao podem ser inferidas apenas "
         "de percentagens de CPU, consumo de RAM ou potencia eletrica "
         "de uma placa sem uma conversao fisica apropriada. "
         "As séries CSV exigem tempo, temperatura do componente, "
         "temperatura ambiente e potencia termica em SI; "
         "sao rotuladas MEASURED_UNVERIFIED, nunca automaticamente "
         "consideradas calibradas.")
    para("O modelo de um unico no omite a dinamica do dissipador, "
         "ventoinha e materiais não uniformes. Uma melhoria futura "
         "será comparar dois nós térmicos e modelos de difusão 2D "
         "com dados reais e incertezas instrumentais. A estimativa "
         "pontual e a divisão cronologica são necessárias mas "
         "insuficientes para demonstrar validação científica completa.")
    head("6. Reprodução")
    equation("python -m pytest tests/test_digital_twin7.py -q")
    equation("PYTHONPATH=src python examples/generate_twin7_pdf.py")
    para("O software não altera processos, planos energéticos, "
         "sensores ou ventiladores. A previsão de uma temperatura "
         "não constitui diagnóstico de segurança térmica e "
         "não autoriza alterações automáticas de hardware.")
    head("Conclusão")
    para("O InProcess 7.0 acrescenta a identificação de parâmetros, "
         "validacao sem fuga de informação, métricas comparáveis, "
         "previsão e limites explícitos de extrapolação. "
         "A validação experimental com sensores físicos continua "
         "como próximo objetivo.")
    doc=SimpleDocTemplate(str(output),pagesize=A4,leftMargin=45,rightMargin=45,
                          topMargin=49,bottomMargin=50,
                          title="InProcess 7.0 Thermal Digital Twin")
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return output


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,
        default=Path("docs/relatorios/InProcess_Thermal_Digital_Twin_7_0.pdf"))
    args=parser.parse_args()
    print(build(args.output))
