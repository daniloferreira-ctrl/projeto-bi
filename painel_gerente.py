"""
PAINEL GERENCIAL — IPR Blefaroplastia
Recriação do dashboard "Gerente de Rede" do Metabase, com visual novo:
vídeo do gerente no topo, números animados, gauges animados, funil, pódio e Modo TV.

Instalar:  pip install dash plotly pandas
Rodar:     python painel_gerente.py   ->  abrir http://127.0.0.1:8051

Vídeo/foto: assets/fotos/<arquivo>  (ex.: assets/fotos/danilo.mp4 ou danilo.png)
Dados: por enquanto FICTÍCIOS na função carregar_dados(). Santos = números do print do Metabase.
Para ligar no banco, troque só o conteúdo de carregar_dados() — o visual não muda.
"""

import math
import random
import re
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

import plotly.graph_objects as go
from dash import no_update as dash_no_update
from dash import ALL, Dash, Input, Output, State, clientside_callback, ctx, dcc, html

# ===========================================================================
# CONFIGURAÇÃO
# ===========================================================================
TITULO = "Painel Gerencial"      # título que aparece no topo
LOGO = "logo_ipr.png"            # arquivo do logo dentro da pasta assets/

GERENTE = {
    "nome": "Danilo",
    "cargo": "Gerente de Rede",
    # nome do arquivo em assets/fotos/ — pode ser com extensão ("danilo.mp4") ou sem ("danilo")
    "arquivo": "danilo",
}
UNIDADES = ["Santos", "São Paulo", "Campinas"]
META_FATURAMENTO = {"Santos": 1_500_000, "São Paulo": 2_400_000, "Campinas": 1_200_000}
DIAS_UTEIS = {0, 1, 2, 3, 4}   # seg–sex contam como dia útil (inclua 5 para sábado)
SEGUNDOS_TV = 20          # Modo TV "painel inteiro": troca de unidade a cada N segundos
SEGUNDOS_CARD = 10
SEGUNDOS_EVENTO = 25      # Modo TV: a cada N segundos verifica contratos novos (celebração)        # Modo TV "card por card": troca de card a cada N segundos
#          # Modo TV: troca de unidade a cada N segundos

# Faixas dos gauges: (fim da escala, limite crítico, limite atenção). Acima de "atenção" = bom.
FAIXAS_CONVERSAO = {
    "leads_agend":   (0.20, 0.06, 0.10),
    "consult_atend": (1.00, 0.50, 0.75),
    "orc_contrato":  (1.00, 0.40, 0.60),
}
# Centro cirúrgico: 0–25 crítico, 25–50 atenção, 50–75 parcial, 75–100 ideal
FAIXAS_CC = [(0.25, "Crítico"), (0.50, "Atenção"), (0.75, "Parcial"), (1.00, "Ideal")]

# Paleta
BG, PANEL, PANEL2 = "#070a09", "#0e1311", "#121a16"
BORDA = "#1c2621"
VERDE, VERDE_ESC, VERDE_CLARO = "#3ddc84", "#1f7a4a", "#9af5c0"   # cor de destaque do tema
SUCESSO = "#3ddc85"      # "bom" nos gauges/indicadores (no tema padrão é igual ao verde)
AMBAR, LARANJA, VERMELHO = "#f5b942", "#f08a3c", "#ff6b6b"
TEXTO, TEXTO_SEC, TEXTO_TER = "#eef4f0", "#93a39a", "#5d6b63"
MEDALHAS = {1: "#f5c542", 2: "#c9d1d9", 3: "#d08a4a"}

# ---------------------------------------------------------------------------
# TEMAS DE CORES — "padrao" (rosé, baseado no site da IPR) e "noite" (verde escuro)
# O CSS é escrito nas cores do "noite"; cada tema troca essas cores pelas dele.
# Para criar outro tema, copie o bloco "padrao" com outro nome e troque as cores.
# ---------------------------------------------------------------------------
TEMA_PADRAO = "padrao"
TEMAS = {
    "padrao": {
        "nome": "Padrão", "amostra": "#e0197d", "claro": True,
        "cores": {
            BG: "#fbf5f8", PANEL: "#ffffff", PANEL2: "#fffafd", BORDA: "#f1dce6",
            VERDE: "#e0197d", VERDE_ESC: "#a3105c", VERDE_CLARO: "#ff8fbf",
            SUCESSO: "#1fae62", AMBAR: "#e8962c", LARANJA: "#f0703c", VERMELHO: "#e5484d",
            TEXTO: "#2a1320", TEXTO_SEC: "#7d6170", TEXTO_TER: "#bba4b0",
            "#c9d1d9": "#9aa4b0",                       # prata do pódio
            "#12301f": "#ffe1ef", "#0f2219": "#fdeef5",  # brilhos do fundo
            "#10301f": "#ffe4f1", "#0b1410": "#fff8fb",  # degradê do topo
            "#0008": "#a3105c1f",                        # sombra do cartão
            "61,220,132": "224,25,125",                  # verde em rgba() dos gráficos
            "255,107,107": "229,72,77",                  # vermelho em rgba() dos gráficos
            "147,163,154": "125,97,112",                 # cinza em rgba() dos gráficos
            "color-scheme: dark": "color-scheme: light",
        },
    },
    "noite": {"nome": "Noite", "amostra": VERDE, "cores": {}},
}


def _trocador(tema):
    cores = TEMAS.get(tema, TEMAS[TEMA_PADRAO])["cores"]
    if not cores:
        return None
    padrao = re.compile("|".join(re.escape(k) for k in sorted(cores, key=len, reverse=True)))
    return lambda txt: padrao.sub(lambda m: cores[m.group(0)], txt)


def recolorir(obj, tema):
    """Troca as cores de um pedaço do painel (componentes, estilos e gráficos) para o tema."""
    troca = _trocador(tema)
    if troca is None:
        return obj

    def r(x):
        if isinstance(x, str):
            return troca(x)
        if isinstance(x, list):
            return [r(i) for i in x]
        if isinstance(x, tuple):
            return tuple(r(i) for i in x)
        if isinstance(x, dict):
            return {k: r(v) for k, v in x.items()}
        if isinstance(x, go.Figure):
            return r(x.to_dict())
        if hasattr(x, "_prop_names"):
            for nome in x._prop_names:
                v = getattr(x, nome, None)
                if v is not None and nome not in ("id",):
                    setattr(x, nome, r(v))
            return x
        return x
    return r(obj)


PASTA_FOTOS = Path(__file__).parent / "assets" / "fotos"
EXT_VIDEO = (".mp4", ".webm")
EXT_FOTO = (".jpg", ".jpeg", ".png", ".webp", ".gif")
MESES_CURTO = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
MESES_LONGO = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
               "agosto", "setembro", "outubro", "novembro", "dezembro"]


# ===========================================================================
# DADOS (FICTÍCIOS) — trocar por queries depois
# ===========================================================================
def carregar_dados(unidade, data_inicial, data_final):
    """Tudo que o painel precisa. Santos reproduz os números do print do Metabase.
    data_inicial/data_final já chegam aqui para quando ligar nas queries."""
    if unidade == "Santos":
        d = {
            "faturamento": 411_700.0, "ticket": 11_408.33,
            "funil": [("Consultas agendadas", 329), ("Consultas atendidas", 82),
                      ("Orçamentos", 80), ("Contratos", 38), ("Cirurgias realizadas", 40)],
            "sem_data": 8, "outros_colab": 4, "mesmo_dia": 24,
            "sem_data_vendedor": [("Mariana Costa", 5), ("Rafael Nunes", 3)],
            "leads": 2195, "leads_agendados": 239, "ddd": 0.6528,
            "ocupacao_cc": 0.3348, "cirurgias_cc": 42, "cancelamento": 0.1203, "no_show": 0.0,
            "jornada": [10.9, 0.0, 0.0, 0.38, None, None],
        }
    else:
        rnd = random.Random(unidade)
        k = {"São Paulo": 1.55, "Campinas": 0.78}[unidade]
        ag = round(329 * k * rnd.uniform(.9, 1.1))
        at = round(ag * rnd.uniform(.22, .30))
        orc = round(at * rnd.uniform(.9, .99))
        ct = round(orc * rnd.uniform(.4, .55))
        sd = max(3, round(8 * k * rnd.uniform(.8, 1.2)))
        a = round(sd * .6)
        d = {
            "faturamento": ct * 11_400 * rnd.uniform(.9, 1.1), "ticket": 11_400 * rnd.uniform(.9, 1.1),
            "funil": [("Consultas agendadas", ag), ("Consultas atendidas", at),
                      ("Orçamentos", orc), ("Contratos", ct),
                      ("Cirurgias realizadas", round(ct * rnd.uniform(.9, 1.1)))],
            "sem_data": sd, "outros_colab": round(4 * k), "mesmo_dia": round(24 * k * rnd.uniform(.8, 1.2)),
            "sem_data_vendedor": [("Beatriz Alves", a), ("Lucas Prado", sd - a)],
            "leads": round(2195 * k * rnd.uniform(.9, 1.1)), "leads_agendados": 0,
            "ddd": rnd.uniform(.55, .75),
            "ocupacao_cc": rnd.uniform(.3, .8), "cirurgias_cc": round(42 * k * rnd.uniform(.9, 1.1)),
            "cancelamento": rnd.uniform(.04, .14), "no_show": rnd.uniform(0, .04),
            "jornada": [round(rnd.uniform(6, 14), 1), round(rnd.uniform(0, 2), 1), 0.0,
                        round(rnd.uniform(0, 1.5), 2), round(rnd.uniform(10, 30), 1), None],
        }
        d["leads_agendados"] = round(d["leads"] * rnd.uniform(.08, .13))

    # pódio (fictício): vendedores por faturamento
    rnd = random.Random(unidade + "podio")
    nomes = ["Mariana Costa", "Rafael Nunes", "Beatriz Alves", "Lucas Prado", "Camila Rocha"]
    rnd.shuffle(nomes)
    d["vendedores"] = [{"nome": n, "valor": d["faturamento"] * p} for n, p in
                       zip(nomes, [.29, .23, .19, .16, .13])]
    # leads por dia (fictício) para o mini gráfico de captação
    hoje = date.today()
    dias = [hoje.replace(day=1) + timedelta(days=i) for i in range(hoje.day)]
    d["leads_dia"] = (dias, [max(10, round(d["leads"] / len(dias) * rnd.uniform(.55, 1.45)))
                             for _ in dias])
    d["meta"] = META_FATURAMENTO[unidade]
    rs = random.Random(unidade + "-semana")
    d["ocupacao_semana"] = [max(.05, min(1, d["ocupacao_cc"] * rs.uniform(.55, 1.45))) for _ in range(6)]

    # faturamento por dia do período até hoje (fictício) — usado na projeção da meta
    p_ini, p_fim = periodo_datas(data_inicial, data_final)
    ultimo = min(date.today(), p_fim)
    dias_corridos = [p_ini + timedelta(days=i) for i in range((ultimo - p_ini).days + 1)]
    pesos = [(rnd.uniform(.4, 1.6) if dia.weekday() in DIAS_UTEIS else rnd.uniform(0, .15))
             for dia in dias_corridos]
    total = sum(pesos) or 1
    d["fat_dia"] = [(dia, d["faturamento"] * w / total) for dia, w in zip(dias_corridos, pesos)]

    d["metricas"] = metricas(d)
    d["anterior"] = carregar_anterior(d, unidade, data_inicial, data_final)
    d["alertas"] = calcular_alertas(d)
    ant_ini, _ = periodo_anterior(data_inicial, data_final)
    d["rotulo_anterior"] = MESES_CURTO[ant_ini.month - 1]
    return d


def metricas(d):
    """Indicadores comparáveis entre períodos (mesmas chaves no atual e no anterior)."""
    f = dict(d["funil"])
    m = {
        "faturamento": d["faturamento"], "ticket": d["ticket"],
        "sem_data": d["sem_data"], "outros_colab": d["outros_colab"], "mesmo_dia": d["mesmo_dia"],
        "leads": d["leads"], "leads_agendados": d["leads_agendados"], "ddd": d["ddd"],
        "conv_leads": d["leads_agendados"] / max(d["leads"], 1),
        "conv_consult": f["Consultas atendidas"] / max(f["Consultas agendadas"], 1),
        "conv_orc": f["Contratos"] / max(f["Orçamentos"], 1),
        "ocupacao": d["ocupacao_cc"], "cirurgias_cc": d["cirurgias_cc"],
        "cancelamento": d["cancelamento"], "no_show": d["no_show"],
    }
    m.update({f"funil:{nome}": v for nome, v in d["funil"]})
    return m


def periodo_anterior(ini, fim):
    """Mesmo intervalo, um mês antes (ex.: 01–30/11 → 01–31/10)."""
    i, f = periodo_datas(ini, fim)
    ai = (i.replace(day=1) - timedelta(days=1)).replace(day=min(i.day, 28))
    af = (i.replace(day=1) - timedelta(days=1)) if f.month != i.month or f.day >= 28 else ai + (f - i)
    return ai, af


def carregar_anterior(d, unidade, data_inicial, data_final):
    """Indicadores do período anterior. FICTÍCIO: no real é carregar_dados() com as datas de
    periodo_anterior() — o mesmo código, só que um mês antes."""
    rnd = random.Random(unidade + "-anterior")
    atual = d["metricas"]
    ant = {}
    for k, v in atual.items():
        if k in ("ddd", "conv_leads", "conv_consult", "conv_orc", "ocupacao", "cancelamento", "no_show"):
            ant[k] = max(v + rnd.uniform(-.035, .035), 0)       # taxas: variação em pontos
        else:
            ant[k] = v / rnd.uniform(.88, 1.14)                   # valores: variação em %
    # para a demonstração mostrar alertas: leads caíram e cancelamento subiu
    ant["leads"] = atual["leads"] / .72
    ant["cancelamento"] = max(atual["cancelamento"] - .045, 0)
    return ant


# Regras dos alertas: (métrica, tipo, limite, piora_quando, nome)
#   tipo "pct" = variação percentual; "pp" = diferença em pontos percentuais
REGRAS_ALERTA = [
    ("faturamento", "pct", .20, "cai", "Faturamento"),
    ("leads", "pct", .20, "cai", "Leads"),
    ("conv_consult", "pp", .05, "cai", "Consultas → atendimentos"),
    ("conv_orc", "pp", .05, "cai", "Orçamentos → contratos"),
    ("cancelamento", "pp", .03, "sobe", "Cancelamento"),
    ("no_show", "pp", .03, "sobe", "No-show"),
    ("sem_data", "pct", .40, "sobe", "Contratos sem data"),
]


def calcular_alertas(d):
    alertas = {}
    for chave, tipo, limite, piora, nome in REGRAS_ALERTA:
        a, b = d["metricas"].get(chave), d["anterior"].get(chave)
        if a is None or not b:
            continue
        var = (a / b - 1) if tipo == "pct" else (a - b)
        if (piora == "cai" and var <= -limite) or (piora == "sobe" and var >= limite):
            qtd = f"{num_br(abs(var) * 100, 0)}%" if tipo == "pct" else f"{num_br(abs(var) * 100, 1)}%"
            direcao = "abaixo" if var < 0 else "acima"
            alertas[chave] = f"{qtd} {direcao} do mês anterior"
    return alertas


def carregar_detalhe(chave, unidade, data_inicial, data_final):
    """Linhas da gaveta de detalhes. FICTÍCIO — trocar por queries (ver comentários)."""
    d = carregar_dados(unidade, data_inicial, data_final)
    rnd = random.Random(f"{unidade}-{chave}")
    hoje_ = date.today()
    procedimentos = ["Blefaroplastia superior", "Blefaroplastia inferior", "Blefaroplastia completa",
                     "Retoque", "Blefaro + bolsas"]
    if chave == "sem_data":
        # real: contratos sem agendamento de cirurgia (vw_contratos x vw_agendamentos)
        linhas = []
        for vend, qtd in d["sem_data_vendedor"]:
            for _ in range(qtd):
                dt = hoje_ - timedelta(days=rnd.randint(2, 55))
                linhas.append({"vendedor": vend, "prontuario": f"#{rnd.randint(10000, 99999)}",
                               "data": dt, "dias": (hoje_ - dt).days,
                               "procedimento": rnd.choice(procedimentos),
                               "valor": d["ticket"] * rnd.uniform(.75, 1.3)})
        return sorted(linhas, key=lambda x: -x["dias"])
    if chave == "faturamento":
        # real: SELECT emissao, vendedor, prontuario, plano_contas, valor_contrato FROM cm_sync.vw_contratos ...
        n = dict(d["funil"])["Contratos"]
        p_ini, _ = periodo_datas(data_inicial, data_final)
        dias_ = max((min(hoje_, _ if _ else hoje_) - p_ini).days, 0)
        vend = [v["nome"] for v in d["vendedores"]]
        brutos = [rnd.uniform(.7, 1.4) for _ in range(n)]
        k = d["faturamento"] / sum(brutos)
        linhas = [{"vendedor": rnd.choice(vend), "prontuario": f"#{rnd.randint(10000, 99999)}",
                   "data": p_ini + timedelta(days=rnd.randint(0, dias_)),
                   "procedimento": rnd.choice(procedimentos), "valor": b * k} for b in brutos]
        return sorted(linhas, key=lambda x: x["data"], reverse=True)
    if chave == "vendedores":
        tot = sum(v["valor"] for v in d["vendedores"])
        return [{"vendedor": v["nome"], "valor": v["valor"], "part": v["valor"] / tot,
                 "contratos": max(1, round(dict(d["funil"])["Contratos"] * v["valor"] / tot))}
                for v in sorted(d["vendedores"], key=lambda v: -v["valor"])]
    return []


def novo_contrato_simulado(unidade, n):
    """Simula um contrato novo para a celebração do Modo TV.
    Real: buscar contratos com emissao > último horário visto (vw_contratos) e retornar o mais recente."""
    rnd = random.Random(f"{unidade}-evento-{n}")
    d = carregar_dados(unidade, None, None)
    v = rnd.choice(d["vendedores"][:4])
    return {"vendedor": v["nome"], "valor": d["ticket"] * rnd.uniform(.8, 1.3),
            "procedimento": rnd.choice(["Blefaroplastia superior", "Blefaroplastia inferior",
                                        "Blefaroplastia completa"])}


# ===========================================================================
# HELPERS
# ===========================================================================
def num_br(v, casas=0):
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def brl(v, casas=2):
    return f"R$ {num_br(v, casas)}"


def pct(v, casas=2):
    return f"{num_br(v * 100, casas)}%"


def slug(txt):
    txt = unicodedata.normalize("NFKD", str(txt)).encode("ascii", "ignore").decode()
    return "_".join(txt.lower().split())


def achar_video(nome):
    """Vídeo com som que abre ao clicar na foto do pódio: assets/fotos/videos/<nome>.mp4"""
    pasta = PASTA_FOTOS / "videos"
    if not pasta.exists():
        return None
    arquivos = {f.stem.lower(): f.name for f in pasta.iterdir() if f.suffix.lower() in (".mp4", ".webm", ".mov")}
    completo = slug(nome)
    for chave in (completo, completo.split("_")[0]):
        if chave in arquivos:
            return app.get_asset_url(f"fotos/videos/{arquivos[chave]}")
    return None


def achar_recorte_video(nome):
    """Vídeo da pessoa SEM fundo (WebM transparente) em assets/fotos/recorte/.
    Gere com:  python recortar_video.py <vídeo> <nome>"""
    pasta = PASTA_FOTOS / "recorte"
    if not pasta.exists():
        return None
    arquivos = {f.stem.lower(): f.name for f in pasta.iterdir() if f.suffix.lower() == ".webm"}
    completo = slug(nome)
    for chave in (completo, completo.split("_")[0]):
        if chave in arquivos:
            return app.get_asset_url(f"fotos/recorte/{arquivos[chave]}")
    return None


def achar_recorte(nome):
    """Foto da pessoa SEM fundo (PNG transparente) em assets/fotos/recorte/.
    Gere com:  python recortar_fotos.py"""
    pasta = PASTA_FOTOS / "recorte"
    if not pasta.exists():
        return None
    arquivos = {f.stem.lower(): f.name for f in pasta.iterdir() if f.suffix.lower() in (".png", ".webp")}
    completo = slug(nome)
    for chave in (completo, completo.split("_")[0]):
        if chave in arquivos:
            return app.get_asset_url(f"fotos/recorte/{arquivos[chave]}")
    return None


def achar_midia(nome):
    """Aceita nome de arquivo exato ('danilo.mp4') ou nome de pessoa ('Maria Silva')."""
    if not PASTA_FOTOS.exists():
        return None, None
    exato = PASTA_FOTOS / str(nome)
    if exato.suffix and exato.exists():
        tipo = "video" if exato.suffix.lower() in EXT_VIDEO else "foto"
        return app.get_asset_url(f"fotos/{exato.name}"), tipo
    arquivos = {}
    for f in PASTA_FOTOS.iterdir():
        ext = f.suffix.lower()
        if ext in EXT_VIDEO:
            arquivos[f.stem.lower()] = (f.name, "video")
        elif ext in EXT_FOTO:
            arquivos.setdefault(f.stem.lower(), (f.name, "foto"))
    completo = slug(nome)
    for chave in (completo, completo.split("_")[0]):
        if chave in arquivos:
            arq, tipo = arquivos[chave]
            return app.get_asset_url(f"fotos/{arq}"), tipo
    return None, None


def iniciais(nome):
    p = str(nome).split()
    return (p[0][0] + (p[-1][0] if len(p) > 1 else "")).upper()


def _alfa(cor, pct_):
    if cor.startswith("#"):
        return f"{cor}{round(pct_ * 2.55):02x}"
    return f"color-mix(in srgb, {cor} {pct_}%, transparent)"


def avatar(nome, tam, cor=VERDE, brilho=False, arquivo=None):
    midia, tipo = achar_midia(arquivo or nome)
    estilo = {"width": f"{tam}px", "height": f"{tam}px", "borderRadius": "50%",
              "border": f"2px solid {cor}", "objectFit": "cover", "objectPosition": "50% 25%",
              "flexShrink": 0, "display": "block",
              "boxShadow": f"0 0 0 5px {_alfa(cor, 13)}, 0 0 34px {_alfa(cor, 40)}" if brilho else "none"}
    if tipo == "video":
        return html.Video(src=midia, autoPlay=True, loop=True, muted=True, controls=False,
                          playsInline=True, style=estilo)
    if tipo == "foto":
        return html.Img(src=midia, style=estilo)
    return html.Div(iniciais(nome), style={
        **estilo, "display": "flex", "alignItems": "center", "justifyContent": "center",
        "background": PANEL2, "color": cor, "fontWeight": 700, "fontSize": f"{tam // 3}px"})


def contador(valor, fmt, classe="num"):
    """Número que conta do zero até o valor (JS no fim do arquivo)."""
    if valor is None:
        return html.Span("—", className=classe + " vazio")
    texto = {"brl": brl(valor), "brlk": brl(valor / 1000) + "k", "int": num_br(valor),
             "pct": pct(valor), "dias": f"{num_br(valor, 2 if valor % 1 and valor < 1 else 1 if valor % 1 else 0)} dias"}[fmt]
    return html.Span(texto, className=f"{classe} countup",
                     **{"data-alvo": str(valor), "data-fmt": fmt})


