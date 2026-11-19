"""
Dashboard Overview (preto + verde neon) ligado no Postgres local do dash de marketing.

Instalar:  pip install dash plotly pandas sqlalchemy psycopg2-binary
Rodar:     python dashboard_overview.py   ->  abrir http://127.0.0.1:8050

Antes de rodar, ajuste o bloco CONEXÃO abaixo (banco, usuário e senha).
Todas as queries são só SELECT (leitura).
"""

import os
import unicodedata
from pathlib import Path
from datetime import date

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, dcc, html
from sqlalchemy import create_engine, text

# ---------------------------------------------------------------------------
# CONEXÃO — ajuste aqui (ou use variáveis de ambiente)
# ---------------------------------------------------------------------------
def _carregar_env():
    """Lê o arquivo .env da pasta do projeto (KEY=valor), se existir."""
    arq = Path(__file__).parent / ".env"
    if arq.exists():
        for linha in arq.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                k, v = linha.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_carregar_env()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "backoffice_local")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "SUA_SENHA_AQUI")
SCHEMA = os.getenv("DB_SCHEMA", "cm_sync")          # schema onde estão as vw_*

engine = create_engine(
    f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
    pool_pre_ping=True,
)

UNIDADES = {"Todas": None, "São Paulo": 15110, "Santos": 18994, "Campinas": 19513}

# ---------------------------------------------------------------------------
# Paleta
# ---------------------------------------------------------------------------
BG = "#0a0d0b"
PANEL = "#111613"
BORDA = "#1f2a23"
VERDE = "#3ddc84"
VERDE_ESCURO = "#1f7a4a"
VERDE_CLARO = "#8ef5b8"
TEXTO = "#e8f0eb"
TEXTO_SEC = "#8a9a90"
VERMELHO = "#ff6b6b"
FONTE = "Inter, Segoe UI, sans-serif"

# ---------------------------------------------------------------------------
# Queries (só SELECT). Filtros padrão: deleted_at IS NULL, período por emissao,
# unidade opcional (estabelecimento_id).
# ---------------------------------------------------------------------------
FILTRO_UNIDADE = "AND (CAST(:estabelecimento_id AS bigint) IS NULL OR estabelecimento_id = CAST(:estabelecimento_id AS bigint))"

SQL_FATURAMENTO = f"""
SELECT COALESCE(SUM(valor_contrato), 0) AS valor
FROM {SCHEMA}.vw_contratos
WHERE deleted_at IS NULL
  AND emissao::date BETWEEN :data_inicial AND :data_final
  {FILTRO_UNIDADE}
"""

SQL_A_RECEBER = f"""
SELECT COALESCE(SUM(valor_devido), 0) AS valor
FROM {SCHEMA}.vw_recebiveis
WHERE deleted_at IS NULL
  AND data_baixa IS NULL
  AND emissao::date BETWEEN :data_inicial AND :data_final
  {FILTRO_UNIDADE}
"""

SQL_RECEBIDO_MES = f"""
SELECT date_trunc('month', emissao)::date AS mes,
       SUM(valor_titulo) AS recebido
FROM {SCHEMA}.vw_recebiveis
WHERE deleted_at IS NULL
  AND data_baixa IS NOT NULL
  AND emissao::date BETWEEN :data_inicial AND :data_final
  {FILTRO_UNIDADE}
GROUP BY 1
ORDER BY 1
"""

SQL_PAGO_MES = f"""
SELECT date_trunc('month', emissao)::date AS mes,
       SUM(valor_titulo) AS pago
FROM {SCHEMA}.vw_exigiveis
WHERE deleted_at IS NULL
  AND emissao::date BETWEEN :data_inicial AND :data_final
  {FILTRO_UNIDADE}
GROUP BY 1
ORDER BY 1
"""

SQL_RANKING = f"""
SELECT COALESCE(NULLIF(TRIM(plano_contas), ''), 'Sem plano de contas') AS nome,
       SUM(valor_contrato) AS valor
FROM {SCHEMA}.vw_contratos
WHERE deleted_at IS NULL
  AND emissao::date BETWEEN :data_inicial AND :data_final
  {FILTRO_UNIDADE}
GROUP BY 1
ORDER BY 2 DESC
LIMIT 10
"""

