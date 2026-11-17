"""Telas da gestão das congregações (uso restrito à liderança).

Chamado pelo app.py do site de gestão: gestao.renderizar(subpagina, calendario_df, mapa_congregacoes)
Bibliotecas necessárias (requirements.txt): psycopg2-binary
"""
import re
import unicodedata
from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

import gestao_db as db

AVISO_DADOS = ("Dados pessoais de membros são sensíveis (a religião é dado sensível na LGPD). "
               "Use apenas o necessário e mantenha o acesso restrito à liderança.")
MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
         "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]


# ---------------------------------------------------------------------------
# Conexão com o banco
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def _obter_banco(url):
    banco = db.Banco(url)
    banco.criar_tabelas()
    return banco


def _instrucoes_configuracao():
    st.info(
        "O banco de dados ainda não foi configurado. Passo a passo:\n\n"
        "1. Crie uma conta gratuita em neon.com e um projeto (banco PostgreSQL).\n"
        "2. Copie a **connection string** do projeto (começa com `postgresql://`).\n"
        "3. No Streamlit Cloud, abra **Settings > Secrets** do app e acrescente a linha:\n\n"
        '`database_url = "cole-a-connection-string-aqui"`\n\n'
        "4. Confirme que o `requirements.txt` tem `psycopg2-binary` e reinicie o app."
    )


def _banco():
    try:
        url = st.secrets["database_url"]
    except Exception:
        url = None
    if not url:
        _instrucoes_configuracao()
        return None
    try:
        return _obter_banco(url)
    except ImportError:
        st.error("Falta a biblioteca `psycopg2-binary`. Acrescente-a ao requirements.txt do repositório.")
    except Exception as erro:
        st.error(f"Não foi possível conectar ao banco de dados: {erro}")
    return None


# ---------------------------------------------------------------------------
# Utilitários de tela
# ---------------------------------------------------------------------------
def _norm(texto):
    return unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower().strip()


def _fmt_data(d):
    return d.strftime("%d/%m/%Y") if d else ""


def _fmt_telefone(chave):
    """Formata o telefone como (83) 9 9999-9999 ao sair do campo."""
    d = re.sub(r"\D", "", st.session_state.get(chave, ""))
    if d.startswith("55") and len(d) > 11:
        d = d[2:]
    d = d[:11]
    if len(d) == 11:
        f = f"({d[:2]}) {d[2]} {d[3:7]}-{d[7:]}"
    elif len(d) == 10:
        f = f"({d[:2]}) {d[2:6]}-{d[6:]}"
    elif len(d) > 2:
        f = f"({d[:2]}) {d[2:]}"
    else:
        f = d
    st.session_state[chave] = f


def _escolher_congregacao(banco, chave, rotulo="Congregação", todas=False):
    """Seletor de congregação. Devolve o id (ou None para 'Todas'). Devolve False se não há congregações.
    No portal da congregação não há escolha: vale sempre a congregação da conta que entrou."""
    fixa = st.session_state.get("_congregacao_fixa")
    if fixa:
        return fixa
    congregacoes = db.listar_congregacoes(banco)
    if not congregacoes:
        st.info("Ainda não há congregações no banco. Abra a **Visão geral** e importe a lista atual.")
        return False
    nomes = {c["id"]: c["nome"] for c in congregacoes}
    opcoes = ([None] if todas else []) + list(nomes.keys())
    return st.selectbox(rotulo, opcoes, format_func=lambda i: "Todas" if i is None else nomes[i], key=chave)


