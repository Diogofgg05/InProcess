"""InProcess 7.3–8.0 academic-methodology PDF.

This report intentionally contains NO fabricated Windows/Linux measurements.
It presents implemented algorithms, safety boundaries and a reproducible
methodology. To add actual result tables, perform real external experiments.
"""
from pathlib import Path
import argparse

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,
)

INK=colors.HexColor("#15243B")
BLUE=colors.HexColor("#256BD6")
MUTED=colors.HexColor("#526578")
TEAL=colors.HexColor("#0E8F84")


def build(output):
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name="InTitle",parent=styles["Title"],fontSize=22,leading=28,
                              textColor=INK,spaceAfter=18))
    styles.add(ParagraphStyle(name="InHeading",parent=styles["Heading2"],fontSize=13,leading=18,
                              textColor=BLUE,spaceBefore=13,spaceAfter=7))
    styles.add(ParagraphStyle(name="InBody",parent=styles["BodyText"],fontSize=9.3,leading=13.7,
                              textColor=INK,spaceAfter=9))
    styles.add(ParagraphStyle(name="InEquation",parent=styles["BodyText"],fontName="Courier",
                              fontSize=8.4,leading=12.5,textColor=TEAL,spaceAfter=11))
    story=[Spacer(1,38)]
    def title(x):story.append(Paragraph(x,styles["InTitle"]))
    def head(x):story.append(Paragraph(x,styles["InHeading"]))
    def p(x):story.append(Paragraph(x,styles["InBody"]))
    def eq(x):story.append(Paragraph(x,styles["InEquation"]))
    def table(rows,widths):
        data=[[Paragraph(str(v),styles["InBody"]) for v in row] for row in rows]
        t=Table(data,colWidths=widths,repeatRows=1,hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#E8F0FB")),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F6F9FC")]),
            ("GRID",(0,0),(-1,-1),.35,colors.HexColor("#D4DFEC")),
            ("VALIGN",(0,0),(-1,-1),"TOP"),
            ("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),
            ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),4),
        ]))
        story.append(t)
    def footer(canvas,doc):
        canvas.setStrokeColor(colors.HexColor("#D7E3F0"))
        canvas.line(43,36,A4[0]-43,36)
        canvas.setFont("Helvetica",8)
        canvas.setFillColor(MUTED)
        canvas.drawString(43,24,"InProcess | Modelacao Computacional de Sistemas Fisicos")
        canvas.drawRightString(A4[0]-43,24,f"Pagina {doc.page}")

    title("InProcess 7.3–8.0 | Scientific Evidence")
    p("<b>Laboratorio de desempenho, robustez de prioridades, politicas "
      "nativas, energia medida e recomendacoes baseadas em evidencias</b>")
    p("Relatorio de metodologia academica | novembro 2026 | "
      "Sem resultados experimentais reais de Windows 11 ou Linux.")
    head("Resumo")
    p("A extensao acrescenta estatistica de repeticoes (7.3), um "
      "watchdog independente de reposicao de prioridades (7.4), "
      "ensaios nativos em tarefas isoladas (7.5), ingestao de leituras "
      "eletricas com proveniencia (7.6) e regras explicaveis "
      "sem atuacao automatica (8.0). O projeto suporta "
      "experiencias cientificas, mas nao demonstrou superioridade "
      "face aos monitores nativos nem poupanca real de energia.")
    head("Objetivos da unidade curricular")
    table([
        ["Competencia","Implementacao no InProcess"],
        ["Metodo experimental","Tarefa identica, baseline, repeticoes e controlo de confundidores"],
        ["Estatistica","Medianas, desvio-padrao, P95 e bootstrap descritivo"],
        ["Sistemas dinamicos","Tarefa CPU, escalonador e impacto na latencia"],
        ["Integracao numerica","Integracao trapezoidal da potencia em joules"],
        ["Conservacao e energia","Distincao entre potencia W e energia J/Wh"],
        ["Validacao","Identificar proveniencia e limites de comparabilidade"],
    ],[185,320])
    story.append(PageBreak())

    head("1. Desenho experimental comparativo")
    p("Definir um problema de referencia de duracao reprodutivel. "
      "Executar primeiro BASELINE sem InProcess, depois ensaios de "
      "observadores iniciados pelo utilizador e identificados por PID: "
      "InProcess, Gestor de Tarefas no Windows ou GNOME System Monitor "
      "no Linux. Repetir sob carga e alimentacao equivalentes; "
      "alternar a ordem para reduzir deriva temporal/termica.")
    eq("Delta(%) = 100 * (mediana(T_observador)/mediana(T_base) - 1)")
    p("A sobrecarga relativa representa duracao adicional da tarefa, "
      "nao consumo de energia. O modulo 7.3 exige no minimo tres "
      "repeticoes por condicao; recomenda-se cinco ou mais e medidas "
      "em dias/ordens diferentes para testar reprodutibilidade.")
    head("Estatistica e incerteza")
    p("Intervalos descritivos de 95% sao obtidos por 1000 "
      "reamostragens bootstrap nao emparelhadas da razao de medianas, "
      "com semente fixa. Nao sao intervalos causais; ruido termico, "
      "carga de fundo, atualizacoes e diferencas de sistema operativo "
      "podem dominar o sinal.")
    table([
        ["Grandeza","Disponibilidade atual"],
        ["Duracao da tarefa, media/mediana/P95","Calculavel de ensaios brutos"],
        ["CPU do observador (% de um nucleo)","Amostrado pelo processo"],
        ["RAM RSS do observador","Pico amostrado, paginas partilhadas possiveis"],
        ["Latencia de clique/renderizacao","NAO MEDIDA"],
        ["Potencia/energia dos monitores nativos","NAO MEDIDA neste relatorio"],
    ],[247,258])
    p("**Nao existem nesta entrega tabelas preenchidas de Windows 11 "
      "versus Linux.** Esses valores exigem aquisicao em computadores reais.")
    story.append(PageBreak())

    head("2. Watchdog de prioridades 7.4")
    p("O motor 7.2 permite alteracoes autorizadas e limitadas "
      "de prioridade. O 7.4 adiciona um processo auxiliar que "
      "verifica a identidade PID+hora de criacao, a prioridade "
      "temporaria esperada e o estado da GUI. Na morte da interface "
      "ou na expiracao da sessao, tenta restaurar somente o alvo "
      "exato, sem alterar prioridades modificadas por terceiros.")
    table([
        ["Sistema","Alteracao permitida / politica"],
        ["Windows","NORMAL -> BELOW_NORMAL -> NORMAL"],
        ["Linux com permissoes existentes","nice 0 -> nice 5 -> nice 0"],
        ["Linux de utilizador normal","Recusar se nao puder repor a prioridade"],
        ["Apos crash do SO/helper","Reposicao NAO GARANTIDA"],
    ],[200,305])
    p("O watchdog nao e um servico privilegiado persistente. "
      "A sua robustez deve ser testada com falhas reais, permissões "
      "e encerramentos forcados, antes de controlo em producao.")
    head("3. Native Efficiency 7.5")
    p("Os ensaios nativos atuam exclusivamente sobre uma tarefa nova "
      "e autorizada, nao sobre processos arbitrarios. "
      "Windows usa SetProcessInformation/ProcessPowerThrottling "
      "para solicitar EcoQoS do processo filho. "
      "Linux usa systemd-run --user --scope com CPUWeight relativo. "
      "A politica pode afetar escalonamento; nao comprova poupanca de energia.")
    eq("CPUWeight: peso RELATIVO de CPU (nao equivale a watts)")
    story.append(PageBreak())

    head("4. Monitorizacao de energia 7.6")
    p("O modelo de aquisicao exige tempos em segundos, potencias "
      "em watts e, opcionalmente, temperaturas em graus Celsius. "
      "Exige a identificacao do sensor, equipamento e dominio de "
      "potencia. Nenhum dado importado e certificado automaticamente; "
      "a proveniencia inicial e MEASURED_UNVERIFIED.")
    eq("E[J] = sum ((P_k + P_(k+1))/2)*(t_(k+1)-t_k)")
    eq("E[Wh] = E[J] / 3600")
    p("Exemplo estritamente didatico: se P=20 W durante 5 s, "
      "a integral e 100 J ou 0,02778 Wh. Este valor nao foi "
      "medido em qualquer ensaio real do InProcess.")
    head("Fronteira fisica e comparabilidade")
    p("A potencia ao nivel da tomada e diferente da potencia eletrica "
      "de um CPU/GPU e da potencia termica produzida. Comparar "
      "perfis exige sensores identicos, mesma fronteira de medicao, "
      "tarefa equivalente e repeticoes. Nao transformar "
      "percentagens de CPU/RAM em watts sem modelo calibrado.")
    head("5. Motor de recomendacoes 8.0")
    p("Um motor de regras EXPLICAVEL consome as analises 7.3 e 7.6. "
      "Se nao houver dados comparaveis ou repeticoes suficientes, "
      "rejeita qualquer conclusao operacional. Caso sejam "
      "observados sinais de sobrecarga, recomenda rever a "
      "frequencia de recolha, sem alterar prioridades automaticamente.")
    table([
        ["Resultado da avaliacao","Acao efetiva"],
        ["INSUFFICIENT_EVIDENCE","Nao alterar nada; pedir dados"],
        ["REVIEW_ONLY","Recomendacao e analise humana"],
        ["NO_JUSTIFIED_ACTION","Sem alteracao justificada"],
        ["Acao autonoma sobre sistema operativo","NAO IMPLEMENTADA"],
    ],[246,259])
    story.append(PageBreak())

    head("6. Verificacoes e seguranca")
    p("Os testes verificam rejeicao de dados fisicos invalidos, "
      "calculo de energia, comparabilidade estatistica, "
      "bloqueio de alteracoes sem autorizacao, PID reutilizado, "
      "watchdog com processos simulados e formacao de comandos "
      "nativos isolados. Os testes nao substituem uma "
      "campanha de validacao em Windows/Linux com hardware real.")
    eq("python -m pytest tests/test_scientific_73_to_80.py -q")
    eq("python -m pytest -q")
    head("7. Trabalho futuro verificavel")
    p("Executar repeticoes de benchmark com observadores reais, "
      "adquirir potencia sincronizada, calibrar os sensores, "
      "quantificar incerteza, testar falhas do helper em maquinas "
      "descartaveis e validar os mecanismos de EcoQoS/systemd "
      "com privilegios minimos. Nao usar alteracoes automaticas "
      "de recursos ate essas verificacoes serem concluidas.")
    head("Enquadramento das interfaces de sistema")
    p("Microsoft Learn: SetProcessInformation, "
      "PROCESS_POWER_THROTTLING_STATE e EcoQoS. "
      "systemd: systemd.resource-control (CPUWeight).")
    head("Conclusao")
    p("O InProcess passa a dispor de ferramentas para formular "
      "e testar hipoteses de desempenho e energia com rigor. "
      "O resultado e uma plataforma experimental e nao uma "
      "prova de eficiencia superior ou de seguranca infalivel.")
    doc=SimpleDocTemplate(str(output),pagesize=A4,
                          leftMargin=44,rightMargin=44,
                          topMargin=47,bottomMargin=52,
                          title="InProcess 7.3-8.0 - Scientific Evidence")
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return output


if __name__=="__main__":
    cli=argparse.ArgumentParser()
    cli.add_argument("--output",type=Path,
        default=Path("docs/relatorios/InProcess_Scientific_Evidence_8_0.pdf"))
    args=cli.parse_args()
    print(build(args.output))