SQL_PODIO = f"""
SELECT TRIM(vendedor)        AS nome,
       SUM(valor_contrato)   AS valor,
       COUNT(*)              AS contratos
FROM {SCHEMA}.vw_contratos
WHERE deleted_at IS NULL
  AND emissao::date BETWEEN :data_inicial AND :data_final
  AND NULLIF(TRIM(vendedor), '') IS NOT NULL
  {FILTRO_UNIDADE}
GROUP BY 1
ORDER BY 2 DESC
LIMIT 3
"""

SQL_EM_ABERTO = f"""
SELECT date_trunc('month', emissao)::date AS mes,
       SUM(valor_devido) AS valor
FROM {SCHEMA}.vw_recebiveis
WHERE deleted_at IS NULL
  AND data_baixa IS NULL
  AND emissao::date BETWEEN :data_inicial AND :data_final
  {FILTRO_UNIDADE}
GROUP BY 1
ORDER BY 1
"""


def traduzir_erro(e):
    """No Windows em português o Postgres manda o erro com acento (cp1252)
    e o Python não consegue ler; aqui decodifica a mensagem original."""
    alvo = e
    while alvo is not None:
        if isinstance(alvo, UnicodeDecodeError):
            return alvo.object.decode("cp1252", errors="replace")
        alvo = alvo.__cause__ or alvo.__context__
    return e


def consultar(sql, data_inicial, data_final, estabelecimento_id):
    params = {"data_inicial": data_inicial, "data_final": data_final,
              "estabelecimento_id": estabelecimento_id}
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)


def tabela_existe(nome):
    with engine.connect() as conn:
        return conn.execute(text("SELECT to_regclass(:t) IS NOT NULL"),
                            {"t": f"{SCHEMA}.{nome}"}).scalar()


def valor_unico(sql, *args):
    df = consultar(sql, *args)
    return float(df.iloc[0, 0] or 0)


def mesmo_periodo_ano_anterior(d):
    d = pd.Timestamp(d)
    try:
        return d.replace(year=d.year - 1).date()
    except ValueError:  # 29/02
        return d.replace(year=d.year - 1, day=28).date()


# ---------------------------------------------------------------------------
# Helpers visuais
# ---------------------------------------------------------------------------
MESES_PT = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
            "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def rotulo_mes(d):
    d = pd.Timestamp(d)
    return f"{MESES_PT[d.month - 1]}/{str(d.year)[2:]}"


def brl(v):
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def layout_grafico(fig, titulo=None):
    fig.update_layout(
        title=dict(text=titulo, font=dict(color=TEXTO, size=13), x=0.01) if titulo else None,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONTE, color=TEXTO_SEC, size=11),
        margin=dict(l=10, r=10, t=40 if titulo else 10, b=10),
        legend=dict(orientation="h", y=-0.15, x=1, xanchor="right",
                    font=dict(color=TEXTO_SEC)),
        hoverlabel=dict(bgcolor=PANEL, bordercolor=VERDE, font_color=TEXTO),
        separators=",.",
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=BORDA)
    fig.update_yaxes(gridcolor=BORDA, zeroline=False)
    return fig


def fig_vazia(titulo, msg="Sem dados no período"):
    fig = go.Figure()
    fig.add_annotation(text=msg, showarrow=False, font=dict(color=TEXTO_SEC, size=13))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return layout_grafico(fig, titulo)


def card_kpi(titulo, valor, valor_aa, destaque=False, aviso=None):
    if aviso:
        valor, valor_aa = 0, 0
    if aviso:
        txt_var, cor_var = "", TEXTO_SEC
    elif valor_aa:
        var = (valor / valor_aa - 1) * 100
        txt_var = f"({var:+.1f}%)".replace(".", ",")
        cor_var = VERDE_CLARO if var >= 0 else VERMELHO
    else:
        txt_var, cor_var = "(sem base)", TEXTO_SEC
    estilo = {
        "flex": "1", "minWidth": "260px",
        "padding": "18px 22px",
        "borderRadius": "14px",
        "border": f"1px solid {VERDE if destaque else VERDE_ESCURO}",
        "background": (f"linear-gradient(135deg, {VERDE_ESCURO} 0%, {PANEL} 70%)"
                       if destaque else
                       f"linear-gradient(135deg, #16241b 0%, {PANEL} 80%)"),
        "boxShadow": f"0 0 18px {VERDE}33" if destaque else "none",
    }
    return html.Div(style=estilo, children=[
        html.Div(titulo, style={"color": TEXTO, "fontSize": "13px", "marginBottom": "10px"}),
        html.Div("—" if aviso else brl(valor),
                 style={"color": "#fff", "fontSize": "28px",
                        "fontWeight": 700, "letterSpacing": "0.3px"}),
        html.Div(aviso if aviso else [html.Span(f"AA: {brl(valor_aa)} "),
                                      html.Span(txt_var, style={"color": cor_var})],
                 style={"color": TEXTO_SEC, "fontSize": "12px", "marginTop": "6px"}),
    ])


