"""Página Financeiro do portal da congregação (Streamlit).

Seções: Caixa do mês (lançamentos e comprovantes), Dízimos e ofertas, Relatórios (PDF) e
Configuração do caixa. Cada congregação só enxerga e altera os próprios dados.
"""
from datetime import date, datetime

import pandas as pd
import streamlit as st

import financeiro_db as fdb
import financeiro_pdf as fpdf

SECOES = ["Caixa do mês", "Dízimos e ofertas", "Relatórios", "Configuração do caixa"]
AVISO = ("Os dados financeiros e a lista de dizimistas são confidenciais: use apenas para a prestação de contas "
         "da igreja e não compartilhe o seu acesso.")
NOVA_CATEGORIA = "➕ Outra descrição…"


def _reais(centavos):
    return fdb.fmt_valor(centavos, simbolo=True)


def _titulo(caixa, conta):
    return caixa.get("titulo_igreja") or fdb.titulo_padrao(conta["congregacao"])


def _nome_arquivo(prefixo, caixa, ano, mes=None):
    base = fdb.db._sem_acento(f"{prefixo}_{caixa['nome']}").replace(" ", "_").lower()
    return f"{base}_{ano}" + (f"_{mes:02d}" if mes else "") + ".pdf"


# ---------------------------------------------------------------------------
# Entrada da página
# ---------------------------------------------------------------------------
def pagina_financeiro(banco, conta):
    cid = conta["congregacao_id"]
    caixas = fdb.garantir_caixa(banco, cid, conta["congregacao"])
    st.caption(AVISO)
    msg = st.session_state.pop("fin_msg", None)
    if msg:
        st.success(msg)

    secao = st.radio("Seção do financeiro", SECOES, horizontal=True, key="fin_secao", label_visibility="collapsed")
    if secao == "Configuração do caixa":
        _configuracao(banco, conta, caixas)
        return

    hoje = date.today()
    c1, c2, c3 = st.columns([2, 1.3, 1])
    por_id = {c["id"]: c for c in caixas}
    caixa_id = c1.selectbox("Caixa", list(por_id.keys()), format_func=lambda i: por_id[i]["nome"], key="fin_caixa")
    mes = c2.selectbox("Mês", list(range(1, 13)), index=hoje.month - 1, format_func=lambda m: fdb.MESES[m - 1],
                       key="fin_mes")
    anos = list(range(hoje.year - 6, hoje.year + 2))
    ano = c3.selectbox("Ano", anos, index=anos.index(hoje.year), key="fin_ano")
    caixa = por_id[caixa_id]

    if secao == "Caixa do mês":
        _caixa_do_mes(banco, conta, caixa, ano, mes)
    elif secao == "Dízimos e ofertas":
        _dizimos(banco, conta, caixa, ano, mes)
    else:
        _relatorios(banco, conta, caixa, ano, mes)


# ---------------------------------------------------------------------------
# Caixa do mês
# ---------------------------------------------------------------------------
def _rotulo_lanc(l):
    doc = f"{l['doc_numero']:02d}" if l.get("doc_numero") is not None else "--"
    sinal = "+" if l["tipo"] == "R" else "-"
    extra = " (informativo)" if l["informativo"] else ""
    return (f"{doc} · {l['data_lanc']:%d/%m} · {l['categoria']} · {(l['historico'] or '')[:32]} · "
            f"{sinal}{fdb.fmt_valor(l['valor_centavos'])}{extra}")


