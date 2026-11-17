"""Páginas da liderança para o portal das congregações.

- pagina_pedidos(calendario): analisar pedidos de remarcação (aprovar aplica a data na planilha).
- pagina_acessos(): criar e administrar os acessos das congregações (somente administradores).
Chamadas pelo app.py do sistema da liderança.
"""
import pandas as pd
import streamlit as st

import agenda
import autenticacao
import contas_congregacao as contas
import gestao
import gestao_db as db
import portal_db


@st.cache_resource(show_spinner=False)
def _preparar(_banco):
    portal_db.criar_tabelas(_banco)
    return True


def _banco():
    banco = gestao._banco()
    if banco is not None:
        _preparar(banco)
    return banco


def _fmt(d):
    return d.strftime("%d/%m/%Y") if d is not None and not pd.isna(d) else ""


def _periodo(ini, fim):
    return _fmt(ini) if ini == fim else f"{_fmt(ini)} a {_fmt(fim)}"


def contar_pendentes():
    """Para avisos no painel inicial. Devolve None se o banco não estiver disponível (sem mensagens na tela)."""
    try:
        banco = gestao._obter_banco(st.secrets["database_url"])
        _preparar(banco)
        return portal_db.contar_pendentes(banco)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Pedidos de remarcação
# ---------------------------------------------------------------------------
def pagina_pedidos(calendario):
    banco = _banco()
    if banco is None:
        return
    msg = st.session_state.pop("pd_msg", None)
    if msg:
        st.success(msg)

    pendentes = portal_db.listar_pedidos(banco, status="pendente")
    regs = agenda.registros_da_planilha(calendario) if calendario is not None else []
    if calendario is None:
        st.warning("Não consegui ler a planilha do calendário. Sem ela não é possível aprovar pedidos.")

    st.markdown(f"#### Aguardando análise ({len(pendentes)})")
    if not pendentes:
        st.success("Nenhum pedido pendente.")
    for p in sorted(pendentes, key=lambda x: x["id"]):
        _cartao_pedido(banco, p, regs)

    historico = [p for p in portal_db.listar_pedidos(banco, limite=60) if p["status"] != "pendente"]
    if historico:
        with st.expander(f"Pedidos já respondidos ({len(historico)})"):
            st.dataframe(pd.DataFrame([{
                "Congregação": p["congregacao"], "Evento": p["evento_nome"],
                "Período anterior": _periodo(p["ini_atual"], p["fim_atual"]),
                "Nova data pedida": _periodo(p["ini_novo"], p["fim_novo"]),
                "Situação": p["status"].capitalize(), "Resposta": p["resposta"] or "",
                "Por": p["decidido_por"] or "",
            } for p in historico]), use_container_width=True, hide_index=True)


def _cartao_pedido(banco, p, regs):
    alvo = next((r for r in regs if r["linha"] == p["evento_linha"]
                 and r["nome"].strip() == p["evento_nome"].strip()), None)
    with st.container(border=True):
        st.markdown(f"**{p['congregacao']}** pede para remarcar **{p['evento_nome']}**")
        st.markdown(f"{_periodo(p['ini_atual'], p['fim_atual'])}  →  **{_periodo(p['ini_novo'], p['fim_novo'])}**")
        st.caption(f"Pedido em {str(p['criado_em'])[:10]}")
        st.markdown(f"Motivo: {p['motivo']}")

        conflitos, aprovar_ok = [], True
        if alvo is None:
            st.error("Este evento não foi encontrado na planilha com o mesmo nome (a linha pode ter mudado). "
                     "Não dá para aprovar: recuse e peça um novo pedido.")
            aprovar_ok = False
        else:
            if alvo["ini"].date() != p["ini_atual"]:
                st.info(f"A data do evento na planilha ({_periodo(alvo['ini'].date(), alvo['fim'].date())}) "
                        "mudou depois do pedido.")
            cand = dict(alvo, ini=pd.Timestamp(p["ini_novo"]), fim=pd.Timestamp(p["fim_novo"]))
            conflitos = agenda.choques_do_novo(cand, [r for r in regs if r["linha"] != alvo["linha"]])
            if conflitos:
                st.error("A nova data entra em choque na mesma região com:\n\n"
                         + "\n".join(f"- {agenda.descrever(c)}" for c, _m in conflitos))
            else:
                st.success("A nova data não tem choque na região.")
            feriados = agenda.feriados_no_periodo(p["ini_novo"], p["fim_novo"])
            if feriados:
                st.warning("Feriados no período: " + "; ".join(f"{d:%d/%m} ({n})" for d, n in feriados) + ".")

        resposta = st.text_input("Resposta à congregação (opcional)", key=f"pd_resp_{p['id']}")
        forcar = True
        if conflitos:
            forcar = st.checkbox("Aprovar mesmo com choque", key=f"pd_forcar_{p['id']}")
        b1, b2, _ = st.columns([1.3, 1, 3])
        if b1.button("Aprovar e aplicar", key=f"pd_ok_{p['id']}", disabled=not (aprovar_ok and forcar),
                     use_container_width=True) and aprovar_ok and forcar:
            try:
                agenda.atualizar_datas_planilha(alvo, p["ini_novo"], p["fim_novo"],
                                                f"Pedido da congregação: {p['motivo']}")
            except Exception as erro:
                st.error(f"Não foi possível gravar na planilha: {erro}")
            else:
                portal_db.decidir_pedido(banco, p["id"], "aprovado", resposta,
                                         autenticacao.usuario_atual().get("nome", ""))
                st.cache_data.clear()
                st.session_state["pd_msg"] = f"Pedido aprovado: \"{p['evento_nome']}\" remarcado na planilha."
                st.rerun()
        if b2.button("Recusar", key=f"pd_no_{p['id']}", use_container_width=True):
            portal_db.decidir_pedido(banco, p["id"], "recusado", resposta,
                                     autenticacao.usuario_atual().get("nome", ""))
            st.session_state["pd_msg"] = f"Pedido de \"{p['evento_nome']}\" recusado."
            st.rerun()