# ---------------------------------------------------------------------------
# Pódio: vídeo (assets/fotos/danilo.mp4) ou foto (assets/fotos/danilo.png).
# Se existirem os dois com o mesmo nome, o vídeo tem prioridade.
# ---------------------------------------------------------------------------
PASTA_FOTOS = Path(__file__).parent / "assets" / "fotos"
EXT_VIDEO = (".mp4", ".webm")
EXT_FOTO = (".jpg", ".jpeg", ".png", ".webp", ".gif")
MEDALHAS = {1: "#f5c542", 2: "#c9d1d9", 3: "#d08a4a"}


def slug(txt):
    txt = unicodedata.normalize("NFKD", str(txt)).encode("ascii", "ignore").decode()
    return "_".join(txt.lower().split())


def achar_midia(nome):
    """Procura vídeo ou foto pelo nome completo (maria_silva.mp4) ou primeiro nome (maria.mp4).
    Retorna (url, "video"|"foto") ou (None, None)."""
    if not PASTA_FOTOS.exists():
        return None, None
    arquivos = {}
    for f in PASTA_FOTOS.iterdir():
        ext = f.suffix.lower()
        if ext in EXT_VIDEO:
            arquivos[f.stem.lower()] = (f.name, "video")      # vídeo ganha da foto
        elif ext in EXT_FOTO:
            arquivos.setdefault(f.stem.lower(), (f.name, "foto"))
    completo = slug(nome)
    primeiro = completo.split("_")[0]
    for chave in (completo, primeiro):
        if chave in arquivos:
            arq, tipo = arquivos[chave]
            return app.get_asset_url(f"fotos/{arq}"), tipo
    return None, None


def iniciais(nome):
    partes = str(nome).split()
    return (partes[0][0] + (partes[-1][0] if len(partes) > 1 else "")).upper()


def bloco_podio(pos, nome, valor, contratos):
    cor = MEDALHAS[pos]
    tam = 132 if pos == 1 else 104
    altura_base = {1: 150, 2: 110, 3: 80}[pos]
    midia, tipo = achar_midia(nome)
    avatar_estilo = {
        "width": f"{tam}px", "height": f"{tam}px", "borderRadius": "50%",
        "border": f"3px solid {cor}",
        "boxShadow": f"0 0 24px {cor}55" if pos == 1 else f"0 0 12px {cor}33",
        "objectFit": "cover", "objectPosition": "50% 22%",
    }
    if tipo == "video":
        avatar = html.Video(src=midia, autoPlay=True, loop=True, muted=True,
                            controls=False, style={**avatar_estilo, "display": "block"},
                            **{"playsInline": True})
    elif tipo == "foto":
        avatar = html.Img(src=midia, style=avatar_estilo)
    else:
        avatar = html.Div(iniciais(nome), style={
            **avatar_estilo, "display": "flex", "alignItems": "center",
            "justifyContent": "center", "background": "#16241b",
            "color": cor, "fontSize": f"{tam // 3}px", "fontWeight": 700,
        })
    return html.Div([
        html.Div("👑" if pos == 1 else "", style={"fontSize": "26px", "height": "32px"}),
        html.Div([
            avatar,
            html.Div(f"{pos}º", style={
                "position": "absolute", "bottom": "-6px", "right": "-6px",
                "background": cor, "color": BG, "fontWeight": 800, "fontSize": "14px",
                "borderRadius": "999px", "padding": "3px 10px",
            }),
        ], style={"position": "relative"}),
        html.Div(nome, style={"color": "#fff", "fontWeight": 600, "marginTop": "14px",
                              "fontSize": "16px" if pos == 1 else "14px",
                              "textAlign": "center", "maxWidth": "190px"}),
        html.Div(brl(valor), style={"color": VERDE, "fontWeight": 700,
                                    "fontSize": "18px" if pos == 1 else "15px",
                                    "marginTop": "4px"}),
        html.Div(f"{contratos} contrato{'s' if contratos != 1 else ''}",
                 style={"color": TEXTO_SEC, "fontSize": "12px", "marginBottom": "12px"}),
        html.Div(str(pos), style={
            "width": "100%", "height": f"{altura_base}px",
            "background": f"linear-gradient(180deg, {cor}40 0%, {PANEL} 100%)",
            "borderTop": f"3px solid {cor}",
            "borderRadius": "10px 10px 0 0",
            "display": "flex", "alignItems": "center", "justifyContent": "center",
            "color": cor, "fontSize": "44px", "fontWeight": 800, "opacity": 0.9,
        }),
    ], style={"display": "flex", "flexDirection": "column", "alignItems": "center",
              "justifyContent": "flex-end", "flex": "1", "maxWidth": "240px"})