def _caixa_do_mes(banco, conta, caixa, ano, mes):
    cid = conta["congregacao_id"]
    r = fdb.resumo_mes(banco, cid, caixa["id"], ano, mes)
    ant_mes, ant_ano = fdb.mes_anterior(ano, mes)[1], fdb.mes_anterior(ano, mes)[0]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(f"Saldo anterior ({fdb.MESES[ant_mes - 1][:3]}/{ant_ano})", _reais(r["saldo_ant"]))
    m2.metric("Recebimentos", _reais(r["rec"]))
    m3.metric("Pagamentos", _reais(r["pag"]))
    m4.metric("Saldo atual", _reais(r["saldo_atual"]))
    if not r["lancamentos"] and r["saldo_ant"] == 0 and caixa["saldo_inicial"] == 0:
        st.info("Primeiro uso do caixa? Em **Configuração do caixa** informe a data inicial e o saldo que o caixa "
                "tinha no mês anterior. Depois é só lançar.")

    _novo_lancamento(banco, conta, caixa, ano, mes)

    todos = r["lancamentos"] + r["informativos"]
    st.markdown(f"#### Lançamentos de {fdb.MESES[mes - 1]}/{ano}")
    if not todos:
        st.caption("Nenhum lançamento neste mês. Use **Novo lançamento** acima, ou lance os totais em "
                   "**Dízimos e ofertas**.")
        return
    st.dataframe(pd.DataFrame([{
        "Doc. Nº": f"{l['doc_numero']:02d}" if l.get("doc_numero") is not None else "—",
        "Data": l["data_lanc"].strftime("%d/%m/%Y"), "Conta": l["categoria"], "Histórico": l["historico"] or "",
        "Recebimento": fdb.fmt_valor(l["valor_centavos"]) if l["tipo"] == "R" else "",
        "Pagamento": fdb.fmt_valor(l["valor_centavos"]) if l["tipo"] == "P" else "",
        "Anexos": l["n_comprovantes"] or "",
        "Obs.": "informativo (não soma)" if l["informativo"] else ("vem dos dízimos" if l["origem"] else ""),
    } for l in todos]), use_container_width=True, hide_index=True)
    _gerenciar(banco, conta, caixa, ano, mes, todos)


def _seletor_categoria(opcoes, atual, chave):
    ops = list(opcoes)
    if atual and atual not in ops:
        ops.insert(0, atual)
    escolha = st.selectbox("Descrição da conta", ops + [NOVA_CATEGORIA], index=ops.index(atual) if atual else 0,
                           key=chave)
    if escolha == NOVA_CATEGORIA:
        return st.text_input("Nova descrição", key=chave + "_nova", placeholder="Ex.: MANUTENCAO").strip()
    return escolha


def _novo_lancamento(banco, conta, caixa, ano, mes):
    cid = conta["congregacao_id"]
    v = st.session_state.get("fl_v", 0)
    k = lambda nome: f"fl_{nome}_{v}"
    hoje = date.today()
    padrao = hoje if (hoje.year, hoje.month) == (ano, mes) else fdb.ultimo_dia(ano, mes)
    with st.expander("➕ Novo lançamento", expanded=st.session_state.pop("fin_novo_aberto", False)):
        tipo = st.radio("Tipo", ["Recebimento", "Pagamento"], index=1, horizontal=True, key=k("tipo"))
        c1, c2, c3 = st.columns(3)
        data = c1.date_input("Data", value=padrao, format="DD/MM/YYYY", key=k("data") + f"{ano}{mes}")
        doc = c2.number_input("Doc. Nº", min_value=1, step=1, value=fdb.proximo_doc(banco, cid, caixa["id"], ano, mes),
                              key=k("doc") + f"{ano}{mes}")
        valor = c3.number_input("Valor (R$)", min_value=0.0, step=0.01, format="%.2f", key=k("valor"))
        categoria = _seletor_categoria(fdb.categorias_usadas(banco, cid, caixa["id"]), None, k("cat"))
        historico = st.text_input("Histórico do lançamento", key=k("hist"),
                                  placeholder="Ex.: PGTO.ENERGISA CF. COMPROVANTE")
        informativo = st.checkbox("Lançamento informativo (aparece em vermelho no fim do relatório e não soma nos "
                                  "totais)", key=k("info"))
        arquivos = st.file_uploader("Comprovantes (fotos ou prints: JPG, PNG, WEBP)", type=["jpg", "jpeg", "png", "webp"],
                                    accept_multiple_files=True, key=k("up"))
        if st.button("Salvar lançamento", key=k("salvar")):
            try:
                lid = fdb.criar_lancamento(banco, cid, {
                    "caixa_id": caixa["id"], "data_lanc": data, "tipo": "R" if tipo == "Recebimento" else "P",
                    "categoria": categoria, "historico": historico, "valor_centavos": fdb.para_centavos(valor),
                    "informativo": informativo, "doc_numero": int(doc), "criado_por": conta["nome"]})
            except ValueError as erro:
                st.error(str(erro))
            else:
                avisos = []
                for arq in arquivos or []:
                    try:
                        fdb.adicionar_comprovante(banco, cid, lid, arq.name, arq.getvalue())
                    except ValueError as erro:
                        avisos.append(f"{arq.name}: {erro}")
                st.session_state["fl_v"] = v + 1
                st.session_state["fin_novo_aberto"] = True
                st.session_state["fin_msg"] = "Lançamento salvo." + (" Atenção: " + "; ".join(avisos) if avisos else "")
                st.rerun()


