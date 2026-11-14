"""Sistema de Gestão das Congregações MEN (site separado do calendário).

Páginas: visão geral, congregações, membros, novo membro, departamentos e eventos.
Segredos necessários (Streamlit Cloud > Settings > Secrets):
    database_url = "postgresql://..."   # banco PostgreSQL na nuvem (Neon)
    senha_gestao = "uma-senha-forte"
Opcionais (para mostrar os eventos do calendário geral na página Eventos):
    google_credentials = "..."          # o mesmo usado no site do calendário
    planilha_url = "https://docs.google.com/spreadsheets/d/..."
"""
import json

import pandas as pd
import streamlit as st

import gestao

st.set_page_config(
    page_title="Gestão das Congregações MEN",
    page_icon="⛪",
    layout="wide",
    initial_sidebar_state="expanded",
)

LOGO_URL = "https://github.com/rcrystiandados/app-igreja/blob/main/logo.jpeg?raw=true"

# Lista inicial, usada só no botão "Importar lista inicial" da Visão geral.
CONGREGACOES_INICIAIS = {
    "Região Cariri": [
        "IEC - São João do Cariri", "IEC - Sumé", "IEC - Serra Branca", "IEC - Monteiro",
        "IEC - Sertânia", "IEC - Santa Luzia do Cariri", "IEC - São José dos Cordeiros",
        "IEC - Coxixola", "IEC - Assentamento Mandacaru",
    ],
    "Região Curimataú": [
        "IEC - Canoa de Dentro", "IEC - Baraúna", "IEC - Sossego", "IEC - Alto do Umbuzeiro",
        "IEC - Pedra Lavrada", "IEC - Soledade",
    ],
    "Região Metropolitana": [
        "IEC - Capim Grande", "IEC - Fagundes", "IEC - Itatuba", "IEC - São Tomé",
        "IEC - Puxinanã", "IEC - Queimadas", "IEC - Ronaldo Cunha Lima",
        "IEC - Santa Terezinha", "IEC - Sítio Rafael", "IEC - Sítio Bastiões",
        "IEC - Galante", "IEC - Chã de Galante",
    ],
    "Região Nacional/Internacional": [
        "IEC - Juliana/BH", "IEC - Juazeiro do Norte/CE", "IEC - Guadalajara/MX",
    ],
}

PAGINAS = ["Visão geral", "Congregações", "Membros", "Novo membro", "Departamentos", "Eventos"]

if "logado" not in st.session_state:
    st.session_state["logado"] = False
if "pagina" not in st.session_state:
    st.session_state["pagina"] = "Visão geral"