def montar_podio(df):
    titulo = html.Div("Pódio de vendedores — faturamento em contratos",
                      style={"color": TEXTO, "fontSize": "13px", "margin": "4px 0 8px 6px"})
    if df.empty:
        return [titulo, html.Div("Sem vendas no período", style={
            "color": TEXTO_SEC, "textAlign": "center", "padding": "40px"})]
    linhas = {i + 1: r for i, r in enumerate(df.itertuples(index=False))}
    ordem = [p for p in (2, 1, 3) if p in linhas]   # 2º à esquerda, 1º no meio, 3º à direita
    blocos = [bloco_podio(p, linhas[p].nome, float(linhas[p].valor), int(linhas[p].contratos))
              for p in ordem]
    return [titulo, html.Div(blocos, style={
        "display": "flex", "justifyContent": "center", "alignItems": "flex-end",
        "gap": "18px", "padding": "0 12px"})]


def painel(children, **extra):
    return html.Div(children, style={
        "background": PANEL, "border": f"1px solid {BORDA}",
        "borderRadius": "14px", "padding": "12px", **extra,
    })


# ---------------------------------------------------------------------------
# Gráficos
# ---------------------------------------------------------------------------
def fig_recebido_pago(df):
    titulo = "Valor recebido e valor pago"
    if df.empty:
        return fig_vazia(titulo)
    x = [rotulo_mes(m) for m in df["mes"]]
    fig = go.Figure()
    if "recebido" in df:
        fig.add_bar(x=x, y=df["recebido"], name="Valor recebido",
                    marker_color=VERDE, marker_line_width=0,
                    hovertemplate="%{x}<br>Recebido: R$ %{y:,.2f}<extra></extra>")
    if "pago" in df:
        fig.add_bar(x=x, y=df["pago"], name="Valor pago",
                    marker_color=VERDE_ESCURO, marker_line_width=0,
                    hovertemplate="%{x}<br>Pago: R$ %{y:,.2f}<extra></extra>")
    if "recebido" not in df:
        titulo += "  <span style='color:#8a9a90;font-size:11px'>(sem vw_recebiveis — só pago)</span>"
    fig.update_layout(barmode="group", bargap=0.35, bargroupgap=0.1)
    fig.update_yaxes(tickprefix="R$ ", tickformat=",.0f")
    return layout_grafico(fig, titulo)


def fig_ranking(df):
    titulo = "Faturamento por plano de contas (top 10)"
    if df.empty:
        return fig_vazia(titulo)
    df = df.sort_values("valor")
    fig = go.Figure(go.Bar(
        x=df["valor"], y=df["nome"], orientation="h",
        marker=dict(color=df["valor"], colorscale=[[0, VERDE_ESCURO], [1, VERDE]]),
        text=[brl(v) for v in df["valor"]],
        textposition="outside", textfont=dict(color=TEXTO, size=11),
        cliponaxis=False,
        hovertemplate="%{y}<br>%{text}<extra></extra>",
    ))
    fig.update_xaxes(visible=False, range=[0, df["valor"].max() * 1.45])
    fig.update_yaxes(gridcolor="rgba(0,0,0,0)", tickfont=dict(color=TEXTO))
    return layout_grafico(fig, titulo)