ICONES = {
    "home": "<path d='M3 10.5 12 3l9 7.5V21H3z'/><path d='M9 21v-6h6v6'/>",
    "tv": "<rect x='2' y='7' width='20' height='14' rx='2'/><path d='m17 2-5 5-5-5'/>",
    "calendario": "<rect x='3' y='4' width='18' height='18' rx='2'/><path d='M16 2v4M8 2v4M3 10h18'/>",
    "unidade": "<path d='M3 21h18M5 21V7l7-4 7 4v14'/><path d='M12 9v6M9 12h6'/>",
    "alerta": "<path d='M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z'/><path d='M12 9v4M12 17h.01'/>",
    "coroa": "<path d='M2 19h20'/><path d='m3 7 5 5 4-7 4 7 5-5-2 10H5z'/>",
    "certo": "<path d='M20 6 9 17l-5-5'/>",
    "alvo": "<circle cx='12' cy='12' r='9'/><circle cx='12' cy='12' r='5'/><circle cx='12' cy='12' r='1'/>",
    "alta": "<path d='m22 7-8.5 8.5-5-5L2 17'/><path d='M16 7h6v6'/>",
    "usuario": "<circle cx='12' cy='8' r='4'/><path d='M4 21a8 8 0 0 1 16 0'/>",
    "grade": "<rect x='3' y='3' width='7' height='7' rx='1.5'/><rect x='14' y='3' width='7' height='7' rx='1.5'/><rect x='3' y='14' width='7' height='7' rx='1.5'/><rect x='14' y='14' width='7' height='7' rx='1.5'/>",
    "card": "<rect x='3' y='4' width='18' height='16' rx='2.5'/><path d='M7 9h6M7 13h10'/>",
    "seta": "<path d='m9 18 6-6-6-6'/>",
    "play": "<path d='M7 4.5v15l12-7.5z' fill='black'/>",
    "sino": "<path d='M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9'/><path d='M10.3 21a1.94 1.94 0 0 0 3.4 0'/>",
    "lua": "<path d='M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9z'/>",
    "sol": "<circle cx='12' cy='12' r='4'/><path d='M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4'/>",
    "analise": "<path d='M3 3v18h18'/><path d='M7 15l4-4 3 3 5-6'/>",
    "info": "<circle cx='12' cy='12' r='9.5'/><path d='M12 16.5v-5M12 8h.01'/>",
    "fechar": "<path d='M18 6 6 18M6 6l12 12'/>",
    "festa": "<path d='M5.8 11.3 2 22l10.7-3.8'/><path d='M4 3h.01M22 8h.01M15 2h.01M22 20h.01'/><path d='m22 2-2.2.7a2.9 2.9 0 0 0-2 2.7v.4a2.3 2.3 0 0 1-1.3 2l-.7.3'/><path d='M14 2v.9c0 1-.5 2-1.4 2.5l-.6.3'/><path d='m9.9 10.1 4 4'/><path d='M6 8.5 15.5 18'/>",
    "tela_cheia": "<path d='M8 3H5a2 2 0 0 0-2 2v3M21 8V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3M16 21h3a2 2 0 0 0 2-2v-3'/>",
}


def icone(nome, cor=None, tam=None):
    estilo = {}
    if cor:
        estilo["color"] = cor
    if tam:
        estilo["fontSize"] = f"{tam}px"
    return html.Span(className=f"ic ic-{nome}", style=estilo)


def css_icones():
    from urllib.parse import quote
    linhas = [".ic { display:inline-block; width:1em; height:1em; flex-shrink:0; vertical-align:-0.14em;"
              " background:currentColor; -webkit-mask:var(--i) center/contain no-repeat;"
              " mask:var(--i) center/contain no-repeat; }"]
    for nome, corpo in ICONES.items():
        svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' "
               "stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>" + corpo + "</svg>")
        linhas.append(f'.ic-{nome} {{ --i: url("data:image/svg+xml,{quote(svg)}"); }}')
    return "\n".join(linhas)


TAXAS = {"ddd", "conv_leads", "conv_consult", "conv_orc", "ocupacao", "cancelamento", "no_show"}
PIORA_SUBINDO = {"sem_data", "cancelamento", "no_show", "outros_colab"}


def delta(d, chave, curto=False):
    """Chip ▲▼ comparando com o período anterior."""
    a, b = d["metricas"].get(chave), d["anterior"].get(chave)
    if a is None or b is None or (b == 0 and chave not in TAXAS):
        return None
    var = (a - b) if chave in TAXAS else (a / b - 1)
    if abs(var) < .0005:
        txt, classe = "= estável", "neutro"
    else:
        sobe = var > 0
        bom = (not sobe) if chave in PIORA_SUBINDO else sobe
        valor = f"{num_br(abs(var) * 100, 1)}%" if chave in TAXAS else f"{num_br(abs(var) * 100, 1)}%"
        txt, classe = f"{'▲' if sobe else '▼'} {valor}", ("bom" if bom else "ruim")
    alerta = d["alertas"].get(chave)
    explicacao = (f"Mês anterior ({d['rotulo_anterior']}): "
                  + (pct(b, 1) if chave in TAXAS else num_br(b, 2 if b < 100 else 0)))
    dica = {"data-titulo": "Comparação com o mês anterior",
            "data-info": f"{txt} em relação a {d['rotulo_anterior']}."
                         + (f" Fora do normal: {alerta}." if alerta else ""),
            "data-calculo": explicacao, "data-fonte": "mesmo cálculo do card, um mês antes"}
    return html.Span(html.Span(txt, className=f"delta {classe}" + (" pulsa" if alerta else "")),
                     className="delta-linha dica", **dica)


def card(children, classe="", detalhe=None, alerta=None, **estilo):
    """detalhe='chave' deixa o card clicável e abre a gaveta de detalhes daquela chave.
    alerta='texto' faz o card pulsar e mostra o motivo."""
    if not isinstance(children, (list, tuple)):
        children = [children]
    children = [c for c in children if c is not None]
    if alerta:
        classe += " alerta-pulsa"
    if detalhe:
        return html.Div(children + [html.Div(["ver detalhes ", icone("seta")], className="ver-detalhes")],
                        id={"tipo": "detalhe", "k": detalhe}, n_clicks=0,
                        className=f"card clicavel {classe}", style=estilo)
    return html.Div(children, className=f"card {classe}", style=estilo)


DEFINICOES = {
    "Meta de faturamento": ("Quanto do faturamento do mês já foi atingido.",
                            "faturamento do período ÷ meta da unidade (META_FATURAMENTO)", "vw_contratos"),
    "Faturamento": ("Soma dos contratos fechados no período.",
                    "SUM(valor_contrato) por data de emissão, sem excluídos (deleted_at IS NULL)", "vw_contratos"),
    "Ticket médio": ("Valor médio de cada contrato.", "faturamento ÷ quantidade de contratos", "vw_contratos"),
    "Funil · Jornada do paciente": ("Quantos pacientes chegaram em cada etapa no período, com as conversões "
                                    "consultas → atendimentos e orçamentos → contratos entre as etapas.",
                                    "consultas de avaliação agendadas → atendidas → orçamentos → contratos → cirurgias; "
                                    "conversão = etapa seguinte ÷ etapa anterior",
                                    "vw_agendamentos, vw_orcamentos, vw_contratos"),
    "Sem data de cirurgia": ("Contratos fechados que ainda não têm a cirurgia agendada.",
                             "contratos do período sem agendamento de cirurgia vinculado", "vw_contratos × vw_agendamentos"),
    "Outros colaboradores": ("Contratos sem data de cirurgia vendidos por quem não é do time de vendas.",
                             "mesma regra de 'sem data', filtrando colaboradores fora da lista de vendedores", "vw_contratos"),
    "Sem data por vendedor": ("Quem tem mais contratos aguardando data de cirurgia.",
                              "contratos sem data agrupados por vendedor; % = parte do total", "vw_contratos"),
    "Vendedor · mesmo dia": ("Contratos fechados no mesmo dia da consulta de avaliação.",
                             "contratos com emissão = data da consulta do paciente", "vw_contratos × vw_agendamentos"),
    "Leads → agendamentos": ("Dos leads que chegaram, quantos agendaram consulta.",
                             "leads agendados ÷ total de leads", "crm.Referrals × vw_agendamentos"),
    "Consultas → atendimentos": ("Das consultas agendadas, quantas foram atendidas.",
                                 "consultas com situação 'Atendido' ÷ consultas agendadas", "vw_agendamentos"),
    "Orçamentos → contratos": ("Dos orçamentos feitos, quantos viraram contrato.",
                               "contratos ÷ orçamentos do período", "vw_orcamentos, vw_contratos"),
    "Ocupação do centro cirúrgico": ("Quanto do tempo disponível das salas foi usado com cirurgias.",
                                     "horas de cirurgia (coluna horario 'HH:MM a HH:MM') ÷ horas disponíveis",
                                     "vw_agendamentos"),
    "Cirurgias": ("Cirurgias realizadas no centro cirúrgico no período.",
                  "agendamentos de cirurgia com situação 'Atendido'", "vw_agendamentos"),
    "Cancelamento": ("Cirurgias agendadas que foram canceladas.",
                     "cirurgias desmarcadas/desistência ÷ cirurgias agendadas", "vw_agendamentos"),
    "No-show": ("Pacientes que faltaram à cirurgia sem avisar.",
                "faltas não justificadas ÷ cirurgias agendadas", "vw_agendamentos"),
    "Leads": ("Total de cliques em anúncios que viraram conversa — não são pessoas únicas.",
              "COUNT(*) com source_type = 'ad'", "crm.Referrals"),
    "% DDD local": ("Parte dos leads com DDD da região da unidade.",
                    "leads com DDD da unidade ÷ total de leads", "crm.Referrals"),
    "Leads agendados": ("Leads que chegaram a agendar uma consulta.",
                        "leads com agendamento posterior ao contato", "crm.Referrals × vw_agendamentos"),
    "Leads por dia": ("Evolução diária da entrada de leads.", "leads agrupados por data de criação", "crm.Referrals"),
    "Pódio de vendedores": ("Os três vendedores que mais faturaram no período.",
                            "SUM(valor_contrato) por vendedor", "vw_contratos"),
    "Cadastro → cirurgia": ("Tempo médio entre o cadastro do paciente e a cirurgia.",
                            "média de dias entre a emissão do prontuário e a cirurgia realizada",
                            "vw_prontuarios × vw_agendamentos"),
    "Projeção de fechamento do mês": ("Onde o faturamento deve terminar o mês no ritmo atual.",
                                      "realizado + (média por dia útil × dias úteis restantes)", "vw_contratos"),
}


def titulo_card(txt, extra=None):
    info = None
    if isinstance(txt, str) and txt in DEFINICOES:
        o_que, calculo, fonte = DEFINICOES[txt]
        info = html.Span(icone("info"), className="info",
                         **{"data-titulo": txt, "data-info": o_que, "data-calculo": calculo,
                            "data-fonte": fonte})
    return html.Div([html.Span([html.Span(txt, className="titulo-card"), info],
                               style={"display": "inline-flex", "alignItems": "center", "gap": "6px"}),
                     extra], className="topo-card")


def passo(n, nome, sub=None, seta=True):
    return html.Span([html.Span(str(n), className="passo-n"), nome,
                      html.Span(f" · {sub}", className="passo-sub") if sub else None,
                      html.Span("›", className="passo-seta") if seta else None], className="passo")


def secao(titulo, filhos, classe=""):
    return html.Div([html.Div(titulo, className="titulo-secao"), *filhos],
                    className=f"secao {classe}")


def cor_faixa(v, critico, atencao):
    return VERMELHO if v < critico else (AMBAR if v < atencao else SUCESSO)


def gauge(valor, escala, faixas, tam=190, rotulos=None):
    """Semicírculo com faixas coloridas, arco animado e ponteiro que gira até o valor.
    faixas = [(limite, cor), ...] em fração da escala."""
    frac = max(0.0, min(valor / escala, 1.0))
    paradas, ini = [], 0.0
    for lim, cor in faixas:
        paradas.append(f"{cor}40 {ini * 50:.2f}% {lim * 50:.2f}%")
        ini = lim
    cor_atual = next(c for lim, c in faixas if frac <= lim + 1e-9)
    trilho = f"conic-gradient(from 270deg, {', '.join(paradas)}, transparent 50% 100%)"
    filhos = [
        html.Div(className="g-trilho", style={"background": trilho}),
        html.Div(className="g-arco", style={"--p": f"{frac * 50:.2f}", "--cor": cor_atual}),
        html.Div(className="g-ponteiro", style={"--ang": f"{frac * 180 - 90:.1f}deg"}),
        html.Div(className="g-eixo"),
    ]
    if rotulos:
        for pos, txt, cor in rotulos:
            ang = math.pi * (1 - pos)
            x, y = 50 + 64 * math.cos(ang), 93 - 122 * math.sin(ang)
            filhos.append(html.Div(txt, className="g-rotulo", style={
                "left": f"{x}%", "top": f"{y}%", "color": cor}))
    return html.Div(filhos, className="gauge", style={"--tam": f"{tam}px", "--cor": cor_atual})


# ===========================================================================
# SEÇÕES (mesmos cards do Metabase)
# ===========================================================================
def secao_faturamento(d):
    frac = d["faturamento"] / d["meta"]
    pj = calcular_projecao(d, None, None)
    cor_pj = SUCESSO if pj["frac_proj"] >= 1 else (AMBAR if pj["frac_proj"] >= .85 else VERMELHO)
    projecao = card([
        titulo_card("Projeção do mês", html.Span(
            "no ritmo" if pj["frac_proj"] >= 1 else "abaixo do ritmo", className="chip", style={"color": cor_pj})),
        html.Div([html.Span(brl_curto(pj["projecao"]), className="num grande", style={"color": cor_pj}),
                  html.Span(f" {pct(pj['frac_proj'], 0)} da meta", className="legenda")],
                 style={"display": "flex", "alignItems": "baseline", "gap": "6px"}),
        html.Div([
            html.Div(className="pj-real", style={"width": f"{min(pj['frac_meta'], 1) * 100:.1f}%"}),
            html.Div(className="pj-proj", style={"left": f"{min(pj['frac_meta'], 1) * 100:.1f}%",
                                                  "width": f"{max(min(pj['frac_proj'], 1) - pj['frac_meta'], 0) * 100:.1f}%",
                                                  "--cor": cor_pj}),
        ], className="pj-trilho"),
        html.Div([html.Span(f"realizado {pct(pj['frac_meta'], 1)}"), html.Span(f"meta {brl_curto(d['meta'])}")],
                 className="meta-escala"),
    ])
    meta = card([
        titulo_card("Meta de faturamento"),
        html.Div([
            html.Div([html.Span(pct(frac), className="marcador-txt"),
                      html.Span(className="marcador-seta")],
                     className="marcador", style={"left": f"{min(frac, 1) * 100:.2f}%"}),
            html.Div(html.Div(className="meta-fill", style={"width": f"{min(frac, 1) * 100:.2f}%"}),
                     className="meta-trilho"),
            html.Div([html.Span("0"), html.Span(f"Meta {brl(d['meta'], 0)}")],
                     className="meta-escala"),
        ], className="meta-wrap"),
    ])
    fat = card([
        titulo_card("Faturamento"),
        contador(d["faturamento"], "brlk", "num gigante"),
        html.Div("realizado até hoje", className="legenda"),
        delta(d, "faturamento"),
    ], "destaque", detalhe="faturamento", alerta=d["alertas"].get("faturamento"))
    ticket = card([
        titulo_card("Ticket médio"),
        contador(d["ticket"], "brl", "num grande"),
        html.Div("faturamento ÷ contratos", className="legenda"),
        delta(d, "ticket"),
    ])
    return secao(passo(1, "Resultado"), [fat, projecao, ticket])


def secao_funil(d, parte=None):
    etapas = d["funil"]
    maior = max(v for _, v in etapas)
    f = dict(etapas)
    # conversões mostradas entre as etapas do funil: (etapa de origem, etapa de destino, chave das faixas)
    conversoes = {
        "Consultas agendadas": ("Consultas atendidas", "consult_atend", "consultas → atendimentos"),
        "Orçamentos": ("Contratos", "orc_contrato", "orçamentos → contratos"),
    }
    # conversão mostrada à direita da etapa de destino: destino -> (origem, chave das faixas, rótulo)
    conv_destino = {destino: (origem, chave, rotulo) for origem, (destino, chave, rotulo) in conversoes.items()}
    linhas = []
    for i, (nome, v) in enumerate(etapas):
        conv = None
        if nome in conv_destino:
            origem, chave, rotulo = conv_destino[nome]
            escala, crit, aten = FAIXAS_CONVERSAO[chave]
            taxa = v / max(f[origem], 1)
            cor = cor_faixa(taxa, crit, aten)
            status = "boa" if taxa >= aten else ("em atenção" if taxa >= crit else "crítica")
            alerta_conv = d["alertas"].get({"consult_atend": "conv_consult", "orc_contrato": "conv_orc"}[chave])
            conv = html.Span(
                [html.Span("↳", className="conv-seta-funil"), contador(taxa, "pct", "conv-taxa")],
                className="conv-funil dica", style={"--cor": cor},
                **{"data-titulo": f"Conversão {rotulo}",
                   "data-info": f"{num_br(v)} de {num_br(f[origem])} "
                                f"{'consultas foram atendidas' if chave == 'consult_atend' else 'orçamentos viraram contrato'}"
                                f" — conversão {status}." + (f" Fora do normal: {alerta_conv}." if alerta_conv else ""),
                   "data-calculo": f"{nome.lower()} ÷ {origem.lower()} · referência: "
                                   f"crítico abaixo de {pct(crit, 0)}, bom acima de {pct(aten, 0)}",
                   "data-fonte": "vw_agendamentos" if chave == "consult_atend" else "vw_orcamentos, vw_contratos"})
        linhas.append(html.Div([
            html.Div(nome, className="funil-nome"),
            html.Div(html.Div(className="funil-fill", style={
                "width": f"{max(v / maior, 0.03) * 100:.1f}%", "animationDelay": f"{i * .08}s",
                "opacity": 1 - i * 0.1}), className="funil-trilho"),
            contador(v, "int", "funil-num"),
            html.Div(conv, className="funil-conv-cel"),
        ], className="funil-linha" + (" com-conv" if conv else "")))
    alertas_funil = [d["alertas"][k] for k in ("conv_consult", "conv_orc") if k in d["alertas"]]
    funil = card([titulo_card("Funil · Jornada do paciente"), html.Div(linhas, className="funil-linhas")],
                 alerta=" · ".join(alertas_funil) or None)

    total = sum(q for _, q in d["sem_data_vendedor"]) or 1
    tabela = [html.Div([
        avatar(n, 34, AMBAR),
        html.Div([html.Div(n, style={"fontSize": "14px", "fontWeight": 600}),
                  html.Div(html.Div(className="trilho-fill", style={
                      "width": f"{q / total * 100:.0f}%", "background": AMBAR}),
                      className="trilho")], style={"flex": 1}),
        html.Div([html.Div(str(q), className="num medio", style={"color": AMBAR}),
                  html.Div(pct(q / total, 1), className="legenda")], style={"textAlign": "right"}),
    ], className="linha-pend") for n, q in d["sem_data_vendedor"]]

    agenda = html.Div([
        card([titulo_card("Sem data de cirurgia",
                          html.Span("ação", className="chip", style={"color": AMBAR})),
              html.Div([html.Span(icone("alerta"), className="alerta-icone"),
                        contador(d["sem_data"], "int", "num grande")],
                       style={"display": "flex", "alignItems": "center", "gap": "12px"}),
              delta(d, "sem_data")],
             "alerta", detalhe="sem_data", alerta=d["alertas"].get("sem_data")),
        card([titulo_card("Outros colaboradores"), contador(d["outros_colab"], "int", "num grande"),
              delta(d, "outros_colab")]),
        card([titulo_card("Sem data por vendedor"),
              html.Div(tabela, style={"display": "flex", "flexDirection": "column", "gap": "12px"})],
             "span-2", detalhe="sem_data#vendedor"),
        card([titulo_card("Vendedor · mesmo dia"), contador(d["mesmo_dia"], "int", "num grande"),
              html.Div("contratos fechados no dia da consulta", className="legenda"),
              delta(d, "mesmo_dia")], "span-2"),
    ], className="grid-agenda")
    if parte == "funil":
        return secao("Funil operacional", [funil])
    if parte == "agenda":
        return secao("Agendamento cirúrgico", [agenda])
    return secao(passo(3, "Conversão", "consulta → contrato"), [funil,
                                       html.Div("Agendamento cirúrgico", className="titulo-secao sub"),
                                       agenda], "funil-col")


def indicador_faixas(valor, escala, faixas, nomes, meta=None, anterior=None, fmt=pct):
    """Bullet chart (visão normal) + barra segmentada com marcador (aparece só no Modo TV).
    faixas = [(limite em fração da escala, cor), ...]; nomes = nome de cada faixa."""
    frac = max(0.0, min(valor / escala, 1.0))
    cor_atual = next(c for lim, c in faixas if frac <= lim + 1e-9)
    ini, fundo, segs, marcas = 0.0, [], [], ["0%"]
    for (lim, cor), nome in zip(faixas, nomes):
        larg = (lim - ini) * 100
        fundo.append(html.Span(style={"width": f"{larg:.2f}%", "background": cor, "opacity": .22}))
        segs.append(html.Div(nome, style={"width": f"{larg:.2f}%", "background": cor}))
        marcas.append(fmt(lim * escala, 0))
        ini = lim
    pos = lambda v: f"{max(0, min(v / escala, 1)) * 100:.2f}%"
    bullet = html.Div([
        html.Div(fundo, className="bul-fundo"),
        html.Div(className="bul-valor", style={"width": f"{frac * 100:.2f}%", "--cor": cor_atual}),
        html.Div(className="bul-anterior dica", style={"left": pos(anterior)},
                 **{"data-titulo": "Mês anterior", "data-info": fmt(anterior, 2),
                    "data-calculo": "mesmo cálculo, um mês antes", "data-fonte": "comparação"})
        if anterior is not None else None,
        html.Div(className="bul-meta dica", style={"left": pos(meta)},
                 **{"data-titulo": "Referência / meta", "data-info": fmt(meta, 0),
                    "data-calculo": "a partir daqui o indicador é considerado bom", "data-fonte": "configuração do painel"})
        if meta is not None else None,
    ], className="bul")
    escala_txt = html.Div([html.Span(m) for m in marcas], className="bul-escala")
    segmentada = html.Div([
        html.Div(html.Div(fmt(valor, 2), className="seg-seta", style={"left": f"{frac * 100:.2f}%", "--cor": cor_atual}),
                 className="seg-seta-wrap"),
        html.Div(segs, className="seg-barra"),
    ], className="seg-tv")
    legenda = html.Div([html.Span([html.I(className="leg-atual", style={"background": cor_atual}), "atual"]),
                        html.Span([html.I(className="leg-ant"), "mês anterior"]) if anterior is not None else None,
                        html.Span([html.I(className="leg-meta"), "referência"]) if meta is not None else None],
                       className="bul-legenda")
    return html.Div([html.Div([bullet, escala_txt, legenda], className="bul-normal"), segmentada],
                    className="ind-faixas", style={"--cor": cor_atual})


def secao_conversao(d):
    funil = dict(d["funil"])
    itens = [
        ("Leads → agendamentos", "leads_agend", d["leads_agendados"] / max(d["leads"], 1),
         f"{num_br(d['leads_agendados'])} de {num_br(d['leads'])} leads"),
    ]
    metrica = {"leads_agend": "conv_leads", "consult_atend": "conv_consult", "orc_contrato": "conv_orc"}
    cards = []
    for titulo, chave, v, leg in itens:
        escala, crit, aten = FAIXAS_CONVERSAO[chave]
        m = metrica[chave]
        faixas = [(crit / escala, VERMELHO), (aten / escala, AMBAR), (1.0, SUCESSO)]
        cor = cor_faixa(v, crit, aten)
        status = "Bom" if v >= aten else ("Atenção" if v >= crit else "Crítico")
        cards.append(card([
            titulo_card(titulo, html.Span(status, className="chip", style={"color": cor})),
            html.Div([contador(v, "pct", "num grande", ), delta(d, m)], className="ind-topo",
                     style={"color": cor}),
            html.Div(leg, className="legenda", style={"marginBottom": "8px"}),
            indicador_faixas(v, escala, faixas, ["Crítico", "Atenção", "Bom"], meta=aten,
                             anterior=d["anterior"].get(m)),
        ], alerta=d["alertas"].get(m)))
    return secao(html.Span("Leads que agendaram", className="passo-cont"), cards, "igual")