ESTILO = """<style>
    :root {
        --azul: #1E3A8A;
        --azul-escuro: #152C6B;
        --azul-claro: #E8EEFB;
        --fundo: #F5F7FA;
        --borda: #DDE3EC;
        --texto: #1F2937;
    }

    .stApp {background: var(--fundo);}
    header[data-testid="stHeader"] {background: transparent;}
    #MainMenu, footer {visibility: hidden;}

    /* Conteúdo */
    .block-container {
        padding: 2.5rem 3rem 4rem 3rem;
        max-width: 1200px;
    }
    .block-container h1, .block-container h2, .block-container h3, .block-container h4 {
        color: var(--azul) !important; font-weight: 700 !important;
    }
    .block-container h1 {
        font-size: 1.9rem; padding-bottom: .6rem; border-bottom: 2px solid var(--borda);
        margin-bottom: 1.2rem;
    }
    .block-container p, .block-container label, .block-container li {color: var(--texto);}

    /* Barra lateral (menu) */
    section[data-testid="stSidebar"] {background: var(--azul); border-right: none;}
    section[data-testid="stSidebar"] * {color: #FFFFFF !important;}
    .sb-titulo {font-size: 1.2rem; font-weight: 700; line-height: 1.3; margin: .4rem 0 .2rem 0;}
    .sb-sub {font-size: .85rem; opacity: .75; margin-bottom: 1.4rem;}

    section[data-testid="stSidebar"] div[role="radiogroup"] {gap: .25rem;}
    section[data-testid="stSidebar"] div[role="radiogroup"] label > div:first-child {display: none;}
    section[data-testid="stSidebar"] div[role="radiogroup"] label {
        width: 100%; padding: .65rem .9rem; border-radius: 6px;
        cursor: pointer; transition: background .15s;
    }
    section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {background: rgba(255,255,255,.12);}
    section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {background: #FFFFFF;}
    section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) * {
        color: var(--azul) !important; font-weight: 600;
    }
    .sb-contato {font-size: .82rem; line-height: 1.7; opacity: .9;}
    section[data-testid="stSidebar"] hr {border-color: rgba(255,255,255,.2);}

    /* Cartões */
    .card {
        background: #FFFFFF; border: 1px solid var(--borda); border-radius: 8px;
        padding: 1.1rem 1.3rem; height: 100%;
    }
    .card .card-titulo {color: var(--azul); font-weight: 700; margin-bottom: .3rem;}
    .card .card-texto {color: var(--texto); font-size: .95rem;}

    /* Indicadores */
    div[data-testid="stMetric"] {
        background: #FFFFFF; border: 1px solid var(--borda);
        border-radius: 8px; padding: .9rem 1.1rem;
    }
    div[data-testid="stMetricValue"] {color: var(--azul);}

    /* Botões */
    div.stButton > button, div.stFormSubmitButton > button, a[data-testid="stBaseLinkButton-secondary"] {
        background-color: var(--azul) !important; color: #FFFFFF !important;
        border: none !important; border-radius: 6px !important;
        padding: .55rem 1.4rem !important; font-weight: 600 !important;
    }
    div.stButton > button *, div.stFormSubmitButton > button * {color: #FFFFFF !important;}
    div.stButton > button:hover, div.stFormSubmitButton > button:hover {
        background-color: var(--azul-escuro) !important;
    }

    /* Avisos legíveis */
    div[data-testid="stAlert"] {border-left: 5px solid var(--azul) !important;}
    div[data-testid="stAlert"] * {color: var(--texto) !important;}

    /* Campos */
    div[data-baseweb="input"], div[data-baseweb="select"] > div, div[data-baseweb="base-input"] {
        background-color: #FFFFFF !important; border-color: #CBD5E1 !important;
    }
    div[data-testid="stForm"] {background: #FFFFFF; border: 1px solid var(--borda); border-radius: 8px;}

    /* ---------- Correções de tema e componentes ---------- */
    :root, .stApp {color-scheme: light;}

    .sb-topo {text-align: center; margin: .2rem 0 1.2rem 0;}
    .sb-logo {width: 100%; max-width: 210px; height: auto; border-radius: 8px;
              background: #FFFFFF; margin-bottom: .8rem;}
    .sb-topo .sb-titulo {margin: 0;}

    /* Menu: some com as bolinhas do radio */
    section[data-testid="stSidebar"] label[data-baseweb="radio"] > div:first-child,
    section[data-testid="stSidebar"] label[data-baseweb="radio"] > span:first-child,
    section[data-testid="stSidebar"] [data-testid="stRadio"] label > div:first-child:not([data-testid="stMarkdownContainer"]) {
        display: none !important;
    }

    /* Campos de texto e senha sempre claros */
    div[data-testid="stTextInput"] div[data-baseweb="input"],
    div[data-testid="stTextInput"] div[data-baseweb="base-input"],
    div[data-testid="stTextInput"] input,
    div[data-testid="stTextInput"] button {
        background-color: #FFFFFF !important; color: #111827 !important;
    }
    div[data-testid="stTextInput"] div[data-baseweb="input"] {border: 1px solid #CBD5E1 !important;}
    div[data-testid="stTextInput"] svg {fill: #475569 !important;}

    /* Avisos sempre claros e legíveis */
    div[data-testid="stAlert"] {background-color: #E8EEFB !important;}
    div[data-testid="stAlert"] * {background-color: transparent !important; color: #1F2937 !important;}

    /* Página de login */
    .login-topo {text-align: center; margin: 1.5rem 0 1.2rem 0;}
    .login-topo .login-icone {
        width: 64px; height: 64px; margin: 0 auto .8rem auto; border-radius: 50%;
        background: var(--azul-claro); display: flex; align-items: center;
        justify-content: center; font-size: 1.8rem;
    }
    .login-topo h2 {margin: 0 0 .4rem 0;}
    .login-topo p {color: #6B7280 !important; margin: 0;}

    /* ---------- Menu lateral em botões ---------- */
    section[data-testid="stSidebar"] div.stButton > button {
        width: 100%; justify-content: flex-start; text-align: left;
        padding: .65rem .9rem !important; border-radius: 6px !important;
        background-color: transparent !important; border: none !important;
        box-shadow: none !important; font-weight: 500 !important;
    }
    section[data-testid="stSidebar"] div.stButton > button * {
        color: #FFFFFF !important; justify-content: flex-start; text-align: left;
    }
    section[data-testid="stSidebar"] div.stButton > button:hover {
        background-color: rgba(255,255,255,.14) !important;
    }
    section[data-testid="stSidebar"] div.stButton > button[kind="primary"],
    section[data-testid="stSidebar"] div.stButton > button[data-testid="stBaseButton-primary"] {
        background-color: #FFFFFF !important;
    }
    section[data-testid="stSidebar"] div.stButton > button[kind="primary"] *,
    section[data-testid="stSidebar"] div.stButton > button[data-testid="stBaseButton-primary"] * {
        color: #1E3A8A !important; font-weight: 700 !important;
    }

    /* ---------- Selects e listas sempre claros ---------- */
    div[data-baseweb="select"] > div {background-color: #FFFFFF !important; border: 1px solid #CBD5E1 !important;}
    div[data-baseweb="select"] * {color: #111827 !important;}
    div[data-baseweb="select"] svg {fill: #475569 !important;}
    div[data-baseweb="popover"], div[data-baseweb="popover"] ul,
    div[data-baseweb="popover"] li, div[data-baseweb="menu"] {
        background-color: #FFFFFF !important; color: #111827 !important;
    }
    div[data-baseweb="popover"] li:hover {background-color: #E8EEFB !important;}
    span[data-baseweb="tag"] {background-color: #1E3A8A !important;}
    span[data-baseweb="tag"] * {color: #FFFFFF !important;}
    div[data-testid="stDateInput"] div[data-baseweb="input"],
    div[data-testid="stDateInput"] input {background-color: #FFFFFF !important; color: #111827 !important;}

    /* ---------- Título do painel, submenu e botão de link ---------- */
    .block-container h1.titulo-sem-linha {border-bottom: none; padding-bottom: 0; margin: 0;}
    .block-container hr.linha-titulo {border: none; border-top: 2px solid #DDE3EC; margin: .6rem 0 1.4rem 0;}

    section[data-testid="stSidebar"] [class*="st-key-sub_"] button {
        padding-left: 2rem !important; font-size: .9rem !important;
    }

    .block-container a[data-testid^="stBaseLinkButton"] {
        background: #FFFFFF !important; border: 1.5px solid #1E3A8A !important;
        border-radius: 6px !important; padding: .55rem 1.4rem !important;
        text-decoration: none !important; transition: background .15s;
    }
    .block-container a[data-testid^="stBaseLinkButton"],
    .block-container a[data-testid^="stBaseLinkButton"] * {
        color: #1E3A8A !important; font-weight: 600 !important;
    }
    .block-container a[data-testid^="stBaseLinkButton"]:hover {background: #1E3A8A !important;}
    .block-container a[data-testid^="stBaseLinkButton"]:hover * {color: #FFFFFF !important;}

    /* ---------- Bloco de exportação em destaque ---------- */
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.marca-exportar) {
        background: #F3F7FF; border: 2px solid #1E3A8A !important;
        border-left: 8px solid #1E3A8A !important; border-radius: 12px;
        box-shadow: 0 4px 14px rgba(30,58,138,.15); padding: .6rem .8rem;
    }
    .exp-topo {display: flex; align-items: center; gap: .9rem; margin-bottom: .6rem;}
    .exp-icone {
        width: 46px; height: 46px; border-radius: 50%; background: #1E3A8A; color: #FFFFFF;
        display: flex; align-items: center; justify-content: center; font-size: 1.4rem; flex: none;
    }
    .exp-titulo {font-size: 1.25rem; font-weight: 700; color: #1E3A8A; line-height: 1.2;}
    .exp-sub {font-size: .9rem; color: #475569;}
    div[data-testid="stDownloadButton"] button {
        background-color: #2E7D5B !important; border: none !important; border-radius: 6px !important;
        padding: .65rem 1.6rem !important; font-weight: 700 !important;
    }
    div[data-testid="stDownloadButton"] button, div[data-testid="stDownloadButton"] button * {color: #FFFFFF !important;}
    div[data-testid="stDownloadButton"] button:hover {background-color: #256649 !important;}

    /* ---------- Blocos da página inicial da liderança ---------- */
    .adm-card {padding: .2rem .2rem .4rem .2rem;}
    .adm-tit {font-size: 1.15rem; font-weight: 700; color: #1E3A8A; margin-bottom: .5rem;}
    .adm-num {font-size: 2.6rem; font-weight: 700; line-height: 1;}
    .adm-lbl {font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; color: #64748B; margin: .2rem 0 .6rem 0;}
    .adm-desc {font-size: .92rem; color: #475569; min-height: 2.6rem;}
</style>
"""
st.markdown(ESTILO, unsafe_allow_html=True)