def fig_em_aberto(df):
    titulo = "Valor em aberto por mês de emissão"
    if df.empty:
        return fig_vazia(titulo)
    x = [rotulo_mes(m) for m in df["mes"]]
    fig = go.Figure(go.Scatter(
        x=x, y=df["valor"], mode="lines+markers",
        line=dict(color=VERDE, width=3, shape="spline"),
        marker=dict(size=6, color=VERDE_CLARO),
        fill="tozeroy", fillcolor="rgba(61,220,132,0.12)",
        name="Em aberto",
        hovertemplate="%{x}<br>R$ %{y:,.2f}<extra></extra>",
    ))
    fig.update_yaxes(tickprefix="R$ ", tickformat=",.0f")
    return layout_grafico(fig, titulo)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = Dash(__name__, title="Dashboard Overview",
           external_stylesheets=["https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap"])

cfg = {"displayModeBar": False}
hoje = date.today()

CSS_FILTROS = {"color": TEXTO_SEC, "fontSize": "12px", "marginBottom": "4px"}

sidebar = html.Div(
    [html.Div(icone, style={"color": VERDE if i == 0 else TEXTO_SEC, "fontSize": "18px",
                            "margin": "18px 0", "textAlign": "center", "cursor": "pointer"})
     for i, icone in enumerate(["▦", "◔", "▤", "▥"])],
    style={"width": "56px", "paddingTop": "90px", "borderRight": f"1px solid {BORDA}"},
)

header = html.Div([
    html.Div([
        html.Span("IPR", style={"color": "#fff", "fontWeight": 700, "fontSize": "20px"}),
        html.Span("|", style={"color": TEXTO_SEC, "margin": "0 14px"}),
        html.Span("DASHBOARD ", style={"color": TEXTO, "letterSpacing": "3px"}),
        html.Span("OVERVIEW", style={"color": VERDE, "letterSpacing": "3px", "fontWeight": 600}),
    ], style={"fontSize": "18px"}),
    html.Div([
        html.Div([
            html.Div("Período", style=CSS_FILTROS),
            dcc.DatePickerRange(
                id="periodo",
                start_date=date(hoje.year, 1, 1),
                end_date=hoje,
                display_format="DD/MM/YYYY",
                first_day_of_week=0,
            ),
        ]),
        html.Div([
            html.Div("Unidade", style=CSS_FILTROS),
            dcc.Dropdown(
                id="unidade",
                options=[{"label": k, "value": k} for k in UNIDADES],
                value="Todas", clearable=False,
                style={"width": "170px"},
            ),
        ]),
    ], style={"display": "flex", "gap": "16px", "alignItems": "flex-end"}),
], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center",
          "flexWrap": "wrap", "gap": "16px", "padding": "22px 0 18px 0"})

conteudo = html.Div([
    header,
    html.Div(id="erro", style={"color": VERMELHO, "marginBottom": "12px", "whiteSpace": "pre-wrap"}),
    dcc.Loading(color=VERDE, children=[
        html.Div(id="cards", style={"display": "flex", "gap": "16px",
                                    "marginBottom": "16px", "flexWrap": "wrap"}),
        painel(html.Div(id="podio"), marginBottom="16px"),
        painel(dcc.Graph(id="g_recebido_pago", config=cfg, style={"height": "280px"}),
               marginBottom="16px"),
        html.Div([
            painel(dcc.Graph(id="g_ranking", config=cfg, style={"height": "340px"}),
                   flex="1.3", minWidth="320px"),
            painel(dcc.Graph(id="g_em_aberto", config=cfg, style={"height": "340px"}),
                   flex="1", minWidth="280px"),
        ], style={"display": "flex", "gap": "16px", "flexWrap": "wrap"}),
    ]),
], style={"flex": "1", "padding": "0 28px 28px 28px"})

app.layout = html.Div([sidebar, conteudo], style={
    "display": "flex", "minHeight": "100vh", "background": BG,
    "fontFamily": FONTE, "color": TEXTO,
})