def secao_cc(d):
    oc = d["ocupacao_cc"]
    cores = [VERMELHO, AMBAR, LARANJA, SUCESSO]
    faixas = [(lim, c) for (lim, _), c in zip(FAIXAS_CC, cores)]
    status, cor = next((nome, c) for (lim, nome), c in zip(FAIXAS_CC, cores) if oc <= lim + 1e-9)
    rotulos = [(0.125, "Crítico", VERMELHO), (0.375, "Atenção", AMBAR),
               (0.625, "Parcial", LARANJA), (0.875, "Ideal", SUCESSO)]
    gcard = card([
        titulo_card("Ocupação do centro cirúrgico",
                    html.Span(status, className="chip", style={"color": cor})),
        html.Div([contador(oc, "pct", "num grande"), delta(d, "ocupacao")], className="ind-topo",
                 style={"color": cor}),
        html.Div("horas de cirurgia ÷ horas disponíveis das salas", className="legenda",
                 style={"marginBottom": "8px"}),
        indicador_faixas(oc, 1.0, faixas, [n for _, n in FAIXAS_CC], meta=FAIXAS_CC[2][0],
                         anterior=d["anterior"].get("ocupacao")),
    ])
    minis = html.Div([
        card([titulo_card("Cirurgias"), contador(d["cirurgias_cc"], "int", "num grande"),
              delta(d, "cirurgias_cc", curto=True)], "mini"),
        card([titulo_card("Cancelamento"),
              contador(d["cancelamento"], "pct", "num grande"),
              delta(d, "cancelamento", curto=True),
              html.Div(html.Div(className="trilho-fill", style={
                  "width": f"{min(d['cancelamento'] / .2, 1) * 100:.0f}%",
                  "background": AMBAR if d["cancelamento"] > .1 else SUCESSO}), className="trilho")],
             "mini", alerta=d["alertas"].get("cancelamento")),
        card([titulo_card("No-show"),
              contador(d["no_show"], "pct", "num grande"),
              delta(d, "no_show", curto=True),
              html.Div(html.Div(className="trilho-fill", style={
                  "width": f"{min(d['no_show'] / .2, 1) * 100:.0f}%",
                  "background": SUCESSO}), className="trilho")], "mini",
             alerta=d["alertas"].get("no_show")),
    ], className="grid-3")
    dias = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]
    melhor = max(range(6), key=lambda i: d["ocupacao_semana"][i])
    pior = min(range(6), key=lambda i: d["ocupacao_semana"][i])
    barras = html.Div([
        html.Div([
            html.Div(pct(v, 0), className="semana-valor"),
            html.Div(html.Div(className="semana-fill", style={
                "height": f"{max(v, .04) * 100:.0f}%", "animationDelay": f"{i * .06}s",
                "background": SUCESSO if v >= .75 else (AMBAR if v >= .40 else VERMELHO)}),
                className="semana-trilho"),
            html.Div(dia, className="semana-dia" + (" destaque" if i in (melhor, pior) else "")),
        ], className="semana-col") for i, (dia, v) in enumerate(zip(dias, d["ocupacao_semana"]))
    ], className="semana-barras")
    semana = card([
        titulo_card("Ocupação por dia da semana",
                    html.Span(["mais ociosa: ", html.B(dias[pior], style={"color": VERMELHO})],
                              className="legenda")),
        barras,
    ], "semana-card")
    return secao(passo(4, "Entrega", "centro cirúrgico", seta=False), [gcard, minis, semana], "cc")


def secao_captacao(d):
    dias, vals = d["leads_dia"]
    fig = go.Figure(go.Scatter(
        x=dias, y=vals, mode="lines", line=dict(color=VERDE, width=2, shape="spline"),
        fill="tozeroy", fillcolor="rgba(61,220,132,0.12)",
        hovertemplate="%{x|%d/%m}: <b>%{y} leads</b><extra></extra>"))
    fig.update_layout(autosize=True, margin=dict(l=0, r=0, t=4, b=0), showlegend=False,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      hoverlabel=dict(bgcolor=PANEL2, bordercolor=VERDE, font_color=TEXTO))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    minis = html.Div([
        card([titulo_card("Leads"), contador(d["leads"], "int", "num grande"),
              delta(d, "leads", curto=True)], "mini", alerta=d["alertas"].get("leads")),
        card([titulo_card("% DDD local"), contador(d["ddd"], "pct", "num grande"),
              delta(d, "ddd", curto=True)], "mini"),
        card([titulo_card("Leads agendados"), contador(d["leads_agendados"], "int", "num grande"),
              delta(d, "leads_agendados", curto=True)], "mini"),
    ], className="grid-3")
    grafico = card([titulo_card("Leads por dia"),
                    dcc.Graph(figure=fig, config={"displayModeBar": False, "responsive": True},
                              className="grafico-flex", style={"height": "100%"})], "cresce")
    return secao(passo(2, "Atração", "leads"), [minis, grafico], "captacao")


def secao_jornada(d):
    etapas = ["Cadastro", "Agendamento", "Atendimento", "Orçamento", "Contrato", "Cirurgia"]
    tempos = d["jornada"]           # 5 trechos + total (cadastro → cirurgia)
    nos = []
    for i, nome in enumerate(etapas):
        nos.append(html.Div([html.Div(className="no-ponto", style={"animationDelay": f"{i * .12}s"}),
                             html.Div(nome, className="no-nome")], className="no"))
        if i < 5:
            t = tempos[i]
            nos.append(html.Div([
                contador(t, "dias", "num trecho-num"),
                html.Div(className="trecho-linha" + (" vazio" if t is None else ""),
                         style={"animationDelay": f"{i * .12}s"}),
                html.Div("sem dados" if t is None else "tempo médio", className="legenda"),
            ], className="trecho"))
    total = html.Div([
        titulo_card("Cadastro → cirurgia"),
        contador(tempos[5], "dias", "num grande"),
        html.Div("tempo médio total" if tempos[5] is not None else "sem cirurgias com data", className="legenda"),
    ], className="total-jornada")
    return card([
        html.Div([html.Div([html.Span("5", className="passo-n"), "Velocidade"], className="jornada-titulo passo"),
                  html.Div("tempo médio entre etapas", className="legenda")], className="jornada-rotulo"),
        html.Div(nos, className="linha-tempo"),
        total,
    ], "faixa-jornada")


def ranking_podio(d, destaque):
    """Balão com o ranking dos 3 primeiros (aparece ao passar o mouse no pódio)."""
    todos = d["vendedores"]
    total = sum(v["valor"] for v in todos) or 1
    n_contratos = dict(d["funil"])["Contratos"]
    linhas = []
    for i, v in enumerate(todos[:3]):
        cor = MEDALHAS[i + 1]
        part = v["valor"] / total
        linhas.append(html.Div([
            html.Span(f"{i + 1}º", className="rk-pos", style={"color": cor}),
            avatar(v["nome"], 30, cor),
            html.Div([
                html.Div([html.B(v["nome"]), html.Span(brl_curto(v["valor"]), className="rk-valor")],
                         className="rk-linha1"),
                html.Div(html.Div(className="rk-fill", style={
                    "width": f"{v['valor'] / todos[0]['valor'] * 100:.0f}%", "background": cor}), className="rk-trilho"),
                html.Div(f"{max(1, round(n_contratos * part))} contratos · {pct(part, 1)} do time",
                         className="legenda", style={"fontSize": "11px"}),
            ], style={"flex": 1, "minWidth": 0}),
        ], className=f"rk-item r{i + 1}"))
    lider, seg = todos[0], todos[1]
    lista = html.Div([
        html.Div([icone("coroa", MEDALHAS[1]), " Ranking do período"], className="rk-titulo"),
        *linhas,
        html.Div(f"{lider['nome'].split()[0]} está {brl_curto(lider['valor'] - seg['valor'])} à frente do 2º lugar",
                 className="rk-rodape"),
    ], className="rk-lista")
    video = achar_recorte_video(lider["nome"])
    lado = html.Div([
        html.Div(className="rk-video-brilho"),
        html.Video(src=video, className="rk-video-el", muted=True, loop=True, playsInline=True,
                   preload="auto", controls=False),
        html.Div([icone("coroa"), f" {lider['nome']}"], className="rk-video-nome"),
    ], className="rk-video") if video else None
    return html.Div([lado, lista], className="rk-balao" + (" com-video" if video else ""))


def secao_podio(d):
    top = d["vendedores"][:3]
    blocos = []
    for pos in (2, 1, 3):
        v = top[pos - 1]
        cor = MEDALHAS[pos]
        recorte = achar_recorte(v["nome"]) if pos == 1 else None
        if recorte:   # 1º lugar com a foto recortada (sem fundo), em pé sobre o degrau
            figura = html.Div([
                html.Div(className="recorte-brilho"),
                html.Img(src=recorte, className="podio-recorte", alt=v["nome"]),
                html.Div([icone("coroa"), " 1º"], className="medalha recorte-medalha", style={"background": cor}),
            ], className="recorte-wrap")
        else:
            figura = html.Div([avatar(v["nome"], 54 if pos == 1 else 42, cor, brilho=pos == 1),
                               html.Div(f"{pos}º", className="medalha", style={"background": cor})],
                              style={"position": "relative"})
        blocos.append(html.Div([
            html.Div(icone("coroa", MEDALHAS[1]) if pos == 1 and not recorte else "", className="coroa"),
            html.Div(figura, className="podio-figura"),
            html.Div(v["nome"], className="podio-nome"),
            html.Div(brl(v["valor"], 0), className="podio-valor"),
            html.Div(str(pos), className="degrau", style={
                "height": {1: "38px", 2: "26px", 3: "18px"}[pos],
                "borderTopColor": cor, "color": cor,
                "background": f"linear-gradient(180deg, {cor}38 0%, transparent 100%)"}),
        ], className=f"podio-col p{pos}" + (" com-recorte" if recorte else "")))
    return secao(html.Span("Quem fez acontecer", className="passo-cont"), [card([
        titulo_card("Pódio de vendedores", html.Span("faturamento", className="legenda")),
        html.Div(blocos + [ranking_podio(d, None)], className="podio")], detalhe="vendedores")])


def periodo_datas(ini, fim):
    hoje_ = date.today()
    i = date.fromisoformat(str(ini)[:10]) if ini else hoje_.replace(day=1)
    f = date.fromisoformat(str(fim)[:10]) if fim else (i + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return i, f


def brl_curto(v):
    if abs(v) >= 1_000_000:
        return f"R$ {num_br(v / 1_000_000, 2)} mi"
    if abs(v) >= 1_000:
        return f"R$ {num_br(v / 1_000, 1)} mil"
    return brl(v, 0)


def calcular_projecao(d, ini, fim):
    p_ini, p_fim = periodo_datas(ini, fim)
    todos = [p_ini + timedelta(days=i) for i in range((p_fim - p_ini).days + 1)]
    uteis = [x for x in todos if x.weekday() in DIAS_UTEIS]
    hoje_ = min(date.today(), p_fim)
    uteis_passados = [x for x in uteis if x <= hoje_]
    uteis_restantes = [x for x in uteis if x > hoje_]
    realizado = sum(v for _, v in d["fat_dia"])
    ritmo = realizado / max(len(uteis_passados), 1)                 # R$ por dia útil
    projecao = realizado + ritmo * len(uteis_restantes)
    diarios = [v for x, v in d["fat_dia"] if x.weekday() in DIAS_UTEIS]
    media = sum(diarios) / max(len(diarios), 1)
    desvio = (sum((v - media) ** 2 for v in diarios) / max(len(diarios) - 1, 1)) ** .5
    margem = desvio * max(len(uteis_restantes), 0) ** .5            # incerteza cresce com o tempo
    falta = max(d["meta"] - realizado, 0)
    por_dia = falta / max(len(uteis_restantes), 1)
    return {
        "todos": todos, "uteis": uteis, "hoje": hoje_, "realizado": realizado,
        "ritmo": ritmo, "projecao": projecao, "margem": margem, "falta": falta,
        "por_dia": por_dia, "contratos_dia": por_dia / max(d["ticket"], 1),
        "restantes": len(uteis_restantes), "frac_mes": len(uteis_passados) / max(len(uteis), 1),
        "frac_meta": realizado / d["meta"], "frac_proj": projecao / d["meta"],
    }


def gargalo(d):
    """Conversão mais distante do esperado (valor ÷ limite de 'atenção')."""
    f = dict(d["funil"])
    itens = [
        ("Leads → agendamentos", d["leads_agendados"] / max(d["leads"], 1), "leads_agend"),
        ("Consultas → atendimentos", f["Consultas atendidas"] / max(f["Consultas agendadas"], 1), "consult_atend"),
        ("Orçamentos → contratos", f["Contratos"] / max(f["Orçamentos"], 1), "orc_contrato"),
    ]
    nome, v, chave = min(itens, key=lambda x: x[1] / FAIXAS_CONVERSAO[x[2]][2])
    return nome, v, FAIXAS_CONVERSAO[chave][2]


def fig_projecao(d, pj):
    todos, uteis = pj["todos"], set(pj["uteis"])
    total_uteis = max(len(uteis), 1)
    ideal, cont = [], 0
    for x in todos:
        cont += x in uteis
        ideal.append(d["meta"] * cont / total_uteis)
    acum, real_x, real_y = 0, [], []
    for x, v in d["fat_dia"]:
        acum += v
        real_x.append(x)
        real_y.append(acum)
    proj_x, proj_y, alto, baixo = [pj["hoje"]], [pj["realizado"]], [pj["realizado"]], [pj["realizado"]]
    acum, n = pj["realizado"], 0
    desvio_dia = pj["margem"] / max(pj["restantes"], 1) ** .5 if pj["restantes"] else 0
    for x in todos:
        if x <= pj["hoje"]:
            continue
        if x in uteis:
            acum += pj["ritmo"]
            n += 1
        proj_x.append(x)
        proj_y.append(acum)
        alto.append(acum + desvio_dia * n ** .5)
        baixo.append(max(acum - desvio_dia * n ** .5, pj["realizado"]))

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=proj_x + proj_x[::-1], y=alto + baixo[::-1], fill="toself",
                             fillcolor="rgba(61,220,132,0.10)", line=dict(width=0),
                             hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=todos, y=ideal, mode="lines", name="Ritmo ideal",
                             line=dict(color=TEXTO_TER, width=1.5, dash="dot"),
                             hovertemplate="%{x|%d/%m} · ideal: R$ %{y:,.0f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=real_x, y=real_y, mode="lines", name="Realizado",
                             line=dict(color=VERDE, width=3, shape="spline"),
                             fill="tozeroy", fillcolor="rgba(61,220,132,0.14)",
                             hovertemplate="%{x|%d/%m} · realizado: R$ %{y:,.0f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=proj_x, y=proj_y, mode="lines", name="Projeção",
                             line=dict(color=VERDE, width=2, dash="dash"),
                             hovertemplate="%{x|%d/%m} · projeção: R$ %{y:,.0f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=[pj["hoje"]], y=[pj["realizado"]], mode="markers",
                             marker=dict(size=11, color=VERDE, line=dict(color=PANEL, width=3)),
                             hoverinfo="skip", showlegend=False))
    fig.add_hline(y=d["meta"], line=dict(color=AMBAR, width=1.5),
                  annotation_text=f"Meta {brl_curto(d['meta'])}", annotation_position="top left",
                  annotation_font=dict(color=AMBAR, size=11))
    fig.add_annotation(x=proj_x[-1], y=proj_y[-1], text=f"<b>{brl_curto(pj['projecao'])}</b>",
                       showarrow=False, xanchor="right", yanchor="bottom", yshift=6,
                       font=dict(color=VERDE, size=12))
    fig.update_layout(height=420, margin=dict(l=0, r=8, t=10, b=0), separators=",.",
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="Inter", color=TEXTO_SEC, size=11),
                      legend=dict(orientation="h", x=1, xanchor="right", y=1.12, font=dict(size=11)),
                      hoverlabel=dict(bgcolor=PANEL2, bordercolor=VERDE, font_color=TEXTO))
    fig.update_xaxes(showgrid=False, tickformat="%d/%m", linecolor=BORDA)
    topo = max(d["meta"], max(alto)) * 1.08
    marcas = [d["meta"] * k for k in (0, .25, .5, .75, 1)]
    fig.update_yaxes(gridcolor=BORDA, zeroline=False, range=[0, topo],
                     tickvals=marcas, ticktext=["R$ 0"] + [brl_curto(m) for m in marcas[1:]])
    return fig


def secao_briefing(d, unidade, ini, fim):
    pj = calcular_projecao(d, ini, fim)
    adiantado = pj["frac_meta"] - pj["frac_mes"]
    if pj["frac_proj"] >= 1:
        status, cor = "No ritmo da meta", SUCESSO
    elif pj["frac_proj"] >= .85:
        status, cor = "Atenção ao ritmo", AMBAR
    else:
        status, cor = "Abaixo do ritmo", VERMELHO

    def hl(txt, c=None):
        return html.B(txt, style={"color": c} if c else None)

    linhas = [
        [f"IPR {unidade} está em ", hl(pct(pj["frac_meta"], 1), VERDE), " da meta com ",
         hl(pct(pj["frac_mes"], 0)), " dos dias úteis do mês já passados — ",
         hl("acima do ritmo" if adiantado >= 0 else "abaixo do ritmo", SUCESSO if adiantado >= 0 else VERMELHO),
         " necessário."],
        ["No ritmo atual (", hl(brl_curto(pj["ritmo"])), " por dia útil), o mês deve fechar em ",
         hl(brl_curto(pj["projecao"]), cor), f" — {pct(pj['frac_proj'], 0)} da meta."],
    ]
    if pj["falta"] > 0 and pj["restantes"]:
        linhas.append(["Faltam ", hl(brl_curto(pj["falta"])), ": são ",
                       hl(f"~{num_br(pj['contratos_dia'], 1)} contratos por dia útil", VERDE),
                       f" ({brl_curto(pj['por_dia'])}/dia) nos {pj['restantes']} dias úteis que restam."])
    elif pj["falta"] <= 0:
        linhas.append([hl("Meta batida! ", SUCESSO), "Tudo que entrar agora é superação."])
    nome, v, esperado = gargalo(d)
    linhas.append(["Gargalo do período: ", hl(nome), " com ", hl(pct(v), VERMELHO if v < esperado else AMBAR),
                   f" (referência: {pct(esperado, 0)})."])
    if d["sem_data"]:
        top = max(d["sem_data_vendedor"], key=lambda x: x[1])
        linhas.append([hl(f"{d['sem_data']} contratos", AMBAR), " estão sem data de cirurgia — ",
                       hl(f"{pct(top[1] / max(d['sem_data'], 1), 0)} com {top[0]}"), "."])

    briefing = card([
        titulo_card(html.Span([icone("alta", "var(--acc)"), " Briefing do período"],
                              style={"display": "flex", "alignItems": "center", "gap": "6px"}),
                    html.Span(status, className="chip", style={"color": cor})),
        html.Div([html.Div([html.Span(className="brief-marca", style={"background": VERDE}),
                            html.Div(l)], className="brief-linha",
                           style={"animationDelay": f"{.15 + i * .18}s"})
                  for i, l in enumerate(linhas)], className="brief-lista"),
        html.Div("Gerado automaticamente a partir dos dados do painel", className="legenda brief-rodape"),
    ], "destaque briefing")

    def stat(rotulo, valor, sub, c=None):
        return html.Div([html.Div(rotulo, className="titulo-card"),
                         html.Div(valor, className="num medio", style={"color": c} if c else None),
                         html.Div(sub, className="legenda")], className="stat")

    projecao = card([
        titulo_card("Projeção de fechamento do mês",
                    html.Span(f"{pj['restantes']} dias úteis restantes", className="legenda")),
        html.Div([
            stat("Projeção", brl_curto(pj["projecao"]), f"{pct(pj['frac_proj'], 0)} da meta", cor),
            stat("Realizado", brl_curto(pj["realizado"]), f"{pct(pj['frac_meta'], 1)} da meta"),
            stat("Falta para a meta", brl_curto(pj["falta"]), "até o fim do período"),
            stat("Necessário por dia", brl_curto(pj["por_dia"]),
                 f"~{num_br(pj['contratos_dia'], 1)} contratos/dia útil"),
        ], className="grid-stats"),
        dcc.Graph(figure=fig_projecao(d, pj), config={"displayModeBar": False},
                  style={"height": "420px"}),
    ])
    return html.Div([briefing, projecao], className="grid-briefing")


# Cenas do Modo TV "card por card": (chave, nome, colunas, zoom)
CENAS = [
    ("faturamento", "Faturamento", 3, 1.9),
    ("funil", "Funil operacional", 1, 1.6),
    ("agenda", "Agendamento cirúrgico", 1, 1.55),
    ("conversao", "Conversão", 1, 1.6),
    ("cc", "Centro cirúrgico", 2, 1.55),
    ("captacao", "Captação", 1, 1.45),
    ("podio", "Destaques do time", 1, 1.7),
    ("jornada", "Jornada do paciente", 1, 1.2),
    ("briefing", "Briefing e projeção", 1, 1.1),
]


def montar_cena(unidade, ini, fim, i):
    d = carregar_dados(unidade, ini, fim)
    chave, nome, cols, zoom = CENAS[i % len(CENAS)]
    conteudo = {
        "faturamento": lambda: secao_faturamento(d),
        "funil": lambda: secao_funil(d, "funil"),
        "agenda": lambda: secao_funil(d, "agenda"),
        "conversao": lambda: secao_conversao(d),
        "cc": lambda: secao_cc(d),
        "captacao": lambda: secao_captacao(d),
        "podio": lambda: secao_podio(d),
        "jornada": lambda: secao_jornada(d),
        "briefing": lambda: secao("Briefing e projeção", [secao_briefing(d, unidade, ini, fim)]),
    }[chave]()
    pontos = html.Div([html.Span(className="cena-ponto" + (" ativo" if j == i % len(CENAS) else ""))
                       for j in range(len(CENAS))], className="cena-pontos")
    return html.Div([html.Div(conteudo, className=f"palco-conteudo cena-{chave}"), pontos],
                    className="palco", style={"--cols": cols, "--z": zoom})


def montar_gaveta(chave, unidade, ini, fim):
    linhas = carregar_detalhe(chave, unidade, ini, fim)

    def cab(titulo, sub, icone_nome, cor=VERDE):
        return html.Div([
            html.Div(icone(icone_nome), className="gaveta-icone", style={"color": cor}),
            html.Div([html.Div(titulo, className="gaveta-titulo"),
                      html.Div(sub, className="legenda")]),
        ], className="gaveta-cab")

    if chave == "sem_data":
        total = sum(l["valor"] for l in linhas)
        criticos = sum(1 for l in linhas if l["dias"] > 30)
        corpo = [
            cab("Contratos sem data de cirurgia", f"IPR {unidade} · ordenado pelos mais antigos", "alerta", AMBAR),
            html.Div([
                html.Div([html.Div("Contratos", className="titulo-card"), html.Div(str(len(linhas)), className="num medio")], className="stat"),
                html.Div([html.Div("Valor parado", className="titulo-card"), html.Div(brl_curto(total), className="num medio")], className="stat"),
                html.Div([html.Div("Há +30 dias", className="titulo-card"), html.Div(str(criticos), className="num medio", style={"color": VERMELHO if criticos else SUCESSO})], className="stat"),
            ], className="grid-3"),
            html.Div([html.Div([
                avatar(l["vendedor"], 38, AMBAR),
                html.Div([html.Div([html.B(l["prontuario"]), html.Span(f" · {l['procedimento']}", className="legenda")]),
                          html.Div(f"{l['vendedor']} · contrato em {l['data']:%d/%m/%Y}", className="legenda")],
                         style={"flex": 1, "minWidth": 0}),
                html.Div([html.Div(brl(l["valor"], 0), style={"fontWeight": 700}),
                          html.Span(f"{l['dias']} dias", className="chip", style={
                              "color": VERMELHO if l["dias"] > 30 else (AMBAR if l["dias"] > 15 else SUCESSO)})],
                         style={"textAlign": "right", "display": "flex", "flexDirection": "column", "gap": "4px", "alignItems": "flex-end"}),
            ], className="gaveta-linha", style={"animationDelay": f"{i * .04}s"}) for i, l in enumerate(linhas)],
                className="gaveta-lista"),
            html.Div("Dica: os vermelhos estão parados há mais de 30 dias — priorize o contato.", className="legenda gaveta-dica"),
        ]
    elif chave == "faturamento":
        total = sum(l["valor"] for l in linhas)
        corpo = [
            cab("Contratos do período", f"IPR {unidade} · {len(linhas)} contratos · {brl_curto(total)}", "alta"),
            html.Div([html.Div([
                avatar(l["vendedor"], 34, VERDE),
                html.Div([html.Div([html.B(l["prontuario"]), html.Span(f" · {l['procedimento']}", className="legenda")]),
                          html.Div(f"{l['vendedor']} · {l['data']:%d/%m/%Y}", className="legenda")],
                         style={"flex": 1, "minWidth": 0}),
                html.Div(brl(l["valor"], 0), style={"fontWeight": 700}),
            ], className="gaveta-linha", style={"animationDelay": f"{min(i, 20) * .03}s"}) for i, l in enumerate(linhas)],
                className="gaveta-lista"),
        ]
    else:
        corpo = [
            cab("Ranking de vendedores", f"IPR {unidade} · faturamento em contratos", "coroa", MEDALHAS[1]),
            html.Div([html.Div([
                html.Div(f"{i + 1}º", className="ranking-pos",
                         style={"color": MEDALHAS.get(i + 1, TEXTO_SEC)}),
                avatar(l["vendedor"], 42, MEDALHAS.get(i + 1, TEXTO_TER), brilho=i == 0),
                html.Div([html.Div(l["vendedor"], style={"fontWeight": 700}),
                          html.Div(html.Div(className="trilho-fill", style={
                              "width": f"{l['part'] / linhas[0]['part'] * 100:.0f}%", "background": VERDE}),
                              className="trilho"),
                          html.Div(f"{l['contratos']} contratos · {pct(l['part'], 1)} do total", className="legenda",
                                   style={"marginTop": "4px"})], style={"flex": 1}),
                html.Div(brl_curto(l["valor"]), style={"fontWeight": 800, "fontSize": "16px"}),
            ], className="gaveta-linha", style={"animationDelay": f"{i * .06}s"}) for i, l in enumerate(linhas)],
                className="gaveta-lista"),
        ]
    return corpo