# ---------------------------------------------------------------------------
# Campos do formulário de membro (novo e edição)
# ---------------------------------------------------------------------------
def _campos_membro(banco, prefixo, membro=None):
    congregacoes = db.listar_congregacoes(banco)
    nomes = {c["id"]: c["nome"] for c in congregacoes}
    ids = list(nomes.keys())
    versao = st.session_state.get("nm_versao", 0)
    base = f"{prefixo}_{membro['id'] if membro else versao}"
    m = membro or {}

    fixa = st.session_state.get("_congregacao_fixa")
    if fixa:
        cid = fixa
    else:
        atual = m.get("congregacao_id")
        cid = st.selectbox("Congregação", ids, index=ids.index(atual) if atual in ids else 0,
                           format_func=lambda i: nomes[i], key=f"{base}_cong")

    c1, c2 = st.columns(2)
    nome = c1.text_input("Nome completo", value=m.get("nome", ""), key=f"{base}_nome")
    nascimento = c2.date_input("Data de nascimento", value=m.get("data_nascimento"),
                               min_value=date(1900, 1, 1), max_value=date.today(),
                               format="DD/MM/YYYY", key=f"{base}_nasc")

    c3, c4, c5 = st.columns(3)
    sexos = ["", "Masculino", "Feminino"]
    sexo = c3.selectbox("Sexo", sexos, index=sexos.index(m["sexo"]) if m.get("sexo") in sexos else 0,
                        key=f"{base}_sexo")
    chave_tel = f"{base}_tel"
    if chave_tel not in st.session_state:
        st.session_state[chave_tel] = m.get("telefone") or ""
    telefone = c4.text_input("Telefone / WhatsApp", key=chave_tel, placeholder="(83) 9 9999-9999",
                             on_change=_fmt_telefone, args=(chave_tel,))
    email = c5.text_input("E-mail", value=m.get("email") or "", key=f"{base}_email")

    c6, c7 = st.columns(2)
    cargos = db.CARGOS
    cargo = c6.selectbox("Cargo/Função", cargos,
                         index=cargos.index(m["cargo"]) if m.get("cargo") in cargos else 0, key=f"{base}_cargo")
    situacoes = db.SITUACOES
    situacao = c7.selectbox("Situação", situacoes,
                            index=situacoes.index(m["situacao"]) if m.get("situacao") in situacoes else 0,
                            key=f"{base}_sit")

    c8, c9 = st.columns(2)
    entrada = c8.date_input("Data de entrada na congregação",
                            value=m.get("data_entrada") if membro else date.today(),
                            min_value=date(1900, 1, 1), max_value=date.today(),
                            format="DD/MM/YYYY", key=f"{base}_entrada")
    batismo = c9.date_input("Data de batismo (opcional)", value=m.get("data_batismo"),
                            min_value=date(1900, 1, 1), max_value=date.today(),
                            format="DD/MM/YYYY", key=f"{base}_batismo")

    deps = db.listar_departamentos(banco, cid, apenas_ativos=True)
    nomes_dep = {d["id"]: d["nome"] for d in deps}
    ja = dict(m.get("departamentos_lista", []))
    escolhidos = st.multiselect(
        "Departamentos", list(nomes_dep.keys()), format_func=lambda i: nomes_dep[i],
        default=[i for i in ja if i in nomes_dep], key=f"{base}_deps_{cid}",
        placeholder="Nenhum departamento" if deps else "Esta congregação ainda não tem departamentos",
    )
    departamentos = []
    for dep_id in escolhidos:
        funcoes = db.FUNCOES_DEPARTAMENTO
        funcao = st.selectbox(f"Função em {nomes_dep[dep_id]}", funcoes,
                              index=funcoes.index(ja[dep_id]) if ja.get(dep_id) in funcoes else 0,
                              key=f"{base}_f_{dep_id}")
        departamentos.append((dep_id, funcao))

    observacoes = st.text_area("Observações (opcional)", value=m.get("observacoes") or "",
                               key=f"{base}_obs", height=80)
    dados = {
        "congregacao_id": cid, "nome": nome.strip(), "data_nascimento": nascimento, "sexo": sexo,
        "telefone": telefone.strip(), "email": email.strip(), "cargo": cargo, "situacao": situacao,
        "data_entrada": entrada, "data_batismo": batismo, "observacoes": observacoes.strip(),
    }
    return dados, departamentos


def _validar_membro(dados):
    if not dados["nome"]:
        return "Informe o nome completo."
    if dados["email"] and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", dados["email"]):
        return "Informe um e-mail válido ou deixe o campo em branco."
    if dados["telefone"] and len(re.sub(r"\D", "", dados["telefone"])) < 10:
        return "Informe o telefone com DDD ou deixe o campo em branco."
    return None


