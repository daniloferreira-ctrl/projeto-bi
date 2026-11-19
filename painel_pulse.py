"""
IPR PULSE — Painel Gerencial (versão conceito, criada do zero)

Um "cockpit" da rede IPR: índice de saúde, faturamento com projeção, jornada do
paciente em fluxo, mapa das unidades, centro cirúrgico, time e insights automáticos.

Instalar:  pip install dash plotly
Rodar:     python painel_pulse.py   ->  abrir http://127.0.0.1:8052

Atalhos:   Ctrl+K abre a paleta de comandos · F alterna tela cheia · P liga o modo apresentação
Dados:     FICTÍCIOS (função carregar_dados). Para ligar no banco, troque só essa função.
Fotos:     assets/fotos/<nome>.png  e  assets/fotos/recorte/<nome>.png (sem fundo, para o líder)
"""

import math
import random
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

import plotly.graph_objects as go
from dash import Dash, Input, Output, State, ctx, dcc, html, no_update

# ===========================================================================
# CONFIGURAÇÃO
# ===========================================================================
UNIDADES = ["Santos", "São Paulo", "Campinas"]
VISOES = ["Rede"] + UNIDADES
IDS_VISAO = {"Rede": "v-rede", "Santos": "v-santos", "São Paulo": "v-sp", "Campinas": "v-campinas"}
PERIODOS = {"mes": "Este mês", "ant": "Mês passado", "tri": "Trimestre"}
META = {"Santos": 1_500_000, "São Paulo": 2_400_000, "Campinas": 1_200_000}
REFERENCIAS = {"leads_agend": .10, "consult_atend": .75, "orc_contrato": .60}  # "bom" a partir de
SEGUNDOS_APRESENTACAO = 12
GERENTE = {"nome": "Danilo", "cargo": "Gerente de Rede"}

# Paleta
BG = "#07060B"
TX, TX2, TX3 = "#F4EEF7", "#A99BB3", "#6E6178"
ROSA, VIOLETA, CIANO = "#FF2D8A", "#8B5CF6", "#22D3EE"
VERDE, AMBAR, VERM = "#34D399", "#FBBF24", "#F87171"
OURO, PRATA, BRONZE = "#F5C542", "#C9D1D9", "#D08A4A"

PASTA_FOTOS = Path(__file__).parent / "assets" / "fotos"


