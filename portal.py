"""Portal da Congregação MEN: cada congregação administra a sua própria gestão.

Segundo app do mesmo repositório (arquivo principal: portal.py). Usa o mesmo banco e os mesmos Secrets
do sistema da liderança (database_url e a conta de serviço da planilha do calendário).

Cada conta pertence a UMA congregação, criada pela liderança (página "Acessos das congregações"),
e só enxerga e altera os dados dessa congregação. A congregação vem da conta autenticada, nunca de um
campo da tela.
"""
import re

import pandas as pd
import streamlit as st

import agenda
import contas_congregacao as contas
import gestao
import gestao_db as db
import portal_db

st.set_page_config(page_title="Portal da Congregação MEN", page_icon="⛪", layout="wide")

PAGINAS = ["Início", "Membros", "Novo membro", "Departamentos", "Eventos internos",
           "Pedir remarcação", "Minha congregação", "Minha conta"]
PAGINAS_GESTAO = ("Membros", "Novo membro", "Departamentos", "Eventos internos")
ROTULO_STATUS = {"pendente": "Aguardando a liderança", "aprovado": "Aprovado",
                 "recusado": "Recusado", "cancelado": "Cancelado por você"}

st.markdown("""<style>
    .titulo-portal {color: #1E3A8A; margin: 0; font-size: 2rem; font-weight: 700;}
    .linha-titulo {border: 0; border-top: 2px solid #CBD5E1; margin: .3rem 0 1rem 0;}
    .login-topo {text-align: center; margin: 2rem 0 1.2rem 0;}
    .login-topo h2 {color: #1E3A8A; margin: 0 0 .4rem 0;}
    .login-topo p {color: #6B7280; margin: 0;}
    .sb-titulo {font-weight: 700; color: #1E3A8A; font-size: 1.1rem;}
    .sb-sub {font-size: .85rem; color: #64748B;}
</style>""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Banco e sessão
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def _preparar(_banco):
    portal_db.criar_tabelas(_banco)
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
    st.markdown('<div class="login-topo"><h2>Portal da Congregação</h2>'
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
# Fluxo principal
# ---------------------------------------------------------------------------
banco = _banco()
if banco is None:
    st.stop()

conta = None
if st.session_state.get("conta_id"):
    conta = contas.conta_ativa(banco, st.session_state["conta_id"])  # confere a cada tela se o acesso segue ativo
    if conta is None:
        _sair()
        st.warning("Este acesso foi desativado. Procure a liderança.")

if conta is None:
    tela_acesso(banco)
elif conta["trocar_senha"]:
    tela_troca_obrigatoria(banco, conta)
else:
    with st.sidebar:
        st.markdown(f'<div class="sb-titulo">{conta["congregacao"]}</div>'
                    f'<div class="sb-sub">Portal da congregação · {conta["nome"]}</div>', unsafe_allow_html=True)
        pagina = st.radio("Menu", PAGINAS, key="pagina_portal", label_visibility="collapsed")
        if st.button("Sair", use_container_width=True):
            _sair()
            st.rerun()

    t1, _ = st.columns([5, 1], vertical_alignment="center")
    t1.markdown(f'<h1 class="titulo-portal">{pagina}</h1>', unsafe_allow_html=True)
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
    elif pagina in PAGINAS_GESTAO:
        gestao.renderizar_congregacao(pagina, conta["congregacao_id"], calendario)