@st.cache_data(ttl=120)
def carregar_calendario():
    """Eventos do calendário geral (opcional). Devolve None se não houver acesso à planilha."""
    try:
        import gspread
        gc = gspread.service_account_from_dict(json.loads(st.secrets["google_credentials"]))
        aba = gc.open_by_url(st.secrets["planilha_url"]).get_worksheet(0)
        valores = aba.get_all_values()
        if len(valores) < 2:
            return pd.DataFrame()
        cab = [c.strip() for c in valores[0]]
        linhas = [(list(l) + [""] * len(cab))[:len(cab)] for l in valores[1:] if any(str(c).strip() for c in l)]
        df = pd.DataFrame(linhas, columns=cab)
        colunas_cong = [c for c in df.columns if "Congregação -" in c]
        if colunas_cong:
            df["Congregação"] = df[colunas_cong].astype(str).agg("".join, axis=1)
        return df
    except Exception:
        return None


def tela_login():
    _, centro, _ = st.columns([1, 1.6, 1])
    with centro:
        st.markdown(
            '<div class="login-topo"><div class="login-icone">🔒</div>'
            '<h2>Gestão das congregações</h2>'
            '<p>Acesso restrito à liderança. Informe a senha para continuar.</p></div>',
            unsafe_allow_html=True,
        )
        with st.form("form_login"):
            senha = st.text_input("Senha", type="password", placeholder="Digite a senha")
            entrar = st.form_submit_button("Entrar", use_container_width=True)
        if entrar:
            if "senha_gestao" in st.secrets and senha == st.secrets["senha_gestao"]:
                st.session_state["logado"] = True
                st.session_state["msg_login"] = True
                st.rerun()
            else:
                st.error("Senha incorreta. Tente novamente.")


