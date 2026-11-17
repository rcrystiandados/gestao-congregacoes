"""Portal da Congregação MEN: cada congregação administra a sua própria gestão.

Segundo app do mesmo repositório (arquivo principal: portal.py). Usa o mesmo banco e os mesmos Secrets
do sistema da liderança (database_url e a conta de serviço da planilha do calendário).

Cada conta pertence a UMA congregação, criada pela liderança (página "Acessos das congregações"),
e só enxerga e altera os dados dessa congregação. A congregação vem da conta autenticada, nunca de um
campo da tela.
"""
import base64
import html
import re
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

import agenda
import contas_congregacao as contas
import ficha_membro
import gestao
import gestao_db as db
import portal_db

st.set_page_config(page_title="Portal da Congregação MEN", page_icon="⛪", layout="wide",
                   initial_sidebar_state="collapsed")

LOGO_URL = "https://raw.githubusercontent.com/rcrystiandados/app-igreja/main/logo.jpeg"


def _obter_logo_src():
    """Carrega logo.jpeg local em base64 (se existir no repositório) para nunca quebrar a imagem."""
    for caminho in (Path(__file__).resolve().parent / "logo.jpeg", Path("logo.jpeg")):
        if caminho.is_file():
            try:
                b64 = base64.b64encode(caminho.read_bytes()).decode("utf-8")
                return f"data:image/jpeg;base64,{b64}"
            except Exception:
                pass
    return LOGO_URL


LOGO_SRC = _obter_logo_src()