# ---------------------------------------------------------------------------
# Acessos das congregações
# ---------------------------------------------------------------------------
def pagina_acessos():
    if autenticacao.usuario_atual().get("perfil") != "admin":
        st.error("Somente administradores gerenciam os acessos das congregações.")
        return
    banco = _banco()
    if banco is None:
        return

    nova = st.session_state.pop("pa_senha", None)
    if nova:
        st.success(f"Acesso pronto para **{nova[0]}**. Envie o e-mail e esta senha temporária; "
                   "ela aparece só agora e precisa ser trocada no primeiro acesso:")
        st.code(nova[1], language=None)
    msg = st.session_state.pop("pa_msg", None)
    if msg:
        st.success(msg)

    st.caption("Cada acesso pertence a uma única congregação e não entra neste sistema da liderança. "
               "O portal é um segundo app do mesmo repositório (arquivo portal.py).")
    todas = contas.listar_contas(banco)
    if todas:
        st.dataframe(pd.DataFrame([{
            "Congregação": c["congregacao"], "Responsável": c["nome"], "E-mail": c["login"],
            "Situação": "Ativo" if c["ativo"] else "Desativado",
            "Senha temporária pendente": "Sim" if c["trocar_senha"] else "Não",
            "Último acesso": c["ultimo_acesso"].strftime("%d/%m/%Y %H:%M") if c["ultimo_acesso"] else "nunca",
        } for c in todas]), use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum acesso de congregação criado ainda.")

    congregacoes = db.listar_congregacoes(banco)
    if not congregacoes:
        st.info("Cadastre as congregações antes de criar acessos.")
        return
    nomes = {c["id"]: c["nome"] for c in congregacoes}

    st.markdown("#### Novo acesso")
    versao = st.session_state.get("pa_versao", 0)
    cid = st.selectbox("Congregação", list(nomes.keys()), format_func=lambda i: nomes[i], key=f"pa_cong_{versao}")
    c1, c2 = st.columns(2)
    nome = c1.text_input("Nome do responsável", key=f"pa_nome_{versao}")
    login = c2.text_input("E-mail de acesso", key=f"pa_login_{versao}")
    if st.button("Criar acesso", key="pa_criar"):
        try:
            _id, senha = contas.criar_conta(banco, cid, nome, login)
        except ValueError as erro:
            st.error(str(erro))
        else:
            st.session_state["pa_versao"] = versao + 1
            st.session_state["pa_senha"] = (login.strip().lower(), senha)
            st.rerun()

    if not todas:
        return
    st.markdown("#### Gerenciar acesso")
    por_id = {c["id"]: c for c in todas}
    escolhido = st.selectbox("Acesso", list(por_id.keys()), key="pa_escolhido",
                             format_func=lambda i: f"{por_id[i]['congregacao']} · {por_id[i]['nome']} ({por_id[i]['login']})")
    c = por_id[escolhido]
    b1, b2, b3 = st.columns(3)
    if b1.button("Desativar acesso" if c["ativo"] else "Reativar acesso", key=f"pa_ativo_{escolhido}",
                 use_container_width=True):
        contas.definir_ativo(banco, escolhido, not c["ativo"])
        st.session_state["pa_msg"] = "Acesso desativado." if c["ativo"] else "Acesso reativado."
        st.rerun()
    if b2.button("Desbloquear", key=f"pa_desb_{escolhido}", use_container_width=True):
        contas.desbloquear(banco, escolhido)
        st.session_state["pa_msg"] = "Acesso desbloqueado."
        st.rerun()
    if b3.button("Nova senha temporária", key=f"pa_reset_{escolhido}", use_container_width=True):
        st.session_state["pa_senha"] = (c["login"], contas.redefinir_temporaria(banco, escolhido))
        st.rerun()