# ---------------------------------------------------------------------------
# Visão geral
# ---------------------------------------------------------------------------
def _visao_geral(banco, mapa_congregacoes):
    congregacoes = db.listar_congregacoes(banco)
    total_lista = sum(len(v) for v in mapa_congregacoes.values())

    if not congregacoes:
        st.info("O banco ainda não tem congregações. Importe a lista inicial para começar a cadastrar "
                "membros e departamentos, ou cadastre uma a uma em **Congregações**.")
        if st.button(f"Importar {total_lista} congregações da lista inicial", key="g_importar_inicial"):
            criadas = db.importar_congregacoes(banco, mapa_congregacoes)
            st.session_state["g_msg"] = f"{criadas} congregação(ões) importada(s)."
            st.rerun()
        return

    msg = st.session_state.pop("g_msg", None)
    if msg:
        st.success(msg)

    r = db.resumo(banco)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Membros ativos", r["membros_ativos"])
    c2.metric("Congregações", r["congregacoes"])
    c3.metric("Departamentos", r["departamentos"])
    c4.metric("Novos membros (30 dias)", r["novos_30_dias"])

    st.markdown("#### Membros por congregação")
    dados = pd.DataFrame(db.membros_por_congregacao(banco))
    if not dados.empty and dados["total"].sum() > 0:
        dados = dados.rename(columns={"nome": "Congregação", "total": "Membros"})
        grafico = (
            alt.Chart(dados).mark_bar(color="#1E3A8A")
            .encode(x=alt.X("Membros:Q", title=None, axis=alt.Axis(tickMinStep=1, format="d")),
                    y=alt.Y("Congregação:N", sort="-x", title=None))
            .properties(height=max(120, 30 * len(dados)), background="#FFFFFF")
            .configure_view(strokeWidth=0)
            .configure_axis(labelColor="#1F2937", gridColor="#E5E7EB", domainColor="#CBD5E1")
        )
        st.altair_chart(grafico, use_container_width=True, theme=None)
    else:
        st.caption("Ainda não há membros cadastrados. Use **Novo membro** no menu.")

    st.markdown("#### Aniversariantes")
    mes = st.selectbox("Mês", list(range(1, 13)), index=date.today().month - 1,
                       format_func=lambda m: MESES[m - 1], key="g_mes_aniv")
    aniv = db.aniversariantes(banco, mes)
    if aniv:
        st.dataframe(
            pd.DataFrame([{"Dia": a["data_nascimento"].day, "Nome": a["nome"], "Congregação": a["congregacao"]}
                          for a in aniv]),
            use_container_width=True, hide_index=True)
    else:
        st.caption("Nenhum aniversariante neste mês.")

    with st.expander("Importar lista inicial de congregações"):
        st.caption(f"A lista inicial tem {total_lista} congregações. "
                   "Este botão cria no banco as que ainda não existem.")
        if st.button("Importar agora", key="g_sincronizar"):
            criadas = db.importar_congregacoes(banco, mapa_congregacoes)
            st.session_state["g_msg"] = f"{criadas} congregação(ões) nova(s) adicionada(s)."
            st.rerun()