ESTILO = f"""<style>
    :root {{
        --azul: #1E3A8A;
        --azul-escuro: #152C6B;
        --azul-claro: #E8EEFB;
        --fundo: #F5F7FA;
        --borda: #DDE3EC;
        --texto: #1F2937;
    }}

    .stApp {{background: var(--fundo);}}
    header[data-testid="stHeader"] {{background: transparent; display: none;}}
    #MainMenu, footer {{visibility: hidden;}}
    section[data-testid="stSidebar"], div[data-testid="stSidebarCollapsedControl"],
    div[data-testid="collapsedControl"] {{display: none !important;}}

    /* Conteúdo */
    .block-container {{
        padding: 1rem 3rem 4rem 3rem;
        max-width: 1200px;
    }}
    .block-container h1, .block-container h2, .block-container h3, .block-container h4 {{
        color: var(--azul) !important; font-weight: 700 !important;
    }}
    .block-container h1 {{
        font-size: 1.9rem; padding-bottom: .6rem; border-bottom: 2px solid var(--borda);
        margin-bottom: 1.2rem;
    }}
    .block-container p, .block-container label, .block-container li {{color: var(--texto);}}

    /* Cartões e Boxes de opções */
    div[data-testid="stVerticalBlockBorderWrapper"] {{
        background: #FFFFFF;
        border: 1px solid var(--borda) !important;
        border-radius: 10px !important;
        padding: .4rem;
        box-shadow: 0 2px 6px rgba(15, 23, 42, 0.04);
    }}
    .box-titulo {{
        color: var(--azul);
        font-size: 1.15rem;
        font-weight: 700;
        margin-bottom: .35rem;
    }}
    .box-desc {{
        color: #475569;
        font-size: .92rem;
        min-height: 2.8rem;
        margin-bottom: .8rem;
    }}

    /* Indicadores */
    div[data-testid="stMetric"] {{
        background: #FFFFFF; border: 1px solid var(--borda);
        border-radius: 8px; padding: .9rem 1.1rem;
    }}
    div[data-testid="stMetricValue"] {{color: var(--azul);}}

    /* Botões padrão do conteúdo */
    div.stButton > button, div.stFormSubmitButton > button, a[data-testid="stBaseLinkButton-secondary"] {{
        background-color: var(--azul) !important; color: #FFFFFF !important;
        border: none !important; border-radius: 6px !important;
        padding: .55rem 1.4rem !important; font-weight: 600 !important;
    }}
    div.stButton > button *, div.stFormSubmitButton > button * {{color: #FFFFFF !important;}}
    div.stButton > button:hover, div.stFormSubmitButton > button:hover {{
        background-color: var(--azul-escuro) !important;
    }}

    /* Avisos legíveis */
    div[data-testid="stAlert"] {{border-left: 5px solid var(--azul) !important; background-color: #E8EEFB !important;}}
    div[data-testid="stAlert"] * {{background-color: transparent !important; color: #1F2937 !important;}}

    /* Campos */
    div[data-baseweb="input"], div[data-baseweb="select"] > div, div[data-baseweb="base-input"] {{
        background-color: #FFFFFF !important; border-color: #CBD5E1 !important;
    }}
    div[data-testid="stForm"] {{background: #FFFFFF; border: 1px solid var(--borda); border-radius: 8px;}}

    /* ---------- Correções de tema e componentes ---------- */
    :root, .stApp {{color-scheme: light;}}

    div[data-testid="stTextInput"] div[data-baseweb="input"],
    div[data-testid="stTextInput"] div[data-baseweb="base-input"],
    div[data-testid="stTextInput"] input,
    div[data-testid="stTextInput"] button,
    div[data-testid="stNumberInput"] div[data-baseweb="input"],
    div[data-testid="stNumberInput"] div[data-baseweb="base-input"],
    div[data-testid="stNumberInput"] input,
    div[data-testid="stNumberInput"] button {{
        background-color: #FFFFFF !important; color: #111827 !important;
    }}
    div[data-testid="stTextInput"] div[data-baseweb="input"],
    div[data-testid="stNumberInput"] div[data-baseweb="input"] {{border: 1px solid #CBD5E1 !important;}}
    div[data-testid="stTextInput"] svg,
    div[data-testid="stNumberInput"] svg {{fill: #475569 !important;}}

    /* Página de login */
    .login-topo {{text-align: center; margin: 1.5rem 0 1.2rem 0;}}
    .login-topo .login-icone {{
        width: 64px; height: 64px; margin: 0 auto .8rem auto; border-radius: 50%;
        background: var(--azul-claro); display: flex; align-items: center;
        justify-content: center; font-size: 1.8rem;
    }}
    .login-topo h2 {{margin: 0 0 .4rem 0;}}
    .login-topo p {{color: #6B7280 !important; margin: 0;}}

    /* Selects e listas sempre claros */
    div[data-baseweb="select"] > div {{background-color: #FFFFFF !important; border: 1px solid #CBD5E1 !important;}}
    div[data-baseweb="select"] * {{color: #111827 !important;}}
    div[data-baseweb="select"] svg {{fill: #475569 !important;}}
    div[data-baseweb="popover"], div[data-baseweb="popover"] ul,
    div[data-baseweb="popover"] li, div[data-baseweb="menu"] {{
        background-color: #FFFFFF !important; color: #111827 !important;
    }}
    div[data-baseweb="popover"] li:hover {{background-color: #E8EEFB !important;}}
    span[data-baseweb="tag"] {{background-color: #1E3A8A !important;}}
    span[data-baseweb="tag"] * {{color: #FFFFFF !important;}}
    div[data-testid="stDateInput"] div[data-baseweb="input"],
    div[data-testid="stDateInput"] input {{background-color: #FFFFFF !important; color: #111827 !important;}}

    /* Título do painel e botão de link */
    .block-container h1.titulo-sem-linha {{border-bottom: none; padding-bottom: 0; margin: 0;}}
    .block-container hr.linha-titulo {{border: none; border-top: 2px solid #DDE3EC; margin: .6rem 0 1.4rem 0;}}

    .block-container a[data-testid^="stBaseLinkButton"] {{
        background: #FFFFFF !important; border: 1.5px solid #1E3A8A !important;
        border-radius: 6px !important; padding: .55rem 1.4rem !important;
        text-decoration: none !important; transition: background .15s;
    }}
    .block-container a[data-testid^="stBaseLinkButton"],
    .block-container a[data-testid^="stBaseLinkButton"] * {{
        color: #1E3A8A !important; font-weight: 600 !important;
    }}
    .block-container a[data-testid^="stBaseLinkButton"]:hover {{background: #1E3A8A !important;}}
    .block-container a[data-testid^="stBaseLinkButton"]:hover * {{color: #FFFFFF !important;}}

    div[data-testid="stDownloadButton"] button {{
        background-color: #2E7D5B !important; border: none !important; border-radius: 6px !important;
        padding: .65rem 1.6rem !important; font-weight: 700 !important;
    }}
    div[data-testid="stDownloadButton"] button, div[data-testid="stDownloadButton"] button * {{color: #FFFFFF !important;}}
    div[data-testid="stDownloadButton"] button:hover {{background-color: #256649 !important;}}

    /* ---------- Barra de navegação superior limpa (sem cascata) ---------- */
    div.st-key-nav {{
        position: sticky; top: .5rem; z-index: 1000;
        display: flex !important; flex-direction: row !important; flex-wrap: wrap;
        align-items: center !important;
        gap: .5rem !important; background: var(--azul); border: none; border-radius: 10px;
        box-shadow: 0 4px 14px rgba(30,58,138,.25); padding: .55rem 1.2rem; margin-bottom: 1.6rem;
        width: 100% !important;
    }}
    div.st-key-nav > div {{
        width: auto !important; flex: 0 0 auto !important;
        margin: 0 !important; display: flex !important; align-items: center !important;
    }}

    /* Botão de Início com a imagem da Logo no canto esquerdo */
    div.st-key-nav .st-key-nav_inicio div.stButton > button,
    div.st-key-nav div.st-key-nav_inicio > button {{
        background-color: #FFFFFF !important;
        background-image: url("{LOGO_SRC}") !important;
        background-size: contain !important;
        background-repeat: no-repeat !important;
        background-position: center !important;
        width: 96px !important;
        height: 44px !important;
        min-height: 44px !important;
        padding: 4px 8px !important;
        border-radius: 8px !important;
        border: 2px solid #FFFFFF !important;
        margin-right: .6rem !important;
        box-shadow: 0 2px 6px rgba(0,0,0,.15) !important;
    }}
    div.st-key-nav .st-key-nav_inicio div.stButton > button *,
    div.st-key-nav div.st-key-nav_inicio > button * {{
        color: transparent !important;
        font-size: 0 !important;
    }}
    div.st-key-nav .st-key-nav_inicio div.stButton > button:hover,
    div.st-key-nav div.st-key-nav_inicio > button:hover {{
        opacity: .92;
        transform: translateY(-1px);
    }}

    /* Botões das abas na barra azul */
    div.st-key-nav div.stButton > button {{
        background: transparent !important; border: none !important; box-shadow: none !important;
        border-radius: 6px !important; padding: .5rem 1rem !important;
        height: 42px !important; min-height: 42px !important; white-space: nowrap;
        display: inline-flex !important; align-items: center !important;
        justify-content: center; text-align: center;
    }}
    div.st-key-nav div.stButton > button * {{
        color: #FFFFFF !important; font-weight: 600 !important; font-size: .92rem !important;
        text-transform: uppercase; letter-spacing: .03em;
    }}
    div.st-key-nav div.stButton > button:hover {{
        background: rgba(255,255,255,.15) !important;
    }}
    div.st-key-nav div.stButton > button[kind="primary"],
    div.st-key-nav div.stButton > button[data-testid="stBaseButton-primary"] {{
        background: rgba(255,255,255,.12) !important;
        border-radius: 6px 6px 0 0 !important;
        box-shadow: inset 0 -3px 0 #FFFFFF !important;
    }}

    /* Saudação e botão SAIR no canto direito */
    div.st-key-nav > div:has(.nav-ola) {{
        margin-left: auto !important;
    }}
    div.st-key-nav .nav-ola {{
        font-size: .95rem; color: #FFFFFF; white-space: nowrap;
        padding: 0 .6rem; height: 42px;
        display: inline-flex; align-items: center;
    }}
    div.st-key-nav .st-key-nav_sair div.stButton > button,
    div.st-key-nav div.st-key-nav_sair > button {{
        border: 1.5px solid #FFFFFF !important; border-radius: 6px !important;
        padding: .4rem 1.1rem !important; height: 38px !important; min-height: 38px !important;
        background: transparent !important; box-shadow: none !important;
    }}
    div.st-key-nav .st-key-nav_sair div.stButton > button:hover,
    div.st-key-nav div.st-key-nav_sair > button:hover {{
        background: #FFFFFF !important;
    }}
    div.st-key-nav .st-key-nav_sair div.stButton > button:hover *,
    div.st-key-nav div.st-key-nav_sair > button:hover * {{
        color: var(--azul) !important;
    }}

    .rodape {{text-align: center; font-size: .8rem; color: #6B7280; margin-top: 2.5rem;}}
</style>
"""
st.markdown(ESTILO, unsafe_allow_html=True)

