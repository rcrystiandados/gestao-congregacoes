"""Portal da Congregação MEN: cada congregação administra a sua própria gestão.

Segundo app do mesmo repositório (arquivo principal: portal.py). Usa o mesmo banco e os mesmos Secrets
do sistema da liderança (database_url e a conta de serviço da planilha do calendário).

Cada conta pertence a UMA congregação, criada pela liderança (página "Acessos das congregações"),
e só enxerga e altera os dados dessa congregação. A congregação vem da conta autenticada, nunca de um
campo da tela.
"""
import html
import re
from datetime import date

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

LOGO_URL = "https://github.com/rcrystiandados/app-igreja/blob/main/logo.jpeg?raw=true"

# Mesmo visual do sistema da liderança (azul MEN, barra superior em bloco azul, campos claros).
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
        padding: 1rem 3rem 4rem 3rem;
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

    /* Botões padrão do conteúdo */
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
    div[data-testid="stAlert"] {border-left: 5px solid var(--azul) !important; background-color: #E8EEFB !important;}
    div[data-testid="stAlert"] * {background-color: transparent !important; color: #1F2937 !important;}

    /* Campos */
    div[data-baseweb="input"], div[data-baseweb="select"] > div, div[data-baseweb="base-input"] {
        background-color: #FFFFFF !important; border-color: #CBD5E1 !important;
    }
    div[data-testid="stForm"] {background: #FFFFFF; border: 1px solid var(--borda); border-radius: 8px;}

    /* ---------- Correções de tema e componentes ---------- */
    :root, .stApp {color-scheme: light;}

    /* Campos de texto e senha sempre claros */
    div[data-testid="stTextInput"] div[data-baseweb="input"],
    div[data-testid="stTextInput"] div[data-baseweb="base-input"],
    div[data-testid="stTextInput"] input,
    div[data-testid="stTextInput"] button {
        background-color: #FFFFFF !important; color: #111827 !important;
    }
    div[data-testid="stTextInput"] div[data-baseweb="input"] {border: 1px solid #CBD5E1 !important;}
    div[data-testid="stTextInput"] svg {fill: #475569 !important;}

    /* Página de login */
    .login-topo {text-align: center; margin: 1.5rem 0 1.2rem 0;}
    .login-topo .login-icone {
        width: 64px; height: 64px; margin: 0 auto .8rem auto; border-radius: 50%;
        background: var(--azul-claro); display: flex; align-items: center;
        justify-content: center; font-size: 1.8rem;
    }
    .login-topo h2 {margin: 0 0 .4rem 0;}
    .login-topo p {color: #6B7280 !important; margin: 0;}

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

    /* ---------- Título do painel e botão de link ---------- */
    .block-container h1.titulo-sem-linha {border-bottom: none; padding-bottom: 0; margin: 0;}
    .block-container hr.linha-titulo {border: none; border-top: 2px solid #DDE3EC; margin: .6rem 0 1.4rem 0;}

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

    /* ---------- Barra de navegação superior em BLOCO AZUL ---------- */
    section[data-testid="stSidebar"], div[data-testid="stSidebarCollapsedControl"],
    div[data-testid="collapsedControl"] {display: none !important;}
    header[data-testid="stHeader"] {display: none;}

    div.st-key-nav {
        position: sticky; top: .5rem; z-index: 1000;
        display: flex !important; flex-direction: row !important; flex-wrap: wrap; align-items: center;
        gap: .35rem !important; background: var(--azul); border: none; border-radius: 10px;
        box-shadow: 0 4px 14px rgba(30,58,138,.25); padding: .6rem 1.2rem; margin-bottom: 1.6rem;
    }
    div.st-key-nav > div {width: auto !important; flex: 0 0 auto;}

    /* Logo no canto esquerdo */
    div.st-key-nav .nav-logo {
        height: 46px; width: auto; background: #FFFFFF; padding: 4px 10px;
        border-radius: 8px; margin-right: 1.2rem; display: block;
    }

    /* Botões de primeiro nível na barra azul */
    div.st-key-nav div.stButton > button {
        background: transparent !important; border: none !important; box-shadow: none !important;
        border-radius: 6px !important; padding: .55rem .95rem !important; white-space: nowrap;
        justify-content: flex-start; text-align: left;
    }
    div.st-key-nav div.stButton > button * {
        color: #FFFFFF !important; font-weight: 600 !important; font-size: .92rem;
        text-transform: uppercase; letter-spacing: .02em;
        justify-content: flex-start; text-align: left;
    }
    div.st-key-nav div.stButton > button:hover {background: rgba(255,255,255,.15) !important;}
    div.st-key-nav div.stButton > button[kind="primary"],
    div.st-key-nav div.stButton > button[data-testid="stBaseButton-primary"] {
        background: rgba(255,255,255,.12) !important;
        box-shadow: inset 0 -3px 0 #FFFFFF !important;
    }

    /* Rótulos de grupos que abrem menu suspenso (ex.: MEMBRESIA, MINHA CONGREGAÇÃO) */
    div.st-key-nav .nav-rot {
        padding: .55rem .95rem; font-weight: 600; font-size: .92rem; color: #FFFFFF;
        text-transform: uppercase; letter-spacing: .02em;
        border-radius: 6px; cursor: pointer; white-space: nowrap;
    }
    div.st-key-nav .nav-rot.ativo {
        background: rgba(255,255,255,.12);
        box-shadow: inset 0 -3px 0 #FFFFFF;
    }
    div.st-key-nav [class*="st-key-ntop_"]:hover .nav-rot {
        background: rgba(255,255,255,.15); color: #FFFFFF;
    }

    /* Painéis suspensos (dropdowns claros) */
    div.st-key-nav [class*="st-key-ntop_"], div.st-key-nav [class*="st-key-nsub_"] {position: relative;}
    div.st-key-nav [class*="st-key-ndrop_"], div.st-key-nav [class*="st-key-nfly_"] {
        display: none; position: absolute; min-width: 260px; background: #FFFFFF;
        border: 1px solid #DDE3EC; border-radius: 0 0 10px 10px; padding: .4rem; gap: .1rem;
        box-shadow: 0 14px 30px rgba(15,23,42,.18);
    }
    div.st-key-nav [class*="st-key-ndrop_"] {top: 100%; left: 0; border-top: 3px solid var(--azul); z-index: 1001;}
    div.st-key-nav [class*="st-key-nfly_"] {
        top: -.4rem; left: 100%; border-radius: 10px; z-index: 1002;
        border-top: 3px solid var(--azul);
    }
    div.st-key-nav [class*="st-key-ntop_"]:hover [class*="st-key-ndrop_"],
    div.st-key-nav [class*="st-key-nsub_"]:hover [class*="st-key-nfly_"] {display: flex;}
    div.st-key-nav [class*="st-key-ndrop_"] [data-testid="stElementContainer"],
    div.st-key-nav [class*="st-key-nfly_"] [data-testid="stElementContainer"] {width: 100% !important;}

    /* Botões internos dos painéis suspensos (fundo claro e texto escuro) */
    div.st-key-nav [class*="st-key-ndrop_"] div.stButton > button,
    div.st-key-nav [class*="st-key-nfly_"] div.stButton > button {
        background: transparent !important; box-shadow: none !important;
    }
    div.st-key-nav [class*="st-key-ndrop_"] div.stButton > button *,
    div.st-key-nav [class*="st-key-nfly_"] div.stButton > button * {
        color: #1F2937 !important; font-weight: 500 !important;
        text-transform: none !important; letter-spacing: normal !important;
    }
    div.st-key-nav [class*="st-key-ndrop_"] div.stButton > button:hover,
    div.st-key-nav [class*="st-key-nfly_"] div.stButton > button:hover {
        background: #E8EEFB !important;
    }
    div.st-key-nav [class*="st-key-ndrop_"] div.stButton > button:hover *,
    div.st-key-nav [class*="st-key-nfly_"] div.stButton > button:hover * {
        color: var(--azul) !important;
    }
    div.st-key-nav [class*="st-key-ndrop_"] div.stButton > button[kind="primary"],
    div.st-key-nav [class*="st-key-ndrop_"] div.stButton > button[data-testid="stBaseButton-primary"],
    div.st-key-nav [class*="st-key-nfly_"] div.stButton > button[kind="primary"],
    div.st-key-nav [class*="st-key-nfly_"] div.stButton > button[data-testid="stBaseButton-primary"] {
        background: #E8EEFB !important; box-shadow: inset 3px 0 0 var(--azul) !important;
    }
    div.st-key-nav [class*="st-key-ndrop_"] div.stButton > button[kind="primary"] *,
    div.st-key-nav [class*="st-key-ndrop_"] div.stButton > button[data-testid="stBaseButton-primary"] *,
    div.st-key-nav [class*="st-key-nfly_"] div.stButton > button[kind="primary"] *,
    div.st-key-nav [class*="st-key-nfly_"] div.stButton > button[data-testid="stBaseButton-primary"] * {
        color: var(--azul) !important; font-weight: 700 !important;
    }

    /* Usuário e botão Sair no canto direito */
    div.st-key-nav div.st-key-nav_usuario {
        margin-left: auto; display: flex !important; flex-direction: row !important;
        align-items: center; gap: .85rem !important;
    }
    div.st-key-nav .nav-ola {font-size: .95rem; color: #FFFFFF; white-space: nowrap;}
    div.st-key-nav div.st-key-nav_sair div.stButton > button {
        border: 1.5px solid #FFFFFF !important; border-radius: 6px !important;
        padding: .45rem 1.1rem !important; background: transparent !important;
    }
    div.st-key-nav div.st-key-nav_sair div.stButton > button:hover {
        background: #FFFFFF !important;
    }
    div.st-key-nav div.st-key-nav_sair div.stButton > button:hover * {
        color: var(--azul) !important;
    }

    .rodape {text-align: center; font-size: .8rem; color: #6B7280; margin-top: 2.5rem;}
</style>
"""
st.markdown(ESTILO, unsafe_allow_html=True)

# Sequência definida: INÍCIO | MEMBRESIA | FINANCEIRO | CALENDÁRIO | MINHA CONGREGAÇÃO
MENU = [
    {"rotulo": "Início", "pagina": "Início"},
    {"rotulo": "Membresia", "filhos": [
        {"rotulo": "Membros", "pagina": "Membros"},
        {"rotulo": "Novo membro", "pagina": "Novo membro", "filhos": [
            {"rotulo": "Inserção no ROL de Membros", "pagina": "Novo membro", "etapa": "rol"},
            {"rotulo": "Entrada por Batismo", "pagina": "Novo membro", "etapa": "Batismo"},
            {"rotulo": "Entrada por Transferência", "pagina": "Novo membro", "etapa": "Transferência"},
        ]},
        {"rotulo": "Departamentos", "pagina": "Departamentos"},
        {"rotulo": "Eventos internos", "pagina": "Eventos internos"},
    ]},
    {"rotulo": "Financeiro", "pagina": "Financeiro"},
    {"rotulo": "Calendário", "pagina": "Pedir remarcação"},
    {"rotulo": "Minha congregação", "filhos": [
        {"rotulo": "Dados da congregação", "pagina": "Minha congregação"},
        {"rotulo": "Minha conta", "pagina": "Minha conta"},
    ]},
]


def _paginas_do_menu(nos):
    for no in nos:
        if no.get("pagina"):
            yield no["pagina"]
        yield from _paginas_do_menu(no.get("filhos", []))


PAGINAS = set(_paginas_do_menu(MENU))
OPCOES_ENTRADA = [
    ("rol", "Inserção no ROL de Membros", "Cadastro do membro no ROL, sem gerar ficha."),
    ("Batismo", "Entrada por Batismo", "Ficha de entrada de quem foi batizado, com PDF para imprimir."),
    ("Transferência", "Entrada por Transferência", "Ficha de entrada de quem vem de outra igreja, com PDF."),
]
PAGINAS_GESTAO = ("Membros", "Departamentos", "Eventos internos", "Financeiro")
ROTULO_STATUS = {"pendente": "Aguardando a liderança", "aprovado": "Aprovado",
                 "recusado": "Recusado", "cancelado": "Cancelado por você"}


# ---------------------------------------------------------------------------
# Banco e sessão
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def _preparar(_banco):
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
# Utilitários
# ---------------------------------------------------------------------------
def _fmt(d):
    return d.strftime("%d/%m/%Y") if d is not None and not pd.isna(d) else ""


def _periodo(ini, fim):
    return _fmt(ini) if ini == fim else f"{_fmt(ini)} a {_fmt(fim)}"


def _eventos_da_congregacao(regs, nome_cong, so_futuros=True):
    hoje = pd.Timestamp.today().normalize()
    alvo = gestao._norm(nome_cong)
    meus = [r for r in regs if r["linha"] is not None and gestao._norm(r["congregacao"]) == alvo]
    if so_futuros:
        meus = [r for r in meus if r["fim"] >= hoje]
    return sorted(meus, key=lambda r: (r["ini"], r["nome"]))


def _carregar_calendario():
    try:
        return agenda.carregar_calendario()
    except Exception as erro:
        st.warning(f"Não foi possível ler o calendário agora: {erro}")
        return None


# ---------------------------------------------------------------------------
# Início
# ---------------------------------------------------------------------------
def pagina_inicio(banco, conta, calendario):
    cid = conta["congregacao_id"]
    membros = db.listar_membros(banco, cid, situacao="Ativo")
    deps = db.listar_departamentos(banco, cid, apenas_ativos=True)
    pedidos = portal_db.listar_pedidos(banco, cid)
    regs = agenda.registros_da_planilha(calendario) if calendario is not None else []
    proximos = _eventos_da_congregacao(regs, conta["congregacao"])

    st.markdown(f"**{conta['congregacao']}** · Região {conta['regiao'] or '-'}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Membros ativos", len(membros))
    c2.metric("Departamentos", len(deps))
    c3.metric("Próximos eventos no calendário", len(proximos))
    c4.metric("Pedidos aguardando a liderança", sum(1 for p in pedidos if p["status"] == "pendente"))

    st.markdown("#### Próximos eventos no calendário")
    if proximos:
        st.dataframe(pd.DataFrame([{"Período": _periodo(r["ini"], r["fim"]), "Evento": r["nome"], "Tipo": r["tipo"]}
                                   for r in proximos[:6]]), use_container_width=True, hide_index=True)
    else:
        st.caption("Nenhum evento futuro desta congregação no calendário.")

    st.markdown("#### Aniversariantes do mês")
    mes = pd.Timestamp.today().month
    aniv = sorted((m for m in membros if m["data_nascimento"] and m["data_nascimento"].month == mes),
                  key=lambda m: (m["data_nascimento"].day, m["nome"]))
    if aniv:
        st.dataframe(pd.DataFrame([{"Dia": m["data_nascimento"].day, "Nome": m["nome"]} for m in aniv]),
                     use_container_width=True, hide_index=True)
    else:
        st.caption("Nenhum aniversariante neste mês.")

    respondidos = [p for p in pedidos if p["status"] in ("aprovado", "recusado")][:3]
    if respondidos:
        st.markdown("#### Respostas da liderança")
        for p in respondidos:
            icone = "✅" if p["status"] == "aprovado" else "❌"
            st.markdown(f"{icone} **{p['evento_nome']}**: {ROTULO_STATUS[p['status']].lower()}"
                        + (f" · {p['resposta']}" if p["resposta"] else ""))


# ---------------------------------------------------------------------------
# Pedir remarcação
# ---------------------------------------------------------------------------
def pagina_remarcacao(banco, conta, calendario):
    cid, nome_cong = conta["congregacao_id"], conta["congregacao"]
    pedidos = portal_db.listar_pedidos(banco, cid)

    pend = st.session_state.pop("pr_pendente", None)
    if pend:
        st.session_state["pr_ini"], st.session_state["pr_fim"] = pend
    msg = st.session_state.pop("pr_msg", None)
    if msg:
        st.success(msg)

    regs = agenda.registros_da_planilha(calendario) if calendario is not None else []
    meus = _eventos_da_congregacao(regs, nome_cong)

    st.markdown("#### 1. Escolha o evento")
    st.caption("Os pedidos vão para a liderança, que aprova ou recusa. A data só muda no calendário "
               "depois da aprovação.")
    if calendario is None:
        st.info("O calendário não está disponível agora. Tente de novo em alguns minutos.")
    elif not meus:
        st.info("Esta congregação não tem eventos futuros no calendário.")
    else:
        por_linha = {r["linha"]: r for r in meus}
        linha = st.selectbox("Evento da congregação", list(por_linha.keys()), key="pr_evento",
                             format_func=lambda l: f"{_periodo(por_linha[l]['ini'], por_linha[l]['fim'])} - "
                                                   f"{por_linha[l]['nome']}")
        alvo = por_linha[linha]
        with st.container(border=True):
            st.markdown(f"**{alvo['nome']}**  \n{alvo['tipo']} · Região {alvo['regiao']}  \n"
                        f"Período atual: **{_periodo(alvo['ini'], alvo['fim'])}**")

        existente = next((p for p in pedidos if p["status"] == "pendente" and p["evento_linha"] == linha), None)
        if existente:
            st.info(f"Já existe um pedido aguardando a liderança para este evento: "
                    f"{_periodo(existente['ini_novo'], existente['fim_novo'])}.")
            if st.button("Cancelar este pedido", key=f"pr_cancel_{existente['id']}"):
                portal_db.cancelar_pedido(banco, existente["id"], cid)
                st.session_state["pr_msg"] = "Pedido cancelado."
                st.rerun()
        else:
            _formulario_pedido(banco, conta, alvo, regs)

    st.markdown("#### Meus pedidos")
    if pedidos:
        st.dataframe(pd.DataFrame([{
            "Pedido em": p["criado_em"].strftime("%d/%m/%Y") if hasattr(p["criado_em"], "strftime")
            else str(p["criado_em"])[:10],
            "Evento": p["evento_nome"], "Período atual": _periodo(p["ini_atual"], p["fim_atual"]),
            "Nova data pedida": _periodo(p["ini_novo"], p["fim_novo"]),
            "Situação": ROTULO_STATUS.get(p["status"], p["status"]), "Resposta": p["resposta"] or "",
        } for p in pedidos]), use_container_width=True, hide_index=True)
    else:
        st.caption("Nenhum pedido feito até agora.")


def _formulario_pedido(banco, conta, alvo, regs):
    linha = alvo["linha"]
    if (st.session_state.get("pr_ultimo") != linha
            or "pr_ini" not in st.session_state or "pr_fim" not in st.session_state):
        st.session_state["pr_ultimo"] = linha
        st.session_state["pr_ini"], st.session_state["pr_fim"] = alvo["ini"].date(), alvo["fim"].date()

    st.markdown("#### 2. Escolha a nova data")
    sugestoes = agenda.sugerir_datas(alvo, regs, limite=2) or \
        agenda.sugerir_datas(alvo, regs, mesmo_dia_semana=False, limite=2)
    if sugestoes:
        st.caption("Datas livres na sua região, sem feriados:")
        for i, sg in enumerate(sugestoes):
            c1, c2 = st.columns([4, 1.4], vertical_alignment="center")
            c1.markdown(f"**{agenda.fmt_periodo(sg['ini'].date(), sg['fim'].date())}**")
            if c2.button("Usar esta data", key=f"pr_sug_{linha}_{i}", use_container_width=True):
                st.session_state["pr_pendente"] = (sg["ini"].date(), sg["fim"].date())
                st.rerun()
    d1, d2 = st.columns(2)
    novo_ini = d1.date_input("Nova data de início", format="DD/MM/YYYY", key="pr_ini")
    if st.session_state.get("pr_fim") is None or st.session_state["pr_fim"] < novo_ini:
        st.session_state["pr_fim"] = novo_ini
    novo_fim = d2.date_input("Nova data final", format="DD/MM/YYYY", min_value=novo_ini, key="pr_fim")

    cand = dict(alvo, ini=pd.Timestamp(novo_ini), fim=pd.Timestamp(novo_fim))
    conflitos = agenda.choques_do_novo(cand, [r for r in regs if r["linha"] != linha])
    if conflitos:
        st.warning("Esta data coincide com outro evento da mesma região: "
                   + "; ".join(agenda.descrever(c) for c, _m in conflitos)
                   + ". A liderança pode recusar o pedido.")
    else:
        st.success("Sem choque com outros eventos da sua região.")
    feriados = agenda.feriados_no_periodo(novo_ini, novo_fim)
    if feriados:
        st.warning("Feriados no período: " + "; ".join(f"{d:%d/%m} ({n})" for d, n in feriados) + ".")

    st.markdown("#### 3. Explique o motivo")
    motivo = st.text_area("Motivo do pedido", key="pr_motivo", height=90,
                          placeholder="Ex.: o templo estará em reforma na data original.")
    igual = novo_ini == alvo["ini"].date() and novo_fim == alvo["fim"].date()
    if igual:
        st.caption("Escolha uma data diferente da atual para enviar o pedido.")
    if st.button("Enviar pedido à liderança", disabled=igual):
        try:
            portal_db.criar_pedido(banco, {
                "congregacao_id": conta["congregacao_id"], "conta_id": conta["id"], "evento_linha": linha,
                "evento_nome": alvo["nome"], "evento_regiao": alvo["regiao"],
                "ini_atual": alvo["ini"].date(), "fim_atual": alvo["fim"].date(),
                "ini_novo": novo_ini, "fim_novo": novo_fim, "motivo": motivo})
        except ValueError as erro:
            st.error(str(erro))
        else:
            st.session_state.pop("pr_motivo", None)
            st.session_state["pr_msg"] = "Pedido enviado. A liderança vai analisar e responder aqui."
            st.rerun()


# ---------------------------------------------------------------------------
# Novo membro: ficha de entrada (batismo ou transferência) com PDF
# ---------------------------------------------------------------------------
def _botao_pdf(rotulo, dados, tipo, chave):
    nome = db._sem_acento(dados.get("nome") or "em_branco").replace(" ", "_")
    arquivo = f"ficha_{db._sem_acento(tipo)}_{nome}.pdf"
    st.download_button(rotulo, data=ficha_membro.gerar_pdf(dados, tipo), file_name=arquivo,
                       mime="application/pdf", key=chave)


def _escolha_tipo_entrada():
    st.markdown("#### Qual é o tipo de cadastro?")
    st.caption("Escolha uma opção para abrir a página correspondente.")
    for col, (etapa, titulo, texto) in zip(st.columns(3), OPCOES_ENTRADA):
        with col, st.container(border=True):
            st.markdown(f"**{titulo}**")
            st.caption(texto)
            if st.button("Selecionar", key=f"nm_esc_{etapa}", use_container_width=True):
                st.session_state["etapa_portal"] = etapa
                st.rerun()


def pagina_novo_membro(banco, conta):
    etapa = st.session_state.get("etapa_portal")
    if etapa not in [e for e, _, _ in OPCOES_ENTRADA]:
        _escolha_tipo_entrada()
        return
    if st.button("← Trocar o tipo de cadastro", key="nm_voltar"):
        st.session_state["etapa_portal"] = None
        st.rerun()
    if etapa == "rol":
        st.markdown("#### Inserção no ROL de Membros")
        gestao.renderizar_congregacao("Novo membro", conta["congregacao_id"], None)
    else:
        _ficha_entrada(banco, conta, etapa)


def _ficha_entrada(banco, conta, tipo):
    cid = conta["congregacao_id"]
    st.caption(gestao.AVISO_PORTAL)
    msg = st.session_state.pop("fn_msg", None)
    if msg:
        st.success(msg)
    ultimo = st.session_state.get("fn_ultimo")
    if ultimo:
        d = ficha_membro.obter_ficha(banco, ultimo["membro_id"], cid)
        if d:
            _botao_pdf(f"Baixar a ficha em PDF: {d['nome']}", d, ultimo["tipo"], "fn_dl_ultimo")

    with st.expander("Ficha em branco, para imprimir e preencher à mão"):
        _botao_pdf(f"Ficha de {tipo} (em branco)", {}, tipo, f"fn_branco_{tipo}")

    st.markdown(f"#### Nova ficha de membro · Entrada por {tipo}")
    v = st.session_state.get("fn_v", 0)
    k = lambda nome: f"fn_{nome}_{v}"

    c1, c2 = st.columns([1, 2])
    local_tipo = c1.radio("A entrada é na", list(ficha_membro.LOCAIS), horizontal=True, key=k("local"))
    local_nome = c2.text_input("Qual?", value=conta["congregacao"] if local_tipo == "Congregação" else "",
                               key=k("local_nome") + local_tipo)

    nome = st.text_input("Nome completo", key=k("nome"))
    c1, c2, c3 = st.columns(3)
    nasc = c1.date_input("Data de nascimento", value=None, min_value=date(1900, 1, 1), max_value=date.today(),
                         format="DD/MM/YYYY", key=k("nasc"))
    conversao = c2.date_input("Data de sua conversão", value=None, min_value=date(1900, 1, 1),
                              max_value=date.today(), format="DD/MM/YYYY", key=k("conv"))
    sexos = ["", "Masculino", "Feminino"]
    sexo = c3.selectbox("Sexo", sexos, key=k("sexo"))

    estado_civil = st.radio("Estado civil", list(ficha_membro.ESTADOS_CIVIS), index=None, horizontal=True,
                            key=k("ec"))
    conjuge = ""
    if estado_civil == "Casado civilmente":
        st.caption("Caso esteja casado civilmente, trazer uma cópia da certidão de casamento.")
        conjuge = st.text_input("Nome do cônjuge", key=k("conj"))

    c1, c2 = st.columns(2)
    pai = c1.text_input("Nome do pai", key=k("pai"))
    mae = c2.text_input("Nome da mãe", key=k("mae"))
    c1, c2, c3 = st.columns([1, 2, 1])
    nacionalidade = c1.text_input("Nacionalidade", value="Brasileira", key=k("nac"))
    cidade = c2.text_input("Cidade onde nasceu", key=k("cidade"))
    uf = c3.text_input("Estado", key=k("uf"), max_chars=2, placeholder="PB")
    residencia = st.text_input("Residência (endereço completo)", key=k("res"))

    chave_tel = k("tel")
    if chave_tel not in st.session_state:
        st.session_state[chave_tel] = ""
    c1, c2, c3 = st.columns(3)
    email = c1.text_input("E-mail", key=k("email"))
    telefone = c2.text_input("Telefone / WhatsApp", key=chave_tel, placeholder="(83) 9 9999-9999",
                             on_change=gestao._fmt_telefone, args=(chave_tel,))
    profissao = c3.text_input("Profissão", key=k("prof"))

    c1, c2 = st.columns(2)
    batismo = c1.date_input("Batismo em", value=None, min_value=date(1900, 1, 1), format="DD/MM/YYYY", key=k("bat"))
    batizado_por = c2.text_input("Batizado pelo Rev.", key=k("revb"))

    igreja_origem = pastor = funcao = ""
    exercia = None
    if tipo == "Transferência":
        c1, c2 = st.columns(2)
        igreja_origem = c1.text_input("Está vindo de qual igreja?", key=k("igr"))
        pastor = c2.text_input("Nome do pastor", key=k("pastor"))
        exercia = st.radio("Exercia alguma função nesta igreja?", ["Sim", "Não"], index=None, horizontal=True,
                           key=k("exer"))
        if exercia == "Sim":
            funcao = st.text_input("Qual função?", key=k("func"))

    inicio = st.date_input("Início como membro da IECCG (preenchido pela secretaria)", value=None,
                           min_value=date(1900, 1, 1), format="DD/MM/YYYY", key=k("ini"))
    st.caption("Se deixar o início em branco, o cadastro usa a data de hoje como entrada e o campo "
               "sai em branco na ficha, para a secretaria preencher.")

    if st.button("Salvar membro e gerar a ficha", key=k("salvar")):
        dados_membro = {"congregacao_id": cid, "nome": nome.strip(), "data_nascimento": nasc, "sexo": sexo,
                        "telefone": telefone.strip(), "email": email.strip(), "cargo": "Membro",
                        "situacao": "Ativo", "data_entrada": inicio or date.today(), "data_batismo": batismo}
        erro = gestao._validar_membro(dados_membro)
        if erro:
            st.error(erro)
        elif db.membro_existe(banco, cid, dados_membro["nome"], nasc):
            st.error("Já existe um membro com este nome e data de nascimento nesta congregação.")
        else:
            membro_id = db.criar_membro(banco, dados_membro)
            try:
                ficha_membro.salvar_ficha(banco, membro_id, cid, {
                    "tipo": tipo, "local_tipo": local_tipo, "local_nome": local_nome,
                    "data_conversao": conversao, "estado_civil": estado_civil, "nome_conjuge": conjuge,
                    "nome_pai": pai, "nome_mae": mae, "nacionalidade": nacionalidade, "cidade_natal": cidade,
                    "estado_natal": uf.upper(), "residencia": residencia, "profissao": profissao,
                    "batizado_por": batizado_por, "igreja_origem": igreja_origem, "pastor_origem": pastor,
                    "exercia_funcao": exercia, "funcao_anterior": funcao, "inicio_membro": inicio})
            except Exception as erro_ficha:
                st.error(f"O membro foi cadastrado, mas a ficha não foi salva: {erro_ficha}")
            else:
                st.session_state["fn_ultimo"] = {"membro_id": membro_id, "tipo": tipo}
                st.session_state["fn_v"] = v + 1
                st.session_state["fn_msg"] = (f"{dados_membro['nome']} foi cadastrado(a). "
                                              "Baixe a ficha em PDF logo abaixo.")
                st.rerun()

    st.markdown("#### Gerar a ficha de um membro já cadastrado")
    membros = db.listar_membros(banco, cid)
    if not membros:
        st.caption("Ainda não há membros cadastrados nesta congregação.")
        return
    por_id = {m["id"]: m for m in membros}
    mid = st.selectbox("Membro", list(por_id.keys()), format_func=lambda i: por_id[i]["nome"], key="fn_sel")
    d = ficha_membro.obter_ficha(banco, mid, cid)
    if d is None:
        return
    padrao = ficha_membro.TIPOS.index(d["tipo"]) if d.get("tipo") in ficha_membro.TIPOS else 0
    tipo2 = st.radio("Modelo da ficha", list(ficha_membro.TIPOS), index=padrao, horizontal=True,
                     key=f"fn_tipo2_{mid}")
    if not d.get("tipo"):
        st.caption("Este membro não tem ficha salva: ela sai com os dados do cadastro e o restante em branco.")
    _botao_pdf(f"Baixar a ficha de {d['nome']}", d, tipo2, f"fn_dl_{mid}")


# ---------------------------------------------------------------------------
# Minha congregação
# ---------------------------------------------------------------------------
def pagina_minha_congregacao(banco, conta):
    cid = conta["congregacao_id"]
    d = portal_db.dados_congregacao(banco, cid)
    msg = st.session_state.pop("mc_msg", None)
    if msg:
        st.success(msg)
    st.markdown(f"**{d['nome']}** · Região {d['regiao'] or '-'}")
    st.caption("O nome e a região só podem ser alterados pela liderança, pois definem a regra de choque do calendário.")

    endereco = st.text_input("Endereço", value=d["endereco"] or "", key="mc_end")
    fundacao = st.date_input("Data de fundação", value=d["data_fundacao"], min_value=pd.Timestamp(1900, 1, 1).date(),
                             max_value=pd.Timestamp.today().date(), format="DD/MM/YYYY", key="mc_fund")
    st.markdown("#### Contato da congregação")
    c1, c2, c3 = st.columns(3)
    nome_contato = c1.text_input("Responsável", value=d["contato_nome"] or "", key="mc_cn")
    chave_tel = "mc_tel"
    if chave_tel not in st.session_state:
        st.session_state[chave_tel] = d["contato_telefone"] or ""
    telefone = c2.text_input("Telefone / WhatsApp", key=chave_tel, placeholder="(83) 9 9999-9999",
                             on_change=gestao._fmt_telefone, args=(chave_tel,))
    email = c3.text_input("E-mail", value=d["contato_email"] or "", key="mc_ce")
    if st.button("Salvar dados", key="mc_salvar"):
        if email.strip() and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()):
            st.error("Informe um e-mail válido ou deixe o campo em branco.")
        elif telefone.strip() and len(re.sub(r"\D", "", telefone)) < 10:
            st.error("Informe o telefone com DDD ou deixe o campo em branco.")
        else:
            portal_db.atualizar_dados_congregacao(banco, cid, endereco, fundacao, nome_contato,
                                                  telefone.strip(), email.strip())
            st.session_state["mc_msg"] = "Dados da congregação atualizados."
            st.rerun()


# ---------------------------------------------------------------------------
# Minha conta
# ---------------------------------------------------------------------------
def pagina_minha_conta(banco, conta):
    st.markdown(f"**{conta['nome']}**  \n{conta['login']}  \n{conta['congregacao']}")
    st.markdown("#### Alterar senha")
    msg = st.session_state.pop("mca_msg", None)
    if msg:
        st.success(msg)
    with st.form("alterar_senha"):
        atual = st.text_input("Senha atual", type="password")
        nova = st.text_input("Nova senha", type="password")
        conf = st.text_input("Repita a nova senha", type="password")
        ok = st.form_submit_button("Alterar senha")
    if ok:
        if nova != conf:
            st.error("As senhas não conferem.")
        else:
            try:
                contas.alterar_senha_propria(banco, conta["id"], atual, nova)
            except ValueError as erro:
                st.error(str(erro))
            else:
                st.session_state["mca_msg"] = "Senha alterada com sucesso."
                st.rerun()


# ---------------------------------------------------------------------------
# Barra de navegação superior
# ---------------------------------------------------------------------------
def _ir_para(pagina, etapa):
    st.session_state["pagina_portal"] = pagina
    st.session_state["etapa_portal"] = etapa
    st.rerun()


def _contem(no, pagina):
    return no.get("pagina") == pagina or any(_contem(f, pagina) for f in no.get("filhos", []))


def _botao_nav(rotulo, chave, ativo, pagina, etapa, largura=False):
    if st.button(rotulo, key=chave, type="primary" if ativo else "secondary", use_container_width=largura):
        _ir_para(pagina, etapa)


def _barra_nav(conta):
    atual = st.session_state["pagina_portal"]
    etapa_atual = st.session_state.get("etapa_portal")
    with st.container(key="nav"):
        st.markdown(f'<img class="nav-logo" src="{LOGO_URL}" alt="Logo">', unsafe_allow_html=True)
        for i, no in enumerate(MENU):
            filhos = no.get("filhos")
            ativo = _contem(no, atual)
            if not filhos:
                _botao_nav(no["rotulo"], f"nav_{i}", ativo, no["pagina"], None)
                continue
            with st.container(key=f"ntop_{i}"):
                st.markdown(f'<div class="nav-rot{" ativo" if ativo else ""}">{html.escape(no["rotulo"])} ▾</div>',
                            unsafe_allow_html=True)
                with st.container(key=f"ndrop_{i}"):
                    for j, f in enumerate(filhos):
                        if not f.get("filhos"):
                            _botao_nav(f["rotulo"], f"nav_{i}_{j}", atual == f["pagina"], f["pagina"], None, True)
                            continue
                        with st.container(key=f"nsub_{i}_{j}"):
                            _botao_nav(f"{f['rotulo']}  ▸", f"nav_{i}_{j}", atual == f["pagina"], f["pagina"],
                                       None, True)
                            with st.container(key=f"nfly_{i}_{j}"):
                                for l, sf in enumerate(f["filhos"]):
                                    sel = atual == sf["pagina"] and etapa_atual == sf.get("etapa")
                                    _botao_nav(sf["rotulo"], f"nav_{i}_{j}_{l}", sel, sf["pagina"],
                                               sf.get("etapa"), True)
        with st.container(key="nav_usuario"):
            st.markdown(f'<span class="nav-ola">Olá, <b>{html.escape(conta["nome"])}</b></span>',
                        unsafe_allow_html=True)
            with st.container(key="nav_sair"):
                if st.button("SAIR", key="btn_sair"):
                    _sair()
                    st.rerun()


def _rodape():
    st.markdown('<div class="rodape">Desenvolvido por <b>Rodolfo Crystian</b> · rcrystiandados@gmail.com · '
                'WhatsApp: (83) 9 9962-3735</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Fluxo principal
# ---------------------------------------------------------------------------
banco = _banco()
if banco is None:
    st.stop()

conta = None
if st.session_state.get("conta_id"):
    conta = contas.conta_ativa(banco, st.session_state["conta_id"])
    if conta is None:
        _sair()
        st.warning("Este acesso foi desativado. Procure a liderança.")

st.session_state.setdefault("pagina_portal", "Início")
if st.session_state["pagina_portal"] not in PAGINAS:
    st.session_state["pagina_portal"] = "Início"

if conta is None:
    tela_acesso(banco)
elif conta["trocar_senha"]:
    tela_troca_obrigatoria(banco, conta)
else:
    pagina = st.session_state["pagina_portal"]
    _barra_nav(conta)
    st.markdown(f'<h1 class="titulo-sem-linha">{pagina}</h1>', unsafe_allow_html=True)
    st.markdown('<hr class="linha-titulo">', unsafe_allow_html=True)

    calendario = _carregar_calendario() if pagina in ("Início", "Pedir remarcação", "Eventos internos") else None

    if pagina == "Início":
        pagina_inicio(banco, conta, calendario)
    elif pagina == "Pedir remarcação":
        pagina_remarcacao(banco, conta, calendario)
    elif pagina == "Minha congregação":
        pagina_minha_congregacao(banco, conta)
    elif pagina == "Minha conta":
        pagina_minha_conta(banco, conta)
    elif pagina == "Novo membro":
        pagina_novo_membro(banco, conta)
    elif pagina in PAGINAS_GESTAO:
        gestao.renderizar_congregacao(pagina, conta["congregacao_id"], calendario)

_rodape()