# Deixa os filtros (Dash 4: dcc.Dropdown / dcc.DatePickerRange) no tema escuro
app.index_string = app.index_string.replace("</head>", """
<style>
  body { margin:0; background:#0a0d0b; }
  .dash-dropdown, [class*="dash-datepicker"] {
      background:#111613 !important; color:#e8f0eb !important;
      border-color:#1f7a4a !important;
  }
  .dash-dropdown *, [class*="dash-datepicker"] input { color:#e8f0eb !important; background:transparent !important; }
  [class*="dash-dropdown-content"], [class*="dash-dropdown-options"], [role="listbox"],
  [class*="dash-datepicker-content"], [class*="dash-datepicker-calendar"] {
      background:#111613 !important; color:#e8f0eb !important; border-color:#1f2a23 !important;
  }
  [role="option"] { color:#e8f0eb !important; }
  [role="option"]:hover, [role="option"][data-highlighted], [role="option"][aria-selected="true"] {
      background:#1f7a4a !important;
  }
  [class*="dash-datepicker"] button, [class*="dash-datepicker"] td { color:#e8f0eb !important; }
  [class*="dash-datepicker"] th { color:#8a9a90 !important; }
  [class*="dash-datepicker-content"] input, [class*="dash-datepicker-content"] [class*="input"] {
      background:#111613 !important; color:#e8f0eb !important; border-color:#1f7a4a !important;
  }
  [class*="dash-datepicker"] [aria-selected="true"],
  [class*="dash-datepicker"] [class*="selected"] { background:#3ddc84 !important; color:#0a0d0b !important; }
  [class*="dash-datepicker"] [class*="in-range"], [class*="dash-datepicker"] [class*="highlighted"] {
      background:#1f7a4a !important; color:#fff !important;
  }
</style>
</head>""")


@app.callback(
    Output("cards", "children"),
    Output("g_recebido_pago", "figure"),
    Output("g_ranking", "figure"),
    Output("g_em_aberto", "figure"),
    Output("podio", "children"),
    Output("erro", "children"),
    Input("periodo", "start_date"),
    Input("periodo", "end_date"),
    Input("unidade", "value"),
)
def atualizar(data_inicial, data_final, unidade):
    est = UNIDADES.get(unidade)
    args = (data_inicial, data_final, est)
    args_aa = (mesmo_periodo_ano_anterior(data_inicial),
               mesmo_periodo_ano_anterior(data_final), est)
    try:
        tem_rec = tabela_existe("vw_recebiveis")
        tem_exi = tabela_existe("vw_exigiveis")
        sem_rec = None if tem_rec else f"Tabela {SCHEMA}.vw_recebiveis não encontrada"

        cards = [
            card_kpi("Faturamento (contratos)",
                     valor_unico(SQL_FATURAMENTO, *args),
                     valor_unico(SQL_FATURAMENTO, *args_aa), destaque=True),
            card_kpi("Valor a receber",
                     valor_unico(SQL_A_RECEBER, *args) if tem_rec else 0,
                     valor_unico(SQL_A_RECEBER, *args_aa) if tem_rec else 0,
                     aviso=sem_rec),
        ]

        partes = []
        if tem_rec:
            partes.append(consultar(SQL_RECEBIDO_MES, *args))
        if tem_exi:
            partes.append(consultar(SQL_PAGO_MES, *args))
        if partes:
            df_rp = partes[0]
            for p in partes[1:]:
                df_rp = df_rp.merge(p, on="mes", how="outer")
            df_rp = df_rp.sort_values("mes").fillna(0)
            g_rp = fig_recebido_pago(df_rp)
        else:
            g_rp = fig_vazia("Valor recebido e valor pago",
                             "vw_recebiveis e vw_exigiveis não encontradas")

        g_aberto = (fig_em_aberto(consultar(SQL_EM_ABERTO, *args)) if tem_rec
                    else fig_vazia("Valor em aberto por mês de emissão", sem_rec))

        return (cards, g_rp,
                fig_ranking(consultar(SQL_RANKING, *args)),
                g_aberto, montar_podio(consultar(SQL_PODIO, *args)), "")
    except Exception as e:  # mostra o erro na tela em vez de quebrar
        e = traduzir_erro(e)
        vazio = fig_vazia("", "Erro ao consultar o banco")
        return [], vazio, vazio, vazio, [], f"Erro ao consultar o banco:\n{e}"


if __name__ == "__main__":
    app.run(debug=True)