def _gerenciar(banco, conta, caixa, ano, mes, todos):
    cid = conta["congregacao_id"]
    st.markdown("#### Editar, excluir ou anexar comprovantes")
    por_id = {l["id"]: l for l in todos}
    lid = st.selectbox("Escolha o lançamento", list(por_id.keys()), format_func=lambda i: _rotulo_lanc(por_id[i]),
                       key=f"fin_sel_{caixa['id']}_{ano}_{mes}")
    l = por_id[lid]
    k = lambda nome: f"fe_{lid}_{nome}"

    with st.container(border=True):
        tipo = st.radio("Tipo", ["Recebimento", "Pagamento"], index=0 if l["tipo"] == "R" else 1, horizontal=True,
                        key=k("tipo"))
        c1, c2, c3 = st.columns(3)
        data = c1.date_input("Data", value=l["data_lanc"], format="DD/MM/YYYY", key=k("data"))
        doc = c2.number_input("Doc. Nº", min_value=1, step=1, value=int(l["doc_numero"] or 1), key=k("doc"),
                              disabled=l["informativo"])
        valor = c3.number_input("Valor (R$)", min_value=0.0, step=0.01, format="%.2f", value=l["valor_centavos"] / 100,
                                key=k("valor"))
        categoria = _seletor_categoria(fdb.categorias_usadas(banco, cid, caixa["id"]), l["categoria"], k("cat"))
        historico = st.text_input("Histórico do lançamento", value=l["historico"] or "", key=k("hist"))
        informativo = st.checkbox("Lançamento informativo (não soma nos totais)", value=l["informativo"], key=k("info"))
        b1, b2 = st.columns([1, 1])
        if b1.button("Salvar alterações", key=k("salvar"), use_container_width=True):
            try:
                fdb.atualizar_lancamento(banco, cid, lid, {
                    "data_lanc": data, "tipo": "R" if tipo == "Recebimento" else "P", "categoria": categoria,
                    "historico": historico, "valor_centavos": fdb.para_centavos(valor), "informativo": informativo,
                    "doc_numero": int(doc) if not informativo else None})
            except ValueError as erro:
                st.error(str(erro))
            else:
                st.session_state["fin_msg"] = "Lançamento atualizado."
                st.rerun()
        confirma = b2.checkbox("Confirmo que quero excluir este lançamento (e os comprovantes dele)", key=k("conf"))
        if b2.button("Excluir lançamento", key=k("excluir"), disabled=not confirma, use_container_width=True) and confirma:
            fdb.excluir_lancamento(banco, cid, lid)
            st.session_state["fin_msg"] = "Lançamento excluído."
            st.rerun()

        # comprovantes
        st.markdown("**Comprovantes**")
        comps = fdb.listar_comprovantes(banco, cid, lid)
        if not comps:
            st.caption("Nenhum comprovante anexado.")
        for i in range(0, len(comps), 3):
            colunas = st.columns(3)
            for col, comp in zip(colunas, comps[i:i + 3]):
                dados = fdb.obter_comprovante(banco, cid, comp["id"])
                with col:
                    if dados:
                        st.image(dados["conteudo"], caption=comp["nome_arquivo"], width=230)
                        if st.button("Remover", key=f"fc_del_{comp['id']}", use_container_width=True):
                            fdb.excluir_comprovante(banco, cid, comp["id"])
                            st.session_state["fin_msg"] = "Comprovante removido."
                            st.rerun()
        vu = st.session_state.get("fc_up_v", 0)
        novos = st.file_uploader("Anexar comprovantes (JPG, PNG, WEBP)", type=["jpg", "jpeg", "png", "webp"],
                                 accept_multiple_files=True, key=f"fc_up_{lid}_{vu}")
        if st.button("Anexar ao lançamento", key=f"fc_add_{lid}", disabled=not novos):
            avisos, ok = [], 0
            for arq in novos:
                try:
                    fdb.adicionar_comprovante(banco, cid, lid, arq.name, arq.getvalue())
                    ok += 1
                except ValueError as erro:
                    avisos.append(f"{arq.name}: {erro}")
            st.session_state["fc_up_v"] = vu + 1
            st.session_state["fin_msg"] = f"{ok} comprovante(s) anexado(s)." + (" Atenção: " + "; ".join(avisos) if avisos else "")
            st.rerun()


