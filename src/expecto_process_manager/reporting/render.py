"""Self-contained HTML and SVG; no network, JavaScript or hidden chart assets."""
from datetime import datetime,timezone
from html import escape
import math
import os
from pathlib import Path
import re
import tempfile
from .document import ScientificReport,Figure

CSS='''body{font-family:Segoe UI,Arial,sans-serif;line-height:1.6;color:#1a2940;background:#f1f4f8;margin:0}main{max-width:1100px;margin:28px auto;padding:40px;background:white;border:1px solid #dbe3ed;border-radius:12px}h1{font-size:30px;line-height:1.2}h2{font-size:22px;border-bottom:1px solid #dbe3ed;padding-bottom:7px;margin-top:35px}h3{font-size:17px;color:#345477}p,li{max-width:95ch}table{border-collapse:collapse;width:100%;margin:15px 0;font-size:14px}th,td{padding:9px 12px;text-align:left;border-bottom:1px solid #e1e7ef;vertical-align:top;overflow-wrap:anywhere}th{background:#edf3fa;color:#244b75}.tag{background:#e7f0fc;padding:5px 12px;border-radius:20px;display:inline-block}.equation{font-family:Cambria,Georgia,serif;font-size:21px;background:#f4f7fb;padding:15px;border-left:3px solid #3777b8;overflow-wrap:anywhere}.figure{border:1px solid #dbe3ed;border-radius:8px;padding:16px;margin:20px 0;break-inside:avoid}svg{width:100%;height:auto}.legend{display:flex;gap:10px 22px;flex-wrap:wrap;font-size:13px}.legend span{overflow-wrap:anywhere}.swatch{display:inline-block;width:17px;height:4px;margin-right:6px;vertical-align:middle}.muted{color:#5f7187}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;background:#f6f8fb;padding:16px}a{color:#2260a0}@media print{body{background:white}main{border:0;margin:0;padding:10px}h2{break-after:avoid}a{color:inherit}.no-print{display:none}}'''


def number(value):
    if value is None: return 'Não disponível'
    if isinstance(value,bool): return 'Sim' if value else 'Não'
    if isinstance(value,(float,int)):
        if not math.isfinite(value): return 'Indefinido'
        return f'{value:.8g}'
    return str(value)