# Abas principais da barra superior (sem menu cascata)
ABAS_MENU = [
    ("Membresia", "MEMBRESIA"),
    ("Financeiro", "FINANCEIRO"),
    ("Calendário", "CALENDÁRIO"),
    ("Minha congregação", "MINHA CONGREGAÇÃO"),
]
PAGINAS = {"Início", "Membresia", "Financeiro", "Calendário", "Minha congregação"}

# Boxes internos de cada aba
OPCOES_MEMBRESIA = [
    ("Membros", "ROL de Membros", "Consulte, filtre, edite e exporte a lista de membros da congregação."),
    ("Novo membro", "Novo Membro", "Cadastre membros no ROL ou emita fichas de entrada por Batismo e Transferência."),
    ("Departamentos", "Departamentos", "Gerencie os departamentos ativos e a liderança local da congregação."),
    ("Eventos internos", "Eventos Internos", "Cadastre e acompanhe as programações e eventos internos da congregação."),
]

OPCOES_ENTRADA = [
    ("rol", "Inserção no ROL de Membros", "Cadastro direto do membro no ROL, sem gerar ficha em PDF."),
    ("Batismo", "Entrada por Batismo", "Ficha completa de entrada de quem foi batizado, com PDF para imprimir."),
    ("Transferência", "Entrada por Transferência", "Ficha de entrada de quem vem de outra igreja, com PDF."),
]