def toast_contrato(unidade, n):
    c = novo_contrato_simulado(unidade, n)
    return html.Div([
        html.Div([avatar(c["vendedor"], 64, VERDE, brilho=True),
                  html.Div(icone("festa"), className="toast-selo")], style={"position": "relative"}),
        html.Div([
            html.Div("NOVO CONTRATO", className="toast-sobre"),
            html.Div(c["vendedor"], className="toast-nome"),
            html.Div([f"fechou {c['procedimento'].lower()} · ", html.B(brl(c["valor"], 0))],
                     className="toast-texto"),
            html.Div(f"IPR {unidade} · agora mesmo", className="legenda"),
        ]),
    ], className="toast-contrato", **{"data-evento": f"{unidade}-{n}"})


# ===========================================================================
# ABA ANÁLISES (dados FICTÍCIOS — cada função diz o que buscar no banco)
# ===========================================================================
DDD_UF = {
    "SP": [11, 12, 13, 14, 15, 16, 17, 18, 19], "RJ": [21, 22, 24], "ES": [27, 28],
    "MG": [31, 32, 33, 34, 35, 37, 38], "PR": [41, 42, 43, 44, 45, 46], "SC": [47, 48, 49],
    "RS": [51, 53, 54, 55], "DF": [61], "GO": [62, 64], "TO": [63], "MT": [65, 66], "MS": [67],
    "AC": [68], "RO": [69], "BA": [71, 73, 74, 75, 77], "SE": [79], "PE": [81, 87], "AL": [82],
    "PB": [83], "RN": [84], "CE": [85, 88], "PI": [86, 89], "PA": [91, 93, 94], "AM": [92, 97],
    "RR": [95], "AP": [96], "MA": [98, 99],
}
# posição de cada estado num "mapa em blocos" (coluna, linha)
UF_POS = {
    "RR": (2, 0), "AP": (4, 0),
    "AM": (1, 1), "PA": (3, 1), "MA": (4, 1), "CE": (5, 1), "RN": (6, 1),
    "AC": (0, 2), "RO": (1, 2), "MT": (2, 2), "TO": (3, 2), "PI": (4, 2), "PE": (5, 2), "PB": (6, 2),
    "MS": (2, 3), "GO": (3, 3), "DF": (4, 3), "BA": (5, 3), "AL": (6, 3),
    "SP": (3, 4), "MG": (4, 4), "ES": (5, 4), "SE": (6, 4),
    "PR": (3, 5), "RJ": (4, 5),
    "SC": (3, 6),
    "RS": (3, 7),
}
DDD_CIDADE = {11: "São Paulo", 13: "Santos", 19: "Campinas", 12: "S. J. Campos", 15: "Sorocaba",
              14: "Bauru", 16: "Ribeirão Preto", 17: "S. J. Rio Preto", 18: "Pres. Prudente",
              21: "Rio de Janeiro", 31: "Belo Horizonte", 41: "Curitiba", 61: "Brasília",
              71: "Salvador", 81: "Recife", 51: "Porto Alegre", 62: "Goiânia", 85: "Fortaleza",
              27: "Vitória", 48: "Florianópolis", 67: "Campo Grande", 92: "Manaus", 91: "Belém"}
DDD_LOCAL = {"Santos": 13, "São Paulo": 11, "Campinas": 19}


def carregar_analises(unidade, ini, fim):
    d = carregar_dados(unidade, ini, fim)
    rnd = random.Random(unidade + "-analises")
    a = {"d": d}

    # --- mapa de calor do centro cirúrgico (real: vw_agendamentos de cirurgia, coluna horario) ---
    dias = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]
    horas = list(range(7, 19))
    grade = []
    for i, _ in enumerate(dias):
        linha = []
        for h in horas:
            if i == 5 and h >= 13:
                linha.append(None)                      # sábado à tarde: fechado
                continue
            base = .78 if 8 <= h <= 11 else (.55 if 13 <= h <= 15 else .3)
            if i == 4 and h >= 14:
                base = .12                              # sexta à tarde quase vazia
            if h == 12:
                base = .08                              # almoço
            linha.append(max(0, min(1, base * rnd.uniform(.6, 1.25) * (d["ocupacao_cc"] / .45))))
        grade.append(linha)
    a["calor"] = (dias, horas, grade)

    # --- jornada com perdas (Sankey) ---
    f = dict(d["funil"])
    a["sankey"] = {
        "leads": d["leads"], "leads_agend": d["leads_agendados"],
        "outras": max(f["Consultas agendadas"] - d["leads_agendados"], 0),
        "agendadas": f["Consultas agendadas"], "atendidas": f["Consultas atendidas"],
        "orcamentos": f["Orçamentos"], "contratos": f["Contratos"],
        "cirurgias": max(f["Contratos"] - d["sem_data"], 0), "sem_data": d["sem_data"],
    }

    # --- comparativo entre unidades ---
    a["unidades"] = {u: carregar_dados(u, ini, fim) for u in UNIDADES}

    # --- leads por DDD (real: crm.Referrals, DDD do telefone do contato) ---
    local = DDD_LOCAL[unidade]
    pesos = {ddd: rnd.uniform(.2, 1.0) for uf in DDD_UF.values() for ddd in uf}
    for ddd in (11, 13, 19):
        pesos[ddd] = pesos[ddd] * 25
    pesos[local] = 0
    total_out = sum(pesos.values())
    n_local = round(d["leads"] * d["ddd"])
    resto = d["leads"] - n_local
    por_ddd = {ddd: round(resto * w / total_out) for ddd, w in pesos.items()}
    por_ddd[local] = n_local
    a["ddd"] = por_ddd
    a["uf"] = {uf: sum(por_ddd[x] for x in ddds) for uf, ddds in DDD_UF.items()}

    # --- coorte (real: leads por semana de criação × contrato em até 30/60/90 dias) ---
    hoje_ = date.today()
    semanas = []
    for k in range(13, 1, -1):
        ini_sem = hoje_ - timedelta(days=hoje_.weekday() + 7 * k)
        idade = (hoje_ - ini_sem).days
        leads_sem = round(d["leads"] / 4.3 * rnd.uniform(.75, 1.25))
        c30 = rnd.uniform(.012, .028)
        c60 = c30 + rnd.uniform(.006, .014)
        c90 = c60 + rnd.uniform(.003, .008)
        semanas.append({"semana": ini_sem, "leads": leads_sem,
                        "c30": c30 if idade >= 30 else None,
                        "c60": c60 if idade >= 60 else None,
                        "c90": c90 if idade >= 90 else None,
                        "parcial": c30 * min(idade / 30, 1) if idade < 30 else None})
    a["coorte"] = semanas

    # --- saúde dos dados (real: MAX(ultima_atualizacao)/COUNT(*) de cada view do cm_sync) ---
    agora = datetime.now()
    a["saude"] = [
        ("vw_agendamentos", agora - timedelta(minutes=rnd.randint(2, 9)), rnd.randint(40_000, 60_000), rnd.uniform(0, .02)),
        ("vw_contratos", agora - timedelta(minutes=rnd.randint(2, 9)), rnd.randint(4_000, 7_000), rnd.uniform(0, .01)),
        ("vw_orcamentos", agora - timedelta(minutes=rnd.randint(2, 9)), rnd.randint(8_000, 12_000), rnd.uniform(0, .015)),
        ("vw_recebiveis", agora - timedelta(minutes=rnd.randint(2, 9)), 42_650, rnd.uniform(0, .01)),
        ("vw_prontuarios", agora - timedelta(minutes=rnd.randint(2, 9)), rnd.randint(30_000, 45_000), rnd.uniform(.02, .06)),
        ("crm.Referrals", agora - timedelta(minutes=rnd.randint(40, 75)), rnd.randint(90_000, 120_000), rnd.uniform(0, .03)),
    ]
    return a


def _layout_fig(fig, altura):
    fig.update_layout(height=altura, margin=dict(l=0, r=0, t=6, b=0), separators=",.",
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="Inter", color=TEXTO_SEC, size=12),
                      hoverlabel=dict(bgcolor=PANEL2, bordercolor=VERDE, font_color=TEXTO))
    return fig


def card_comparativo(a, unidade):
    us = a["unidades"]
    linhas = [
        ("% da meta", lambda d: d["faturamento"] / d["meta"], lambda v: pct(v, 1), True),
        ("Faturamento", lambda d: d["faturamento"], brl_curto, True),
        ("Contratos", lambda d: dict(d["funil"])["Contratos"], num_br, True),
        ("Ticket médio", lambda d: d["ticket"], lambda v: brl(v, 0), True),
        ("Consultas → atendimentos", lambda d: d["metricas"]["conv_consult"], lambda v: pct(v, 1), True),
        ("Orçamentos → contratos", lambda d: d["metricas"]["conv_orc"], lambda v: pct(v, 1), True),
        ("Ocupação do centro cirúrgico", lambda d: d["ocupacao_cc"], lambda v: pct(v, 1), True),
        ("Leads", lambda d: d["leads"], num_br, True),
        ("Cancelamento", lambda d: d["cancelamento"], lambda v: pct(v, 1), False),
        ("Sem data de cirurgia", lambda d: d["sem_data"], num_br, False),
    ]
    ranking = sorted(UNIDADES, key=lambda u: -us[u]["faturamento"] / us[u]["meta"])
    cab = html.Div([html.Div("Indicador", className="cmp-rotulo")] + [
        html.Div([html.Span(f"{ranking.index(u) + 1}º", className="cmp-pos",
                            style={"color": MEDALHAS.get(ranking.index(u) + 1, TEXTO_SEC)}),
                  html.Span(f"IPR {u}")],
                 className="cmp-cab" + (" atual" if u == unidade else ""))
        for u in UNIDADES], className="cmp-linha cmp-topo")
    corpo = []
    for nome, fn, fmt, maior_melhor in linhas:
        vals = {u: fn(us[u]) for u in UNIDADES}
        melhor = (max if maior_melhor else min)(vals, key=vals.get)
        teto = max(vals.values()) or 1
        corpo.append(html.Div([html.Div(nome, className="cmp-rotulo")] + [
            html.Div([
                html.Div([html.Span(fmt(vals[u])),
                          icone("coroa", MEDALHAS[1]) if u == melhor else None],
                         className="cmp-valor"),
                html.Div(html.Div(className="trilho-fill", style={
                    "width": f"{vals[u] / teto * 100:.0f}%",
                    "background": (SUCESSO if u == melhor else VERDE) if maior_melhor
                    else (SUCESSO if u == melhor else AMBAR)}), className="trilho"),
            ], className="cmp-cel" + (" atual" if u == unidade else ""))
            for u in UNIDADES], className="cmp-linha"))
    lider = ranking[0]
    return card([
        titulo_card("Comparativo entre unidades",
                    html.Span(["Líder em % da meta: ", html.B(f"IPR {lider}")], className="legenda")),
        html.Div([cab] + corpo, className="cmp-tabela"),
        html.Div([icone("coroa", MEDALHAS[1]), " = melhor unidade no indicador · coluna destacada = unidade selecionada"],
                 className="legenda", style={"marginTop": "10px"}),
    ])


def card_sankey(a):
    s = a["sankey"]
    nos = ["Vindas de leads", "", "Outras origens", "Consultas agendadas", "Faltas e desmarcações",
           "Atendidas", "Sem orçamento", "Orçamentos", "Não fecharam", "Contratos",
           "Sem data de cirurgia", "Cirurgia agendada"]
    ok, perda, neutro = "rgba(61,220,132,0.45)", "rgba(255,107,107,0.30)", "rgba(147,163,154,0.30)"
    fluxos = [
        (0, 3, s["leads_agend"], ok),
        (2, 3, s["outras"], neutro),
        (3, 5, s["atendidas"], ok), (3, 4, s["agendadas"] - s["atendidas"], perda),
        (5, 7, s["orcamentos"], ok), (5, 6, max(s["atendidas"] - s["orcamentos"], 0), perda),
        (7, 9, s["contratos"], ok), (7, 8, s["orcamentos"] - s["contratos"], perda),
        (9, 11, s["cirurgias"], ok), (9, 10, s["sem_data"], AMBAR + "66"),
    ]
    cor_no = [VERDE, BORDA, TEXTO_TER, VERDE, VERMELHO, VERDE, VERMELHO, VERDE, VERMELHO, VERDE, AMBAR, SUCESSO]
    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(label=nos, color=cor_no, pad=18, thickness=14, line=dict(width=0),
                  hovertemplate="%{label}: <b>%{value:,.0f}</b><extra></extra>"),
        link=dict(source=[x[0] for x in fluxos], target=[x[1] for x in fluxos],
                  value=[x[2] for x in fluxos], color=[x[3] for x in fluxos],
                  hovertemplate="%{source.label} → %{target.label}: <b>%{value:,.0f}</b><extra></extra>"),
        textfont=dict(color=TEXTO, size=12, family="Inter")))
    _layout_fig(fig, 360)
    fig.update_layout(margin=dict(l=0, r=0, t=6, b=14))
    perdas = [("faltas e desmarcações", s["agendadas"] - s["atendidas"], s["agendadas"]),
              ("orçamentos que não fecharam", s["orcamentos"] - s["contratos"], s["orcamentos"])]
    maior = max(perdas, key=lambda p: p[1] / max(p[2], 1))
    return card([
        titulo_card("Para onde vão os pacientes"),
        html.Div(["Maior perda: ", html.B(f"{pct(maior[1] / max(maior[2], 1), 0)} {maior[0]}",
                                          style={"color": VERMELHO}),
                  f" ({num_br(maior[1])} de {num_br(maior[2])}). Antes disso, ",
                  html.B(f"{pct(1 - s['leads_agend'] / max(s['leads'], 1), 0)} dos leads"),
                  " não chegaram a agendar."], className="insight"),
        dcc.Graph(figure=fig, config={"displayModeBar": False}, style={"height": "360px"}),
    ], "cresce")


SIM_CAMPOS = [
    ("sim-consult", "Consultas → atendimentos", "conv_consult", 0, 60),
    ("sim-orc", "Orçamentos → contratos", "conv_orc", 20, 80),
    ("sim-ticket", "Ticket médio (variação %)", None, -20, 20),
]


def card_simulador(a):
    m = a["d"]["metricas"]
    controles = []
    for cid, nome, chave, mn, mx in SIM_CAMPOS:
        atual = round(m[chave] * 100) if chave else 0
        controles.append(html.Div([
            html.Div([html.Span(nome, className="titulo-card"),
                      html.Span(id=f"{cid}-valor", className="sim-valor")],
                     style={"display": "flex", "justifyContent": "space-between"}),
            dcc.Slider(id=cid, min=mn, max=mx, step=1, value=atual, marks=None,
                       tooltip={"always_visible": False}, className="sim-slider"),
            html.Div(f"hoje: {atual}{'%' if chave else '% (ticket atual)'}", className="legenda"),
        ], className="sim-controle"))
    return card([
        titulo_card("Simulador “e se”"),
        html.Div("Arraste para ver quanto o faturamento muda se um indicador melhorar.",
                 className="legenda", style={"marginBottom": "12px"}),
        *controles,
        html.Div(id="sim-resultado", className="sim-resultado"),
    ])


def resultado_simulacao(a, consult, orc, ticket_var):
    d, m = a["d"], a["d"]["metricas"]
    f = dict(d["funil"])
    agendadas = f["Consultas agendadas"]
    taxa_orc = f["Orçamentos"] / max(f["Consultas atendidas"], 1)
    base = agendadas * round(m["conv_consult"] * 100) / 100 * taxa_orc * round(m["conv_orc"] * 100) / 100
    escala = f["Contratos"] / max(base, 1e-9)        # calibra para "sem mudança" = números de hoje
    contratos_sim = agendadas * (consult / 100) * taxa_orc * (orc / 100) * escala
    fat_atual = d["faturamento"]
    fat_sim = fat_atual * (contratos_sim / max(f["Contratos"], 1)) * (1 + ticket_var / 100)
    dif = fat_sim - fat_atual
    cor = SUCESSO if dif >= 0 else VERMELHO
    return [
        html.Div([html.Div("Faturamento hoje", className="titulo-card"),
                  html.Div(brl_curto(fat_atual), className="num medio")], className="stat"),
        html.Div(icone("seta"), className="sim-seta"),
        html.Div([html.Div("Faturamento simulado", className="titulo-card"),
                  html.Div(brl_curto(fat_sim), className="num medio", style={"color": cor}),
                  html.Div([f"{'+' if dif >= 0 else '−'}{brl_curto(abs(dif))} · ",
                            f"{'+' if contratos_sim >= f['Contratos'] else '−'}"
                            f"{num_br(abs(contratos_sim - f['Contratos']), 0)} contratos"],
                           className="legenda", style={"color": cor, "fontWeight": 700})],
                 className="stat destaque-sim"),
    ]


def card_calor(a):
    dias, horas, grade = a["calor"]
    fig = go.Figure(go.Heatmap(
        z=grade, x=[f"{h}h" for h in horas], y=dias, zmin=0, zmax=1, xgap=4, ygap=4,
        colorscale=[[0, BORDA], [.35, VERDE_ESC], [1, VERDE]], showscale=False,
        text=[[("" if v is None else f"{v * 100:.0f}%") for v in linha] for linha in grade],
        texttemplate="%{text}", textfont=dict(size=11, color=TEXTO),
        hovertemplate="%{y} %{x}: <b>%{text}</b> de ocupação<extra></extra>"))
    _layout_fig(fig, 300)
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(showgrid=False, side="top")
    livres = [(grade[i][j], dias[i], horas[j]) for i in range(len(dias)) for j in range(len(horas))
              if grade[i][j] is not None and horas[j] != 12]
    v, dia, h = min(livres)
    return card([
        titulo_card("Mapa de calor do centro cirúrgico"),
        html.Div(["Janela mais ociosa: ", html.B(f"{dia} às {h}h", style={"color": AMBAR}),
                  f" ({pct(v, 0)} de ocupação) — boa hora para encaixar cirurgias."], className="insight"),
        dcc.Graph(figure=fig, config={"displayModeBar": False}, style={"height": "300px"}),
    ])


def card_mapa_ddd(a, unidade):
    uf, ddd = a["uf"], a["ddd"]
    teto = max(uf.values()) or 1
    total = sum(uf.values()) or 1
    blocos = []
    for sigla, (c, l) in UF_POS.items():
        v = uf.get(sigla, 0)
        inten = (v / teto) ** .35 if v else 0
        alfa = round(15 + inten * 240)
        blocos.append(html.Div([html.B(sigla), html.Span(num_br(v))], className="uf",
                               title=f"{sigla}: {num_br(v)} leads ({pct(v / total, 1)})",
                               style={"gridColumn": c + 1, "gridRow": l + 1,
                                      "background": f"{VERDE}{alfa:02x}",
                                      "color": PANEL if inten > .55 else TEXTO}))
    top = sorted(ddd.items(), key=lambda x: -x[1])[:7]
    maior = top[0][1] or 1
    barras = [html.Div([
        html.Span(f"({k}) {DDD_CIDADE.get(k) or next(uf for uf, ds in DDD_UF.items() if k in ds)}",
                  className="ddd-nome"),
        html.Div(html.Div(className="trilho-fill", style={"width": f"{v / maior * 100:.0f}%",
                                                          "background": VERDE if k == DDD_LOCAL[unidade] else VERDE_ESC}),
                 className="trilho", style={"flex": 1, "marginTop": 0}),
        html.B(num_br(v), className="ddd-num"),
    ], className="ddd-linha") for k, v in top]
    return card([
        titulo_card("De onde vêm os leads (DDD)"),
        html.Div(["DDD local (", html.B(f"{DDD_LOCAL[unidade]}"), "): ",
                  html.B(pct(a["d"]["ddd"], 1), style={"color": VERDE}),
                  f" dos leads · {sum(1 for x in uf.values() if x)} estados com leads"], className="insight"),
        html.Div([html.Div(blocos, className="mapa-uf"), html.Div(barras, className="ddd-lista")],
                 className="mapa-wrap"),
    ])


def card_coorte(a):
    linhas = []
    for s in a["coorte"]:
        def cel(v, parcial=None):
            if v is None and parcial is None:
                return html.Div("—", className="coorte-cel vazia")
            val = v if v is not None else parcial
            inten = min(val / .045, 1)
            return html.Div(pct(val, 1) + ("*" if v is None else ""), className="coorte-cel",
                            style={"background": f"{VERDE}{round(20 + inten * 200):02x}",
                                   "color": PANEL if inten > .6 else TEXTO})
        linhas.append(html.Div([
            html.Div(f"{s['semana']:%d/%m}", className="coorte-sem"),
            html.Div(num_br(s["leads"]), className="coorte-leads"),
            cel(s["c30"], s["parcial"]), cel(s["c60"]), cel(s["c90"]),
        ], className="coorte-linha"))
    return card([
        titulo_card("Coorte de leads → contrato"),
        html.Div("Dos leads que entraram em cada semana, quantos % viraram contrato em até 30, 60 e 90 dias.",
                 className="legenda", style={"marginBottom": "10px"}),
        html.Div([html.Div("Semana", className="coorte-sem"), html.Div("Leads", className="coorte-leads"),
                  html.Div("30 dias", className="coorte-cab"), html.Div("60 dias", className="coorte-cab"),
                  html.Div("90 dias", className="coorte-cab")], className="coorte-linha topo"),
        *linhas,
        html.Div("* semana ainda em andamento · — prazo ainda não completou", className="legenda",
                 style={"marginTop": "8px"}),
    ])


def card_saude(a):
    agora = datetime.now()
    itens = []
    pior = 0
    for nome, quando, linhas, nulos in a["saude"]:
        minutos = (agora - quando).total_seconds() / 60
        status, cor = (("Atualizado", SUCESSO) if minutos <= 30 else
                       ("Atrasado", AMBAR) if minutos <= 120 else ("Parado", VERMELHO))
        pior = max(pior, 0 if minutos <= 30 else 1 if minutos <= 120 else 2)
        itens.append(html.Div([
            html.Span(className="saude-ponto", style={"background": cor}),
            html.Div([html.B(nome, style={"fontFamily": "ui-monospace, Consolas, monospace", "fontSize": "13px"}),
                      html.Div(f"{num_br(linhas)} linhas · {pct(nulos, 1)} incompletos", className="legenda")],
                     style={"flex": 1}),
            html.Div([html.Span(status, className="chip", style={"color": cor}),
                      html.Div(f"há {minutos:.0f} min", className="legenda", style={"marginTop": "4px"})],
                     style={"textAlign": "right"}),
        ], className="saude-linha"))
    geral = ["Tudo sincronizado", "Atenção: alguma fonte atrasada", "Fonte parada"][pior]
    cor_geral = [SUCESSO, AMBAR, VERMELHO][pior]
    return card([
        titulo_card("Saúde dos dados", html.Span(geral, className="chip", style={"color": cor_geral})),
        html.Div(itens, style={"display": "flex", "flexDirection": "column", "gap": "8px"}),
        html.Div("Verifica a última sincronização de cada fonte do painel.", className="legenda",
                 style={"marginTop": "10px"}),
    ])


def montar_analises(unidade, ini, fim):
    a = carregar_analises(unidade, ini, fim)
    return html.Div([
        secao("Comparativo entre unidades", [card_comparativo(a, unidade)]),
        html.Div([
            secao("Jornada com perdas", [card_sankey(a)]),
            secao("Simulador", [card_simulador(a)]),
        ], className="grid-analises a"),
        html.Div([
            secao("Centro cirúrgico", [card_calor(a)]),
            secao("Captação", [card_mapa_ddd(a, unidade)]),
        ], className="grid-analises b"),
        html.Div([
            secao("Maturação dos leads", [card_coorte(a)]),
            secao("Qualidade", [card_saude(a)]),
        ], className="grid-analises c"),
    ], className="fade-in analises")