# ---------------------------------------------------------------------------
# Dízimos e ofertas
# ---------------------------------------------------------------------------
_COL_VALOR = "Valor (R$)"


def _df_lista(itens, coluna_nome="Nome"):
    return pd.DataFrame({coluna_nome: [i["nome"] for i in itens],
                         _COL_VALOR: [i["valor_centavos"] / 100 for i in itens]}).astype({coluna_nome: "object", _COL_VALOR: "float"})


def _linhas(df, coluna_nome="Nome"):
    saida = []
    for _, linha in df.iterrows():
        nome = linha.get(coluna_nome)
        valor = linha.get(_COL_VALOR)
        saida.append({"nome": "" if pd.isna(nome) else str(nome).strip(),
                      "valor_centavos": 0 if pd.isna(valor) else fdb.para_centavos(valor)})
    return saida


def _dizimos(banco, conta, caixa, ano, mes):
    cid = conta["congregacao_id"]
    contrib = fdb.obter_contribuicoes(banco, cid, ano, mes)
    v = st.session_state.get("fd_v", 0)
    chave = f"{ano}_{mes}_{v}"
    st.caption("Digite o nome e o valor de cada dizimista e as ofertas do mês. Use a última linha vazia da tabela para "
               "acrescentar um nome. Os totais batem com o relatório que a tesouraria já usa.")
    cfg = {_COL_VALOR: st.column_config.NumberColumn(_COL_VALOR, min_value=0.0, step=0.01, format="%.2f")}

    st.markdown("##### Dizimistas · Envelope")
    ed_env = st.data_editor(_df_lista(contrib["dizimo_envelope"]), num_rows="dynamic", hide_index=True,
                            use_container_width=True, key=f"ed_env_{chave}", column_config=cfg)
    st.markdown("##### Dizimistas · PIX")
    ed_pix = st.data_editor(_df_lista(contrib["dizimo_pix"]), num_rows="dynamic", hide_index=True,
                            use_container_width=True, key=f"ed_pix_{chave}", column_config=cfg)

    st.markdown("##### Ofertas · Envelopes (por semana)")
    semanas = {i["nome"].strip().upper(): i["valor_centavos"] / 100 for i in contrib["oferta_envelope"]}
    df_sem = pd.DataFrame({"Semana": [f"SEMANA {n}" for n in range(1, 6)],
                           _COL_VALOR: [semanas.get(f"SEMANA {n}") or 0.0 for n in range(1, 6)]})
    ed_sem = st.data_editor(df_sem, num_rows="fixed", hide_index=True, use_container_width=True,
                            disabled=["Semana"], key=f"ed_sem_{chave}", column_config=cfg)
    st.markdown("##### Ofertas · PIX")
    pix_itens = contrib["oferta_pix"] or [{"nome": "OFERTA MENSAL - PIX", "valor_centavos": 0}]
    ed_opix = st.data_editor(_df_lista(pix_itens, "Descrição"), num_rows="dynamic", hide_index=True,
                             use_container_width=True, key=f"ed_opix_{chave}", column_config=cfg)

    novos = {"dizimo_envelope": _linhas(ed_env), "dizimo_pix": _linhas(ed_pix),
             "oferta_envelope": [{"nome": s["nome"] or f"SEMANA {i + 1}", "valor_centavos": s["valor_centavos"]}
                                 for i, s in enumerate(_linhas(ed_sem, "Semana"))],
             "oferta_pix": _linhas(ed_opix, "Descrição")}
    t = fdb.totais_contribuicoes(novos)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Dízimos (envelope + PIX)", _reais(t["dizimos"]))
    m2.metric("Ofertas (envelope + PIX)", _reais(t["ofertas"]))
    m3.metric("Total geral de entradas", _reais(t["geral"]))
    m4.metric("Dizimistas", sum(1 for g in ("dizimo_envelope", "dizimo_pix") for i in novos[g] if i["valor_centavos"] > 0))

    b1, b2, b3 = st.columns(3)
    if b1.button("Salvar dízimos e ofertas", key=f"fd_salvar_{chave}", use_container_width=True):
        try:
            fdb.salvar_contribuicoes(banco, cid, ano, mes, novos)
        except ValueError as erro:
            st.error(str(erro))
        else:
            st.session_state["fin_msg"] = f"Dízimos e ofertas de {fdb.MESES[mes - 1]}/{ano} salvos."
            st.rerun()
    if b2.button(f"Salvar e lançar no caixa de {fdb.MESES[mes - 1]}", key=f"fd_lancar_{chave}", use_container_width=True):
        try:
            fdb.salvar_contribuicoes(banco, cid, ano, mes, novos)
            r = fdb.sincronizar_receitas(banco, cid, caixa["id"], ano, mes, conta["nome"])
        except ValueError as erro:
            st.error(str(erro))
        else:
            st.session_state["fin_msg"] = (f"Salvo e lançado no caixa: {r['criados']} criado(s), "
                                           f"{r['atualizados']} atualizado(s), {r['removidos']} removido(s).")
            st.rerun()
    am, aa = fdb.mes_anterior(ano, mes)[1], fdb.mes_anterior(ano, mes)[0]
    if b3.button(f"Copiar nomes de {fdb.MESES[am - 1]}", key=f"fd_copiar_{chave}", use_container_width=True):
        copiou = {}
        for g in ("dizimo_envelope", "dizimo_pix"):
            if contrib[g]:
                continue
            copiou[g] = [{"nome": n, "valor_centavos": 0} for n in fdb.nomes_do_mes(banco, cid, aa, am, g)]
        if not any(copiou.values()):
            st.warning("Nada para copiar: os dizimistas deste mês já foram preenchidos ou o mês anterior está vazio.")
        else:
            fdb.salvar_contribuicoes(banco, cid, ano, mes, {**contrib, **copiou})
            st.session_state["fd_v"] = v + 1
            st.session_state["fin_msg"] = "Nomes copiados do mês anterior. Agora é só digitar os valores."
            st.rerun()
    st.caption("O botão do meio cria (ou atualiza) no caixa os três recebimentos do mês: dízimos de envelope, "
               "dízimos por PIX e ofertas. Pode apertar de novo depois de corrigir um valor: nada é duplicado.")