def _table(headers,rows):
    return '<table><thead><tr>'+''.join('<th>'+escape(str(h))+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join(
        '<tr>'+''.join('<td>'+escape(number(v))+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table>'


def _paragraphs(lines):
    return ''.join('<p>'+escape(str(line))+'</p>' for line in lines)


def figure_html(figure: Figure):
    curves=[]
    for curve in figure.curves:
        n=min(len(curve.x),len(curve.y))
        stride=max(1,math.ceil(max(1,n-1)/599))
        indices=list(range(0,n,stride))
        if n and indices[-1]!=n-1: indices.append(n-1)
        points=[(float(curve.x[i]),float(curve.y[i])) for i in indices
                if curve.x[i] is not None and curve.y[i] is not None and math.isfinite(curve.x[i]) and math.isfinite(curve.y[i])]
        if points: curves.append((curve,points))
    if not curves: return '<p>Gráfico indisponível para esta configuração.</p>'
    width,height,left,top,right,bottom=900,360,88,20,28,63
    plotw,ploth=width-left-right,height-top-bottom
    all_points=[p for _,points in curves for p in points]
    xmin,xmax=min(x for x,y in all_points),max(x for x,y in all_points)
    ymin,ymax=min(y for x,y in all_points),max(y for x,y in all_points)
    xspan,yspan=max(xmax-xmin,1e-12),max(ymax-ymin,1e-12)
    if figure.equal_scale:
        xspan=max(xspan,yspan*plotw/ploth)
        yspan=max(yspan,xspan*ploth/plotw)
    else:
        # Small SI quantities (vibration displacement or capacitor energy) must
        # not be flattened by a fixed 0.01-unit floor on every scientific plot.
        scale=max(abs(ymin),abs(ymax))
        yspan=max(yspan,scale*.02 if scale else 1e-12)
    cx,cy=(xmin+xmax)/2,(ymin+ymax)/2
    xpad=.55 if figure.equal_scale else .54
    xmin,xmax=cx-xspan*xpad,cx+xspan*xpad
    ymin,ymax=cy-yspan*.55,cy+yspan*.55
    px=lambda x:left+(x-xmin)/(xmax-xmin)*plotw
    py=lambda y:top+ploth-(y-ymin)/(ymax-ymin)*ploth
    svg=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 360" role="img"><title>'+escape(figure.title)+'</title>']
    svg.append('<rect width="900" height="360" fill="white"/>')
    for i in range(6):
        x=xmin+(xmax-xmin)*i/5
        y=ymin+(ymax-ymin)*i/5
        svg.append(f'<path d="M {px(x):.2f} {top} V {top+ploth} M {left} {py(y):.2f} H {left+plotw}" stroke="#e2e8ef" fill="none"/>')
        svg.append(f'<text x="{px(x):.2f}" y="{top+ploth+23}" text-anchor="middle" fill="#4b6078" font-size="12">{x:.4g}</text>')
        svg.append(f'<text x="{left-9}" y="{py(y)+4:.2f}" text-anchor="end" fill="#4b6078" font-size="12">{y:.4g}</text>')
    legends=[]
    for curve,points in curves:
        color=curve.color if re.fullmatch('#[0-9a-fA-F]{6}',curve.color) else '#2176c1'
        path=' '.join(('M' if i==0 else 'L')+f'{px(x):.3f},{py(y):.3f}' for i,(x,y) in enumerate(points))
        svg.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="1.8"/>')
        legends.append(f'<span><i class="swatch" style="background:{color}"></i>{escape(curve.name)}</span>')
    svg.append(f'<text x="{left+plotw/2}" y="350" text-anchor="middle" font-size="14">{escape(figure.x_label)}</text>')
    svg.append(f'<text transform="translate(20 {top+ploth/2}) rotate(-90)" text-anchor="middle" font-size="14">{escape(figure.y_label)}</text></svg>')
    return '<div class="figure"><h3>'+escape(figure.title)+'</h3><div class="legend">'+''.join(legends)+'</div>'+''.join(svg)+'</div>'


def render_report(report: ScientificReport,*,figures=True):
    sections=['<header><p class="muted">InProcess Physical Systems Lab</p><h1>'+escape(report.title)+'</h1><span class="tag">'+escape(report.provenance)+'</span></header>',
              '<h2>1. Problema físico e objetivo</h2><p>'+escape(report.problem)+'</p>',
              '<h2>2. Hipóteses e validade do modelo</h2><ul>'+''.join('<li>'+escape(x)+'</li>' for x in report.assumptions)+'</ul>',
              '<h2>3. Formulação matemática e unidades</h2>'+''.join('<div class="equation">'+escape(x)+'</div>' for x in report.equations),
              _table(('Parâmetro','Valor','Unidade'),report.parameters),
              '<h2>4. Métodos numéricos e implementação</h2>'+_paragraphs(report.methods),
              '<h2>5. Resultados e análise de erros</h2>']
    for table in report.tables:
        sections.append('<h3>'+escape(table.title)+'</h3>'+_table(table.headers,table.rows))
    if figures:
        sections.append('<h2>6. Gráficos dos resultados</h2>'+''.join(figure_html(fig) for fig in report.figures))
    else:
        sections.append('<h2>6. Gráficos</h2><p>O ficheiro HTML completo inclui todos os gráficos vetoriais e legendas. Use Abrir no navegador para os visualizar ou imprimir.</p>')
    sections.extend(['<h2>7. Interpretação física</h2>'+_paragraphs(report.interpretation),
                     '<h2>8. Limitações e incerteza</h2>'+_paragraphs(report.limitations),
                     '<h2>9. Reprodução e proveniência</h2>'+_paragraphs(report.reproduction),
                     _table(('Metadado','Valor'),[(k,v) for k,v in report.metadata.items()])])
    if report.technical_notes:
        sections.append('<details><summary>Registo técnico completo</summary><pre>'+escape(report.technical_notes)+'</pre></details>')
    sections.append('<h2>10. Referências de apoio</h2><ul><li><a href="https://openstax.org/details/books/university-physics-volume-2">OpenStax — University Physics, Volume 2: energia e termodinâmica.</a></li><li><a href="https://www.nist.gov/pml/owm/metric-si">NIST — Sistema Internacional de Unidades.</a></li><li><a href="https://docs.scipy.org/doc/scipy/reference/generated/scipy.integrate.solve_ivp.html">SciPy — formulação de problemas de valor inicial.</a> Os métodos deste projeto são implementados diretamente; SciPy não é utilizado como resolvedor.</li><li><a href="https://psutil.io/">Documentação oficial psutil — monitorização e limitações por plataforma.</a></li></ul>')
    return '<!doctype html><html lang="pt"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>'+escape(report.title)+'</title><style>'+CSS+'</style></head><body><main>'+''.join(sections)+'</main></body></html>'


def save_report(path,report: ScientificReport,token=None):
    if token: token.check()
    content=render_report(report)
    target=Path(path)
    target.parent.mkdir(parents=True,exist_ok=True)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=target.parent,delete=False) as stream:
            temporary=stream.name
            stream.write(content)
        if token: token.check()
        os.replace(temporary,target)
    finally:
        if temporary and os.path.exists(temporary): os.unlink(temporary)
    return str(target.resolve())