# ===========================================================================
# TICKER DO MODO TV
# ===========================================================================
def ticker_itens(unidade, ini, fim):
    """Faixa de notícias do Modo TV. FICTÍCIO: no real, últimos contratos (vw_contratos),
    cirurgias de hoje (vw_agendamentos) e os alertas calculados."""
    d = carregar_dados(unidade, ini, fim)
    rnd = random.Random(unidade + "-ticker")
    itens = []
    for i in range(3):
        v = rnd.choice(d["vendedores"])
        itens.append(("festa", VERDE, f"{v['nome']} fechou contrato · {brl(d['ticket'] * rnd.uniform(.8, 1.3), 0)}",
                      f"há {rnd.randint(4, 50) + i * 40} min"))
    itens.append(("unidade", SUCESSO, f"{rnd.randint(4, 9)} cirurgias hoje no centro cirúrgico", f"IPR {unidade}"))
    pj = calcular_projecao(d, ini, fim)
    itens.append(("alvo", VERDE, f"Meta em {pct(pj['frac_meta'], 1)} · faltam {brl_curto(pj['falta'])}",
                  f"~{num_br(pj['contratos_dia'], 1)} contratos/dia útil"))
    itens.append(("alerta", AMBAR, f"{d['sem_data']} contratos sem data de cirurgia", "priorizar agendamento"))
    for chave, msg in d["alertas"].items():
        nome = next((r[4] for r in REGRAS_ALERTA if r[0] == chave), chave)
        itens.append(("alerta", VERMELHO, f"{nome}: {msg}", "fora do normal"))
    v = d["vendedores"][0]
    itens.append(("coroa", MEDALHAS[1], f"Líder do mês: {v['nome']}", brl_curto(v["valor"])))
    return itens


def montar_ticker(unidade, ini, fim):
    itens = ticker_itens(unidade, ini, fim)
    def bloco():
        return [html.Span([html.Span(icone(ic), style={"color": cor}), html.B(txt),
                           html.Span(sub, className="ticker-sub"), html.Span("•", className="ticker-sep")],
                          className="ticker-item") for ic, cor, txt, sub in itens]
    duracao = max(40, len(itens) * 9)
    return [html.Div("AO VIVO", className="ticker-selo"),
            html.Div(html.Div(bloco() + bloco(), className="ticker-trilha",
                              style={"animationDuration": f"{duracao}s"}), className="ticker-janela")]


ABAS = {
    "geral": ("Visão geral", "grade"),
    "briefing": ("Briefing e projeção", "alta"),
    "analises": ("Análises", "analise"),
}


def montar_painel(unidade, ini, fim, aba="geral"):
    d = carregar_dados(unidade, ini, fim)
    if aba == "briefing":
        return html.Div(secao_briefing(d, unidade, ini, fim), className="fade-in")
    if aba == "analises":
        return montar_analises(unidade, ini, fim)
    return html.Div([
        html.Div([
            html.Div([secao_faturamento(d), secao_podio(d)], className="col"),
            html.Div([secao_captacao(d), secao_conversao(d)], className="col"),
            html.Div(secao_funil(d), className="col"),
            html.Div(secao_cc(d), className="col"),
        ], className="grid-colunas"),
        secao_jornada(d),
    ], className="fade-in")


# ===========================================================================
# APP
# ===========================================================================
app = Dash(__name__, title="Painel Gerencial · IPR", suppress_callback_exceptions=True,
           external_stylesheets=["https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap"])

hoje = date.today()
inicio_mes = hoje.replace(day=1)
fim_mes = (inicio_mes + timedelta(days=32)).replace(day=1) - timedelta(days=1)

CAMINHO = ["Coleções", "Gerente de Rede"]
PRESETS = [("hoje", "Hoje"), ("7d", "7 dias"), ("mes", "Este mês"), ("mes_ant", "Mês passado"), ("ano", "Este ano")]


def menu(id_, resumo, conteudo, classe=""):
    """Menu suspenso (abre ao clicar, fecha ao clicar fora)."""
    return html.Details([html.Summary(resumo), html.Div(conteudo, className="menu-pop")],
                        id=id_, className=f"menu {classe}")


barra_topo = html.Div([
    # fundo animado (grade + brilho girando como um radar)
    html.Div([html.Div(className="hero-grade"), html.Div(className="hero-brilho")], className="topo-fundo"),
    # 1) identidade: logo + caminho + título
    html.Div([
        (html.Img(src=app.get_asset_url(LOGO), alt="IPR Blefaroplastia", className="logo-img")
         if (Path(__file__).parent / "assets" / LOGO).exists()
         else html.Div("IPR", className="logo-selo")),
        html.Div(className="logo-divisor"),
        html.Div([
            html.Div([icone("home"), " ", " › ".join(CAMINHO[:-1]), " › ", html.B(CAMINHO[-1])],
                     className="migalhas"),
            html.H1(TITULO, className="topo-titulo"),
        ]),
    ], className="topo-id"),
    html.Div(id="tv-info", className="tv-info"),

    # 2) pílula de contexto: unidade · período · meta
    html.Div([
        menu("menu-unidade",
             [icone("unidade"), html.Span(id="unidade-rotulo"), html.Span("▾", className="car")],
             [html.Div("Unidade", className="menu-rot")] +
             [html.Button([f"IPR {u}", html.Span("✓", className="check")],
                          id={"tipo": "btn-unidade", "u": u}, className="opt", n_clicks=0) for u in UNIDADES],
             "seg"),
        html.Span(className="pilula-sep"),
        menu("menu-periodo",
             [icone("calendario"), html.Span(id="periodo-rotulo"), html.Span("▾", className="car")],
             [html.Div("Período", className="menu-rot"),
              html.Div([html.Button(nome, id={"tipo": "preset", "p": k}, className="chip-p", n_clicks=0)
                        for k, nome in PRESETS], className="presets"),
              html.Div("ou escolha as datas:", className="legenda", style={"margin": "10px 0 6px"}),
              dcc.DatePickerRange(id="periodo", start_date=inicio_mes, end_date=fim_mes,
                                  display_format="DD/MM/YYYY")],
             "seg"),
        html.Span(className="pilula-sep"),
        html.Div(id="meta-pilula", className="meta-pilula"),
    ], className="pilula"),

    # 3) ações
    html.Div([
        html.Div([html.Span(className="ponto-vivo"), html.Span(id="relogio")], className="vivo"),
        menu("menu-alertas",
             [html.Span(icone("sino"), className="ic-btn"), html.Span(id="alertas-badge", className="badge")],
             html.Div(id="alertas-lista"), "icone alinhar-dir"),
        html.Button([icone("lua", None), icone("sol", None)], id="btn-tema-toggle", n_clicks=0,
                    className="btn-ic tema-btn", title="Trocar tema"),
        html.Button(icone("tela_cheia"), id="btn-tela-cheia", className="btn-ic", n_clicks=0,
                    title="Tela cheia (Esc sai)"),
        html.Div([
            html.Button("‹", id="btn-cena-ant", className="pill nav-cena", n_clicks=0, title="Card anterior"),
            html.Button("›", id="btn-cena-prox", className="pill nav-cena", n_clicks=0, title="Próximo card"),
        ], className="tv-nav"),
        html.Div([
            html.Button([icone("grade"), " Painel inteiro"], id={"tipo": "btn-estilo", "e": "painel"},
                        className="pill ativo", n_clicks=0),
            html.Button([icone("card"), " Card por card"], id={"tipo": "btn-estilo", "e": "cards"},
                        className="pill", n_clicks=0),
        ], className="pills tv-estilo"),
        html.Button([icone("tv"), " Modo TV"], id="btn-tv", className="pill tv", n_clicks=0,
                    title="Esconde o título e troca de unidade sozinho"),
        menu("menu-avatar",
             avatar(GERENTE["nome"], 40, "var(--acc)", brilho=True, arquivo=GERENTE["arquivo"]),
             [html.Div([avatar(GERENTE["nome"], 52, "var(--acc)", arquivo=GERENTE["arquivo"]),
                        html.Div([html.Div(GERENTE["nome"], className="gerente-nome"),
                                  html.Div(GERENTE["cargo"], className="legenda")])],
                       className="perfil"),
              # TEMPORÁRIO: apagar este botão quando não precisar mais da demonstração
              html.Button([icone("festa"), " Simular venda"], id="btn-simular", className="opt demo",
                          n_clicks=0)],
             "avatar-menu alinhar-dir"),
    ], className="acoes"),
    html.Div(id="meta-linha", className="meta-linha"),
], className="barra-topo topo-novo")

app.layout = html.Div([
    dcc.Store(id="unidade", data=UNIDADES[0]),
    dcc.Store(id="tv", data=False),
    dcc.Interval(id="tick", interval=SEGUNDOS_TV * 1000, disabled=True),
    dcc.Store(id="tela-cheia-dummy"),
    dcc.Store(id="aba", data="geral"),
    dcc.Store(id="tv-estilo", data="painel"),
    dcc.Store(id="cena", data=0),
    dcc.Interval(id="evento", interval=SEGUNDOS_EVENTO * 1000, disabled=True),
    html.Div([
        html.Div(id="gaveta-fundo", n_clicks=0, className="gaveta-fundo"),
        html.Div([
            html.Button(icone("fechar"), id="gaveta-fechar", n_clicks=0, className="gaveta-x",
                        title="Fechar (Esc)"),
            html.Div(id="gaveta-conteudo"),
        ], className="gaveta"),
    ], id="gaveta-wrap", className="gaveta-wrap"),
    html.Div(id="toast-area", className="toast-area"),
    html.Div(id="ticker", className="ticker"),
    dcc.Store(id="tema", data=TEMA_PADRAO, storage_type="local"),   # o navegador lembra a escolha
    barra_topo,
    html.Div([
        html.Div([
            html.Div([
                html.Button([icone(ic), f" {nome}"], id={"tipo": "btn-aba", "a": chave},
                            className="aba", n_clicks=0)
                for chave, (nome, ic) in ABAS.items()
            ], style={"display": "flex"}),
            html.Div(id="destaques-hero", className="resumo-abas"),
        ], className="barra-abas"),
        html.Div(id="painel"),
        html.Div("Dados fictícios para demonstração · IPR Blefaroplastia · TOU", className="rodape"),
    ], className="conteudo"),
], id="pagina", className="pagina")


@app.callback(Output("tv", "data"), Output("btn-tv", "className"), Output("btn-tv", "children"),
              Output("tick", "disabled"), Output("evento", "disabled"),
              Input("btn-tv", "n_clicks"), State("tv", "data"), prevent_initial_call=True)
def alternar_tv(_, tv):
    novo = not tv
    return (novo, ("pill tv ativo" if novo else "pill tv"),
            [icone("tv"), " Sair do modo TV" if novo else " Modo TV"],
            not novo, not novo)  # os relógios só rodam no modo TV (e reiniciam ao entrar)


@app.callback(Output("gaveta-wrap", "className"), Output("gaveta-conteudo", "children"),
              Input({"tipo": "detalhe", "k": ALL}, "n_clicks"),
              Input("gaveta-fechar", "n_clicks"), Input("gaveta-fundo", "n_clicks"),
              State("unidade", "data"), State("periodo", "start_date"), State("periodo", "end_date"),
              State("tema", "data"), prevent_initial_call=True)
def gaveta(_, __, ___, unidade, ini, fim, tema):
    gatilho = ctx.triggered_id
    if gatilho in ("gaveta-fechar", "gaveta-fundo"):
        return "gaveta-wrap", dash_no_update
    if not ctx.triggered or not ctx.triggered[0]["value"]:   # card recém-desenhado, sem clique
        return dash_no_update, dash_no_update
    chave = gatilho["k"].split("#")[0]          # "sem_data#vendedor" abre a mesma lista de "sem_data"
    return "gaveta-wrap aberta", recolorir(montar_gaveta(chave, unidade, ini, fim), tema)


@app.callback(Output("toast-area", "children"), Input("evento", "n_intervals"),
              Input("btn-simular", "n_clicks"),
              State("unidade", "data"), State("tema", "data"), State("tv", "data"),
              prevent_initial_call=True)
def celebrar(n, cliques, unidade, tema, tv):
    if ctx.triggered_id == "btn-simular":          # botão temporário de demonstração
        return recolorir(toast_contrato(unidade, 1000 + (cliques or 0)), tema)
    if not tv:
        return dash_no_update
    return recolorir(toast_contrato(unidade, n), tema)


@app.callback(Output("tv-estilo", "data"), Input({"tipo": "btn-estilo", "e": ALL}, "n_clicks"),
              prevent_initial_call=True)
def escolher_estilo(cliques):
    if not any(cliques):
        return dash_no_update
    return ctx.triggered_id["e"]


@app.callback(Output("pagina", "className"), Output({"tipo": "btn-estilo", "e": ALL}, "className"),
              Output("tick", "interval"),
              Input("tv", "data"), Input("tv-estilo", "data"))
def classe_pagina(tv, estilo):
    classe = "pagina" + (" modo-tv" if tv else "") + (" estilo-cards" if tv and estilo == "cards" else "")
    botoes = ["pill ativo" if e == estilo else "pill" for e in ("painel", "cards")]
    segundos = SEGUNDOS_CARD if estilo == "cards" else SEGUNDOS_TV
    return classe, botoes, segundos * 1000


@app.callback(Output("aba", "data"), Input({"tipo": "btn-aba", "a": ALL}, "n_clicks"),
              prevent_initial_call=True)
def escolher_aba(cliques):
    if not any(cliques):
        return dash_no_update
    return ctx.triggered_id["a"]


@app.callback(Output("tema", "data"), Input("btn-tema-toggle", "n_clicks"), State("tema", "data"),
              prevent_initial_call=True)
def escolher_tema(_, atual):
    chaves = list(TEMAS)
    atual = atual if atual in chaves else TEMA_PADRAO
    return chaves[(chaves.index(atual) + 1) % len(chaves)]


# Liga a folha de estilo do tema escolhido e marca o botão ativo (roda no navegador)
clientside_callback(
    """
    function(tema) {
        var existe = document.querySelector('style[data-tema="' + tema + '"]');
        if (!tema || !existe) { tema = "padrao"; }
        document.querySelectorAll("style[data-tema]").forEach(function(el) {
            el.media = (el.dataset.tema === tema) ? "all" : "not all";
        });
        return ["btn-ic tema-btn tema-" + tema, tema === "noite" ? "Mudar para o tema Padrão" : "Mudar para o tema Noite"];
    }
    """,
    Output("btn-tema-toggle", "className"), Output("btn-tema-toggle", "title"),
    Input("tema", "data"),
)


# Tela cheia: roda no navegador (não precisa do Python)
clientside_callback(
    """
    function(n) {
        if (!n) return window.dash_clientside.no_update;
        if (!document.fullscreenElement) {
            document.documentElement.requestFullscreen().catch(() => {});
        } else {
            document.exitFullscreen();
        }
        return n;
    }
    """,
    Output("tela-cheia-dummy", "data"),
    Input("btn-tela-cheia", "n_clicks"),
)


@app.callback(Output("periodo", "start_date"), Output("periodo", "end_date"),
              Input({"tipo": "preset", "p": ALL}, "n_clicks"), prevent_initial_call=True)