# ---------------------------------------------------------------------------
# Relatórios
# ---------------------------------------------------------------------------
def _relatorios(banco, conta, caixa, ano, mes):
    cid = conta["congregacao_id"]
    titulo = _titulo(caixa, conta)
    emitido = datetime.now()

    st.markdown(f"#### Relatório de caixa · {fdb.MESES[mes - 1]}/{ano}")
    c1, c2 = st.columns(2)
    com_data = c1.checkbox("Imprimir a data de cada lançamento", value=True, key="fr_data")
    anexar = c2.checkbox("Incluir os comprovantes no final do PDF", value=False, key="fr_anexo")
    r = fdb.resumo_mes(banco, cid, caixa["id"], ano, mes)
    comprovantes = fdb.comprovantes_do_mes(banco, cid, caixa["id"], ano, mes) if anexar else None
    if anexar and not comprovantes:
        st.caption("Nenhum comprovante anexado neste mês.")
    dados = dict(r, titulo_igreja=titulo, caixa_nome=caixa["nome"], ano=ano, mes=mes, emitido_em=emitido)
    st.download_button("Baixar relatório de caixa (PDF)", data=fpdf.pdf_caixa(dados, com_data, comprovantes),
                       file_name=_nome_arquivo("caixa", caixa, ano, mes), mime="application/pdf", key="dl_caixa")
    st.caption(f"{len(r['lancamentos'])} lançamento(s) · recebimentos {_reais(r['rec'])} · pagamentos "
               f"{_reais(r['pag'])} · saldo atual {_reais(r['saldo_atual'])}")

    st.markdown(f"#### Relatório dos dizimistas · {fdb.MESES[mes - 1]}/{ano}")
    contrib = fdb.obter_contribuicoes(banco, cid, ano, mes)
    if not any(contrib.values()):
        st.caption("Ainda não há dízimos e ofertas salvos neste mês (o relatório sai com as linhas em branco).")
    st.download_button("Baixar relatório dos dizimistas (PDF)",
                       data=fpdf.pdf_dizimistas({"titulo_igreja": titulo, "ano": ano, "mes": mes, "contrib": contrib}),
                       file_name=_nome_arquivo("dizimistas", caixa, ano, mes), mime="application/pdf", key="dl_dizimo")

    st.markdown(f"#### Relatório anual · {ano}")
    st.caption("Resumo mês a mês, recebimentos e pagamentos por conta, dízimos e ofertas e a lista de dizimistas do ano.")
    resumo = fdb.resumo_ano(banco, cid, caixa["id"], ano)
    st.download_button("Baixar relatório anual (PDF)",
                       data=fpdf.pdf_anual({"titulo_igreja": titulo, "caixa_nome": caixa["nome"], "ano": ano,
                                            "resumo": resumo, "contrib_ano": fdb.contribuicoes_do_ano(banco, cid, ano),
                                            "emitido_em": emitido}),
                       file_name=_nome_arquivo("anual", caixa, ano), mime="application/pdf", key="dl_anual")


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
def _configuracao(banco, conta, caixas):
    cid = conta["congregacao_id"]
    st.markdown("#### Configuração do caixa")
    st.caption("A **data inicial** e o **saldo inicial** definem de onde o caixa começa: o saldo inicial é o que sobrou "
               "do mês anterior ao primeiro mês controlado aqui (no modelo da igreja, o “SALDO ANTERIOR”). Os meses "
               "seguintes continuam sozinhos a partir dos lançamentos.")
    por_id = {c["id"]: c for c in caixas}
    cid_caixa = st.selectbox("Caixa", list(por_id.keys()), format_func=lambda i: por_id[i]["nome"], key="cfg_caixa")
    c = por_id[cid_caixa]
    k = lambda nome: f"cfg_{cid_caixa}_{nome}"
    nome = st.text_input("Nome do caixa (aparece no relatório)", value=c["nome"], key=k("nome"))
    titulo = st.text_input("Nome da igreja nos relatórios", value=c["titulo_igreja"] or fdb.titulo_padrao(conta["congregacao"]),
                           key=k("titulo"))
    c1, c2 = st.columns(2)
    inicio = c1.date_input("Data inicial do caixa", value=c["data_inicial"], min_value=date(2000, 1, 1),
                           format="DD/MM/YYYY", key=k("data"))
    saldo = c2.number_input("Saldo inicial (R$)", value=c["saldo_inicial"] / 100, step=0.01, format="%.2f", key=k("saldo"))
    if st.button("Salvar configuração", key=k("salvar")):
        try:
            fdb.atualizar_caixa(banco, cid, cid_caixa, nome, titulo, fdb.para_centavos(saldo), inicio)
        except ValueError as erro:
            st.error(str(erro))
        else:
            st.session_state["fin_msg"] = "Configuração do caixa salva."
            st.rerun()

    with st.expander("Criar outro caixa (por exemplo, missões, construção…)"):
        n_nome = st.text_input("Nome do novo caixa", key="cfg_novo_nome")
        n1, n2 = st.columns(2)
        n_data = n1.date_input("Data inicial", value=date(date.today().year, 1, 1), format="DD/MM/YYYY",
                               key="cfg_novo_data")
        n_saldo = n2.number_input("Saldo inicial (R$)", value=0.0, step=0.01, format="%.2f", key="cfg_novo_saldo")
        if st.button("Criar caixa", key="cfg_novo_criar"):
            try:
                fdb.criar_caixa(banco, cid, n_nome, titulo, fdb.para_centavos(n_saldo), n_data)
            except ValueError as erro:
                st.error(str(erro))
            else:
                st.session_state["fin_msg"] = f"Caixa “{n_nome.strip()}” criado."
                st.rerun()