OPCOES_FINANCEIRO = [
    ("extrato", "Extrato e Relatório", "Consulte todos os lançamentos do mês, exclua registros ou baixe a planilha Excel/CSV."),
    ("entrada", "Nova Entrada (Dízimos / Ofertas)", "Registre dízimos vinculados aos membros e ofertas de cultos ou departamentos."),
    ("saida", "Nova Saída (Despesas)", "Registre pagamentos de água, energia, manutenção, eventos e repasses."),
]

OPCOES_CONGREGACAO = [
    ("dados", "Dados da Congregação", "Atualize o endereço, a data de fundação e o contato do responsável pela congregação."),
    ("conta", "Minha Conta e Senha", "Visualize os seus dados de acesso e altere a sua senha do portal."),
]

ROTULO_STATUS = {
    "pendente": "Aguardando a liderança",
    "aprovado": "Aprovado",
    "recusado": "Recusado",
    "cancelado": "Cancelado por você",
}

MESES_NOMES = [
    (1, "Janeiro"), (2, "Fevereiro"), (3, "Março"), (4, "Abril"),
    (5, "Maio"), (6, "Junho"), (7, "Julho"), (8, "Agosto"),
    (9, "Setembro"), (10, "Outubro"), (11, "Novembro"), (12, "Dezembro"),
]


# ---------------------------------------------------------------------------
# Banco e sessão
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def _preparar(_banco, _versao_schema=2):
    portal_db.criar_tabelas(_banco)
    ficha_membro.criar_tabela(_banco)
    return True


def _banco():
    banco = gestao._banco()
    if banco is not None:
        _preparar(banco)
    return banco


def _sair():
    for chave in list(st.session_state.keys()):
        del st.session_state[chave]


def tela_acesso(banco):
    st.markdown('<div class="login-topo"><div class="login-icone">⛪</div><h2>Portal da Congregação</h2>'
                '<p>Entre com o e-mail e a senha fornecidos pela liderança.</p></div>', unsafe_allow_html=True)
    _, centro, _ = st.columns([1, 1.2, 1])
    with centro:
        with st.form("login"):
            login = st.text_input("E-mail")
            senha = st.text_input("Senha", type="password")
            entrou = st.form_submit_button("Entrar", use_container_width=True)
        if entrou:
            r = contas.autenticar(banco, login, senha)
            if r["ok"]:
                st.session_state["conta_id"] = r["usuario"]["id"]
                st.rerun()
            st.error(r["erro"])
            if r.get("restantes"):
                st.caption(f"Restam {r['restantes']} tentativa(s).")
        st.caption("Esqueceu a senha? Peça à liderança uma senha temporária.")


def tela_troca_obrigatoria(banco, conta):
    st.markdown("#### Defina uma nova senha")
    st.caption(f"Olá, {conta['nome']}. Você entrou com uma senha temporária. Crie a sua própria senha para continuar "
               "(mínimo de 8 caracteres, com letras e números).")
    with st.form("troca_obrigatoria"):
        nova = st.text_input("Nova senha", type="password")
        conf = st.text_input("Repita a nova senha", type="password")
        salvar = st.form_submit_button("Salvar senha")
    if salvar:
        if nova != conf:
            st.error("As senhas não conferem.")
        else:
            try:
                contas.definir_nova_senha(banco, conta["id"], nova)
            except ValueError as erro:
                st.error(str(erro))
            else:
                st.rerun()
    if st.button("Sair"):
        _sair()
        st.rerun()


# ---------------------------------------------------------------------------
# Utilitários e renderização de Boxes
# ---------------------------------------------------------------------------
def _fmt(d):
    return d.strftime("%d/%m/%Y") if d is not None and not pd.isna(d) else ""


def _periodo(ini, fim):
    return _fmt(ini) if ini == fim else f"{_fmt(ini)} a {_fmt(fim)}"


def _moeda(valor