# ===========================================================================
# DADOS (FICTÍCIOS)
# ===========================================================================
def _unidade(nome, periodo):
    rnd = random.Random(f"{nome}-{periodo}")
    k = {"Santos": 1.0, "São Paulo": 1.55, "Campinas": .78}[nome] * {"mes": 1, "ant": 1.08, "tri": 3.05}[periodo]
    hoje = date.today()
    leads = round(2195 * k * rnd.uniform(.92, 1.08))
    agend = round(329 * k * rnd.uniform(.9, 1.1))
    atend = round(agend * rnd.uniform(.23, .31))
    orc = round(atend * rnd.uniform(.9, .98))
    contr = round(orc * rnd.uniform(.42, .56))
    ticket = 11_400 * rnd.uniform(.92, 1.08)
    fat = contr * ticket
    meta = META[nome] * (3 if periodo == "tri" else 1)
    # faturamento por dia
    ini = hoje.replace(day=1)
    fim = (ini + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    dias_mes = [ini + timedelta(days=i) for i in range((fim - ini).days + 1)]
    corte = hoje if periodo == "mes" else fim
    pesos = [(rnd.uniform(.4, 1.6) if d.weekday() < 5 else rnd.uniform(0, .12)) if d <= corte else 0 for d in dias_mes]
    s = sum(pesos) or 1
    fat_dia = [fat * w / s for w in pesos]
    vend = ["Mariana Costa", "Rafael Nunes", "Beatriz Alves", "Lucas Prado", "Camila Rocha",
            "Thiago Moura", "Juliana Reis", "Pedro Taddeo"]
    rnd.shuffle(vend)
    partes = sorted([rnd.uniform(.5, 1.6) for _ in range(5)], reverse=True)
    sp = sum(partes)
    return {
        "nome": nome, "leads": leads, "agendadas": agend, "atendidas": atend, "orcamentos": orc,
        "contratos": contr, "cirurgias": max(contr - round(contr * .2), 0), "sem_data": max(3, round(contr * .2)),
        "leads_agendados": round(leads * rnd.uniform(.09, .125)),
        "ticket": ticket, "faturamento": fat, "meta": meta,
        "ocupacao": rnd.uniform(.32, .78), "cancelamento": rnd.uniform(.04, .13), "no_show": rnd.uniform(0, .04),
        "ddd_local": rnd.uniform(.58, .72),
        "dias": dias_mes, "fat_dia": fat_dia, "corte": corte,
        "hist_fat": [fat * rnd.uniform(.78, 1.15) for _ in range(7)] + [fat],
        "hist_leads": [leads * rnd.uniform(.8, 1.2) for _ in range(7)] + [leads],
        "anterior": {"faturamento": fat / rnd.uniform(.88, 1.12), "leads": leads / rnd.uniform(.7, .95),
                     "ticket": ticket / rnd.uniform(.95, 1.05), "contratos": contr / rnd.uniform(.88, 1.12),
                     "cancelamento": rnd.uniform(.05, .1), "no_show": rnd.uniform(0, .04)},
        "vendedores": [{"nome": v, "valor": fat * p / sp, "contratos": max(1, round(contr * p / sp))}
                       for v, p in zip(vend, partes)],
        "calor": [[None if (i == 5 and h >= 13) else
                   max(0, min(1, (.08 if h == 12 else (.8 if 8 <= h <= 11 else .5 if 13 <= h <= 15 else .25))
                              * rnd.uniform(.55, 1.3) * (1 if not (i == 4 and h >= 14) else .3)))
                   for h in range(7, 19)] for i in range(6)],
    }


def carregar_dados(visao, periodo):
    us = {u: _unidade(u, periodo) for u in UNIDADES}
    if visao != "Rede":
        d = us[visao]
    else:
        d = {"nome": "Rede"}
        for k in ("leads", "agendadas", "atendidas", "orcamentos", "contratos", "cirurgias", "sem_data",
                  "leads_agendados", "faturamento", "meta"):
            d[k] = sum(u[k] for u in us.values())
        d["ticket"] = d["faturamento"] / max(d["contratos"], 1)
        for k in ("ocupacao", "cancelamento", "no_show", "ddd_local"):
            d[k] = sum(u[k] for u in us.values()) / 3
        base = us["Santos"]
        d["dias"], d["corte"] = base["dias"], base["corte"]
        d["fat_dia"] = [sum(u["fat_dia"][i] for u in us.values()) for i in range(len(base["dias"]))]
        d["hist_fat"] = [sum(u["hist_fat"][i] for u in us.values()) for i in range(8)]
        d["hist_leads"] = [sum(u["hist_leads"][i] for u in us.values()) for i in range(8)]
        d["anterior"] = {k: sum(u["anterior"][k] for u in us.values()) for k in ("faturamento", "leads", "contratos")}
        d["anterior"]["ticket"] = d["anterior"]["faturamento"] / max(d["anterior"]["contratos"], 1)
        d["anterior"]["cancelamento"] = sum(u["anterior"]["cancelamento"] for u in us.values()) / 3
        d["anterior"]["no_show"] = sum(u["anterior"]["no_show"] for u in us.values()) / 3
        d["vendedores"] = sorted([dict(v, unidade=n) for n, u in us.items() for v in u["vendedores"]],
                                 key=lambda v: -v["valor"])[:5]
        d["calor"] = [[None if us["Santos"]["calor"][i][j] is None else
                       sum(u["calor"][i][j] or 0 for u in us.values()) / 3 for j in range(12)] for i in range(6)]
    d["unidades"] = us
    d["periodo"] = periodo
    return d


# ===========================================================================
# CÁLCULOS
# ===========================================================================
def projecao(d):
    uteis = [x for x in d["dias"] if x.weekday() < 5]
    passados = [x for x in uteis if x <= d["corte"]]
    restantes = len(uteis) - len(passados)
    ritmo = d["faturamento"] / max(len(passados), 1)
    proj = d["faturamento"] + ritmo * restantes if d["periodo"] == "mes" else d["faturamento"]
    falta = max(d["meta"] - d["faturamento"], 0)
    return {"proj": proj, "ritmo": ritmo, "restantes": restantes, "falta": falta,
            "por_dia": falta / max(restantes, 1), "frac_tempo": len(passados) / max(len(uteis), 1)}


def conversoes(d):
    return [
        ("Leads → agendamentos", d["leads_agendados"] / max(d["leads"], 1), REFERENCIAS["leads_agend"]),
        ("Consultas → atendimentos", d["atendidas"] / max(d["agendadas"], 1), REFERENCIAS["consult_atend"]),
        ("Orçamentos → contratos", d["contratos"] / max(d["orcamentos"], 1), REFERENCIAS["orc_contrato"]),
    ]


def saude(d):
    """Índice de 0 a 100 que resume a unidade em quatro dimensões."""
    pj = projecao(d)
    receita = min(pj["proj"] / d["meta"], 1) * 100
    conv = sum(min(v / ref, 1) for _, v, ref in conversoes(d)) / 3 * 100
    oper = max(0, min(d["ocupacao"] / .75, 1) * 100 - d["cancelamento"] * 150)
    capt = min(d["leads"] / max(d["anterior"]["leads"], 1), 1.2) / 1.2 * 100
    dims = [("Receita", receita, ROSA), ("Conversão", conv, VIOLETA), ("Operação", oper, CIANO), ("Captação", capt, VERDE)]
    return round(sum(v for _, v, _ in dims) / 4), dims


# ===========================================================================
# HELPERS
# ===========================================================================
def nbr(v, c=0):
    return f"{v:,.{c}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def brl(v):
    if abs(v) >= 1e6:
        return f"R$ {nbr(v / 1e6, 2)} mi"
    if abs(v) >= 1e3:
        return f"R$ {nbr(v / 1e3, 1)} mil"
    return f"R$ {nbr(v)}"


def pct(v, c=1):
    return f"{nbr(v * 100, c)}%"


def slug(t):
    t = unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode()
    return "_".join(t.lower().split())


def foto(nome, recorte=False):
    pasta = PASTA_FOTOS / "recorte" if recorte else PASTA_FOTOS
    if not pasta.exists():
        return None
    arqs = {f.stem.lower(): f.name for f in pasta.iterdir() if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")}
    s = slug(nome)
    for k in (s, s.split("_")[0]):
        if k in arqs:
            return app.get_asset_url(("fotos/recorte/" if recorte else "fotos/") + arqs[k])
    return None


def avatar(nome, tam, cor=ROSA):
    src = foto(nome)
    est = {"width": tam, "height": tam, "borderColor": cor}
    if src:
        return html.Img(src=src, className="av", style=est)
    ini = "".join(p[0] for p in nome.split()[:2]).upper()
    return html.Div(ini, className="av av-ini", style={**est, "color": cor, "fontSize": tam * .36})


def conta(valor, fmt, classe=""):
    txt = {"brl": brl(valor), "int": nbr(valor), "pct": pct(valor), "pct0": pct(valor, 0)}[fmt]
    return html.Span(txt, className=f"countup {classe}", **{"data-alvo": str(valor), "data-fmt": fmt})


def delta(atual, ant, taxa=False, inverso=False):
    if not ant:
        return None
    v = (atual - ant) if taxa else (atual / ant - 1)
    bom = (v < 0) if inverso else (v >= 0)
    txt = f"{'▲' if v >= 0 else '▼'} {nbr(abs(v) * 100, 1)}%"
    return html.Span(txt, className="delta " + ("bom" if bom else "ruim"))


def spark(vals, cor, w=150, h=38):
    mn, mx = min(vals), max(vals)
    rg = (mx - mn) or 1
    pts = [(i * w / (len(vals) - 1), h - 4 - (v - mn) / rg * (h - 8)) for i, v in enumerate(vals)]
    linha = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"0,{h} " + linha + f" {w},{h}"
    gid = f"g{abs(hash((cor, tuple(round(v) for v in vals)))) % 10**8}"
    return html.Div(className="spark", **{"data-svg": (
        f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none"><defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{cor}" stop-opacity=".35"/><stop offset="1" stop-color="{cor}" stop-opacity="0"/>'
        f'</linearGradient></defs><polygon points="{area}" fill="url(#{gid})"/>'
        f'<polyline points="{linha}" fill="none" stroke="{cor}" stroke-width="2" stroke-linejoin="round" class="spark-l"/>'
        f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="3" fill="{cor}"/></svg>')})


def svg(markup, classe="", **estilo):
    """Desenho em SVG feito à mão (renderizado no navegador pelo JS)."""
    return html.Div(className=f"svgbox {classe}", style=estilo, **{"data-svg": markup})


def card(titulo, filhos, classe="", extra=None, area=None):
    return html.Div([
        html.Div([html.Span(titulo, className="c-tit"), extra], className="c-topo"),
        html.Div(filhos, className="c-corpo"),
    ], className=f"card {classe}", style={"gridArea": area} if area else None)


# ===========================================================================
# BLOCOS
# ===========================================================================
def bloco_pulso(d):
    score, dims = saude(d)
    cor = VERDE if score >= 75 else AMBAR if score >= 55 else VERM
    estado = "Saudável" if score >= 75 else "Atenção" if score >= 55 else "Crítico"
    r, c = 74, 2 * math.pi * 74
    anel = (f'<svg viewBox="0 0 180 180"><defs><linearGradient id="gpulso" x1="0" y1="0" x2="1" y2="1">'
            f'<stop offset="0" stop-color="{ROSA}"/><stop offset="1" stop-color="{VIOLETA}"/></linearGradient></defs>'
            f'<circle cx="90" cy="90" r="{r}" fill="none" stroke="rgba(255,255,255,.07)" stroke-width="12"/>'
            f'<circle cx="90" cy="90" r="{r}" fill="none" stroke="url(#gpulso)" stroke-width="12" stroke-linecap="round" '
            f'transform="rotate(-90 90 90)" stroke-dasharray="{c:.1f}" stroke-dashoffset="{c:.1f}" '
            f'class="anel-prog" style="--alvo:{c * (1 - score / 100):.1f}"/></svg>')
    ecg = ('<svg viewBox="0 0 600 80" preserveAspectRatio="none"><path class="ecg" d="M0 40 H170 L185 40 L195 20 L205 62 '
           'L218 6 L232 74 L244 40 H360 L372 40 L380 28 L390 52 L400 40 H600" fill="none" stroke="' + ROSA +
           '" stroke-width="2"/></svg>')
    return card("Pulso da unidade", [
        svg(ecg, "ecg-fundo"),
        html.Div([
            html.Div([svg(anel, "anel"),
                      html.Div([conta(score, "int", "score"), html.Div("de 100", className="score-de")], className="anel-centro")],
                     className="anel-wrap"),
            html.Div([html.Div([html.Div([html.Span(nome, className="dim-nome"), html.B(nbr(v))], className="dim-linha"),
                                html.Div(html.Div(className="barra-f", style={"width": f"{v:.0f}%", "background": cr,
                                                                              "animationDelay": f"{i * .1}s"}),
                                         className="barra")], className="dim") for i, (nome, v, cr) in enumerate(dims)],
                     className="dims"),
        ], className="pulso"),
    ], "c-pulso", html.Span(estado, className="selo", style={"color": cor, "borderColor": cor}), "pulso")


def fig_faturamento(d, pj):
    dias, vals = d["dias"], d["fat_dia"]
    real_x, real_y, acc = [], [], 0
    for x, v in zip(dias, vals):
        if x > d["corte"]:
            break
        acc += v
        real_x.append(x)
        real_y.append(acc)
    uteis = [x for x in dias if x.weekday() < 5]
    ideal, n = [], 0
    for x in dias:
        n += x.weekday() < 5
        ideal.append(d["meta"] * n / len(uteis))
    proj_x, proj_y, alto, baixo = [real_x[-1]], [acc], [acc], [acc]
    p, k = acc, 0
    for x in dias:
        if x <= d["corte"]:
            continue
        if x.weekday() < 5:
            p += pj["ritmo"]
            k += 1
        proj_x.append(x)
        proj_y.append(p)
        alto.append(p + pj["ritmo"] * .35 * k ** .5)
        baixo.append(max(p - pj["ritmo"] * .35 * k ** .5, acc))
    f = go.Figure()
    if len(proj_x) > 1:
        f.add_scatter(x=proj_x + proj_x[::-1], y=alto + baixo[::-1], fill="toself", fillcolor="rgba(139,92,246,.14)",
                      line=dict(width=0), hoverinfo="skip", showlegend=False)
    f.add_scatter(x=dias, y=ideal, mode="lines", name="Ritmo da meta", line=dict(color=TX3, width=1.5, dash="dot"),
                  hovertemplate="%{x|%d/%m} · ideal %{y:,.0f}<extra></extra>")
    f.add_scatter(x=real_x, y=real_y, mode="lines", name="Realizado", line=dict(color=ROSA, width=3, shape="spline"),
                  fill="tozeroy", fillgradient=dict(type="vertical", colorscale=[[0, "rgba(255,45,138,0)"], [1, "rgba(255,45,138,.35)"]]),
                  hovertemplate="%{x|%d/%m} · R$ %{y:,.0f}<extra></extra>")
    if len(proj_x) > 1:
        f.add_scatter(x=proj_x, y=proj_y, mode="lines", name="Projeção", line=dict(color=VIOLETA, width=2.5, dash="dash"),
                      hovertemplate="%{x|%d/%m} · projeção R$ %{y:,.0f}<extra></extra>")
    f.add_scatter(x=[real_x[-1]], y=[acc], mode="markers", marker=dict(size=12, color=ROSA, line=dict(color=BG, width=3)),
                  hoverinfo="skip", showlegend=False)
    f.add_hline(y=d["meta"], line=dict(color=AMBAR, width=1.2), annotation_text=f"meta {brl(d['meta'])}",
                annotation_font=dict(color=AMBAR, size=11), annotation_position="top left")
    f.update_layout(margin=dict(l=0, r=6, t=8, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(family="Inter", color=TX2, size=11), separators=",.",
                    legend=dict(orientation="h", x=1, xanchor="right", y=1.12, bgcolor="rgba(0,0,0,0)"),
                    hoverlabel=dict(bgcolor="#151020", bordercolor=ROSA, font_color=TX))
    f.update_xaxes(showgrid=False, tickformat="%d/%m", linecolor="rgba(255,255,255,.08)")
    top = max(d["meta"], max(alto)) * 1.08
    f.update_yaxes(gridcolor="rgba(255,255,255,.05)", zeroline=False, range=[0, top],
                   tickvals=[d["meta"] * q for q in (0, .25, .5, .75, 1)],
                   ticktext=["0"] + [brl(d["meta"] * q) for q in (.25, .5, .75, 1)])
    return f


def bloco_faturamento(d):
    pj = projecao(d)
    frac = d["faturamento"] / d["meta"]
    cor = VERDE if pj["proj"] >= d["meta"] else AMBAR if pj["proj"] >= .85 * d["meta"] else VERM
    status = "no ritmo da meta" if pj["proj"] >= d["meta"] else "abaixo do ritmo"
    return card("Faturamento", [
        html.Div([
            html.Div([
                html.Div([conta(d["faturamento"], "brl", "big"), delta(d["faturamento"], d["anterior"]["faturamento"])],
                         className="big-linha"),
                html.Div(["realizado · ", html.B(pct(frac)), " da meta de ", brl(d["meta"])], className="leg"),
                html.Div([
                    html.Div(className="meta-real", style={"width": f"{min(frac, 1) * 100:.1f}%"}),
                    html.Div(className="meta-proj", style={"left": f"{min(frac, 1) * 100:.1f}%",
                                                           "width": f"{max(min(pj['proj'] / d['meta'], 1) - frac, 0) * 100:.1f}%"}),
                    html.Div(className="meta-tempo", style={"left": f"{pj['frac_tempo'] * 100:.1f}%"},
                             title="Quanto do mês (em dias úteis) já passou"),
                ], className="meta-trilho"),
                html.Div([
                    html.Div([html.Span("Projeção", className="mini-r"), html.B(brl(pj["proj"]), style={"color": cor})], className="mini"),
                    html.Div([html.Span("Ticket médio", className="mini-r"), html.B(brl(d["ticket"]))], className="mini"),
                    html.Div([html.Span("Falta / dia útil", className="mini-r"), html.B(brl(pj["por_dia"]))], className="mini"),
                ], className="minis"),
            ], className="fat-esq"),
            dcc.Graph(figure=fig_faturamento(d, pj), config={"displayModeBar": False, "responsive": True},
                      className="fat-graf", style={"height": "100%"}),
        ], className="fat"),
    ], "c-fat", html.Span(status, className="selo", style={"color": cor, "borderColor": cor}), "fat")


def bloco_jornada(d):
    etapas = [("Leads", d["leads"]), ("Agendadas", d["agendadas"]), ("Atendidas", d["atendidas"]),
              ("Orçamentos", d["orcamentos"]), ("Contratos", d["contratos"]), ("Cirurgias", d["cirurgias"])]
    W, H, top = 980, 290, 60
    n = len(etapas)
    xs = [40 + i * (W - 80) / (n - 1) for i in range(n)]
    mx = math.sqrt(etapas[0][1])
    alt = [max(10, math.sqrt(v) / mx * 150) for _, v in etapas]
    cy = top + 85
    taxas = [etapas[i + 1][1] / max(etapas[i][1], 1) for i in range(n - 1)]
    refs = [REFERENCIAS["leads_agend"] * 1.4, REFERENCIAS["consult_atend"], .9, REFERENCIAS["orc_contrato"], .8]
    pior = min(range(n - 1), key=lambda i: taxas[i] / refs[i])
    partes = [f'<defs><linearGradient id="gj" x1="0" x2="1"><stop offset="0" stop-color="{ROSA}"/>'
              f'<stop offset="1" stop-color="{VIOLETA}"/></linearGradient>'
              f'<linearGradient id="gp" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="{VERM}" stop-opacity=".45"/>'
              f'<stop offset="1" stop-color="{VERM}" stop-opacity="0"/></linearGradient></defs>']
    for i in range(n - 1):
        x0, x1, h0, h1 = xs[i], xs[i + 1], alt[i], alt[i + 1]
        mxm = (x0 + x1) / 2
        d_path = (f"M{x0},{cy - h0 / 2} C{mxm},{cy - h0 / 2} {mxm},{cy - h1 / 2} {x1},{cy - h1 / 2} "
                  f"L{x1},{cy + h1 / 2} C{mxm},{cy + h1 / 2} {mxm},{cy + h0 / 2} {x0},{cy + h0 / 2} Z")
        partes.append(f'<path d="{d_path}" fill="url(#gj)" opacity="{.95 - i * .08:.2f}" class="banda" style="--i:{i}"/>')
        perdidos = etapas[i][1] - etapas[i + 1][1]
        if perdidos > 0:
            partes.append(f'<text x="{mxm}" y="{H - 34}" text-anchor="middle" class="j-perda">−{nbr(perdidos)}</text>')
        # fluxo animado
        partes.append(f'<path d="M{x0},{cy} C{mxm},{cy} {mxm},{cy} {x1},{cy}" stroke="rgba(255,255,255,.55)" '
                      f'stroke-width="1.5" fill="none" stroke-dasharray="3 9" class="fluxo"/>')
        cor = VERM if i == pior else TX
        partes.append(f'<text x="{mxm}" y="{top - 16}" text-anchor="middle" class="j-taxa" fill="{cor}">{pct(taxas[i])}</text>')
        if i == pior:
            partes.append(f'<rect x="{mxm - 34}" y="{top - 52}" width="68" height="18" rx="9" fill="{VERM}" class="gargalo"/>'
                          f'<text x="{mxm}" y="{top - 39}" text-anchor="middle" class="j-garg">GARGALO</text>')
    for i, (nome, v) in enumerate(etapas):
        partes.append(f'<line x1="{xs[i]}" x2="{xs[i]}" y1="{cy - alt[i] / 2 - 6}" y2="{cy + alt[i] / 2 + 6}" '
                      f'stroke="rgba(255,255,255,.6)" stroke-width="2"/>')
        partes.append(f'<text x="{xs[i]}" y="{cy - alt[i] / 2 - 14 if i else top - 2}" text-anchor="middle" class="j-num">{nbr(v)}</text>')
        partes.append(f'<text x="{xs[i]}" y="{H - 4}" text-anchor="middle" class="j-nome">{nome}</text>')
    total = d["cirurgias"] / max(d["leads"], 1)
    return card("Jornada do paciente", [svg(f'<svg viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet">{"".join(partes)}</svg>', "jornada")],
                "c-jornada", html.Span(["lead → cirurgia ", html.B(pct(total, 2))], className="leg"), "jornada")


def bloco_mapa(d):
    us = d["unidades"]
    pos = {"Campinas": (70, 60), "São Paulo": (190, 130), "Santos": (275, 205)}
    mx = max(u["faturamento"] for u in us.values())
    p = ['<defs><radialGradient id="mar" cx="1" cy="1" r="1"><stop offset="0" stop-color="#22D3EE" stop-opacity=".18"/>'
         '<stop offset="1" stop-color="#22D3EE" stop-opacity="0"/></radialGradient></defs>',
         '<path d="M90 260 C170 250 230 248 290 236 C350 224 400 210 460 180 L460 260 Z" fill="url(#mar)"/>',
         '<path d="M90 260 C170 250 230 248 290 236 C350 224 400 210 460 180" fill="none" stroke="rgba(34,211,238,.4)" '
         'stroke-width="1.5" stroke-dasharray="2 6"/>',
         '<text x="452" y="252" text-anchor="end" class="m-oceano">Oceano Atlântico</text>']
    nomes = list(pos)
    for a, b in zip(nomes, nomes[1:]):
        (x0, y0), (x1, y1) = pos[a], pos[b]
        p.append(f'<line x1="{x0}" y1="{y0}" x2="{x1}" y2="{y1}" stroke="rgba(255,255,255,.18)" stroke-width="1.5" '
                 f'stroke-dasharray="4 6" class="rota"/>')
    for nome, (x, y) in pos.items():
        u = us[nome]
        r = 10 + 18 * math.sqrt(u["faturamento"] / mx)
        fm = u["faturamento"] / u["meta"]
        cor = VERDE if fm >= .9 else AMBAR if fm >= .6 else ROSA
        sel = d["nome"] in (nome, "Rede")
        op = 1 if sel else .35
        p.append(f'<g opacity="{op}"><circle cx="{x}" cy="{y}" r="{r}" fill="{cor}" fill-opacity=".18" class="onda"/>'
                 f'<circle cx="{x}" cy="{y}" r="{r * .55}" fill="{cor}"/>'
                 f'<circle cx="{x}" cy="{y}" r="{r * .55}" fill="none" stroke="{cor}" stroke-width="2" class="pulso-pin"/>'
                 f'<text x="{x + r + 8}" y="{y - 4}" class="m-nome">IPR {nome}</text>'
                 f'<text x="{x + r + 8}" y="{y + 14}" class="m-val">{brl(u["faturamento"])} · {pct(fm, 0)} da meta</text></g>')
    ranking = sorted(us.values(), key=lambda u: -u["faturamento"] / u["meta"])
    return card("Rede IPR", [
        svg(f'<svg viewBox="0 0 460 260" preserveAspectRatio="xMidYMid meet">{"".join(p)}</svg>', "mapa"),
        html.Div([html.Div([html.Span(f"{i + 1}º", className="r-pos", style={"color": [OURO, PRATA, BRONZE][i]}),
                            html.Span(u["nome"]), html.B(pct(u["faturamento"] / u["meta"], 0))], className="r-item")
                  for i, u in enumerate(ranking)], className="r-lista"),
    ], "c-mapa", html.Span("% da meta", className="leg"), "mapa")


def bloco_cc(d):
    dias = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]
    cells = []
    for i, linha in enumerate(d["calor"]):
        cells.append(html.Span(dias[i], className="h-dia"))
        for j, v in enumerate(linha):
            if v is None:
                cells.append(html.Span(className="h-cel vazio"))
            else:
                cells.append(html.Span(className="h-cel", title=f"{dias[i]} {7 + j}h · {pct(v, 0)}",
                                       style={"background": f"rgba(34,211,238,{.08 + v * .85:.2f})",
                                              "animationDelay": f"{(i + j) * 25}ms"}))
    cells.append(html.Span())
    cells += [html.Span(f"{h}h" if h % 3 == 1 else "", className="h-hora") for h in range(7, 19)]
    oc = d["ocupacao"]
    cor = VERDE if oc >= .75 else AMBAR if oc >= .5 else VERM
    return card("Centro cirúrgico", [
        html.Div([
            html.Div([conta(oc, "pct", "big"), html.Span("ocupação", className="leg")], className="cc-num"),
            html.Div([
                html.Div([html.Span("Cirurgias", className="mini-r"), html.B(nbr(d["cirurgias"]))], className="mini"),
                html.Div([html.Span("Cancel.", className="mini-r"), html.B(pct(d["cancelamento"]))], className="mini"),
                html.Div([html.Span("No-show", className="mini-r"), html.B(pct(d["no_show"]))], className="mini"),
            ], className="minis col3"),
        ], className="cc-topo"),
        html.Div(cells, className="heat"),
    ], "c-cc", html.Span("Atenção" if oc < .75 else "Ideal", className="selo", style={"color": cor, "borderColor": cor}), "cc")


def bloco_time(d):
    vs = d["vendedores"][:5]
    lider = vs[0]
    rec = foto(lider["nome"], recorte=True)
    linhas = []
    for i, v in enumerate(vs):
        cor = [OURO, PRATA, BRONZE, TX3, TX3][i]
        linhas.append(html.Div([
            html.Span(f"{i + 1}", className="t-pos", style={"color": cor}),
            avatar(v["nome"], 30, cor),
            html.Div([
                html.Div([html.Span(v["nome"], className="t-nome"),
                          html.Span(v.get("unidade", ""), className="t-uni"),
                          html.B(brl(v["valor"]), className="t-val")], className="t-l1"),
                html.Div(html.Div(className="barra-f", style={"width": f"{v['valor'] / lider['valor'] * 100:.0f}%",
                                                              "background": f"linear-gradient(90deg,{ROSA},{VIOLETA})" if i == 0 else "rgba(255,255,255,.22)",
                                                              "animationDelay": f"{i * .08}s"}), className="barra"),
            ], className="t-info"),
        ], className="t-item"))
    heroi = html.Div([
        html.Div(className="heroi-luz"),
        html.Img(src=rec, className="heroi-img") if rec else avatar(lider["nome"], 92, OURO),
        html.Div([html.Span("LÍDER DO MÊS", className="heroi-tag"), html.B(lider["nome"].split()[0]),
                  html.Span(f"{lider['contratos']} contratos")], className="heroi-txt"),
    ], className="heroi")
    return card("Time comercial", [html.Div([heroi, html.Div(linhas, className="t-lista")], className="time")],
                "c-time", html.Span("faturamento", className="leg"), "time")


def bloco_insights(d):
    pj = projecao(d)
    conv = conversoes(d)
    nome_g, v_g, ref_g = min(conv, key=lambda c: c[1] / c[2])
    ins = []
    if pj["proj"] >= d["meta"]:
        ins.append(("ok", "Meta à vista", f"No ritmo atual, fecha em {brl(pj['proj'])} — acima da meta."))
    else:
        ins.append(("ruim", "Ritmo abaixo da meta",
                    f"Projeção de {brl(pj['proj'])} ({pct(pj['proj'] / d['meta'], 0)}). Faltam {brl(pj['por_dia'])} por dia útil."))
    ins.append(("ruim" if v_g < ref_g else "ok", f"Gargalo: {nome_g.lower()}",
                f"{pct(v_g)} contra referência de {pct(ref_g, 0)}."))
    ins.append(("aviso", f"{d['sem_data']} contratos sem data de cirurgia",
                f"{brl(d['sem_data'] * d['ticket'])} aguardando agendamento."))
    vl = d["leads"] / d["anterior"]["leads"] - 1
    ins.append(("ok" if vl >= 0 else "ruim", f"Leads {'subiram' if vl >= 0 else 'caíram'} {pct(abs(vl), 0)}",
                "em relação ao mês anterior."))
    melhor = max(d["unidades"].values(), key=lambda u: u["faturamento"] / u["meta"])
    ins.append(("info", f"IPR {melhor['nome']} lidera a rede", f"{pct(melhor['faturamento'] / melhor['meta'], 0)} da meta atingida."))
    cores = {"ok": VERDE, "ruim": VERM, "aviso": AMBAR, "info": CIANO}
    icones = {"ok": "✓", "ruim": "!", "aviso": "◷", "info": "★"}
    return card("Insights automáticos", [html.Div([
        html.Div([html.Span(icones[t], className="i-ic", style={"color": cores[t], "borderColor": cores[t]}),
                  html.Div([html.B(tit), html.Span(txt, className="i-txt")])], className="i-item",
                 style={"animationDelay": f"{k * .08}s"})
        for k, (t, tit, txt) in enumerate(ins)], className="insights")],
        "c-ins", html.Span("gerados dos dados", className="leg"), "ins")


def bloco_kpis(d):
    a = d["anterior"]
    itens = [
        ("Leads", conta(d["leads"], "int"), delta(d["leads"], a["leads"]), spark(d["hist_leads"], CIANO)),
        ("Contratos", conta(d["contratos"], "int"), delta(d["contratos"], a["contratos"]),
         spark([v / d["ticket"] for v in d["hist_fat"]], VIOLETA)),
        ("Cancelamento", conta(d["cancelamento"], "pct"), delta(d["cancelamento"], a["cancelamento"], True, True),
         spark([d["cancelamento"] * (1 + math.sin(i) * .2) for i in range(8)], AMBAR)),
        ("Conv. orçamento", conta(conversoes(d)[2][1], "pct"), None,
         spark([conversoes(d)[2][1] * (1 + math.cos(i * 1.3) * .12) for i in range(8)], VERDE)),
    ]
    return html.Div([html.Div([html.Span(n, className="k-nome"), html.Div([html.Span(v, className="k-val"), dl], className="k-l"), sp],
                              className="kpi", style={"animationDelay": f"{i * .07}s"})
                     for i, (n, v, dl, sp) in enumerate(itens)], className="kpis", style={"gridArea": "kpis"})


def montar(d):
    return html.Div([bloco_pulso(d), bloco_faturamento(d), bloco_kpis(d), bloco_jornada(d), bloco_mapa(d),
                     bloco_cc(d), bloco_time(d), bloco_insights(d)], className="grade fade")


# ===========================================================================
# APP
# ===========================================================================
app = Dash(__name__, title="IPR Pulse", suppress_callback_exceptions=True,
           external_stylesheets=["https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&"
                                 "family=Space+Grotesk:wght@500;600;700&display=swap"])

LOGO = "logo_ipr.png"
logo = (html.Img(src=app.get_asset_url(LOGO), className="logo") if (Path(__file__).parent / "assets" / LOGO).exists()
        else html.B("IPR", className="logo-txt"))

app.layout = html.Div([
    dcc.Store(id="visao", data="Rede"),
    dcc.Store(id="periodo", data="mes"),
    dcc.Store(id="apresentando", data=False),
    dcc.Interval(id="tick", interval=SEGUNDOS_APRESENTACAO * 1000, disabled=True),
    html.Div([html.Div(className="aurora a1"), html.Div(className="aurora a2"), html.Div(className="aurora a3"),
              html.Div(className="grão")], className="fundo"),
    html.Div([
        html.Div([logo, html.Div(className="sep"),
                  html.Div([html.Span("PULSE", className="marca"), html.Span("Painel Gerencial", className="marca-sub")])],
                 className="tb-esq"),
        html.Div([html.Button(v if v == "Rede" else f"IPR {v}", id=IDS_VISAO[v], className="seg", n_clicks=0) for v in VISOES],
                 className="segs"),
        html.Div([html.Button(n, id=f"p-{k}", className="chip", n_clicks=0) for k, n in PERIODOS.items()], className="chips"),
        html.Div([
            html.Button([html.Span("⌘K", className="kbd"), " Comandos"], id="btn-cmd", className="tb-btn"),
            html.Button("▶ Apresentar", id="btn-apresentar", className="tb-btn", n_clicks=0),
            html.Div([html.Span(className="vivo"), html.Span(id="relogio")], className="tb-vivo"),
            avatar(GERENTE["nome"], 34),
        ], className="tb-dir"),
        html.Div(id="progresso", className="progresso"),
    ], className="topo"),
    html.Div(id="corpo", className="corpo"),
    # paleta de comandos (montada pelo JS)
    html.Div(id="cmd", className="cmd", children=[
        html.Div([
            html.Div([html.Span("⌕", className="cmd-lupa"),
                      dcc.Input(id="cmd-input", placeholder="Buscar comando… (unidade, período, tela cheia, apresentar)",
                                className="cmd-input", debounce=False, autoComplete="off")], className="cmd-busca"),
            html.Div(className="cmd-lista", id="cmd-lista", children=[
                html.Div([html.Span(ic, className="cmd-ic"), html.Span(t), html.Span(atalho, className="cmd-atalho")],
                         className="cmd-item", **{"data-alvo": alvo, "data-busca": t.lower()})
                for ic, t, alvo, atalho in
                [("◎", "Ver a rede inteira", "v-rede", "1"), ("◉", "IPR Santos", "v-santos", "2"),
                 ("◉", "IPR São Paulo", "v-sp", "3"), ("◉", "IPR Campinas", "v-campinas", "4"),
                 ("▦", "Período: este mês", "p-mes", ""), ("▦", "Período: mês passado", "p-ant", ""),
                 ("▦", "Período: trimestre", "p-tri", ""), ("⛶", "Tela cheia", "tela-cheia", "F"),
                 ("▶", "Modo apresentação", "btn-apresentar", "P")]]),
            html.Div("↑↓ navegar · Enter executar · Esc fechar", className="cmd-rodape"),
        ], className="cmd-caixa"),
    ]),
], className="app")


@app.callback(Output("visao", "data"),
              [Input(i, "n_clicks") for i in IDS_VISAO.values()] + [Input("tick", "n_intervals")],
              State("visao", "data"), prevent_initial_call=True)
def trocar_visao(*args):
    atual = args[-1]
    if ctx.triggered_id == "tick":
        return VISOES[(VISOES.index(atual) + 1) % len(VISOES)]
    return {v: k for k, v in IDS_VISAO.items()}[ctx.triggered_id]


@app.callback(Output("periodo", "data"), [Input(f"p-{k}", "n_clicks") for k in PERIODOS], prevent_initial_call=True)
def trocar_periodo(*_):
    return ctx.triggered_id[2:]


@app.callback(Output("apresentando", "data"), Output("tick", "disabled"), Output("btn-apresentar", "children"),
              Output("btn-apresentar", "className"),
              Input("btn-apresentar", "n_clicks"), State("apresentando", "data"), prevent_initial_call=True)
def apresentar(_, on):
    on = not on
    return on, not on, ("■ Parar" if on else "▶ Apresentar"), "tb-btn ativo" if on else "tb-btn"


@app.callback(Output("corpo", "children"), Output("relogio", "children"),
              Output("progresso", "children"),
              [Output(i, "className") for i in IDS_VISAO.values()] + [Output(f"p-{k}", "className") for k in PERIODOS],
              Input("visao", "data"), Input("periodo", "data"), Input("apresentando", "data"))
def atualizar(visao, periodo, on):
    d = carregar_dados(visao, periodo)
    barra = html.Div(className="progresso-f", style={"animationDuration": f"{SEGUNDOS_APRESENTACAO}s"},
                     key=f"{visao}{datetime.now().timestamp()}") if on else None
    return ([montar(d)], f"ao vivo · {datetime.now():%H:%M}", barra,
            *["seg ativo" if v == visao else "seg" for v in VISOES],
            *["chip ativo" if k == periodo else "chip" for k in PERIODOS])


# ===========================================================================
# ESTILO
# ===========================================================================
CSS = f"""
* {{ box-sizing:border-box; }}
html, body {{ margin:0; height:100%; background:{BG}; color:{TX}; font-family:Inter, 'Segoe UI', sans-serif; overflow:hidden; }}
button {{ font-family:inherit; }}
.app {{ position:relative; height:100vh; display:flex; flex-direction:column; }}

/* fundo aurora */
.fundo {{ position:fixed; inset:0; z-index:0; overflow:hidden; pointer-events:none; }}
.aurora {{ position:absolute; width:60vw; height:60vw; border-radius:50%; filter:blur(90px); opacity:.33; }}
.a1 {{ background:{ROSA}; top:-30vw; left:-15vw; animation: deriva 26s ease-in-out infinite alternate; }}
.a2 {{ background:{VIOLETA}; top:-20vw; right:-25vw; opacity:.26; animation: deriva 32s ease-in-out infinite alternate-reverse; }}
.a3 {{ background:{CIANO}; bottom:-45vw; left:25vw; opacity:.12; animation: deriva 40s ease-in-out infinite alternate; }}
@keyframes deriva {{ to {{ transform: translate(8vw, 6vw) scale(1.15); }} }}
.grão {{ position:absolute; inset:0; opacity:.06;
  background-image: radial-gradient(rgba(255,255,255,.7) 1px, transparent 1px); background-size: 3px 3px; }}

/* topo */
.topo {{ position:relative; z-index:2; display:flex; align-items:center; gap:22px; padding:12px 22px; height:64px;
  border-bottom:1px solid rgba(255,255,255,.07); background:rgba(7,6,11,.55); backdrop-filter:blur(14px); }}
.tb-esq {{ display:flex; align-items:center; gap:14px; }}
.logo {{ height:26px; filter: brightness(1.15); }}
.logo-txt {{ color:{ROSA}; font-size:22px; }}
.sep {{ width:1px; height:26px; background:rgba(255,255,255,.12); }}
.marca {{ font-family:'Space Grotesk', Inter, 'Segoe UI', Arial, sans-serif; font-weight:700; letter-spacing:5px; font-size:15px;
  background: linear-gradient(90deg,{ROSA},{VIOLETA}); -webkit-background-clip:text; background-clip:text; color:transparent; display:block; }}
.marca-sub {{ font-size:11.5px; color:{TX2}; display:block; margin-top:-2px; }}
.segs {{ display:flex; gap:2px; padding:3px; border-radius:8px; background:rgba(255,255,255,.04); border:1px solid rgba(255,255,255,.07); margin-left:10px; }}
.seg {{ border:0; background:transparent; color:{TX2}; padding:7px 14px; border-radius:6px; font-size:13px; font-weight:600; cursor:pointer; transition:.2s; }}
.seg:hover {{ color:{TX}; }}
.seg.ativo {{ color:{TX}; background: linear-gradient(135deg, rgba(255,45,138,.35), rgba(139,92,246,.35)); box-shadow: inset 0 0 0 1px rgba(255,255,255,.12); }}
.chips {{ display:flex; gap:6px; }}
.chip {{ border:1px solid rgba(255,255,255,.1); background:transparent; color:{TX2}; padding:6px 12px; border-radius:999px; font-size:12px; cursor:pointer; }}
.chip.ativo {{ color:{TX}; border-color:{ROSA}; background:rgba(255,45,138,.12); }}
.tb-dir {{ margin-left:auto; display:flex; align-items:center; gap:12px; }}
.tb-btn {{ border:1px solid rgba(255,255,255,.1); background:rgba(255,255,255,.04); color:{TX}; padding:7px 12px; border-radius:6px;
  font-size:12.5px; font-weight:600; cursor:pointer; display:flex; align-items:center; gap:6px; }}
.tb-btn:hover {{ border-color:rgba(255,255,255,.25); }}
.tb-btn.ativo {{ border-color:{ROSA}; color:{ROSA}; }}
.kbd {{ font-size:10.5px; padding:1px 5px; border-radius:4px; background:rgba(255,255,255,.1); color:{TX2}; }}
.tb-vivo {{ display:flex; align-items:center; gap:7px; font-size:12px; color:{TX2}; }}
.vivo {{ width:7px; height:7px; border-radius:50%; background:{VERDE}; animation: bate 1.6s infinite; }}
@keyframes bate {{ 0% {{ box-shadow:0 0 0 0 rgba(52,211,153,.7); }} 70% {{ box-shadow:0 0 0 8px transparent; }} 100% {{ box-shadow:0 0 0 0 transparent; }} }}
.progresso {{ position:absolute; left:0; right:0; bottom:-1px; height:2px; }}
.progresso-f {{ height:100%; background: linear-gradient(90deg,{ROSA},{VIOLETA}); transform-origin:left;
  animation-name: enche; animation-timing-function:linear; animation-fill-mode:both; }}
@keyframes enche {{ from {{ transform:scaleX(0); }} to {{ transform:scaleX(1); }} }}

/* grade */
.corpo {{ position:relative; z-index:1; flex:1; min-height:0; padding:14px 18px 16px; }}
.grade {{ height:100%; display:grid; gap:12px;
  grid-template-columns: repeat(12, minmax(0,1fr));
  grid-template-rows: minmax(0,1.12fr) auto minmax(0,1.18fr) minmax(0,1fr);
  grid-template-areas:
    "pulso pulso pulso fat fat fat fat fat fat fat fat fat"
    "kpis kpis kpis kpis kpis kpis kpis kpis kpis kpis kpis kpis"
    "jornada jornada jornada jornada jornada jornada mapa mapa mapa cc cc cc"
    "time time time time time ins ins ins ins cc cc cc"; }}
.fade > * {{ animation: entra .6s cubic-bezier(.2,.8,.2,1) both; }}
.fade > *:nth-child(2) {{ animation-delay:.05s }} .fade > *:nth-child(3) {{ animation-delay:.1s }}
.fade > *:nth-child(4) {{ animation-delay:.15s }} .fade > *:nth-child(5) {{ animation-delay:.2s }}
.fade > *:nth-child(6) {{ animation-delay:.25s }} .fade > *:nth-child(7) {{ animation-delay:.3s }} .fade > *:nth-child(8) {{ animation-delay:.35s }}
@keyframes entra {{ from {{ opacity:0; transform: translateY(14px); }} }}

/* card de vidro */
.card {{ position:relative; min-height:0; display:flex; flex-direction:column; border-radius:8px; padding:14px 16px; overflow:hidden;
  background: linear-gradient(180deg, rgba(255,255,255,.055), rgba(255,255,255,.02));
  border:1px solid rgba(255,255,255,.08); backdrop-filter: blur(18px);
  box-shadow: 0 1px 0 rgba(255,255,255,.06) inset, 0 20px 40px rgba(0,0,0,.25); transition: border-color .3s, transform .3s; }}
.card::before {{ content:''; position:absolute; inset:0; border-radius:inherit; pointer-events:none; opacity:0; transition:opacity .4s;
  background: radial-gradient(400px circle at var(--mx,50%) var(--my,50%), rgba(255,45,138,.10), transparent 45%); }}
.card:hover {{ border-color:rgba(255,255,255,.16); }}
.card:hover::before {{ opacity:1; }}
.c-topo {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; position:relative; z-index:1; }}
.c-tit {{ font-family:'Space Grotesk', Inter, 'Segoe UI', Arial, sans-serif; font-size:12px; font-weight:600; letter-spacing:2px; text-transform:uppercase; color:{TX2}; }}
.c-corpo {{ flex:1; min-height:0; position:relative; display:flex; flex-direction:column; }}
.selo {{ font-size:11px; font-weight:700; padding:2px 9px; border:1px solid; border-radius:999px; }}
.leg {{ font-size:12px; color:{TX2}; }}
.leg b {{ color:{TX}; }}
.big {{ font-family:'Space Grotesk', Inter, 'Segoe UI', Arial, sans-serif; font-size:40px; font-weight:700; letter-spacing:-1px; line-height:1; }}
.delta {{ font-size:11.5px; font-weight:700; padding:2px 6px; border-radius:4px; }}
.delta.bom {{ color:{VERDE}; background:rgba(52,211,153,.12); }}
.delta.ruim {{ color:{VERM}; background:rgba(248,113,113,.12); }}
.barra {{ height:5px; border-radius:3px; background:rgba(255,255,255,.07); overflow:hidden; }}
.barra-f {{ height:100%; border-radius:3px; transform-origin:left; animation: cresce 1.1s cubic-bezier(.2,.8,.2,1) both; }}
@keyframes cresce {{ from {{ transform:scaleX(0); }} }}
.svgbox {{ flex:1; min-height:0; display:flex; }}
.svgbox svg {{ width:100%; height:100%; display:block; overflow:visible; }}
.minis {{ display:grid; grid-template-columns:repeat(3,1fr); gap:8px; }}
.mini {{ padding:8px 10px; border-radius:6px; background:rgba(255,255,255,.035); border:1px solid rgba(255,255,255,.06); }}
.mini-r {{ display:block; font-size:10.5px; color:{TX3}; text-transform:uppercase; letter-spacing:.8px; margin-bottom:2px; }}
.mini b {{ font-size:15px; }}

/* pulso */
.ecg-fundo {{ position:absolute; left:-16px; right:-16px; top:30%; height:40%; opacity:.25; }}
.ecg {{ stroke-dasharray: 1400; stroke-dashoffset:1400; animation: ecg 3.2s linear infinite; }}
@keyframes ecg {{ to {{ stroke-dashoffset:0; }} }}
.pulso {{ flex:1; display:flex; align-items:center; gap:22px; position:relative; }}
.anel-wrap {{ position:relative; width:min(170px, 100%); aspect-ratio:1; flex-shrink:0; }}
.anel-wrap .svgbox {{ position:absolute; inset:0; }}
.anel-prog {{ animation: anel 1.6s cubic-bezier(.2,.8,.2,1) .2s forwards; filter: drop-shadow(0 0 8px rgba(255,45,138,.6)); }}
@keyframes anel {{ to {{ stroke-dashoffset: var(--alvo); }} }}
.anel-centro {{ position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; }}
.score {{ font-family:'Space Grotesk', Inter, 'Segoe UI', Arial, sans-serif; font-size:52px; font-weight:700; line-height:1; letter-spacing:-2px; }}
.score-de {{ font-size:11px; color:{TX2}; }}
.dims {{ flex:1; display:flex; flex-direction:column; gap:12px; }}
.dim-linha {{ display:flex; justify-content:space-between; font-size:13px; margin-bottom:4px; }}
.dim-nome {{ color:{TX2}; }}

/* faturamento */
.fat {{ flex:1; min-height:0; display:grid; grid-template-columns: minmax(270px, .8fr) 2fr; gap:20px; }}
.fat-esq {{ display:flex; flex-direction:column; justify-content:space-between; gap:10px; min-width:0; }}
.big-linha {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; }}
.fat-esq .big {{ font-size:46px; }}
.meta-trilho {{ position:relative; height:10px; border-radius:5px; background:rgba(255,255,255,.07); overflow:visible; }}
.meta-real {{ position:absolute; left:0; top:0; bottom:0; border-radius:5px; background: linear-gradient(90deg,{ROSA},{VIOLETA});
  box-shadow:0 0 14px rgba(255,45,138,.5); transform-origin:left; animation: cresce 1.3s cubic-bezier(.2,.8,.2,1) both; }}
.meta-proj {{ position:absolute; top:0; bottom:0; background: repeating-linear-gradient(45deg, rgba(139,92,246,.6) 0 4px, transparent 4px 8px); border-radius:0 5px 5px 0; }}
.meta-tempo {{ position:absolute; top:-5px; width:2px; height:20px; background:{TX}; border-radius:1px; }}
.fat-graf {{ min-height:0; }}

/* kpis */
.kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }}
.kpi {{ display:grid; grid-template-columns: 1fr 150px; grid-template-rows:auto auto; align-items:center; column-gap:12px;
  padding:10px 16px; border-radius:8px; background: linear-gradient(180deg, rgba(255,255,255,.05), rgba(255,255,255,.02));
  border:1px solid rgba(255,255,255,.08); backdrop-filter: blur(18px); animation: entra .6s both; }}
.k-nome {{ font-size:11px; letter-spacing:1.5px; text-transform:uppercase; color:{TX2}; grid-column:1; }}
.k-l {{ display:flex; align-items:baseline; gap:8px; grid-column:1; }}
.k-val {{ font-family:'Space Grotesk', Inter, 'Segoe UI', Arial, sans-serif; font-size:26px; font-weight:700; }}
.spark {{ grid-column:2; grid-row:1 / span 2; height:38px; }}
.spark svg {{ width:100%; height:100%; display:block; }}
.spark-l {{ stroke-dasharray:400; stroke-dashoffset:400; animation: traca 1.4s ease-out forwards; }}
@keyframes traca {{ to {{ stroke-dashoffset:0; }} }}

/* jornada */
.jornada svg text {{ font-family:Inter; }}
.j-num {{ fill:{TX}; font-size:15px; font-weight:700; font-family:'Space Grotesk', Inter, Arial, sans-serif !important; }}
.j-nome {{ fill:{TX2}; font-size:11.5px; letter-spacing:1px; text-transform:uppercase; }}
.j-taxa {{ font-size:13px; font-weight:700; }}
.j-perda {{ fill:{VERM}; font-size:11.5px; font-weight:600; opacity:.8; }}
.j-garg {{ fill:#1a0b10; font-size:9.5px; font-weight:800; letter-spacing:1px; }}
.gargalo {{ animation: pisca 1.8s ease-in-out infinite; }}
@keyframes pisca {{ 50% {{ opacity:.55; }} }}
.banda {{ transform-origin:left center; animation: abre .9s cubic-bezier(.2,.8,.2,1) both; animation-delay: calc(var(--i) * 90ms); }}
@keyframes abre {{ from {{ opacity:0; transform:scaleX(.4); }} }}
.fluxo {{ animation: flui 1.2s linear infinite; }}
@keyframes flui {{ to {{ stroke-dashoffset:-24; }} }}
.perda {{ animation: entra 1s .5s both; }}

/* mapa */
.c-mapa .c-corpo {{ display:flex; flex-direction:column; gap:10px; }}
.mapa {{ height:100%; }}
.m-nome {{ fill:{TX}; font-size:15px; font-weight:700; font-family:Inter; }}
.m-val {{ fill:{TX2}; font-size:12.5px; font-family:Inter; }}
.m-oceano {{ fill:rgba(34,211,238,.45); font-size:10px; letter-spacing:2px; text-transform:uppercase; font-family:Inter; }}
.onda {{ transform-box:fill-box; transform-origin:center; animation: onda 2.6s ease-out infinite; }}
@keyframes onda {{ from {{ transform:scale(.6); opacity:.9; }} to {{ transform:scale(1.6); opacity:0; }} }}
.pulso-pin {{ transform-box:fill-box; transform-origin:center; animation: onda 2.6s ease-out .8s infinite; }}
.rota {{ animation: flui 1.6s linear infinite; }}
.r-lista {{ display:grid; grid-template-columns:repeat(3,1fr); gap:8px; }}
.r-item {{ display:grid; grid-template-columns: 22px 1fr auto; gap:6px; white-space:nowrap; font-size:12.5px; padding:7px 8px; border-radius:6px; background:rgba(255,255,255,.035); }}
.r-pos {{ font-weight:800; }}

/* centro cirúrgico */
.cc-topo {{ display:flex; flex-direction:column; gap:10px; margin-bottom:10px; }}
.cc-num {{ display:flex; align-items:baseline; gap:8px; }}
.cc-num .big {{ color:{CIANO}; text-shadow: 0 0 24px rgba(34,211,238,.35); }}
.col3 .mini b {{ font-size:14px; }}
.heat {{ flex:1; min-height:0; display:grid; grid-template-columns: 30px repeat(12, 1fr); grid-auto-rows:1fr; gap:3px; }}
.h-dia {{ font-size:10.5px; color:{TX2}; display:flex; align-items:center; }}
.h-hora {{ font-size:9.5px; color:{TX3}; text-align:center; }}
.h-cel {{ border-radius:3px; animation: entra .5s both; transition: transform .15s; }}
.h-cel:hover {{ transform:scale(1.25); outline:1px solid {CIANO}; }}
.h-cel.vazio {{ background: repeating-linear-gradient(45deg, rgba(255,255,255,.04) 0 3px, transparent 3px 6px); }}

/* time */
.time {{ flex:1; min-height:0; display:grid; grid-template-columns: 150px 1fr; gap:16px; }}
.heroi {{ position:relative; display:flex; flex-direction:column; align-items:center; justify-content:flex-end; gap:8px; overflow:hidden; border-radius:6px;
  background: linear-gradient(180deg, rgba(245,197,66,.06), rgba(245,197,66,.16)); border:1px solid rgba(245,197,66,.25); }}
.heroi-luz {{ position:absolute; inset:auto -20% -30% -20%; height:70%; background: radial-gradient(closest-side, rgba(245,197,66,.45), transparent); }}
.heroi-img {{ position:absolute; bottom:0; left:50%; transform:translateX(-50%); height:96%; object-fit:contain; filter: drop-shadow(0 8px 14px rgba(0,0,0,.5)); }}
.heroi-txt {{ position:relative; z-index:1; width:100%; padding:8px 10px; display:flex; flex-direction:column;
  background: linear-gradient(0deg, rgba(7,6,11,.95), transparent); font-size:11px; color:{TX2}; }}
.heroi-txt b {{ font-size:16px; color:{TX}; }}
.heroi-tag {{ color:{OURO}; font-weight:800; letter-spacing:1.5px; font-size:9.5px; }}
.t-lista {{ display:flex; flex-direction:column; justify-content:space-around; gap:4px; min-width:0; }}
.t-item {{ display:flex; align-items:center; gap:10px; }}
.t-pos {{ font-family:'Space Grotesk', Inter, 'Segoe UI', Arial, sans-serif; font-weight:700; width:14px; }}
.t-info {{ flex:1; min-width:0; }}
.t-l1 {{ display:flex; align-items:baseline; gap:8px; font-size:13px; margin-bottom:4px; }}
.t-nome {{ font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.t-uni {{ font-size:10.5px; color:{TX3}; }}
.t-val {{ margin-left:auto; white-space:nowrap; }}
.av {{ border-radius:50%; border:2px solid; object-fit:cover; object-position:50% 20%; flex-shrink:0; display:block; }}
.av-ini {{ display:flex; align-items:center; justify-content:center; font-weight:800; background:rgba(255,255,255,.05); }}

/* insights */
.insights {{ display:flex; flex-direction:column; gap:7px; overflow:hidden; }}
.i-item {{ display:flex; gap:10px; align-items:flex-start; font-size:12.5px; line-height:1.35; animation: entra .5s both; }}
.i-ic {{ width:22px; height:22px; flex-shrink:0; border-radius:50%; border:1.5px solid; display:flex; align-items:center;
  justify-content:center; font-size:11px; font-weight:800; }}
.i-item b {{ display:block; font-size:13px; }}
.i-txt {{ color:{TX2}; }}

/* paleta de comandos */
.cmd {{ position:fixed; inset:0; z-index:100; display:none; align-items:flex-start; justify-content:center; padding-top:16vh;
  background:rgba(4,3,8,.6); backdrop-filter: blur(6px); }}
.cmd.aberto {{ display:flex; }}
.cmd-caixa {{ width:560px; border-radius:10px; overflow:hidden; background:rgba(20,15,28,.96); border:1px solid rgba(255,255,255,.12);
  box-shadow: 0 30px 80px rgba(0,0,0,.6), 0 0 0 1px rgba(255,45,138,.15); animation: entra .2s both; }}
.cmd-busca {{ display:flex; align-items:center; gap:10px; padding:14px 16px; border-bottom:1px solid rgba(255,255,255,.08); }}
.cmd-lupa {{ color:{TX2}; font-size:18px; }}
.cmd-input {{ flex:1; background:transparent; border:0; outline:0; color:{TX}; font-size:15px; font-family:inherit; }}
.cmd-lista {{ max-height:360px; overflow:auto; padding:6px; }}
.cmd-item {{ display:flex; align-items:center; gap:12px; padding:10px 12px; border-radius:6px; font-size:14px; cursor:pointer; color:{TX}; }}
.cmd-item.sel {{ background: linear-gradient(90deg, rgba(255,45,138,.22), rgba(139,92,246,.12)); }}
.cmd-ic {{ width:20px; text-align:center; color:{ROSA}; }}
.cmd-atalho {{ margin-left:auto; font-size:11px; color:{TX3}; border:1px solid rgba(255,255,255,.12); padding:1px 6px; border-radius:4px; }}
.cmd-atalho:empty {{ display:none; }}
.cmd-rodape {{ padding:8px 16px; font-size:11px; color:{TX3}; border-top:1px solid rgba(255,255,255,.06); }}
"""

JS = """
(function () {
  const br = (v, c) => v.toLocaleString('pt-BR', {minimumFractionDigits: c, maximumFractionDigits: c});
  const brl = v => Math.abs(v) >= 1e6 ? 'R$ ' + br(v / 1e6, 2) + ' mi' : Math.abs(v) >= 1e3 ? 'R$ ' + br(v / 1e3, 1) + ' mil' : 'R$ ' + br(v, 0);
  const fmt = {brl: brl, int: v => br(Math.round(v), 0), pct: v => br(v * 100, 1) + '%', pct0: v => br(v * 100, 0) + '%'};
  function conta(el) {
    if (el.dataset.feito === el.dataset.alvo) return;
    el.dataset.feito = el.dataset.alvo;
    const alvo = parseFloat(el.dataset.alvo), f = fmt[el.dataset.fmt], t0 = performance.now();
    const passo = t => { const p = Math.min((t - t0) / 1300, 1), e = 1 - Math.pow(1 - p, 3);
      el.textContent = f(alvo * e); if (p < 1) requestAnimationFrame(passo); else el.textContent = f(alvo); };
    requestAnimationFrame(passo);
  }
  function desenha(el) {   // desenhos SVG feitos em Python
    if (el.dataset.feito === el.dataset.svg) return;
    el.dataset.feito = el.dataset.svg; el.innerHTML = el.dataset.svg;
  }
  new MutationObserver(() => {
    document.querySelectorAll('.countup').forEach(conta);
    document.querySelectorAll('[data-svg]').forEach(desenha);
  }).observe(document.documentElement, {childList: true, subtree: true});

  // brilho que segue o mouse nos cards
  document.addEventListener('mousemove', e => {
    const c = e.target.closest('.card'); if (!c) return;
    const r = c.getBoundingClientRect();
    c.style.setProperty('--mx', (e.clientX - r.left) + 'px'); c.style.setProperty('--my', (e.clientY - r.top) + 'px');
  });

  // paleta de comandos
  const cmd = () => document.getElementById('cmd');
  let sel = 0;
  function itens() { return [...document.querySelectorAll('.cmd-item')].filter(i => i.style.display !== 'none'); }
  function marca() { itens().forEach((i, k) => i.classList.toggle('sel', k === sel)); }
  function abre() { cmd().classList.add('aberto'); const inp = document.getElementById('cmd-input'); inp.value = ''; filtra(''); setTimeout(() => inp.focus(), 30); }
  function fecha() { cmd().classList.remove('aberto'); }
  function filtra(q) { document.querySelectorAll('.cmd-item').forEach(i => i.style.display = i.dataset.busca.includes(q.toLowerCase()) ? '' : 'none'); sel = 0; marca(); }
  function executa(alvo) {
    fecha();
    if (alvo === 'tela-cheia') { document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen(); return; }
    const b = document.getElementById(alvo); if (b) b.click();
  }
  document.addEventListener('input', e => { if (e.target.id === 'cmd-input') filtra(e.target.value); });
  document.addEventListener('click', e => {
    if (e.target.closest('#btn-cmd')) { abre(); return; }
    const it = e.target.closest('.cmd-item'); if (it) { executa(it.dataset.alvo); return; }
    if (e.target.id === 'cmd') fecha();
  });
  document.addEventListener('keydown', e => {
    const aberto = cmd() && cmd().classList.contains('aberto');
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); aberto ? fecha() : abre(); return; }
    if (aberto) {
      const lista = itens();
      if (e.key === 'Escape') fecha();
      if (e.key === 'ArrowDown') { sel = (sel + 1) % lista.length; marca(); e.preventDefault(); }
      if (e.key === 'ArrowUp') { sel = (sel - 1 + lista.length) % lista.length; marca(); e.preventDefault(); }
      if (e.key === 'Enter' && lista[sel]) executa(lista[sel].dataset.alvo);
      return;
    }
    if (e.target.tagName === 'INPUT') return;
    const atalhos = {'1': 'v-rede', '2': 'v-santos', '3': 'v-sp', '4': 'v-campinas', 'p': 'btn-apresentar', 'f': 'tela-cheia'};
    const a = atalhos[e.key.toLowerCase()]; if (a) executa(a);
  });
})();
"""

app.index_string = f"""<!DOCTYPE html>
<html lang="pt-BR"><head>{{%metas%}}<title>{{%title%}}</title>{{%favicon%}}{{%css%}}<style>{CSS}</style></head>
<body>{{%app_entry%}}<footer>{{%config%}}{{%scripts%}}{{%renderer%}}</footer><script>{JS}</script></body></html>"""

if __name__ == "__main__":
    app.run(debug=True, port=8052)