def atalho_periodo(cliques):
    if not any(cliques):
        return dash_no_update, dash_no_update
    h = date.today()
    ini_mes = h.replace(day=1)
    fim_mes_ = (ini_mes + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    k = ctx.triggered_id["p"]
    if k == "hoje":
        return h, h
    if k == "7d":
        return h - timedelta(days=6), h
    if k == "mes_ant":
        f = ini_mes - timedelta(days=1)
        return f.replace(day=1), f
    if k == "ano":
        return h.replace(month=1, day=1), h.replace(month=12, day=31)
    return ini_mes, fim_mes_


@app.callback(Output("unidade", "data"), Output("cena", "data"),
              Input({"tipo": "btn-unidade", "u": ALL}, "n_clicks"), Input("tick", "n_intervals"),
              Input("btn-cena-ant", "n_clicks"), Input("btn-cena-prox", "n_clicks"),
              Input("tv-estilo", "data"),
              State("unidade", "data"), State("cena", "data"), State("tv", "data"),
              prevent_initial_call=True)
def navegar(_, __, ___, ____, estilo, atual, cena, tv):
    gatilho = ctx.triggered_id
    proxima_unidade = UNIDADES[(UNIDADES.index(atual) + 1) % len(UNIDADES)]
    if gatilho == "tv-estilo":
        return atual, 0
    if gatilho == "btn-cena-prox":
        return atual, (cena + 1) % len(CENAS)
    if gatilho == "btn-cena-ant":
        return atual, (cena - 1) % len(CENAS)
    if gatilho == "tick":
        if not tv:
            return atual, cena
        if estilo == "cards":                        # card por card: avança o card;
            if cena + 1 >= len(CENAS):               # no fim dos cards, passa para a próxima unidade
                return proxima_unidade, 0
            return atual, cena + 1
        return proxima_unidade, 0
    return gatilho["u"], 0


def chips_hero(d):
    """Destaques discretos à direita da linha das abas."""
    contratos = dict(d["funil"])["Contratos"]
    return [html.Span([html.B(brl_curto(d["faturamento"])), " faturados"]),
            html.Span([html.B(num_br(contratos)), " contratos"]),
            html.Span([html.B(num_br(d["sem_data"])), " sem data de cirurgia"], className="aviso")]


def rotulo_periodo(ini, fim):
    i, f = periodo_datas(ini, fim)
    ultimo = (i.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    if i.day == 1 and f == ultimo:
        return f"{MESES_LONGO[i.month - 1].capitalize()} {i.year}"
    if i == f:
        return f"{i:%d/%m/%Y}"
    if i.month == 1 and i.day == 1 and f.month == 12 and f.day == 31 and i.year == f.year:
        return f"Ano de {i.year}"
    return f"{i:%d/%m} – {f:%d/%m/%Y}"


def lista_alertas(d):
    if not d["alertas"]:
        return [html.Div("Alertas", className="menu-rot"),
                html.Div([icone("certo", SUCESSO), " Nenhum indicador fora do normal"], className="legenda",
                         style={"padding": "6px 4px"})]
    itens = [html.Div(f"{len(d['alertas'])} alerta{'s' if len(d['alertas']) > 1 else ''} fora do normal",
                      className="menu-rot")]
    for chave, msg in d["alertas"].items():
        nome = next((r[4] for r in REGRAS_ALERTA if r[0] == chave), chave)
        itens.append(html.Div([icone("alerta", VERMELHO), html.Div([html.B(nome), html.Div(msg, className="legenda")])],
                              className="alerta-item"))
    return itens


def tv_info(unidade, estilo="painel", cena=0):
    """Faixa que aparece no topo só no modo TV: unidade atual + barra do tempo até a próxima troca."""
    proxima = UNIDADES[(UNIDADES.index(unidade) + 1) % len(UNIDADES)]
    segundos = SEGUNDOS_TV
    texto_prox = f"próxima: IPR {proxima}"
    if estilo == "cards":
        i = cena % len(CENAS)
        segundos = SEGUNDOS_CARD
        seguinte = CENAS[(i + 1) % len(CENAS)][1] if i + 1 < len(CENAS) else f"IPR {proxima}"
        texto_prox = f"card {i + 1}/{len(CENAS)} · {CENAS[i][1]} · próximo: {seguinte}"
    return [
        html.Div(html.Div([html.Span() for _ in range(4)], className="icone-grade"),
                 className="titulo-icone mini"),
        html.Div([
            html.Div([html.B(TITULO), html.Span(" · ", style={"color": TEXTO_TER}),
                      html.Span(f"IPR {unidade}", className="tv-unidade")]),
            html.Div([html.Span(texto_prox, className="legenda"),
                      html.Div(html.Div(className="tv-progresso-fill",
                                        style={"animationDuration": f"{segundos}s"}),
                               className="tv-progresso")],
                     style={"display": "flex", "alignItems": "center", "gap": "10px"}),
        ]),
    ]


@app.callback(
    Output("painel", "children"), Output("relogio", "children"),
    Output("destaques-hero", "children"), Output("tv-info", "children"), Output("ticker", "children"),
    Output("unidade-rotulo", "children"), Output("periodo-rotulo", "children"), Output("meta-pilula", "children"),
    Output("meta-linha", "style"), Output("alertas-lista", "children"), Output("alertas-badge", "children"),
    Output("alertas-badge", "style"),
    Output({"tipo": "btn-unidade", "u": ALL}, "className"),
    Output({"tipo": "btn-aba", "a": ALL}, "className"),
    Input("unidade", "data"), Input("periodo", "start_date"), Input("periodo", "end_date"),
    Input("tema", "data"), Input("aba", "data"), Input("cena", "data"),
    Input("tv", "data"), Input("tv-estilo", "data"))
def atualizar(unidade, ini, fim, tema, aba, cena, tv, estilo):
    agora = datetime.now()
    d = carregar_dados(unidade, ini, fim)
    classes = ["opt ativo" if u == unidade else "opt" for u in UNIDADES]
    frac = d["faturamento"] / d["meta"]
    meta = [html.Span(className="anel-mini", style={"--p": f"{min(frac, 1) * 100:.1f}"}),
            html.Span([html.B(pct(frac)), " da meta"])]
    n_al = len(d["alertas"])
    classes_abas = ["aba ativa" if a == aba else "aba" for a in ABAS]
    if tv and estilo == "cards":
        corpo = montar_cena(unidade, ini, fim, cena or 0)
    else:
        corpo = montar_painel(unidade, ini, fim, aba)
    return (recolorir(corpo, tema),
            f"ao vivo · {agora:%H:%M}",
            recolorir(chips_hero(d), tema), recolorir(tv_info(unidade, estilo if tv else "painel", cena or 0), tema),
            recolorir(montar_ticker(unidade, ini, fim), tema) if tv else [],
            f"IPR {unidade}", rotulo_periodo(ini, fim), meta,
            {"width": f"{min(frac, 1) * 100:.2f}%"},
            recolorir(lista_alertas(d), tema), str(n_al) if n_al else "",
            {"display": "flex" if n_al else "none"},
            classes, classes_abas)


@app.callback(Output("sim-resultado", "children"), Output("sim-consult-valor", "children"),
              Output("sim-orc-valor", "children"), Output("sim-ticket-valor", "children"),
              Input("sim-consult", "value"), Input("sim-orc", "value"), Input("sim-ticket", "value"),
              State("unidade", "data"), State("periodo", "start_date"), State("periodo", "end_date"),
              State("tema", "data"))
def simular(consult, orc, ticket, unidade, ini, fim, tema):
    if consult is None:
        return dash_no_update, dash_no_update, dash_no_update, dash_no_update
    a = carregar_analises(unidade, ini, fim)
    return (recolorir(resultado_simulacao(a, consult, orc, ticket or 0), tema),
            f"{consult}%", f"{orc}%", f"{'+' if (ticket or 0) > 0 else ''}{ticket or 0}%")


# ===========================================================================
# ESTILO + ANIMAÇÕES
# ===========================================================================
CSS = f"""
:root {{ color-scheme: dark; --acc:{VERDE}; --texto-sec:{TEXTO_SEC}; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:{BG}; color:{TEXTO}; font-family:Inter,'Segoe UI',sans-serif; }}
.pagina {{ min-height:100vh;
  background: radial-gradient(1400px 600px at 0% -10%, #12301f 0%, transparent 60%),
              radial-gradient(1000px 500px at 100% 0%, #0f2219 0%, transparent 55%), {BG}; }}
html, body, #react-entry-point, #_dash-app-content {{ width:100% !important; max-width:none !important; margin:0 !important; padding:0 !important; }}
.conteudo {{ padding:18px 16px 14px; }}
@keyframes gira {{ to {{ transform: rotate(360deg); }} }}
@keyframes flutua {{ 50% {{ transform: translateY(-5px); }} }}

/* ---------- barra do topo com o caminho ---------- */
.barra-topo {{ position:sticky; top:0; z-index:50; display:flex; justify-content:space-between; align-items:center;
  gap:16px; padding:10px 16px; background:{BG}cc; backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
  border-bottom:1px solid {BORDA}; flex-wrap:wrap; }}
.logo-selo {{ width:38px; height:38px; border-radius:11px; display:flex; align-items:center; justify-content:center;
  font-weight:900; font-size:13px; letter-spacing:.5px; color:{BG};
  background: linear-gradient(135deg, {VERDE_CLARO}, {VERDE} 50%, {VERDE_ESC}); box-shadow:0 0 18px {VERDE}55; }}
.logo-img {{ height:30px; width:auto; display:block; filter: drop-shadow(0 0 10px #d80e8433); }}
.logo-divisor {{ width:1px; height:26px; background:{BORDA}; }}
.migalhas {{ display:flex; align-items:center; flex-wrap:wrap; font-size:13px; }}
.migalha {{ color:{TEXTO_SEC}; padding:5px 8px; border-radius:4px; cursor:default; transition:all .2s; }}
.migalha:hover {{ background:{PANEL2}; color:{TEXTO}; }}
.migalha.atual {{ color:{VERDE}; font-weight:700; background:{VERDE}14; border:1px solid {VERDE}33; }}
.migalhas .ic {{ margin-right:2px; }}
.migalha-sep {{ color:{TEXTO_TER}; margin:0 2px; }}

/* ---------- modo TV ---------- */
.tv-info {{ display:none; align-items:center; gap:12px; }}
.modo-tv .tv-info {{ display:flex; }}
.modo-tv .migalhas, .modo-tv .hero {{ display:none; }}
.modo-tv .conteudo {{ padding-top:14px; }}
.titulo-icone.mini {{ width:34px; height:34px; border-radius:6px; }}
.titulo-icone.mini .icone-grade {{ width:16px; height:16px; gap:3px; }}
.titulo-icone.mini .icone-grade span {{ border-radius:2px; }}
.tv-info b {{ font-size:15px; }}
.tv-unidade {{ color:{VERDE}; font-weight:800; font-size:15px; }}
.tv-progresso {{ width:140px; height:4px; border-radius:4px; background:{BORDA}; overflow:hidden; }}
.tv-progresso-fill {{ height:100%; width:100%; background:{VERDE}; transform-origin:left;
  animation-name: tvbarra; animation-timing-function: linear; animation-fill-mode: both; }}
@keyframes tvbarra {{ from {{ transform:scaleX(0); }} to {{ transform:scaleX(1); }} }}
.tv-progresso {{ width:180px; }}
.tv-estilo, .tv-nav {{ display:none !important; }}
.modo-tv .tv-estilo {{ display:flex !important; }}
.modo-tv.estilo-cards .tv-nav {{ display:flex !important; gap:4px; }}
.nav-cena {{ border:1px solid {BORDA} !important; font-size:18px !important; line-height:1; padding:4px 12px !important; }}
.modo-tv.estilo-cards .rodape {{ display:none; }}

/* comparação com o período anterior */
.delta {{ font-size:12px; font-weight:700; padding:2px 7px; border-radius:3px; }}
.delta.bom {{ color:{SUCESSO}; background:{SUCESSO}1f; }}
.delta.ruim {{ color:{VERMELHO}; background:{VERMELHO}1a; }}
.delta-linha {{ display:inline-flex; align-items:center; gap:5px; margin-top:6px; white-space:nowrap; cursor:help; align-self:flex-start; }}
.delta.pulsa {{ animation: pisca 1.6s ease-in-out infinite; }}
.delta.neutro {{ color:{TEXTO_SEC}; background:{BORDA}; font-size:11px; font-weight:700; padding:2px 7px; border-radius:6px; }}
.funil-linha {{ grid-template-columns: 150px 1fr 40px 86px !important; }}
.funil-nome {{ white-space:nowrap; }}
.funil-conv-cel {{ display:flex; justify-content:flex-start; }}
.funil-linha.com-conv .funil-trilho {{ box-shadow: inset 0 0 0 1px {BORDA}; }}
.funil-conv {{ margin:-3px 0 3px 160px; }}
@media (max-width:760px) {{ .funil-conv {{ margin-left:0; }} }}
.conv-funil {{ display:inline-flex; align-items:center; gap:5px; padding:2px 9px 2px 7px; border-radius:3px; cursor:help;
  border-left:3px solid var(--cor); background: color-mix(in srgb, var(--cor) 10%, transparent); color:var(--cor);
  transition: background .2s; }}
.conv-funil:hover {{ background: color-mix(in srgb, var(--cor) 20%, transparent); }}
.conv-seta-funil {{ font-weight:900; font-size:14px; line-height:1; }}
.conv-taxa {{ font-weight:800; font-size:15px; font-variant-numeric:tabular-nums; color:var(--cor); }}
.conv-rotulo {{ font-size:12px; color:{TEXTO}; font-weight:600; }}
.conv-trilho {{ flex:1 1 60px; min-width:60px; margin-top:0 !important; height:4px !important; }}
.funil-linha .delta-linha {{ margin-top:0; }}
.funil-linha .delta {{ font-size:10.5px; padding:1px 5px; }}
.card.mini .delta {{ font-size:10.5px; }}

/* ⓘ como é calculado */
.info {{ color:{TEXTO_TER}; cursor:help; display:inline-flex; font-size:13px; transition:color .2s; }}
.info:hover {{ color:{VERDE}; }}
.balao-info {{ position:fixed; z-index:400; max-width:320px; padding:12px 14px; border-radius:6px; pointer-events:none;
  background:{PANEL}; border:1px solid {VERDE}; box-shadow:0 14px 40px #0006; font-size:12.5px; line-height:1.45;
  color:{TEXTO}; opacity:0; transform:translateY(4px); transition: opacity .15s, transform .15s; }}
.balao-info.visivel {{ opacity:1; transform:none; }}
.balao-info b {{ display:block; font-size:13px; margin-bottom:4px; color:{VERDE}; }}
.balao-info .calc {{ margin-top:6px; color:{TEXTO_SEC}; }}
.balao-info .fonte {{ margin-top:6px; font-size:11px; color:{TEXTO_TER}; font-family:ui-monospace, Consolas, monospace; }}

/* alertas inteligentes */
.card.alerta-pulsa {{ border-color:{VERMELHO}88 !important; animation: pulsa-card 2.2s ease-in-out infinite; }}
@keyframes pulsa-card {{ 0%,100% {{ box-shadow:0 0 0 0 {VERMELHO}00; }} 50% {{ box-shadow:0 0 0 5px {VERMELHO}26; }} }}
.faixa-alerta {{ display:flex; align-items:center; gap:5px; margin-top:8px; padding:5px 8px; border-radius:3px;
  font-size:11.5px; font-weight:600; color:{VERMELHO}; background:{VERMELHO}14; line-height:1.3; }}

/* botão temporário de simulação */
.pill.demo {{ border:1px dashed {VERDE} !important; color:{VERDE} !important; }}
.pill.demo:hover {{ background:{VERDE}14; }}

/* bullet chart + barra segmentada (Modo TV) */
.ind-topo {{ display:flex; align-items:baseline; gap:10px; }}
.ind-topo .num {{ color:inherit; margin:0; }}
.ind-topo .delta-linha {{ margin-top:0; }}
.ind-faixas {{ margin-top:2px; }}
.bul {{ position:relative; height:26px; }}
.bul-fundo {{ position:absolute; inset:0; display:flex; border-radius:3px; overflow:hidden; }}
.bul-fundo span {{ height:100%; }}
.bul-valor {{ position:absolute; left:0; top:8px; height:10px; border-radius:2px; background:{TEXTO};
  transform-origin:left; animation: cresce 1.2s cubic-bezier(.2,.8,.2,1) both; }}
.bul-valor::after {{ content:''; position:absolute; right:-1px; top:-3px; width:4px; height:16px; border-radius:2px; background:var(--cor); }}
.bul-meta {{ position:absolute; top:1px; width:3px; height:24px; margin-left:-1.5px; background:{TEXTO}; border-radius:1px; cursor:help; }}
.bul-anterior {{ position:absolute; top:5px; width:2px; height:16px; margin-left:-1px; background:{TEXTO_SEC}; opacity:.75; cursor:help; }}
.bul-escala {{ display:flex; justify-content:space-between; font-size:10.5px; color:{TEXTO_TER}; margin-top:4px; font-variant-numeric:tabular-nums; }}
.bul-legenda {{ display:flex; gap:12px; font-size:11px; color:{TEXTO_SEC}; margin-top:6px; }}
.bul-legenda i {{ display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:4px; vertical-align:-1px; }}
.bul-legenda .leg-ant {{ width:2px; background:{TEXTO_SEC}; }}
.bul-legenda .leg-meta {{ width:3px; background:{TEXTO}; }}
.seg-tv {{ display:none; }}
.modo-tv .seg-tv {{ display:block; }}
.modo-tv .bul-normal {{ display:none; }}
.seg-seta-wrap {{ position:relative; height:30px; }}
.seg-seta {{ position:absolute; transform:translateX(-50%); display:flex; flex-direction:column; align-items:center;
  font-weight:800; font-size:15px; color:var(--cor); white-space:nowrap; animation: aparece .6s .4s both; }}
.seg-seta::after {{ content:''; border:7px solid transparent; border-top-color:var(--cor); margin-top:1px; }}
.seg-barra {{ display:flex; gap:3px; height:26px; }}
.seg-barra div {{ border-radius:2px; color:#fff; font-size:11.5px; font-weight:700; display:flex; align-items:center;
  justify-content:center; overflow:hidden; white-space:nowrap; }}

/* aba análises */
.analises .secao {{ margin-bottom:0; }}
.grid-analises {{ display:grid; gap:16px; margin:22px 0 0; align-items:stretch; }}
.grid-analises > .secao {{ min-width:0; }}
.grid-analises > .secao > .card {{ flex:1; }}
.grid-analises.a {{ grid-template-columns: 1.6fr 1fr; }}
.grid-analises.b {{ grid-template-columns: 1.15fr 1fr; }}
.grid-analises.c {{ grid-template-columns: 1.3fr 1fr; }}
@media (max-width:1100px) {{ .grid-analises.a, .grid-analises.b, .grid-analises.c {{ grid-template-columns:1fr; }} }}
.insight {{ font-size:14px; color:{TEXTO}; padding:9px 12px; border-radius:4px; background:{BG}88;
  border:1px solid {BORDA}; margin-bottom:10px; }}
.cmp-tabela {{ display:flex; flex-direction:column; overflow-x:auto; }}
.cmp-linha {{ display:grid; grid-template-columns: 230px repeat(3, minmax(150px, 1fr)); align-items:center; }}
.cmp-linha + .cmp-linha {{ border-top:1px solid {BORDA}; }}
.cmp-rotulo {{ color:{TEXTO_SEC}; font-size:13px; padding:9px 8px 9px 0; }}
.cmp-topo .cmp-rotulo {{ font-size:11px; text-transform:uppercase; letter-spacing:.6px; }}
.cmp-cab {{ font-weight:800; font-size:15px; padding:10px 14px; display:flex; gap:8px; align-items:center; }}
.cmp-pos {{ font-size:13px; font-weight:900; }}
.cmp-cel {{ padding:8px 14px; }}
.cmp-cab.atual, .cmp-cel.atual {{ background:{VERDE}12; }}
.cmp-cab.atual {{ border-radius:4px 4px 0 0; color:{VERDE}; }}
.cmp-valor {{ display:flex; align-items:center; gap:6px; font-weight:700; font-size:15px; font-variant-numeric:tabular-nums; }}
.cmp-cel .trilho {{ margin-top:5px; }}
.sim-controle {{ padding:10px 0; border-top:1px solid {BORDA}; }}
.sim-valor {{ font-weight:800; color:{VERDE}; font-size:15px; }}
.sim-slider {{ margin:6px 0 2px; }}
.sim-resultado {{ display:grid; grid-template-columns:1fr auto 1fr; gap:10px; align-items:center; margin-top:12px; }}
.sim-seta {{ color:{TEXTO_TER}; font-size:20px; }}
.stat.destaque-sim {{ border-color:{VERDE}; background:{VERDE}10; }}
.mapa-wrap {{ display:grid; grid-template-columns: auto 1fr; gap:20px; align-items:center; }}
@media (max-width:760px) {{ .mapa-wrap {{ grid-template-columns:1fr; }} }}
.mapa-uf {{ display:grid; grid-template-columns:repeat(7, 42px); grid-template-rows:repeat(8, 38px); gap:4px; }}
.uf {{ border-radius:3px; display:flex; flex-direction:column; align-items:center; justify-content:center;
  font-size:10px; line-height:1.1; cursor:default; transition: transform .15s; animation: aparece .5s both; }}
.uf b {{ font-size:11px; }}
.uf:hover {{ transform:scale(1.12); }}
.ddd-lista {{ display:flex; flex-direction:column; gap:9px; }}
.ddd-linha {{ display:flex; align-items:center; gap:10px; }}
.ddd-nome {{ width:150px; font-size:12.5px; color:{TEXTO_SEC}; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.ddd-num {{ width:52px; text-align:right; font-variant-numeric:tabular-nums; }}
.coorte-linha {{ display:grid; grid-template-columns: 80px 70px repeat(3, 1fr); gap:5px; margin-bottom:5px; align-items:center; }}
.coorte-linha.topo {{ color:{TEXTO_SEC}; font-size:11px; text-transform:uppercase; letter-spacing:.5px; }}
.coorte-sem {{ font-weight:700; font-size:13px; }}
.coorte-leads {{ color:{TEXTO_SEC}; font-size:13px; font-variant-numeric:tabular-nums; }}
.coorte-cab {{ text-align:center; }}
.coorte-cel {{ text-align:center; padding:7px 4px; border-radius:3px; font-size:12.5px; font-weight:700; font-variant-numeric:tabular-nums; }}
.coorte-cel.vazia {{ color:{TEXTO_TER}; background:{BORDA}55; font-weight:400; }}
.saude-linha {{ display:flex; align-items:center; gap:12px; padding:10px 12px; border-radius:4px; background:{BG}88; border:1px solid {BORDA}; }}
.saude-ponto {{ width:10px; height:10px; border-radius:50%; flex-shrink:0; box-shadow:0 0 0 4px {BORDA}; }}

/* slider (Dash 4) nas cores do tema */
.sim-slider > input {{ display:none !important; }}
.sim-slider .dash-slider-track {{ background:{BORDA} !important; height:6px !important; }}
.sim-slider .dash-slider-range {{ background:{VERDE} !important; }}
.sim-slider .dash-slider-thumb {{ background:{PANEL} !important; border:3px solid {VERDE} !important; box-shadow:0 0 0 4px {VERDE}26 !important; }}
.sim-slider .dash-slider-tooltip {{ background:{PANEL2} !important; color:{TEXTO} !important; border:1px solid {VERDE} !important; }}

/* ticker do Modo TV */
.ticker {{ display:none; }}
.modo-tv .ticker {{ display:flex; position:fixed; left:0; right:0; bottom:0; z-index:150; height:48px; align-items:center;
  background:{PANEL}f2; border-top:1px solid {VERDE}; backdrop-filter: blur(10px); overflow:hidden; }}
.modo-tv .conteudo {{ padding-bottom:64px; }}
.ticker-selo {{ flex-shrink:0; height:100%; display:flex; align-items:center; padding:0 18px; font-weight:900; font-size:12px;
  letter-spacing:2px; color:{PANEL}; background:{VERDE}; }}
.ticker-janela {{ flex:1; overflow:hidden; -webkit-mask: linear-gradient(90deg, transparent, #000 4%, #000 96%, transparent);
  mask: linear-gradient(90deg, transparent, #000 4%, #000 96%, transparent); }}
.ticker-trilha {{ display:inline-flex; white-space:nowrap; animation: rola linear infinite; }}
@keyframes rola {{ from {{ transform:translateX(0); }} to {{ transform:translateX(-50%); }} }}
.ticker-item {{ display:inline-flex; align-items:center; gap:8px; padding:0 4px; font-size:15px; }}
.ticker-sub {{ color:{TEXTO_SEC}; font-size:13px; }}
.ticker-sep {{ color:{TEXTO_TER}; margin:0 18px; }}

/* cards clicáveis */
.card.clicavel {{ cursor:pointer; }}
.ver-detalhes {{ position:absolute; right:14px; bottom:10px; display:flex; align-items:center; gap:2px;
  font-size:11px; font-weight:600; color:{VERDE}; opacity:0; transform:translateX(-4px); transition: all .2s; }}
.card.clicavel:hover .ver-detalhes {{ opacity:1; transform:none; }}
.card.clicavel:hover {{ border-color:{VERDE} !important; box-shadow:0 8px 30px {VERDE}22; }}
.modo-tv .ver-detalhes {{ display:none; }}

/* gaveta lateral */
.gaveta-wrap {{ position:fixed; inset:0; z-index:200; pointer-events:none; }}
.gaveta-fundo {{ position:absolute; inset:0; background:#0007; opacity:0; transition:opacity .3s; backdrop-filter: blur(2px); }}
.gaveta {{ position:absolute; top:0; right:0; height:100%; width:min(560px, 100%); overflow-y:auto;
  background:{PANEL}; border-left:1px solid {BORDA}; box-shadow:-20px 0 60px #0006; padding:26px 26px 30px;
  transform:translateX(102%); transition: transform .35s cubic-bezier(.2,.8,.2,1); }}
.gaveta-wrap.aberta {{ pointer-events:auto; }}
.gaveta-wrap.aberta .gaveta-fundo {{ opacity:1; }}
.gaveta-wrap.aberta .gaveta {{ transform:none; }}
.gaveta-x {{ position:absolute; top:18px; right:18px; width:36px; height:36px; border-radius:4px; cursor:pointer;
  background:{PANEL2}; border:1px solid {BORDA}; color:{TEXTO_SEC}; font-size:16px; display:flex; align-items:center; justify-content:center; }}
.gaveta-x:hover {{ color:{TEXTO}; border-color:{VERDE}; }}
.gaveta-cab {{ display:flex; align-items:center; gap:14px; margin:0 44px 20px 0; }}
.gaveta-icone {{ width:46px; height:46px; border-radius:6px; display:flex; align-items:center; justify-content:center;
  font-size:22px; background:currentColor; }}
.gaveta-icone .ic {{ color:{PANEL}; }}
.gaveta-titulo {{ font-size:20px; font-weight:800; letter-spacing:-.3px; }}
.gaveta .grid-3 {{ margin-bottom:18px; }}
.gaveta-lista {{ display:flex; flex-direction:column; gap:8px; }}
.gaveta-linha {{ display:flex; align-items:center; gap:12px; padding:12px 14px; border-radius:4px;
  background:{PANEL2}; border:1px solid {BORDA}; animation: entra-dir .4s both; }}
@keyframes entra-dir {{ from {{ opacity:0; transform:translateX(16px); }} }}
.ranking-pos {{ font-size:18px; font-weight:900; width:30px; text-align:center; }}
.gaveta-dica {{ margin-top:16px; padding:10px 12px; border-radius:4px; border:1px dashed {BORDA}; }}

/* celebração do Modo TV */
.toast-area {{ position:fixed; right:28px; bottom:28px; z-index:300; pointer-events:none; }}
.toast-contrato {{ display:flex; align-items:center; gap:18px; padding:18px 26px 18px 18px; border-radius:8px;
  background:{PANEL}; border:1px solid {VERDE}; box-shadow:0 20px 60px #0008, 0 0 40px {VERDE}44;
  animation: toast-vida 8s cubic-bezier(.2,.8,.2,1) both; }}
@keyframes toast-vida {{ 0% {{ opacity:0; transform:translateY(40px) scale(.9); }}
  8% {{ opacity:1; transform:none; }} 88% {{ opacity:1; transform:none; }}
  100% {{ opacity:0; transform:translateY(20px) scale(.96); }} }}
.toast-selo {{ position:absolute; right:-6px; bottom:-6px; width:28px; height:28px; border-radius:50%;
  background:{VERDE}; color:{PANEL}; display:flex; align-items:center; justify-content:center; font-size:15px; }}
.toast-sobre {{ color:{VERDE}; font-size:11px; font-weight:800; letter-spacing:2.5px; }}
.toast-nome {{ font-size:24px; font-weight:800; letter-spacing:-.4px; }}
.toast-texto {{ font-size:15px; color:{TEXTO}; }}
.confete {{ position:fixed; top:-12px; width:10px; height:14px; border-radius:2px; z-index:250; pointer-events:none;
  animation: confete-cai linear forwards; }}
@keyframes confete-cai {{ to {{ transform: translateY(110vh) rotate(720deg); }} }}

/* palco do card por card */
.palco {{ display:flex; flex-direction:column; justify-content:center; min-height:calc(100vh - 92px);
  animation: cena-entra .7s cubic-bezier(.2,.8,.2,1) both; }}
@keyframes cena-entra {{ from {{ opacity:0; transform: translateY(18px) scale(.985); }} }}
.palco-conteudo {{ zoom: var(--z); width:100%; }}
.palco .secao {{ display:grid; grid-template-columns:repeat(var(--cols), minmax(0, 1fr)); gap:20px; align-items:stretch; }}
.palco .secao > .titulo-secao {{ grid-column:1 / -1; font-size:18px; }}
.palco .grid-jornada, .palco .grid-briefing {{ margin-bottom:0; }}
.cena-podio .card {{ max-width:760px; width:100%; margin:0 auto; }}
.cena-podio .secao {{ justify-items:center; }}
.cena-podio .secao > .titulo-secao {{ justify-self:start; }}
.cena-captacao .card.cresce {{ min-height:260px; }}
.cena-pontos {{ display:flex; justify-content:center; gap:8px; margin-top:22px; }}
.cena-ponto {{ width:8px; height:8px; border-radius:999px; background:{BORDA}; transition: all .3s; }}
.cena-ponto.ativo {{ width:28px; background:{VERDE}; box-shadow:0 0 10px {VERDE}88; }}

/* ---------- hero ---------- */
.hero {{ position:relative; display:flex; justify-content:space-between; align-items:center; gap:28px;
  flex-wrap:wrap; padding:14px 20px; margin-bottom:16px; border-radius:8px; overflow:hidden;
  border:1px solid {VERDE_ESC}; background: linear-gradient(115deg, #10301f 0%, {PANEL} 50%, #0b1410 100%); }}
.hero-grade {{ position:absolute; inset:0; pointer-events:none; opacity:.35;
  background-image: linear-gradient({BORDA} 1px, transparent 1px), linear-gradient(90deg, {BORDA} 1px, transparent 1px);
  background-size: 36px 36px;
  -webkit-mask: radial-gradient(ellipse at 70% 50%, #000 0%, transparent 70%);
  mask: radial-gradient(ellipse at 70% 50%, #000 0%, transparent 70%); }}
.hero-brilho {{ position:absolute; inset:-60%; pointer-events:none;
  background: conic-gradient(from 0deg, transparent 0 72%, {VERDE}1f 80%, transparent 88%);
  animation: gira 12s linear infinite; }}
.hero-texto {{ position:relative; display:flex; align-items:center; gap:16px; }}
.hero-sobre {{ color:{VERDE}; font-size:10px; font-weight:700; letter-spacing:2px; display:flex; align-items:center; gap:5px; }}
.hero-titulo {{ margin:0; font-size:26px; line-height:1.1; font-weight:800; letter-spacing:-.6px; color:{TEXTO}; }}
.titulo-linha-x {{ height:3px; width:0; margin-top:8px; border-radius:3px;
  background: linear-gradient(90deg, {VERDE}, {VERDE}00); animation: risca 1.2s .2s cubic-bezier(.2,.8,.2,1) forwards; }}
@keyframes risca {{ to {{ width:100%; }} }}
.titulo-icone {{ width:52px; height:52px; border-radius:8px; flex-shrink:0; display:flex; align-items:center; justify-content:center;
  background: linear-gradient(145deg, {VERDE}33, {VERDE}0d); border:1px solid {VERDE}55; box-shadow: 0 0 30px {VERDE}33, inset 0 0 20px {VERDE}1a; }}
.icone-grade {{ display:grid; grid-template-columns:1fr 1fr; gap:5px; width:28px; height:28px; }}
.icone-grade span {{ border-radius:4px; background:{VERDE}; animation: acende 2.4s ease-in-out infinite; }}
.icone-grade span:nth-child(2) {{ animation-delay:.3s; opacity:.7 }} .icone-grade span:nth-child(3) {{ animation-delay:.6s; opacity:.7 }}
.icone-grade span:nth-child(4) {{ animation-delay:.9s }}
@keyframes acende {{ 50% {{ opacity:.25; }} }}
.hero-sub {{ color:{TEXTO_SEC}; font-size:13px; margin-top:2px; }}
.hero-sub b {{ color:{TEXTO}; }}
.hero-chips {{ display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }}
.hero-chip {{ display:flex; align-items:center; gap:6px; padding:4px 10px; border-radius:999px; font-size:13px;
  color:{TEXTO_SEC}; background:{BG}99; border:1px solid {BORDA}; animation: aparece .5s both; }}
.hero-chip:nth-child(2) {{ animation-delay:.08s }} .hero-chip:nth-child(3) {{ animation-delay:.16s }} .hero-chip:nth-child(4) {{ animation-delay:.24s }}
.chip-icone {{ font-size:12px; }}
.cartao-gerente {{ position:relative; display:flex; align-items:center; gap:16px; padding:10px 20px 10px 12px;
  border-radius:6px; background: linear-gradient(135deg, {PANEL2}ee, {BG}cc); border:1px solid {BORDA};
  box-shadow: 0 20px 50px #0008; }}
.hero-video {{ position:relative; width:70px; height:70px; flex-shrink:0; animation: flutua 5s ease-in-out infinite; }}
.hero-anel {{ position:absolute; inset:-6px; border-radius:50%;
  background: conic-gradient({VERDE}, transparent 30%, {VERDE_CLARO} 50%, transparent 80%, {VERDE});
  -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 3px), #000 calc(100% - 2px));
  mask: radial-gradient(farthest-side, transparent calc(100% - 3px), #000 calc(100% - 2px));
  animation: gira 4s linear infinite; }}
.gerente-nome {{ font-size:19px; font-weight:800; margin:2px 0 0; letter-spacing:-.3px; }}
.aceno {{ display:inline-block; animation: aceno 2.4s ease-in-out infinite; transform-origin:70% 70%; }}
@keyframes aceno {{ 0%,60%,100% {{transform:rotate(0)}} 10%,30% {{transform:rotate(14deg)}} 20% {{transform:rotate(-8deg)}} }}

/* ---------- barra de filtros ---------- */
.barra-filtros {{ position:relative; display:flex; flex-direction:column; gap:6px; margin-left:auto; }}
.barra-filtros .filtro {{ justify-content:space-between; }}
@media (min-width:1200px) {{ .hero {{ flex-wrap:nowrap !important; }} .hero-texto {{ flex:1; min-width:0; }} }}
.filtro {{ display:flex; align-items:center; gap:8px; padding:5px 6px 5px 12px; border-radius:6px;
  background:{BG}aa; border:1px solid {BORDA}; }}

.filtro-rotulo {{ color:{TEXTO_SEC}; font-size:13px; font-weight:600; }}
.pills {{ display:flex; gap:4px; background:{BG}aa; border:1px solid {BORDA}; border-radius:999px; padding:4px; }}
.pill {{ display:inline-flex; align-items:center; gap:6px; background:transparent; color:{TEXTO_SEC}; border:1px solid transparent; border-radius:999px;
  padding:6px 14px; font:500 13px Inter; cursor:pointer; transition:all .2s; white-space:nowrap; }}
.pill:hover {{ color:{TEXTO}; }}
.pill.ativo {{ background:{VERDE}; color:{BG}; font-weight:700; }}
.pill.tv {{ border-color:{BORDA}; }}
.temas {{ align-items:center; padding:3px; }}
.tema-rotulo {{ color:{TEXTO_SEC}; font-size:12px; padding:0 6px 0 10px; }}
.temas .pill {{ padding:5px 12px; }}
.pill.ativo .tema-bolinha {{ box-shadow:0 0 0 2px rgba(255,255,255,.9); }}
.tema-bolinha {{ width:10px; height:10px; border-radius:50%; display:inline-block; box-shadow:0 0 0 2px {BG}, 0 0 0 3px {BORDA}; }}
.pill.tv.ativo {{ background:transparent; color:{VERDE}; border-color:{VERDE}; box-shadow:0 0 14px {VERDE}44; }}
.ponto-vivo {{ width:8px; height:8px; border-radius:50%; background:{VERDE}; animation: pulsa 1.8s infinite; }}
@keyframes pulsa {{ 0% {{ box-shadow:0 0 0 0 {VERDE}; }} 70% {{ box-shadow:0 0 0 8px transparent; }} }}

/* filtros de data (Dash 4) no tema escuro */
.dash-datepicker, [class*="dash-datepicker"] {{ background:{PANEL} !important; color:{TEXTO} !important; border-color:{VERDE_ESC} !important; }}
[class*="dash-datepicker"] input {{ color:{TEXTO} !important; background:transparent !important; }}
[class*="dash-datepicker-content"], [class*="dash-datepicker-calendar"] {{ background:{PANEL} !important; }}
[class*="dash-datepicker"] button, [class*="dash-datepicker"] td {{ color:{TEXTO} !important; }}
[class*="dash-datepicker"] th {{ color:{TEXTO_SEC} !important; }}
[class*="dash-datepicker"] [aria-selected="true"], [class*="dash-datepicker"] [class*="selected"] {{ background:{VERDE} !important; color:{BG} !important; }}
[class*="dash-datepicker"] [class*="in-range"] {{ background:{VERDE_ESC} !important; }}

/* ---------- grade principal ---------- */
.grid-colunas {{ display:grid; grid-template-columns: .82fr 1.02fr 1.25fr 1.02fr; gap:16px; align-items:start; }}
@media (max-width:1400px) {{ .grid-colunas {{ grid-template-columns: 1fr 1fr; }} }}
@media (max-width:760px) {{ .grid-colunas {{ grid-template-columns: 1fr; }} .conteudo {{ padding:14px; }}
  .barra-topo {{ padding:10px 14px; }} .hero {{ padding:22px 18px; }} .hero-titulo {{ font-size:22px; }} .titulo-icone {{ width:44px; height:44px; }}
  .cartao-gerente {{ width:100%; }} .filtro {{ flex-wrap:wrap; width:100%; }} .pill {{ padding:7px 11px; font-size:12px; }} .hero-video {{ width:84px; height:84px; }}
  .hero-video video, .hero-video img, .hero-video > div:last-child {{ width:84px !important; height:84px !important; }} }}
.col {{ display:flex; flex-direction:column; gap:16px; min-width:0; }}
/* alinhamento: todas as colunas terminam na mesma linha; o último bloco de cada uma estica */
.grid-colunas {{ align-items:stretch !important; }}
.col > .secao:last-child {{ flex:1; }}
.col > .secao:last-child > :last-child {{ flex:1; }}
.card {{ display:flex; flex-direction:column; }}
.grid-agenda {{ grid-template-rows:auto auto 1fr; }}
.grid-agenda > .card:last-child {{ justify-content:center; }}
.gauge-box {{ flex:1; justify-content:center; }}
.col .secao > .card:last-child .podio {{ flex:1; }}
.card.cresce {{ min-height:120px; }}
.secao.igual > .card {{ flex:1; }}
.secao.cc > .card {{ flex:0 0 auto; }}
.col > .secao.cc:last-child > .semana-card {{ flex:1; }}
.col > .secao.captacao {{ flex:1; }}
.col > .secao.captacao > .card.cresce {{ flex:1; }}
.col > .secao.igual:last-child {{ flex:0 0 auto; }}
.col > .secao.igual:last-child > .card {{ flex:0 0 auto; }}
.semana-card {{ min-height:150px; }}
.semana-barras {{ flex:1; display:flex; gap:8px; align-items:stretch; min-height:90px; }}
.semana-col {{ flex:1; display:flex; flex-direction:column; align-items:center; gap:4px; }}
.semana-valor {{ font-size:11.5px; font-weight:700; color:{TEXTO}; font-variant-numeric:tabular-nums; }}
.semana-trilho {{ flex:1; width:100%; max-width:46px; display:flex; align-items:flex-end;
  background:{BORDA}66; border-radius:3px; overflow:hidden; }}
.semana-fill {{ width:100%; border-radius:3px 3px 0 0; transform-origin:bottom; animation: sobe .9s cubic-bezier(.2,.8,.2,1) both; }}
.semana-dia {{ font-size:11px; color:{TEXTO_SEC}; text-transform:uppercase; letter-spacing:.5px; }}
.semana-dia.destaque {{ color:{TEXTO}; font-weight:800; }}
.gauge-box.grande {{ padding-top:34px !important; }}
.grid-3 .num.grande {{ font-size:clamp(20px, 1.55vw, 28px) !important; }}
.grafico-flex {{ flex:1; min-height:70px; }}
.secao {{ display:flex; flex-direction:column; gap:12px; }}
.secao.largura-total {{ margin-top:26px; }}
.titulo-secao {{ font-size:15px; font-weight:800; letter-spacing:2px; text-transform:uppercase; padding:2px 0 4px; }}
.titulo-secao::before {{ content:''; display:inline-block; width:10px; height:10px; border-radius:3px;
  background:{VERDE}; margin-right:10px; box-shadow:0 0 10px {VERDE}; }}
.titulo-secao.sub {{ margin-top:10px; font-size:13px; color:{TEXTO_SEC}; }}
.titulo-secao.sub::before {{ background:{AMBAR}; box-shadow:0 0 10px {AMBAR}; }}

.card {{ background:linear-gradient(180deg, {PANEL2} 0%, {PANEL} 100%); border:1px solid {BORDA};
  border-radius:6px; padding:16px 18px; position:relative; overflow:hidden; transition: transform .25s, border-color .25s; }}
.card:hover {{ border-color:{VERDE_ESC}; transform: translateY(-2px); }}
.card.destaque {{ border-color:{VERDE_ESC}; box-shadow:0 0 40px {VERDE}14;
  background: radial-gradient(380px 160px at 0% 0%, {VERDE}26 0%, transparent 70%), linear-gradient(180deg, {PANEL2}, {PANEL}); }}
.card.alerta {{ border-color:{AMBAR}66; background: linear-gradient(135deg, {AMBAR}1f 0%, {PANEL} 70%); }}
.card.mini {{ padding:14px; }}
.topo-card {{ display:flex; justify-content:space-between; align-items:center; gap:8px; margin-bottom:10px; }}
.titulo-card {{ color:{TEXTO_SEC}; font-size:12px; font-weight:600; letter-spacing:.3px; }}
.legenda {{ color:{TEXTO_SEC}; font-size:12px; }}
.chip {{ font-size:11px; font-weight:700; border:1px solid currentColor; border-radius:999px; padding:2px 10px; opacity:.95; }}
.num {{ display:block; font-weight:800; letter-spacing:-0.8px; font-variant-numeric:tabular-nums; font-size:26px; }}
.num.grande {{ font-size:34px; }}
.num.gigante {{ font-size:46px; letter-spacing:-1.5px; margin:6px 0 4px; }}
.num.medio {{ font-size:22px; }}
.num.vazio {{ color:{TEXTO_TER}; }}
.grid-3 {{ display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }}
.grid-3 .num.grande {{ font-size:28px; }}
@media (max-width:760px) {{ .grid-3 .num.grande {{ font-size:21px; }} .grid-3 .card.mini {{ padding:12px 10px; }} }}
.grid-agenda {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
.span-2 {{ grid-column: span 2; }}

/* meta */
.meta-wrap {{ padding:34px 2px 4px; position:relative; }}
.meta-trilho {{ height:46px; background:{BORDA}; border-radius:4px; overflow:hidden; }}
.meta-fill {{ height:100%; border-radius:4px; background: linear-gradient(90deg, {VERDE_ESC}, {VERDE});
  box-shadow: 0 0 20px {VERDE}66; border-radius:4px !important; animation: cresce 1.4s cubic-bezier(.2,.8,.2,1) both; transform-origin:left; }}
.marcador {{ position:absolute; top:0; transform:translateX(-50%); display:flex; flex-direction:column; align-items:center;
  animation: aparece .6s .9s both; }}
.marcador-txt {{ font-weight:800; font-size:14px; color:{VERDE}; }}
.marcador-seta {{ width:0; height:0; border:7px solid transparent; border-top-color:{VERDE}; margin-top:2px; }}
.meta-escala {{ display:flex; justify-content:space-between; color:{TEXTO_SEC}; font-size:12px; margin-top:8px; }}

/* funil */
.funil-linha {{ display:grid; grid-template-columns: 140px 1fr 46px; align-items:center; gap:10px; margin:9px 0; }}
.funil-nome {{ color:{TEXTO_SEC}; font-size:13px; text-align:right; }}
.funil-trilho {{ height:30px; background:{BORDA}66; border-radius:3px; overflow:hidden; }}
.funil-fill {{ height:100%; border-radius:3px; background: linear-gradient(90deg, {VERDE_ESC}, {VERDE} 70%, {VERDE_CLARO});
  animation: cresce 1s cubic-bezier(.2,.8,.2,1) both; transform-origin:left; }}
.funil-num {{ font-weight:800; font-size:17px; font-variant-numeric:tabular-nums; }}

/* gauges */
.gauge-box {{ position:relative; display:flex; flex-direction:column; align-items:center; padding-top:8px; }}
.gauge-box.grande {{ padding:34px 0 0; }}
.gauge {{ --tam:190px; position:relative; width:var(--tam); height:calc(var(--tam) / 2 + 8px); }}
.g-trilho, .g-arco {{ position:absolute; left:0; top:0; width:var(--tam); height:var(--tam); border-radius:50%;
  -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 16px), #000 calc(100% - 15px));
  mask: radial-gradient(farthest-side, transparent calc(100% - 16px), #000 calc(100% - 15px)); }}
@property --pa {{ syntax:'<number>'; inherits:false; initial-value:0; }}
.g-arco {{ --pa:0; background: conic-gradient(from 270deg, var(--cor) calc(var(--pa) * 1%), transparent 0);
  filter: drop-shadow(0 0 8px var(--cor)); animation: enche 1.5s cubic-bezier(.2,.8,.2,1) forwards; }}
@keyframes enche {{ to {{ --pa: var(--p); }} }}
.g-ponteiro {{ position:absolute; left:50%; top:calc(var(--tam) / 2); width:3px; height:calc(var(--tam) / 2 - 24px);
  background: linear-gradient(0deg, {TEXTO}, transparent); border-radius:3px; transform-origin: 50% 0;
  transform: translateX(-50%) rotate(calc(var(--ang) + 180deg)); animation: ponteiro 1.5s cubic-bezier(.2,.8,.2,1) both; }}
@keyframes ponteiro {{ from {{ transform: translateX(-50%) rotate(90deg); }} }}
.g-eixo {{ position:absolute; left:50%; top:calc(var(--tam) / 2); width:12px; height:12px; border-radius:50%;
  transform:translate(-50%,-50%); background:var(--cor); box-shadow:0 0 12px var(--cor); }}
.g-rotulo {{ position:absolute; transform:translate(-50%,-50%); font-size:11px; font-weight:700; white-space:nowrap; }}
.gauge-centro {{ text-align:center; margin-top:2px; }}
.gauge-num {{ font-size:30px; }}

/* agendamento cirúrgico */
.alerta-icone {{ font-size:26px; color:{AMBAR}; display:flex; animation: pisca 2s ease-in-out infinite; }}
@keyframes pisca {{ 50% {{ opacity:.35; }} }}
.card.alerta .num {{ color:{AMBAR}; }}
.linha-pend {{ display:flex; align-items:center; gap:12px; }}
.trilho {{ height:5px; background:{BORDA}; border-radius:2px; margin-top:8px; overflow:hidden; }}
.trilho-fill {{ height:100%; border-radius:2px; animation: cresce 1.1s cubic-bezier(.2,.8,.2,1) both; transform-origin:left; }}
@keyframes cresce {{ from {{ transform:scaleX(0); }} }}

/* abas */
.barra-abas {{ display:flex; gap:4px; margin:-4px 0 16px; border-bottom:1px solid {BORDA}; }}
.aba {{ display:inline-flex; align-items:center; gap:7px; background:transparent; border:none; cursor:pointer;
  color:{TEXTO_SEC}; font:600 13px Inter; padding:10px 16px; border-bottom:2px solid transparent; margin-bottom:-1px;
  transition: color .2s, border-color .2s; }}
.aba:hover {{ color:{TEXTO}; }}
.aba.ativa {{ color:{VERDE}; border-bottom-color:{VERDE}; }}
.modo-tv .barra-abas {{ display:none; }}

/* briefing + projeção */
.grid-briefing {{ display:grid; grid-template-columns: 1fr 1.55fr; gap:16px; margin-bottom:22px; align-items:stretch; }}
@media (max-width:1100px) {{ .grid-briefing {{ grid-template-columns:1fr; }} }}
.grid-briefing > * {{ min-width:0; }}
.briefing {{ display:flex; flex-direction:column; }}
.brief-lista {{ display:flex; flex-direction:column; justify-content:center; gap:14px; margin-top:4px; flex:1; }}
.brief-linha {{ display:flex; gap:12px; align-items:flex-start; font-size:17px; line-height:1.55; color:{TEXTO};
  animation: aparece .6s both; }}
.brief-marca {{ width:4px; min-height:22px; align-self:stretch; border-radius:4px; flex-shrink:0; opacity:.8; }}
.brief-rodape {{ margin-top:14px; font-size:11px; color:{TEXTO_TER}; }}
.grid-stats {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-bottom:6px; }}
@media (max-width:760px) {{ .grid-stats {{ grid-template-columns:1fr 1fr; }} }}
.stat {{ padding:10px 12px; border-radius:4px; background:{BG}88; border:1px solid {BORDA}; }}
.stat .num.medio {{ margin:2px 0; }}

/* jornada (linha do tempo) */
.grid-jornada {{ display:grid; grid-template-columns: 1fr 300px; gap:16px; }}
@media (max-width:1100px) {{ .grid-jornada {{ grid-template-columns:1fr; }} }}
.linha-tempo {{ display:flex; align-items:center; gap:4px; padding:18px 6px; overflow-x:auto; }}
.no {{ display:flex; flex-direction:column; align-items:center; gap:10px; min-width:86px; }}
.no-ponto {{ width:20px; height:20px; border-radius:50%; background:{BG}; border:3px solid {VERDE};
  box-shadow:0 0 14px {VERDE}88; animation: aparece .5s both; }}
.no-nome {{ font-size:12px; font-weight:600; text-transform:uppercase; letter-spacing:.6px; color:{TEXTO_SEC}; }}
.trecho {{ flex:1; display:flex; flex-direction:column; align-items:center; gap:4px; min-width:96px; margin-bottom:26px; }}
.trecho-num {{ font-size:22px; }}
.trecho-linha {{ width:100%; height:3px; border-radius:3px; background: linear-gradient(90deg, {VERDE}, {VERDE_ESC});
  animation: cresce .9s cubic-bezier(.2,.8,.2,1) both; transform-origin:left; }}
.trecho-linha.vazio {{ background: repeating-linear-gradient(90deg, {TEXTO_TER} 0 6px, transparent 6px 12px); }}
.total-jornada {{ display:flex; flex-direction:column; justify-content:center; }}

/* pódio */
.podio {{ display:flex; justify-content:center; align-items:flex-end; gap:8px; margin-bottom:-16px; }}
.podio-col {{ flex:1; max-width:190px; display:flex; flex-direction:column; align-items:center; text-align:center;
  animation: entra .7s cubic-bezier(.2,.8,.2,1) both; }}
@keyframes entra {{ from {{ opacity:0; transform:translateY(24px); }} }}
.coroa {{ font-size:22px; height:28px; display:flex; align-items:center; justify-content:center; animation: flutua 3s ease-in-out infinite; }}
.medalha {{ position:absolute; bottom:-4px; right:-6px; color:{BG}; font-weight:800; font-size:12px; border-radius:999px; padding:2px 8px; }}
.podio-nome {{ font-weight:600; font-size:12px; margin-top:8px; line-height:1.2; }}
.podio-valor {{ color:{VERDE}; font-weight:700; font-size:12px; }}
.degrau {{ width:100%; margin-top:8px; border-top:3px solid; border-radius:3px 3px 0 0;
  display:flex; align-items:center; justify-content:center; font-size:22px; font-weight:800; }}

.fade-in {{ animation: aparece .5s ease both; }}
@keyframes aparece {{ from {{ opacity:0; transform: translateY(8px); }} }}
.rodape {{ text-align:center; color:{TEXTO_TER}; font-size:11px; padding:18px 0 0; }}
"""

CSS += f"""
/* ================= ENCAIXE EM UMA TELA (1920×1080) ================= */
.barra-topo {{ padding:6px 16px; }}
.logo-img {{ height:24px; }}
.conteudo {{ padding:10px 16px 8px; }}
.hero {{ padding:8px 14px; margin-bottom:8px; gap:16px; }}
.titulo-icone {{ width:40px; height:40px; }}
.icone-grade {{ width:20px; height:20px; gap:4px; }}
.hero-linha1 {{ display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; }}
.hero-titulo {{ font-size:22px; }}
.hero-sub {{ margin-top:0; font-size:12.5px; }}
.hero-chips {{ margin-top:5px; gap:5px; }}
.hero-chip {{ padding:2px 9px; font-size:12px; }}
.barra-filtros {{ flex-direction:row !important; gap:6px; }}
.filtro {{ padding:3px 4px 3px 10px; }}
.pill {{ padding:5px 12px; }}
.cartao-gerente {{ padding:6px 14px 6px 8px; gap:12px; }}
.hero-video {{ width:54px; height:54px; }}
.hero-anel {{ inset:-5px; }}
.gerente-nome {{ font-size:16px; }}
.barra-abas {{ margin:0 0 8px; }}
.aba {{ padding:6px 14px; }}
.grid-colunas {{ gap:12px; }}
.col {{ gap:10px; }}
.secao {{ gap:7px; }}
.titulo-secao {{ font-size:12px; letter-spacing:1.6px; padding:0; }}
.titulo-secao::before {{ width:7px; height:7px; margin-right:8px; }}
.titulo-secao.sub {{ margin-top:2px; font-size:11.5px; }}
.card {{ padding:10px 14px; }}
.card.mini {{ padding:9px 11px; }}
.topo-card {{ margin-bottom:4px; }}
.num {{ font-size:22px; }}
.num.grande {{ font-size:26px; }}
.num.gigante {{ font-size:34px; margin:2px 0; }}
.grid-3 .num.grande {{ font-size:clamp(18px, 1.3vw, 23px) !important; }}
.delta-linha {{ margin-top:3px; }}
.meta-wrap {{ padding:24px 2px 0; }}
.meta-trilho {{ height:28px; }}
.meta-escala {{ margin-top:4px; }}
.funil-linha {{ margin:4px 0; }}
.funil-trilho {{ height:22px; }}
.funil-num {{ font-size:15px; }}
.funil-conv {{ margin:-1px 0 1px 160px; }}
.grid-agenda {{ gap:8px; }}
.linha-pend {{ gap:10px; }}
.coroa {{ height:20px; font-size:16px; }}
.podio-nome {{ margin-top:5px; }}
.gauge-box {{ padding-top:2px; }}
.gauge-box.grande {{ padding-top:22px; }}
.gauge-num {{ font-size:24px; }}
.anel-valor.grande {{ font-size:26px; }}
.card.cresce {{ min-height:70px; }}
.grafico-flex {{ min-height:56px; }}
.trilho {{ margin-top:5px; }}
/* jornada em faixa única */
.faixa-jornada {{ flex-direction:row !important; align-items:center; gap:18px; margin-top:12px; padding:8px 16px; }}
.jornada-rotulo {{ min-width:150px; }}
.jornada-titulo {{ font-size:12px; font-weight:800; letter-spacing:1.4px; text-transform:uppercase; }}
.faixa-jornada .linha-tempo {{ flex:1; padding:4px 0; }}
.faixa-jornada .no {{ min-width:70px; gap:5px; }}
.faixa-jornada .no-ponto {{ width:14px; height:14px; border-width:3px; }}
.faixa-jornada .no-nome {{ font-size:10.5px; }}
.faixa-jornada .trecho {{ margin-bottom:18px; min-width:80px; gap:2px; }}
.faixa-jornada .trecho-num {{ font-size:17px; }}
.total-jornada {{ min-width:170px; padding-left:18px; border-left:1px solid {BORDA}; }}
.total-jornada .num.grande {{ font-size:22px; }}
.rodape {{ padding:4px 0 0; font-size:10px; }}
.podio {{ margin-bottom:-10px !important; }}
.degrau {{ font-size:15px !important; }}
/* as colunas crescem para ocupar a altura da tela que sobrar */
.grid-colunas {{ min-height: calc(100vh - 234px); }}
/* coluna do funil: o funil cresce e as barras se distribuem; agendamento fica no tamanho natural */
.secao.funil-col > .card:nth-child(2) {{ flex:1; }}
.col > .secao.funil-col:last-child > :last-child {{ flex:0 0 auto; }}
.secao.funil-col .grid-agenda {{ grid-template-rows:auto; }}
.funil-linhas {{ flex:1; display:flex; flex-direction:column; justify-content:space-evenly; }}
.funil-linhas .funil-trilho {{ height:clamp(20px, 2.5vh, 34px); }}
.funil-linhas .funil-num {{ font-size:17px; }}
.funil-linhas .funil-nome {{ font-size:13.5px; }}
.conv-funil {{ font-size:14px; }}
.modo-tv .grid-colunas {{ min-height: calc(100vh - 253px); }}

/* storytelling */
.passo {{ display:inline-flex; align-items:center; gap:8px; }}
.titulo-secao:has(.passo)::before, .titulo-secao:has(.passo-cont)::before {{ display:none; }}
.passo-n {{ width:20px; height:20px; border-radius:50%; background:{VERDE}; color:{PANEL}; font-size:11px; font-weight:900;
  display:inline-flex; align-items:center; justify-content:center; letter-spacing:0; }}
.passo-sub {{ color:{TEXTO_SEC}; font-weight:600; letter-spacing:.8px; }}
.passo-seta {{ color:{VERDE}; font-size:18px; font-weight:900; margin-left:2px; }}
.passo-cont {{ color:{TEXTO_SEC}; font-size:11.5px; letter-spacing:1.4px; padding-left:28px; }}
.pj-trilho {{ position:relative; height:14px; background:{BORDA}; border-radius:3px; overflow:hidden; margin-top:8px; }}
.pj-real {{ position:absolute; left:0; top:0; bottom:0; background:{VERDE}; border-radius:3px 0 0 3px;
  transform-origin:left; animation: cresce 1.2s cubic-bezier(.2,.8,.2,1) both; }}
.pj-proj {{ position:absolute; top:0; bottom:0; opacity:.5;
  background: repeating-linear-gradient(45deg, var(--cor) 0 5px, transparent 5px 9px); }}

/* pódio: zoom na foto + ranking ao passar o mouse */
.podio {{ position:relative; }}
.podio-figura {{ position:relative; display:flex; flex-direction:column; align-items:center; justify-content:flex-end;
  transform-origin:50% 100%; transition: transform .35s cubic-bezier(.2,.8,.2,1), filter .35s; }}
.podio-col.com-recorte .podio-figura {{ flex:1; width:100%; }}
.podio-col.com-recorte .podio-figura .recorte-wrap {{ flex:1; }}
.podio-col:hover .podio-figura {{ transform: scale(1.18); z-index:3; }}
.podio-col.com-recorte:hover .podio-figura {{ transform: scale(1.1); }}
.podio-col:hover .podio-figura img, .podio-col:hover .podio-figura video {{ filter: drop-shadow(0 12px 22px #0006); }}
.podio:hover .podio-col:not(:hover) {{ opacity:.55; transition: opacity .3s; }}
.podio-col {{ transition: opacity .3s; }}
.rk-balao {{ position:absolute; top:-6px; width:290px; z-index:30; pointer-events:none; padding:10px 12px;
  background:{PANEL}; border:1px solid {BORDA}; border-radius:6px; box-shadow:0 16px 40px #0005;
  opacity:0; transform:translateY(-6px) scale(.97); transition: opacity .25s, transform .25s; }}
.rk-balao {{ left:calc(100% + 26px); }}
.rk-balao::before {{ content:''; position:absolute; left:-7px; top:24px; width:12px; height:12px; background:{PANEL};
  border-left:1px solid {BORDA}; border-bottom:1px solid {BORDA}; transform:rotate(45deg); }}
.card:has(.podio) {{ overflow:visible !important; }}
.card:has(.podio):hover {{ z-index:40; }}
.secao:has(.podio) {{ position:relative; z-index:5; }}
.podio:has(.podio-col:hover) .rk-balao {{ opacity:1; transform:none; }}
.podio:has(.p1:hover) .rk-item.r1, .podio:has(.p2:hover) .rk-item.r2, .podio:has(.p3:hover) .rk-item.r3 {{
  background:{VERDE}14; box-shadow: inset 3px 0 0 {VERDE}; }}
.rk-titulo {{ font-size:10.5px; font-weight:800; letter-spacing:1.2px; text-transform:uppercase; color:{TEXTO_SEC};
  display:flex; align-items:center; gap:5px; margin-bottom:6px; }}
.rk-item {{ display:flex; align-items:center; gap:8px; padding:6px; border-radius:4px; text-align:left; }}

.rk-pos {{ font-size:13px; font-weight:900; width:22px; text-align:center; }}
.rk-linha1 {{ display:flex; justify-content:space-between; gap:6px; font-size:12.5px; }}
.rk-linha1 b {{ white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.rk-valor {{ font-weight:800; color:{VERDE}; white-space:nowrap; }}
.rk-trilho {{ height:4px; border-radius:2px; background:{BORDA}; margin:3px 0 2px; overflow:hidden; }}
.rk-fill {{ height:100%; border-radius:2px; transform-origin:left; }}
.podio:has(.podio-col:hover) .rk-fill {{ animation: cresce .7s cubic-bezier(.2,.8,.2,1) both; }}
.rk-rodape {{ margin-top:6px; padding-top:6px; border-top:1px solid {BORDA}; font-size:11px; color:{TEXTO_SEC}; }}
.modo-tv .rk-balao {{ display:none; }}


/* balão ao lado do pódio: vídeo recortado (1º lugar) + ranking */
.rk-balao.com-video {{ display:flex; align-items:stretch; gap:0; padding:0; width:auto; }}
.rk-balao.com-video .rk-lista {{ width:290px; padding:10px 12px; }}
.rk-video {{ display:none; position:relative; width:200px; flex-shrink:0; border-right:1px solid {BORDA};
  background: radial-gradient(120% 80% at 50% 100%, {MEDALHAS[1]}38, transparent 70%); border-radius:6px 0 0 6px; overflow:hidden; }}
.podio:has(.p1:hover) .rk-video {{ display:block; }}
.rk-video-el {{ position:absolute; left:50%; bottom:0; transform:translateX(-50%); height:calc(100% - 4px); width:auto;
  max-width:none; filter: drop-shadow(0 8px 14px #0005); }}
.rk-video-brilho {{ position:absolute; left:50%; bottom:-20px; width:160px; height:60px; transform:translateX(-50%);
  background: radial-gradient(closest-side, {MEDALHAS[1]}66, transparent); filter:blur(8px); }}
.rk-video-nome {{ position:absolute; left:8px; bottom:8px; display:flex; align-items:center; gap:4px; z-index:2;
  font-size:11px; font-weight:800; padding:3px 9px; border-radius:999px; background:{MEDALHAS[1]}; color:#2a1320; }}

/* vídeo ao clicar na foto do pódio */
.podio-figura.tem-video {{ cursor:pointer; }}
.play-selo {{ position:absolute; left:50%; top:42%; transform:translate(-50%,-50%) scale(.8); width:44px; height:44px; border-radius:50%;
  display:flex; align-items:center; justify-content:center; font-size:18px; color:#fff; background:{VERDE}e6;
  box-shadow:0 0 0 6px {VERDE}40, 0 8px 20px #0006; opacity:0; transition: opacity .25s, transform .25s; pointer-events:none; }}
.play-selo .ic {{ margin-left:3px; }}
.podio-col:hover .play-selo {{ opacity:1; transform:translate(-50%,-50%) scale(1); }}
.podio-col:not(.com-recorte) .play-selo {{ width:30px; height:30px; font-size:12px; top:auto; bottom:18px; }}
.video-modal {{ position:fixed; inset:0; z-index:500; display:flex; align-items:center; justify-content:center;
  background:#000b; backdrop-filter: blur(6px); animation: aparece .25s both; }}
.video-caixa {{ position:relative; display:flex; flex-direction:column; align-items:center; gap:12px; animation: video-entra .35s cubic-bezier(.2,.8,.2,1) both; }}
@keyframes video-entra {{ from {{ opacity:0; transform: scale(.92) translateY(20px); }} }}
.video-caixa video {{ max-height:78vh; max-width:90vw; border-radius:8px; border:2px solid {VERDE};
  box-shadow:0 0 0 6px {VERDE}33, 0 30px 80px #000a; background:#000; }}
.video-legenda {{ color:#fff; font-size:18px; font-weight:800; display:flex; align-items:center; gap:10px; }}
.video-legenda span {{ font-size:12px; font-weight:800; padding:3px 10px; border-radius:999px; background:{VERDE}; color:{PANEL}; }}
.video-fechar {{ position:absolute; top:-14px; right:-14px; width:36px; height:36px; border-radius:50%; border:none; cursor:pointer;
  background:{PANEL}; color:{TEXTO}; font-size:18px; font-weight:800; box-shadow:0 6px 18px #0006; }}

/* pódio: 1º lugar com a pessoa recortada (sem fundo) */
.podio {{ align-items:stretch !important; }}
.podio-col {{ justify-content:flex-end; }}
.podio-col.com-recorte {{ flex:1.25; max-width:none; }}
.recorte-wrap {{ position:relative; flex:1; width:100%; min-height:90px; display:flex; align-items:flex-end; justify-content:center; }}
.podio-recorte {{ position:absolute; bottom:0; left:50%; transform:translateX(-50%); height:100%; max-width:150%;
  object-fit:contain; object-position:bottom center; filter: drop-shadow(0 10px 16px #0005);
  animation: sobe-recorte .9s cubic-bezier(.2,.8,.2,1) both; }}
@keyframes sobe-recorte {{ from {{ opacity:0; transform:translate(-50%, 24px); }} }}
.recorte-brilho {{ position:absolute; left:50%; bottom:-10px; width:120%; height:80%; transform:translateX(-50%);
  background: radial-gradient(closest-side, {MEDALHAS[1]}55, transparent); filter:blur(6px); }}
.recorte-medalha {{ position:absolute !important; right:auto !important; left:50%; bottom:6px !important; transform:translateX(-50%);
  display:flex; align-items:center; gap:3px; font-size:12px; padding:3px 10px !important; box-shadow:0 4px 12px #0004; }}

/* ================= TOPO NOVO (barra única) ================= */
.topo-fundo {{ position:absolute; inset:0; overflow:hidden; pointer-events:none; z-index:0;
  background: linear-gradient(115deg, {VERDE}1c 0%, transparent 45%, {VERDE}0d 100%); }}
.topo-fundo .hero-brilho {{ inset:auto; left:50%; top:50%; width:2600px; height:2600px; margin:-1300px 0 0 -1300px; animation-duration:8s;
  background: conic-gradient(from 0deg, transparent 0 68%, {VERDE}14 74%, {VERDE}38 79.5%, {VERDE}66 80%, transparent 80.4%); }}
.topo-fundo .hero-grade {{ opacity:.55; background-size:28px 28px; }}
.topo-novo > *:not(.topo-fundo):not(.meta-linha) {{ position:relative; z-index:1; }}
.topo-novo {{ display:flex !important; flex-wrap:nowrap !important; align-items:center; gap:18px; padding:10px 18px !important;
  background:{PANEL} !important; position:sticky; top:0; z-index:60; }}
.topo-id {{ display:flex; align-items:center; gap:14px; flex-shrink:0; }}
.topo-novo .logo-img {{ height:28px; }}
.topo-novo .migalhas {{ font-size:11px; color:{TEXTO_TER}; display:flex; align-items:center; gap:3px; }}
.topo-novo .migalhas b {{ color:{TEXTO_SEC}; font-weight:600; }}
.topo-titulo {{ margin:1px 0 0; font-size:19px; font-weight:800; letter-spacing:-.4px; line-height:1.15; color:{TEXTO}; }}
.meta-linha {{ position:absolute; left:0; bottom:-1px; height:2px; background:{VERDE}; box-shadow:0 0 8px {VERDE}88;
  transition: width 1.2s cubic-bezier(.2,.8,.2,1); }}
/* pílula */
.pilula {{ margin:0 auto; display:flex; align-items:center; gap:2px; padding:4px; border-radius:999px;
  background:{PANEL2}; border:1px solid {BORDA}; box-shadow:0 2px 10px #0000000d; }}
.pilula-sep {{ width:1px; height:20px; background:{BORDA}; }}
.menu {{ position:relative; }}
.menu > summary {{ list-style:none; cursor:pointer; }}
.menu > summary::-webkit-details-marker {{ display:none; }}
.menu.seg > summary {{ display:flex; align-items:center; gap:8px; padding:7px 14px; border-radius:999px;
  font-size:14px; font-weight:600; color:{TEXTO}; white-space:nowrap; transition: background .2s; }}
.menu.seg > summary .ic {{ color:{VERDE}; }}
.menu.seg > summary:hover, .menu.seg[open] > summary {{ background:{VERDE}1f; }}
.car {{ font-size:10px; color:{TEXTO_TER}; }}
.menu-pop {{ position:absolute; top:calc(100% + 8px); left:0; min-width:200px; z-index:90; padding:12px;
  background:{PANEL}; border:1px solid {BORDA}; border-radius:8px; box-shadow:0 14px 40px #0006; animation: aparece .18s both; }}
.menu.alinhar-dir .menu-pop {{ left:auto; right:0; }}
.menu-rot {{ font-size:10.5px; font-weight:800; letter-spacing:1.2px; text-transform:uppercase; color:{TEXTO_SEC}; margin-bottom:6px; }}
.opt {{ display:flex; width:100%; align-items:center; justify-content:space-between; gap:10px; padding:8px 10px; border:none;
  border-radius:5px; background:transparent; color:{TEXTO}; font:500 13.5px Inter; cursor:pointer; text-align:left; }}
.opt:hover {{ background:{BORDA}88; }}
.opt .check {{ opacity:0; color:{VERDE}; font-weight:900; }}
.opt.ativo {{ background:{VERDE}1f; color:{VERDE}; font-weight:700; }}
.opt.ativo .check {{ opacity:1; }}
.opt.demo {{ border:1px dashed {VERDE}; color:{VERDE}; justify-content:flex-start; gap:6px; margin-top:8px; }}
.presets {{ display:flex; flex-wrap:wrap; gap:6px; width:300px; }}
.chip-p {{ border:1px solid {BORDA}; border-radius:999px; padding:5px 11px; background:transparent; color:{TEXTO_SEC};
  font:500 12.5px Inter; cursor:pointer; }}
.chip-p:hover {{ border-color:{VERDE}; color:{VERDE}; }}
.meta-pilula {{ display:flex; align-items:center; gap:8px; padding:4px 12px 4px 8px; font-size:12.5px; color:{TEXTO_SEC}; white-space:nowrap; }}
.meta-pilula b {{ color:{TEXTO}; font-size:13.5px; }}
.anel-mini {{ --pa:0; width:24px; height:24px; border-radius:50%; flex-shrink:0;
  background: conic-gradient({VERDE} calc(var(--pa) * 1%), {BORDA} 0);
  -webkit-mask: radial-gradient(farthest-side, transparent 62%, #000 63%); mask: radial-gradient(farthest-side, transparent 62%, #000 63%);
  animation: enche-mini 1.2s cubic-bezier(.2,.8,.2,1) forwards; }}
@keyframes enche-mini {{ to {{ --pa: var(--p); }} }}
/* ações */
.acoes {{ display:flex; align-items:center; gap:7px; flex-shrink:0; }}
.vivo {{ display:flex; align-items:center; gap:6px; font-size:11.5px; color:{TEXTO_SEC}; margin-right:4px; white-space:nowrap; }}
.btn-ic, .menu.icone > summary {{ width:36px; height:36px; border-radius:8px; display:flex; align-items:center; justify-content:center;
  border:1px solid {BORDA}; background:{PANEL2}; color:{TEXTO_SEC}; font-size:17px; cursor:pointer; position:relative; transition: all .2s; }}
.btn-ic:hover, .menu.icone > summary:hover, .menu.icone[open] > summary {{ color:{VERDE}; border-color:{VERDE}; }}
.badge {{ position:absolute; top:-6px; right:-6px; min-width:18px; height:18px; border-radius:9px; background:{VERMELHO}; color:#fff;
  font-size:10.5px; font-weight:800; align-items:center; justify-content:center; padding:0 5px; border:2px solid {PANEL}; }}
.alerta-item {{ display:flex; gap:10px; align-items:flex-start; padding:8px 4px; border-top:1px solid {BORDA}; min-width:260px; font-size:13px; }}
.alerta-item .ic {{ margin-top:2px; }}
.tema-btn .ic-sol {{ display:none; }}
.tema-btn.tema-noite .ic-lua {{ display:none; }}
.tema-btn.tema-noite .ic-sol {{ display:inline-block; }}
.topo-novo .pill.tv {{ height:36px; border-radius:8px; border:1px solid {BORDA}; background:{PANEL2}; color:{TEXTO}; font-weight:700; }}
.menu.avatar-menu > summary {{ border-radius:50%; margin-left:4px; }}
.perfil {{ display:flex; align-items:center; gap:12px; min-width:220px; padding-bottom:6px; }}
.perfil .gerente-nome {{ font-size:16px; font-weight:800; }}
/* resumo na linha das abas */
.barra-abas {{ justify-content:space-between; align-items:center; }}
.resumo-abas {{ display:flex; gap:18px; font-size:12px; color:{TEXTO_SEC}; white-space:nowrap; }}
.resumo-abas b {{ color:{TEXTO}; }}
.resumo-abas .aviso, .resumo-abas .aviso b {{ color:{AMBAR}; }}
/* modo TV: some a identidade e a pílula, aparece a faixa da TV */
.modo-tv .topo-id, .modo-tv .pilula, .modo-tv .vivo, .modo-tv .menu-avatar {{ display:none !important; }}
.modo-tv .tv-info {{ display:flex; margin-right:auto; }}
@media (max-width:1100px) {{ .topo-novo {{ flex-wrap:wrap !important; }} .pilula {{ order:3; margin:0; }} .vivo {{ display:none; }} }}
/* ---- equilíbrio das colunas: gráficos com altura fixa, os indicadores crescem ---- */
/* coluna Captação + Conversão */
.col > .secao.captacao {{ flex:1 !important; }}
.secao.captacao > .grid-3 {{ flex:1; }}
.secao.captacao > .grid-3 > .card {{ justify-content:center; }}
.col > .secao.captacao > .card.cresce {{ flex:0 0 auto !important; height:clamp(120px, 15vh, 170px); min-height:0; }}
.col > .secao.igual:last-child {{ flex:1 !important; }}
.col > .secao.igual:last-child > .card {{ flex:1 !important; }}
.secao.igual .ind-topo, .secao.cc > .card:nth-child(2) .ind-topo {{ margin-top:auto; }}
.secao.igual .ind-faixas, .secao.cc > .card:nth-child(2) .ind-faixas {{ margin-top:auto; }}
/* coluna Centro cirúrgico */
.secao.cc > .card:nth-child(2) {{ flex:1.3 !important; }}
.secao.cc > .grid-3 {{ flex:1; }}
.secao.cc > .grid-3 > .card {{ justify-content:center; }}
.col > .secao.cc:last-child > .semana-card {{ flex:0 0 auto !important; height:clamp(150px, 20vh, 220px); min-height:0; }}
.semana-barras {{ min-height:0; }}
/* números maiores nos indicadores que ganharam espaço */
.secao.captacao .grid-3 .num.grande, .secao.cc .grid-3 .num.grande {{ font-size:clamp(22px, 1.75vw, 32px) !important; }}
.secao.igual .ind-topo .num.grande, .secao.cc > .card:nth-child(2) .ind-topo .num.grande {{ font-size:clamp(30px, 2.3vw, 42px); }}
.secao.igual .bul, .secao.cc .bul {{ height:32px; }}
.secao.igual .bul-valor, .secao.cc .bul-valor {{ top:10px; height:12px; }}
.secao.igual .bul-meta, .secao.cc .bul-meta {{ height:30px; }}
.secao.igual .bul-anterior, .secao.cc .bul-anterior {{ top:6px; height:20px; }}
"""

JS = """
(function () {
  const br = (v, c) => v.toLocaleString('pt-BR', {minimumFractionDigits: c, maximumFractionDigits: c});
  const fmt = {
    brl:  v => 'R$ ' + br(v, 2),
    brlk: v => 'R$ ' + br(v / 1000, 2) + 'k',
    int:  v => br(Math.round(v), 0),
    pct:  v => br(v * 100, 2) + '%',
    dias: (v, alvo) => br(v, (alvo % 1 && alvo < 1) ? 2 : (alvo % 1 ? 1 : 0)) + ' dias'
  };
  function anima(el) {
    if (el.dataset.feito === el.dataset.alvo) return;
    el.dataset.feito = el.dataset.alvo;
    const alvo = parseFloat(el.dataset.alvo), f = fmt[el.dataset.fmt] || fmt.int;
    const t0 = performance.now(), dur = 1300;
    const passo = t => {
      const p = Math.min((t - t0) / dur, 1), e = 1 - Math.pow(1 - p, 3);
      el.textContent = f(alvo * e, alvo);
      if (p < 1) requestAnimationFrame(passo); else el.textContent = f(alvo, alvo);
    };
    requestAnimationFrame(passo);
  }
  // confete quando aparece um contrato novo no Modo TV
  function confete() {
    const cores = [getComputedStyle(document.documentElement).getPropertyValue('--acc').trim() || '#e0197d',
                   '#f5c542', '#ffffff', '#ff8fbf', '#3ddc85'];
    for (let i = 0; i < 90; i++) {
      const c = document.createElement('div');
      c.className = 'confete';
      c.style.left = Math.random() * 100 + 'vw';
      c.style.background = cores[i % cores.length];
      c.style.animationDuration = (2.2 + Math.random() * 2) + 's';
      c.style.animationDelay = (Math.random() * .6) + 's';
      c.style.transform = 'rotate(' + Math.random() * 360 + 'deg)';
      document.body.appendChild(c);
      setTimeout(() => c.remove(), 5000);
    }
  }
  let ultimoEvento = null;
  function verificaEvento() {
    const t = document.querySelector('.toast-contrato');
    if (t && t.dataset.evento !== ultimoEvento) { ultimoEvento = t.dataset.evento; confete(); }
  }
  // balão do ⓘ "como é calculado"
  const balao = document.createElement('div');
  balao.className = 'balao-info';
  document.addEventListener('DOMContentLoaded', () => document.body.appendChild(balao));
  document.addEventListener('mouseover', e => {
    const el = e.target.closest('.info, .dica');
    if (!el) { balao.classList.remove('visivel'); return; }
    balao.innerHTML = '<b>' + el.dataset.titulo + '</b>' + el.dataset.info +
      '<div class="calc"><strong>Cálculo:</strong> ' + el.dataset.calculo + '</div>' +
      '<div class="fonte">Fonte: ' + el.dataset.fonte + '</div>';
    if (!balao.isConnected) document.body.appendChild(balao);
    const r = el.getBoundingClientRect(), w = 320;
    let x = Math.min(r.left - 12, window.innerWidth - w - 12);
    balao.style.left = Math.max(12, x) + 'px';
    balao.style.top = (r.bottom + 10) + 'px';
    balao.classList.add('visivel');
    const b = balao.getBoundingClientRect();
    if (b.bottom > window.innerHeight - 8) balao.style.top = (r.top - b.height - 10) + 'px';
  });
  // clicar no ⓘ não abre a gaveta do card
  document.addEventListener('click', e => { if (e.target.closest('.info')) e.stopPropagation(); }, true);
  // pódio: ao passar o mouse, o vídeo recortado (sem fundo) toca no lugar da foto
  document.addEventListener('mouseover', e => {
    const col = e.target.closest('.podio-col.p1');
    if (!col) return;
    const v = col.closest('.podio').querySelector('video.rk-video-el');
    if (v && v.paused) { v.currentTime = 0; v.play().catch(() => {}); }
  });
  document.addEventListener('mouseout', e => {
    const col = e.target.closest('.podio-col.p1');
    if (!col || (e.relatedTarget && col.contains(e.relatedTarget))) return;
    const v = col.closest('.podio').querySelector('video.rk-video-el');
    if (v) v.pause();
  });

  // menus do topo: fecha ao clicar fora, ao abrir outro, ou ao escolher uma opção
  document.addEventListener('click', e => {
    const dentro = e.target.closest('details.menu');
    document.querySelectorAll('details.menu[open]').forEach(m => { if (m !== dentro) m.removeAttribute('open'); });
    const opcao = e.target.closest('.menu-pop .opt, .menu-pop .chip-p');
    if (opcao) { const m = opcao.closest('details.menu'); if (m) setTimeout(() => m.removeAttribute('open'), 120); }
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') document.querySelectorAll('details.menu[open]').forEach(m => m.removeAttribute('open'));
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') { const b = document.getElementById('gaveta-fechar'); if (b) b.click(); }
  });
  new MutationObserver(() => { document.querySelectorAll('.countup').forEach(anima); verificaEvento(); })
    .observe(document.documentElement, {childList: true, subtree: true});
})();
"""

def folhas_tema():
    """Uma <style> por tema; só a do tema escolhido fica ativa (o JS troca o 'media')."""
    blocos = []
    for chave in TEMAS:
        troca = _trocador(chave)
        css = troca(CSS) if troca else CSS
        media = "all" if chave == TEMA_PADRAO else "not all"
        blocos.append(f'<style data-tema="{chave}" media="{media}">{css}</style>')
    return "".join(blocos)


app.index_string = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>{{%metas%}}<title>{{%title%}}</title>{{%favicon%}}{{%css%}}{folhas_tema()}<style>{css_icones()}</style></head>
<body>{{%app_entry%}}<footer>{{%config%}}{{%scripts%}}{{%renderer%}}</footer>
<script>{JS}</script></body>
</html>"""

if __name__ == "__main__":
    app.run(debug=True, port=8051)