# ---------------------------------------------------------------------------
# Menu lateral
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        f'<div class="sb-topo"><img class="sb-logo" src="{LOGO_URL}" alt="Logo">'
        '<div class="sb-titulo">Gestão das Congregações</div>'
        '<div class="sb-sub">Sistema interno da liderança MEN</div></div>',
        unsafe_allow_html=True,
    )
    if st.session_state["logado"]:
        for nome in PAGINAS:
            ativa = st.session_state["pagina"] == nome
            if st.button(nome, key=f"menu_{nome}", type="primary" if ativa else "secondary",
                         use_container_width=True):
                st.session_state["pagina"] = nome
                st.rerun()
    st.markdown("---")
    st.markdown(
        '<div class="sb-contato">Desenvolvido por <b>Rodolfo Crystian</b><br>'
        'rcrystiandados@gmail.com<br>WhatsApp: (83) 9 9962-3735</div>',
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Conteúdo
# ---------------------------------------------------------------------------
if not st.session_state["logado"]:
    tela_login()
else:
    if st.session_state.pop("msg_login", False):
        try:
            st.toast("Autenticação realizada com sucesso.", icon="✅", duration=3)
        except TypeError:
            st.toast("Autenticação realizada com sucesso.", icon="✅")

    t1, t2 = st.columns([5, 1], vertical_alignment="center")
    t1.markdown(f'<h1 class="titulo-sem-linha">{st.session_state["pagina"]}</h1>', unsafe_allow_html=True)
    if t2.button("Sair", use_container_width=True):
        st.session_state["logado"] = False
        st.rerun()
    st.markdown('<hr class="linha-titulo">', unsafe_allow_html=True)

    calendario = carregar_calendario() if st.session_state["pagina"] == "Eventos" else None
    gestao.renderizar(st.session_state["pagina"], calendario, CONGREGACOES_INICIAIS)