# ---------------------------------------------------------------------------
# Novo membro
# ---------------------------------------------------------------------------
def _novo_membro(banco):
    if not db.listar_congregacoes(banco):
        st.info("Ainda não há congregações no banco. Abra a **Visão geral** e importe a lista atual.")
        return
    st.markdown("#### Inclusão de novo membro")
    msg = st.session_state.pop("nm_msg", None)
    if msg:
        st.success(msg)

    dados, departamentos = _campos_membro(banco, "nm")
    if st.button("Cadastrar membro", key="nm_salvar"):
        erro = _validar_membro(dados)
        if erro:
            st.error(erro)
        elif db.membro_existe(banco, dados["congregacao_id"], dados["nome"], dados["data_nascimento"]):
            st.error("Já existe um membro com este nome e data de nascimento nesta congregação.")
        else:
            db.criar_membro(banco, dados, departamentos)
            st.session_state["nm_versao"] = st.session_state.get("nm_versao", 0) + 1
            st.session_state["nm_msg"] = f"{dados['nome']} foi cadastrado(a) com sucesso."
            st.rerun()

    recentes = db.ultimos_membros(banco, 6, st.session_state.get("_congregacao_fixa"))
    if recentes:
        st.markdown("#### Últimos membros incluídos")
        st.dataframe(
            pd.DataFrame([{"Nome": r["nome"], "Congregação": r["congregacao"], "Cargo": r["cargo"] or "",
                           "Entrada": _fmt_data(r["data_entrada"])} for r in recentes]),
            use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Membros (lista, edição e exclusão)
# ---------------------------------------------------------------------------
def _membros(banco):
    cid = _escolher_congregacao(banco, "mb_cong", todas=True)
    if cid is False:
        return
    f1, f2, f3 = st.columns(3)
    deps = db.listar_departamentos(banco, cid)
    nomes_dep = {d["id"]: (d["nome"] if cid else f"{d['nome']} ({d['congregacao']})") for d in deps}
    dep_id = f1.selectbox("Departamento", [None] + list(nomes_dep.keys()), key=f"mb_dep_{cid}",
                          format_func=lambda i: "Todos" if i is None else nomes_dep[i])
    situacao = f2.selectbox("Situação", [None] + db.SITUACOES, key="mb_sit",
                            format_func=lambda s: "Todas" if s is None else s)
    busca = f3.text_input("Buscar por nome", key="mb_busca")

    membros = db.listar_membros(banco, cid, dep_id, situacao, busca)
    msg = st.session_state.pop("mb_msg", None)
    if msg:
        st.success(msg)
    st.caption(f"{len(membros)} membro(s) encontrado(s).")
    if not membros:
        return

    tabela = pd.DataFrame([{
        "Nome": m["nome"], "Congregação": m["congregacao"], "Cargo": m["cargo"] or "",
        "Situação": m["situacao"], "Departamentos": m["departamentos"],
        "Telefone": m["telefone"] or "", "Nascimento": _fmt_data(m["data_nascimento"]),
        "Entrada": _fmt_data(m["data_entrada"]),
    } for m in membros])
    st.dataframe(tabela, use_container_width=True, hide_index=True)
    st.download_button("Baixar lista (CSV)", tabela.to_csv(index=False).encode("utf-8-sig"),
                       file_name="membros.csv", mime="text/csv", key="mb_csv")

    st.markdown("#### Editar membro")
    por_id = {m["id"]: m for m in membros}
    escolhido = st.selectbox("Escolha o membro", list(por_id.keys()), key="mb_escolhido",
                             format_func=lambda i: f"{por_id[i]['nome']} · {por_id[i]['congregacao']}")
    membro = por_id[escolhido]
    dados, departamentos = _campos_membro(banco, "em", membro)

    b1, b2 = st.columns([1, 3])
    if b1.button("Salvar alterações", key=f"mb_salvar_{escolhido}", use_container_width=True):
        erro = _validar_membro(dados)
        if erro:
            st.error(erro)
        elif db.membro_existe(banco, dados["congregacao_id"], dados["nome"], dados["data_nascimento"],
                              ignorar_id=escolhido):
            st.error("Já existe outro membro com este nome e data de nascimento nesta congregação.")
        else:
            db.atualizar_membro(banco, escolhido, dados, departamentos)
            st.session_state["mb_msg"] = f"Dados de {dados['nome']} atualizados."
            st.rerun()

    with st.expander("Excluir membro definitivamente"):
        st.caption("Prefira mudar a situação (Inativo, Transferido). A exclusão apaga todos os dados "
                   "do membro e não pode ser desfeita.")
        confirma = st.checkbox(f"Confirmo a exclusão de {membro['nome']}", key=f"mb_conf_{escolhido}")
        if st.button("Excluir", key=f"mb_excluir_{escolhido}", disabled=not confirma):
            db.excluir_membro(banco, escolhido)
            st.session_state["mb_msg"] = f"{membro['nome']} foi excluído(a)."
            st.rerun()


# ---------------------------------------------------------------------------
# Departamentos
# ---------------------------------------------------------------------------
def _departamentos(banco):
    cid = _escolher_congregacao(banco, "dp_cong")
    if cid is False:
        return
    msg = st.session_state.pop("dp_msg", None)
    if msg:
        st.success(msg)

    deps = db.listar_departamentos(banco, cid)
    if deps:
        st.dataframe(pd.DataFrame([{
            "Departamento": d["nome"], "Líder": d["lider"] or "", "Membros ativos": d["total_membros"],
            "Fundação": _fmt_data(d["data_fundacao"]), "Situação": "Ativo" if d["ativo"] else "Inativo",
        } for d in deps]), use_container_width=True, hide_index=True)
    else:
        st.caption("Esta congregação ainda não tem departamentos.")

    st.markdown("#### Novo departamento")
    versao = st.session_state.get("dp_versao", 0)
    n1, n2 = st.columns(2)
    nome = n1.text_input("Nome do departamento", key=f"dp_nome_{versao}", placeholder="Ex.: UAC, UHC")
    fundacao = n2.date_input("Data de fundação (opcional)", value=None, min_value=date(1900, 1, 1),
                             max_value=date.today(), format="DD/MM/YYYY", key=f"dp_fund_{versao}")
    if st.button("Criar departamento", key="dp_criar"):
        try:
            db.criar_departamento(banco, cid, nome, fundacao)
        except ValueError as erro:
            st.error(str(erro))
        else:
            st.session_state["dp_versao"] = versao + 1
            st.session_state["dp_msg"] = f"Departamento {nome.strip()} criado."
            st.rerun()

    if not deps:
        return
    st.markdown("#### Gerenciar departamento")
    por_id = {d["id"]: d for d in deps}
    dep_id = st.selectbox("Departamento", list(por_id.keys()), key=f"dp_sel_{cid}",
                          format_func=lambda i: por_id[i]["nome"] + ("" if por_id[i]["ativo"] else " (inativo)"))
    dep = por_id[dep_id]

    ativo = st.checkbox("Departamento ativo", value=bool(dep["ativo"]), key=f"dp_ativo_{dep_id}")
    if ativo != bool(dep["ativo"]):
        db.definir_departamento_ativo(banco, dep_id, ativo)
        st.rerun()

    integrantes = db.membros_do_departamento(banco, dep_id)
    if integrantes:
        for i in integrantes:
            c1, c2, c3 = st.columns([4, 2, 1.2], vertical_alignment="center")
            c1.markdown(f"**{i['nome']}**" + ("" if i["situacao"] == "Ativo" else f"  ({i['situacao']})"))
            c2.caption(i["funcao"])
            if c3.button("Remover", key=f"dp_rm_{dep_id}_{i['id']}", use_container_width=True):
                db.remover_do_departamento(banco, i["id"], dep_id)
                st.rerun()
    else:
        st.caption("Nenhum integrante neste departamento.")

    st.markdown("#### Adicionar integrante ou trocar função")
    candidatos = db.listar_membros(banco, cid, situacao="Ativo")
    if not candidatos:
        st.caption("Cadastre membros ativos nesta congregação para adicioná-los.")
        return
    nomes = {m["id"]: m["nome"] for m in candidatos}
    a1, a2 = st.columns(2)
    membro_id = a1.selectbox("Membro", list(nomes.keys()), format_func=lambda i: nomes[i], key=f"dp_add_{dep_id}")
    funcao = a2.selectbox("Função", db.FUNCOES_DEPARTAMENTO, key=f"dp_func_{dep_id}")
    if st.button("Salvar integrante", key=f"dp_salvar_{dep_id}"):
        db.definir_funcao_no_departamento(banco, membro_id, dep_id, funcao)
        st.session_state["dp_msg"] = f"{nomes[membro_id]} agora é {funcao.lower()} em {dep['nome']}."
        st.rerun()


# ---------------------------------------------------------------------------
# Eventos
# ---------------------------------------------------------------------------
def _eventos(banco, calendario_df):
    congregacoes = db.listar_congregacoes(banco)
    cid = _escolher_congregacao(banco, "ev_cong")
    if cid is False:
        return
    nome_cong = next(c["nome"] for c in congregacoes if c["id"] == cid)

    st.markdown("#### No calendário geral")
    if calendario_df is not None and not calendario_df.empty and "Congregação" in calendario_df.columns:
        do_calendario = calendario_df[calendario_df["Congregação"].map(_norm) == _norm(nome_cong)]
    else:
        do_calendario = pd.DataFrame()
    if do_calendario.empty:
        st.caption("Nenhum evento desta congregação no calendário geral.")
    else:
        colunas = [c for c in ["Data de Inicio da Festividade", "Data Final da Festividade",
                               "Nome da Festividade", "Tipo de Festividade"] if c in do_calendario.columns]
        st.dataframe(do_calendario[colunas].rename(columns={
            "Data de Inicio da Festividade": "Início", "Data Final da Festividade": "Fim",
            "Nome da Festividade": "Festividade", "Tipo de Festividade": "Tipo"}),
            use_container_width=True, hide_index=True)

    st.markdown("#### Eventos internos")
    st.caption("Reuniões, ensaios e cultos especiais da congregação. Ficam só nos sistemas internos "
               "(liderança e congregação) e não aparecem no calendário público.")
    msg = st.session_state.pop("ev_msg", None)
    if msg:
        st.success(msg)

    internos = db.listar_eventos_internos(banco, cid)
    if internos:
        st.dataframe(pd.DataFrame([{
            "Início": _fmt_data(e["data_inicio"]), "Fim": _fmt_data(e["data_fim"]), "Evento": e["titulo"],
            "Tipo": e["tipo"] or "", "Departamento": e["departamento"] or "", "Local": e["local"] or "",
        } for e in internos]), use_container_width=True, hide_index=True)
        por_id = {e["id"]: e for e in internos}
        r1, r2 = st.columns([4, 1.2], vertical_alignment="bottom")
        remover = r1.selectbox("Remover evento", list(por_id.keys()), key=f"ev_rm_sel_{cid}",
                               format_func=lambda i: f"{_fmt_data(por_id[i]['data_inicio'])} · {por_id[i]['titulo']}")
        if r2.button("Remover", key=f"ev_rm_{cid}", use_container_width=True):
            db.remover_evento_interno(banco, remover)
            st.session_state["ev_msg"] = "Evento removido."
            st.rerun()
    else:
        st.caption("Nenhum evento interno cadastrado.")

    st.markdown("#### Novo evento interno")
    versao = st.session_state.get("ev_versao", 0)
    chave = f"ev_{cid}_{versao}"
    titulo = st.text_input("Título", key=f"{chave}_titulo")
    c1, c2 = st.columns(2)
    tipo = c1.selectbox("Tipo", db.TIPOS_EVENTO_INTERNO, key=f"{chave}_tipo")
    deps = db.listar_departamentos(banco, cid, apenas_ativos=True)
    nomes_dep = {d["id"]: d["nome"] for d in deps}
    departamento = c2.selectbox("Departamento (opcional)", [None] + list(nomes_dep.keys()),
                                format_func=lambda i: "Toda a congregação" if i is None else nomes_dep[i],
                                key=f"{chave}_dep")
    d1, d2 = st.columns(2)
    inicio = d1.date_input("Data de início", value=date.today(), format="DD/MM/YYYY", key=f"{chave}_ini")
    chave_fim = f"{chave}_fim"
    if st.session_state.get(chave_fim) is None or st.session_state[chave_fim] < inicio:
        st.session_state[chave_fim] = inicio
    fim = d2.date_input("Data final", min_value=inicio, format="DD/MM/YYYY", key=chave_fim)
    local = st.text_input("Local (opcional)", key=f"{chave}_local")
    descricao = st.text_area("Descrição (opcional)", key=f"{chave}_desc", height=80)
    if st.button("Cadastrar evento", key=f"{chave}_salvar"):
        try:
            db.criar_evento_interno(banco, {
                "congregacao_id": cid, "departamento_id": departamento, "titulo": titulo, "tipo": tipo,
                "data_inicio": inicio, "data_fim": fim, "local": local, "descricao": descricao})
        except ValueError as erro:
            st.error(str(erro))
        else:
            st.session_state["ev_versao"] = versao + 1
            st.session_state["ev_msg"] = f"Evento \"{titulo.strip()}\" cadastrado."
            st.rerun()


# ---------------------------------------------------------------------------
# Congregações
# ---------------------------------------------------------------------------
def _congregacoes(banco, mapa_congregacoes):
    msg = st.session_state.pop("cg_msg", None)
    if msg:
        st.success(msg)
    congregacoes = db.listar_congregacoes(banco, apenas_ativas=False)
    if congregacoes:
        st.dataframe(pd.DataFrame([{
            "Congregação": c["nome"], "Região": c["regiao"] or "", "Endereço": c["endereco"] or "",
            "Fundação": _fmt_data(c["data_fundacao"]), "Situação": "Ativa" if c["ativa"] else "Inativa",
        } for c in congregacoes]), use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma congregação cadastrada ainda.")

    st.markdown("#### Nova congregação")
    versao = st.session_state.get("cg_versao", 0)
    regioes = sorted({c["regiao"] for c in congregacoes if c["regiao"]} | set(mapa_congregacoes.keys()))
    n1, n2 = st.columns(2)
    nome = n1.text_input("Nome da congregação", key=f"cg_nome_{versao}", placeholder="Ex.: IEC - Nome da cidade")
    regiao = n2.selectbox("Região", regioes + ["Outra região"], key=f"cg_reg_{versao}")
    if regiao == "Outra região":
        regiao = st.text_input("Nome da nova região", key=f"cg_outra_{versao}")
    n3, n4 = st.columns(2)
    endereco = n3.text_input("Endereço (opcional)", key=f"cg_end_{versao}")
    fundacao = n4.date_input("Data de fundação (opcional)", value=None, min_value=date(1900, 1, 1),
                             max_value=date.today(), format="DD/MM/YYYY", key=f"cg_fund_{versao}")
    if st.button("Cadastrar congregação", key="cg_criar"):
        if not (regiao or "").strip():
            st.error("Informe a região.")
        else:
            try:
                db.criar_congregacao(banco, nome, regiao, endereco, fundacao)
            except ValueError as erro:
                st.error(str(erro))
            else:
                st.session_state["cg_versao"] = versao + 1
                st.session_state["cg_msg"] = f"Congregação {nome.strip()} cadastrada."
                st.rerun()


def resumo_silencioso():
    """Indicadores para o painel inicial. Devolve None se o banco não estiver disponível (sem mensagens na tela)."""
    try:
        return db.resumo(_obter_banco(st.secrets["database_url"]))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------
def renderizar(subpagina, calendario_df, mapa_congregacoes):
    st.session_state.pop("_congregacao_fixa", None)
    banco = _banco()
    if banco is None:
        return
    st.caption(AVISO_DADOS)
    try:
        if subpagina == "Visão geral":
            _visao_geral(banco, mapa_congregacoes)
        elif subpagina == "Congregações":
            _congregacoes(banco, mapa_congregacoes)
        elif subpagina == "Membros":
            _membros(banco)
        elif subpagina == "Novo membro":
            _novo_membro(banco)
        elif subpagina == "Departamentos":
            _departamentos(banco)
        elif subpagina in ("Eventos", "Eventos internos"):
            _eventos(banco, calendario_df)
    except ImportError:
        st.error("Falta a biblioteca `psycopg2-binary`. Acrescente-a ao requirements.txt do repositório.")
    except Exception as erro:
        st.error(f"Não foi possível concluir a operação: {erro}")


AVISO_PORTAL = ("Dados pessoais de membros são sensíveis (a religião é dado sensível na LGPD). "
                "Cadastre apenas o necessário e não compartilhe o seu acesso.")


def renderizar_congregacao(subpagina, congregacao_id, calendario_df):
    """Portal da congregação: as mesmas telas da gestão, travadas na congregação da conta que entrou.

    A congregação vem da conta autenticada (nunca de um campo da tela) e é regravada a cada execução.
    Páginas: Membros, Novo membro, Departamentos, Eventos internos.
    """
    banco = _banco()
    if banco is None:
        return
    st.session_state["_congregacao_fixa"] = int(congregacao_id)
    st.caption(AVISO_PORTAL)
    try:
        if subpagina == "Membros":
            _membros(banco)
        elif subpagina == "Novo membro":
            _novo_membro(banco)
        elif subpagina == "Departamentos":
            _departamentos(banco)
        elif subpagina in ("Eventos", "Eventos internos"):
            _eventos(banco, calendario_df)
    except ImportError:
        st.error("Falta a biblioteca `psycopg2-binary`. Acrescente-a ao requirements.txt do repositório.")
    except Exception as erro:
        st.error(f"Não foi possível concluir a operação: {erro}")
