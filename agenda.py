"""Gestão do calendário de festividades (uso da liderança).

Reúne: leitura da planilha do calendário, regras de prioridade e choque de datas, feriados,
sugestão de novas datas, ajuste de datas e exportação em PDF/Excel.
Segredos: google_credentials (obrigatório) e planilha_url (opcional).
"""
import json
import re
import unicodedata
from datetime import date, datetime, timedelta

import gspread
import pandas as pd
import streamlit as st

try:
    import exportacao
    EXPORT_OK, EXPORT_ERRO = True, ""
except Exception as _erro_import:  # exportacao.py ausente no repositório
    EXPORT_OK, EXPORT_ERRO = False, str(_erro_import)

LOGO_URL = "https://github.com/rcrystiandados/app-igreja/blob/main/logo.jpeg?raw=true"

PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1XEJ5z3hSdbfGEdeJFljZgZwBqYtuiI3zh6H9bLAT4ks/edit?usp=sharing"

NOME_PRIORIDADE = {1: "Alta", 2: "Média", 3: "Baixa"}

DIAS_SEMANA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]

FERIADOS_LOCAIS_FIXOS = {
    (6, 24): "São João (feriado em Campina Grande)",
    (8, 5): "Fundação da Paraíba (feriado estadual)",
    (10, 11): "Aniversário de Campina Grande (feriado municipal)",
}

try:
    PLANILHA_URL = st.secrets.get("planilha_url", PLANILHA_URL)
except Exception:
    pass


def _abrir_aba():
    credenciais = json.loads(st.secrets["google_credentials"])
    gc = gspread.service_account_from_dict(credenciais)
    return gc.open_by_url(PLANILHA_URL).get_worksheet(0)

def _norm(texto):
    return unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower().strip()

def peso_evento(tipo):
    t = _norm(tipo)
    if "aniversario" in t and "congrega" in t:
        return 1
    if "aniversario" in t and ("uac" in t or "uhc" in t):
        return 2
    return 3

def _para_data(valor):
    return pd.to_datetime(valor, dayfirst=True, errors="coerce")

def _registro(nome, regiao, tipo, inicio, fim, origem, linha=None, congregacao=""):
    ini = _para_data(inicio)
    if pd.isna(ini):
        return None
    f = _para_data(fim)
    if pd.isna(f) or f < ini:
        f = ini
    return {"nome": str(nome), "regiao": str(regiao), "tipo": str(tipo),
            "ini": ini, "fim": f, "peso": peso_evento(tipo), "origem": origem, "linha": linha,
            "congregacao": str(congregacao).strip()}

def registros_da_planilha(df_base):
    regs = []
    if df_base is None or df_base.empty:
        return regs
    for _, r in df_base.iterrows():
        reg = _registro(
            r.get("Nome da Festividade", ""), r.get("Região da Congregação", ""),
            r.get("Tipo de Festividade", ""), r.get("Data de Inicio da Festividade"),
            r.get("Data Final da Festividade"), "Planilha",
            int(r["_linha"]) if "_linha" in r and str(r["_linha"]).strip() != "" else None,
            r.get("Congregação", ""),
        )
        if reg:
            regs.append(reg)
    return regs

def motivo_do_choque(a, b):
    if not (a["ini"] <= b["fim"] and b["ini"] <= a["fim"]):
        return None
    # Regra: não pode haver choque dentro da mesma região; entre regiões diferentes pode.
    ra, rb = _norm(a["regiao"]), _norm(b["regiao"])
    if ra and ra == rb:
        return "Mesma região"
    return None

def choques_do_novo(novo, base):
    return [(b, m) for b in base if (m := motivo_do_choque(novo, b))]

def todos_os_choques(regs):
    pares = []
    for i in range(len(regs)):
        for j in range(i + 1, len(regs)):
            m = motivo_do_choque(regs[i], regs[j])
            if m:
                pares.append((regs[i], regs[j], m))
    return pares

def descrever(reg):
    ini, fim = reg["ini"].strftime("%d/%m/%Y"), reg["fim"].strftime("%d/%m/%Y")
    periodo = ini if ini == fim else f"{ini} a {fim}"
    local = " · ".join(x for x in (reg.get("congregacao", ""), reg["regiao"]) if x)
    return f"{reg['nome']} ({local}, {periodo})" if local else f"{reg['nome']} ({periodo})"

def _pascoa(ano):
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)

def feriados_do_ano(ano):
    p = _pascoa(ano)
    f = {
        date(ano, 1, 1): "Confraternização Universal",
        p - timedelta(days=48): "Carnaval (ponto facultativo)",
        p - timedelta(days=47): "Carnaval (ponto facultativo)",
        p - timedelta(days=2): "Sexta-feira Santa",
        p: "Páscoa",
        date(ano, 4, 21): "Tiradentes",
        date(ano, 5, 1): "Dia do Trabalho",
        p + timedelta(days=60): "Corpus Christi",
        date(ano, 9, 7): "Independência do Brasil",
        date(ano, 10, 12): "Nossa Senhora Aparecida",
        date(ano, 11, 2): "Finados",
        date(ano, 11, 15): "Proclamação da República",
        date(ano, 11, 20): "Consciência Negra",
        date(ano, 12, 24): "Véspera de Natal (ponto facultativo)",
        date(ano, 12, 25): "Natal",
        date(ano, 12, 31): "Véspera de Ano-Novo (ponto facultativo)",
    }
    for (m, d), nome in FERIADOS_LOCAIS_FIXOS.items():
        f[date(ano, m, d)] = nome
    return f

def feriados_no_periodo(ini, fim):
    achados = []
    for ano in range(ini.year, fim.year + 1):
        for d, nome in feriados_do_ano(ano).items():
            if ini <= d <= fim:
                achados.append((d, nome))
    return sorted(achados)

def fmt_data(d):
    return f"{d:%d/%m/%Y} ({DIAS_SEMANA[d.weekday()]})"

def fmt_periodo(ini, fim):
    return fmt_data(ini) if ini == fim else f"{fmt_data(ini)} a {fmt_data(fim)}"

def sugerir_datas(alvo, todos, evitar_feriados=True, mesmo_dia_semana=True, limite=6, janela=180):
    """Datas livres, com a mesma duração do evento, mais próximas da data original.
    Respeita a regra de choque da região (outras regiões podem coincidir) e os feriados."""
    duracao = alvo["fim"] - alvo["ini"]
    hoje = pd.Timestamp.today().normalize()
    outros = [r for r in todos if r.get("linha") != alvo.get("linha")]
    sugestoes = []
    for delta in sorted(range(-janela, janela + 1), key=lambda x: (abs(x), x)):
        if delta == 0 or (mesmo_dia_semana and delta % 7 != 0):
            continue
        ini = alvo["ini"] + pd.Timedelta(days=delta)
        fim = ini + duracao
        if ini < hoje or ini.year != alvo["ini"].year or fim.year != alvo["ini"].year:
            continue
        cand = dict(alvo, ini=ini, fim=fim)
        if any(motivo_do_choque(cand, o) for o in outros):
            continue
        if evitar_feriados and feriados_no_periodo(ini.date(), fim.date()):
            continue
        sugestoes.append({"ini": ini, "fim": fim, "delta": delta})
        if len(sugestoes) >= limite:
            break
    return sugestoes

def atualizar_datas_planilha(alvo, novo_ini, novo_fim, motivo):
    """Grava as novas datas na linha do evento e registra a alteração na aba 'Alterações de datas'."""
    from gspread.utils import rowcol_to_a1
    aba = _abrir_aba()
    cab = [c.strip() for c in aba.row_values(1)]
    ci = cab.index("Data de Inicio da Festividade") + 1
    cf = cab.index("Data Final da Festividade") + 1
    cn = cab.index("Nome da Festividade") + 1
    linha = alvo["linha"]
    atual = aba.row_values(linha)
    atual += [""] * (max(ci, cf, cn) - len(atual))
    ini_antigo, fim_antigo = alvo["ini"].strftime("%d/%m/%Y"), alvo["fim"].strftime("%d/%m/%Y")
    if (atual[cn - 1].strip() != alvo["nome"].strip()
            or _para_data(atual[ci - 1]) != alvo["ini"]):
        raise ValueError("A planilha foi alterada por outra pessoa. Recarregue a página e tente de novo.")
    aba.batch_update(
        [{"range": rowcol_to_a1(linha, ci), "values": [[novo_ini.strftime("%d/%m/%Y")]]},
         {"range": rowcol_to_a1(linha, cf), "values": [[novo_fim.strftime("%d/%m/%Y")]]}],
        value_input_option="RAW",
    )
    planilha = aba.spreadsheet
    try:
        hist = planilha.worksheet("Alterações de datas")
    except gspread.WorksheetNotFound:
        hist = planilha.add_worksheet(title="Alterações de datas", rows=200, cols=7)
        hist.append_row(["Data da alteração", "Festividade", "Região", "Início anterior",
                         "Fim anterior", "Novo início", "Novo fim", "Motivo"])
    hist.append_row([
        datetime.now().strftime("%d/%m/%Y %H:%M:%S"), alvo["nome"], alvo["regiao"],
        ini_antigo, fim_antigo, novo_ini.strftime("%d/%m/%Y"), novo_fim.strftime("%d/%m/%Y"), motivo,
    ], value_input_option="RAW")

def _cartao_evento(r, remanejar=False):
    """Cartão com os dados de um evento (usado nos dois lados do choque)."""
    with st.container(border=True):
        if remanejar:
            st.markdown(":red[**Deve ser remarcado**]")
        st.markdown(
            f"**{r['nome']}**  \n{r['tipo']} · prioridade **{NOME_PRIORIDADE[r['peso']].lower()}**  \n"
            f"{r['congregacao'] or '-'} · {r['regiao']}  \n"
            f"Período atual: **{fmt_periodo(r['ini'].date(), r['fim'].date())}**"
        )

CSS_AJUSTE = """<style>
    span.aj-marca {display: none;}
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.aj-p1) {
        background: #FDECEA !important; border: 2px solid #C0392B !important; border-radius: 10px;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.aj-p2) {
        background: #FFF6DD !important; border: 2px solid #D69E2E !important; border-radius: 10px;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.aj-p3) {
        background: #E6F4EC !important; border: 2px solid #2E7D5B !important; border-radius: 10px;
    }
    .aj-legenda {font-size: .85rem; color: #475569; margin: .2rem 0 .8rem 0;}
    .aj-legenda b.p1 {color: #C0392B;} .aj-legenda b.p2 {color: #B7791F;} .aj-legenda b.p3 {color: #2E7D5B;}
</style>"""


def _cartao_ajuste(r, regs, deve_remarcar):
    """Cartão do evento, colorido pela prioridade, com a opção de remarcar e as 2 sugestões."""
    selecionado = st.session_state.get("aj_alvo") == r["linha"]
    with st.container(border=True):
        st.markdown(f'<span class="aj-marca aj-p{r["peso"]}"></span>', unsafe_allow_html=True)
        if deve_remarcar:
            st.markdown(":red[**Deve ser remarcado**]")
        st.markdown(
            f"**{r['nome']}**  \n{r['tipo']} · prioridade **{NOME_PRIORIDADE[r['peso']].lower()}**  \n"
            f"{r['congregacao'] or '-'} · {r['regiao']}  \n"
            f"Período atual: **{fmt_periodo(r['ini'].date(), r['fim'].date())}**"
        )
        if not selecionado:
            if st.button("Remarcar este evento", key=f"aj_rem_{r['linha']}", use_container_width=True):
                st.session_state["aj_alvo"] = r["linha"]
                st.session_state.pop("aj_confirmar", None)
                st.session_state["aj_pendente"] = (r["ini"].date(), r["fim"].date())
                st.rerun()
            return

        st.markdown("**Datas sugeridas**")
        sugestoes = sugerir_datas(r, regs, limite=2)
        if not sugestoes:
            sugestoes = sugerir_datas(r, regs, mesmo_dia_semana=False, limite=2)
            if sugestoes:
                st.caption("Não há datas livres no mesmo dia da semana; estas são de outros dias.")
        if not sugestoes:
            st.info("Não encontrei datas livres neste ano. Escolha a data manualmente.")
        for i, sg in enumerate(sugestoes):
            dias = abs(sg["delta"])
            quando = f"{dias} dia(s) {'depois' if sg['delta'] > 0 else 'antes'} · sem choque na região e sem feriados"
            c1, c2 = st.columns([3, 1.3], vertical_alignment="center")
            c1.markdown(f"**{fmt_periodo(sg['ini'].date(), sg['fim'].date())}**")
            c1.caption(quando)
            if c2.button("Escolher", key=f"aj_sug_{r['linha']}_{i}", use_container_width=True):
                st.session_state["aj_pendente"] = (sg["ini"].date(), sg["fim"].date())
                st.session_state["aj_confirmar"] = r["linha"]
                st.rerun()
        if st.button("Escolher outra data", key=f"aj_outra_{r['linha']}", use_container_width=True):
            st.session_state["aj_pendente"] = (r["ini"].date(), r["fim"].date())
            st.session_state["aj_confirmar"] = r["linha"]
            st.rerun()


def painel_ajuste_datas(df_base):
    st.markdown(CSS_AJUSTE, unsafe_allow_html=True)
    regs = registros_da_planilha(df_base)
    regs = [r for r in regs if r["linha"] is not None]
    if not regs:
        st.info("Não há eventos cadastrados para ajustar.")
        return

    # aplica a data escolhida (antes de criar os campos de data)
    pend = st.session_state.pop("aj_pendente", None)
    if pend:
        st.session_state["aj_ini"], st.session_state["aj_fim"] = pend
    msg = st.session_state.pop("aj_msg", None)
    if msg:
        st.success(msg)

    pares = todos_os_choques(regs)
    st.markdown("#### 1. Escolha o evento")
    if not pares:
        st.success("A agenda está limpa. Nenhum choque detectado.")
        return

    pares = sorted(pares, key=lambda p: (max(p[0]["ini"], p[1]["ini"]), p[0]["nome"]))
    por_id = {(a_["linha"], b_["linha"]): (a_, b_, m) for a_, b_, m in pares}

    def rotulo_par(chave):
        a_, b_, _m = por_id[chave]
        return f"{max(a_['ini'], b_['ini']):%d/%m/%Y} - {a_['nome']}  ×  {b_['nome']}"

    chave = st.selectbox("Evento em choque", list(por_id.keys()), format_func=rotulo_par, key="aj_choque")
    a_, b_, motivo_choque = por_id[chave]

    # ao trocar de choque, limpa a escolha anterior
    if st.session_state.get("aj_par") != chave:
        st.session_state["aj_par"] = chave
        st.session_state.pop("aj_alvo", None)
        st.session_state.pop("aj_confirmar", None)
    if st.session_state.get("aj_alvo") not in (a_["linha"], b_["linha"]):
        st.session_state.pop("aj_alvo", None)
        st.session_state.pop("aj_confirmar", None)

    # quem deve ser remarcado: o de menor prioridade (maior número); empate, a liderança escolhe
    if a_["peso"] > b_["peso"]:
        sugerido = 0
    elif b_["peso"] > a_["peso"]:
        sugerido = 1
    else:
        sugerido = None

    st.caption(f"Choque: {motivo_choque.lower()}. Escolha, em um dos cartões, o evento que será remarcado.")
    st.markdown(
        '<div class="aj-legenda">Cor do cartão = prioridade: <b class="p1">vermelho</b> alta · '
        '<b class="p2">amarelo</b> média · <b class="p3">verde</b> baixa</div>', unsafe_allow_html=True)
    if sugerido is None:
        st.info("Os dois eventos têm a mesma prioridade: a liderança define qual será remarcado.")
    col_a, col_b = st.columns(2)
    with col_a:
        _cartao_ajuste(a_, regs, deve_remarcar=sugerido == 0)
    with col_b:
        _cartao_ajuste(b_, regs, deve_remarcar=sugerido == 1)

    # ---------------- 2. confirmação (só depois de escolher uma data) ----------------
    alvo = next((r for r in (a_, b_) if r["linha"] == st.session_state.get("aj_alvo")), None)
    if alvo is None or st.session_state.get("aj_confirmar") != alvo["linha"]:
        return
    outros = [r for r in regs if r["linha"] != alvo["linha"]]
    if "aj_ini" not in st.session_state or "aj_fim" not in st.session_state:
        st.session_state["aj_ini"], st.session_state["aj_fim"] = alvo["ini"].date(), alvo["fim"].date()

    st.markdown("#### 2. Confirme a nova data")
    st.caption(f"Remarcando: **{alvo['nome']}**")
    d1, d2 = st.columns(2)
    novo_ini = d1.date_input("Nova data de início", format="DD/MM/YYYY", key="aj_ini")
    if st.session_state.get("aj_fim") is None or st.session_state["aj_fim"] < novo_ini:
        st.session_state["aj_fim"] = novo_ini
    novo_fim = d2.date_input("Nova data final", format="DD/MM/YYYY", min_value=novo_ini, key="aj_fim")

    cand = dict(alvo, ini=pd.Timestamp(novo_ini), fim=pd.Timestamp(novo_fim))
    conflitos = choques_do_novo(cand, outros)
    feriados = feriados_no_periodo(novo_ini, novo_fim)
    if conflitos:
        st.error("A nova data entra em choque com:\n\n" + "\n".join(
            f"- {descrever(c)}  ({m.lower()})" for c, m in conflitos))
    else:
        st.success("A nova data não tem choque na região.")
    if feriados:
        st.warning("Feriados no período: " + "; ".join(f"{d:%d/%m} ({n})" for d, n in feriados) + ".")
    if pd.Timestamp(novo_ini) < pd.Timestamp.today().normalize():
        st.warning("A nova data de início já passou.")

    motivo = st.text_input("Motivo da alteração (opcional)", key="aj_motivo",
                           placeholder="Ex.: choque com aniversário de congregação")
    confirma = True
    if conflitos:
        confirma = st.checkbox("Salvar mesmo com choque de datas", key="aj_confirma")
    igual = novo_ini == alvo["ini"].date() and novo_fim == alvo["fim"].date()
    if st.button("Salvar nova data", disabled=igual or not confirma):
        try:
            atualizar_datas_planilha(alvo, novo_ini, novo_fim, motivo.strip())
        except Exception as erro:
            st.error(f"Não foi possível salvar: {erro}")
        else:
            st.cache_data.clear()
            st.session_state.pop("aj_alvo", None)
            st.session_state.pop("aj_confirmar", None)
            st.session_state["aj_msg"] = (
                f"Datas de \"{alvo['nome']}\" atualizadas para {fmt_periodo(novo_ini, novo_fim)}."
            )
            st.rerun()


@st.cache_data(ttl=86400)
def baixar_logo():
    try:
        import urllib.request
        with urllib.request.urlopen(LOGO_URL, timeout=6) as r:
            return r.read()
    except Exception:
        return None

def _slug(texto):
    return re.sub(r"[^a-z0-9]+", "_", _norm(texto)).strip("_")

def _painel_exportacao(df_base, chave, incluir_contato=False):
    """Painel para exportar o calendário (completo ou por região; anual, semestral ou mensal)."""
    if not EXPORT_OK:
        st.warning("A exportação não está disponível: o arquivo exportacao.py não foi encontrado "
                   f"no repositório. Detalhe: {EXPORT_ERRO}")
        return
    eventos = exportacao.preparar_eventos(df_base, peso_evento)
    if not eventos:
        st.info("Ainda não há eventos para exportar.")
        return

    anos = sorted({e["ini"].year for e in eventos} | {e["fim"].year for e in eventos})
    agora = datetime.now()
    futuros = [a for a in anos if a >= agora.year]
    ano_padrao = futuros[0] if futuros else anos[-1]
    regioes = sorted({e["regiao"] for e in eventos if e["regiao"]})

    c1, c2 = st.columns(2)
    escopo = c1.radio("O que exportar", ["Calendário completo", "Por região"],
                      horizontal=True, key=f"{chave}_escopo")
    regiao = None
    if escopo == "Por região":
        regiao = c2.selectbox("Região", regioes, key=f"{chave}_regiao")

    p1, p2, p3 = st.columns(3)
    tipo_periodo = p1.selectbox("Período", ["Anual", "Semestral", "Mensal"], key=f"{chave}_periodo")
    ano = p2.selectbox("Ano", anos, index=anos.index(ano_padrao), key=f"{chave}_ano")
    semestre, mes = 1, 1
    if tipo_periodo == "Semestral":
        semestre = p3.selectbox("Semestre", [1, 2], format_func=lambda x: f"{x}º semestre", key=f"{chave}_sem")
    elif tipo_periodo == "Mensal":
        mes = p3.selectbox("Mês", list(range(1, 13)), index=agora.month - 1,
                           format_func=lambda m: exportacao.MESES[m - 1], key=f"{chave}_mes")

    formato = st.radio("Formato", ["PDF (visual)", "Excel"], horizontal=True, key=f"{chave}_formato")

    ini, fim, rotulo = exportacao.intervalo(tipo_periodo, ano, semestre, mes)
    selecionados = exportacao.filtrar(eventos, ini, fim, regiao)
    st.caption(f"{len(selecionados)} evento(s) no período selecionado.")

    sig = (escopo, regiao, tipo_periodo, ano, semestre, mes, formato, len(eventos), incluir_contato)
    chave_arq = f"{chave}_arquivo"

    if st.button("Gerar arquivo", key=f"{chave}_gerar", disabled=not selecionados):
        titulo = "Calendário de Atividades MEN"
        subtitulo = f"{rotulo} · {regiao if regiao else 'Todas as regiões'}"
        if incluir_contato:
            subtitulo += " · Uso interno"
        try:
            if formato.startswith("PDF"):
                dados = exportacao.gerar_pdf(selecionados, titulo, subtitulo, incluir_contato, baixar_logo())
                ext, mime = "pdf", "application/pdf"
            else:
                dados = exportacao.gerar_excel(selecionados, f"{titulo} - {subtitulo}", incluir_contato,
                                               abas_por_regiao=regiao is None)
                ext, mime = "xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            st.session_state[chave_arq] = {
                "sig": sig, "dados": dados, "mime": mime,
                "nome": f"calendario_men_{_slug(regiao or 'completo')}_{_slug(rotulo)}.{ext}",
                "rotulo": "PDF" if ext == "pdf" else "Excel",
            }
        except ImportError:
            st.error("Faltam bibliotecas para exportar. Adicione `openpyxl` e `reportlab` ao arquivo "
                     "requirements.txt do repositório.")
        except Exception as erro:
            st.error(f"Não foi possível gerar o arquivo: {erro}")

    arq = st.session_state.get(chave_arq)
    if arq and arq["sig"] == sig:
        st.download_button(f"Baixar {arq['rotulo']}", data=arq["dados"], file_name=arq["nome"],
                           mime=arq["mime"], key=f"{chave}_baixar")

def bloco_exportacao(df_base, chave, incluir_contato=False):
    """Bloco em destaque com o painel de exportação."""
    with st.container(border=True):
        st.markdown(
            '<div class="marca-exportar"></div>'
            '<div class="exp-topo"><div class="exp-icone">⬇</div><div>'
            '<div class="exp-titulo">Exportar calendário</div>'
            '<div class="exp-sub">Baixe o calendário em PDF (visual) ou Excel, completo ou por região.</div>'
            '</div></div>',
            unsafe_allow_html=True,
        )
        _painel_exportacao(df_base, chave, incluir_contato)


@st.cache_data(ttl=60)
def carregar_calendario():
    """Lê a planilha do calendário como texto, guardando o número da linha de cada evento (_linha)."""
    valores = _abrir_aba().get_all_values()
    if len(valores) < 2:
        return pd.DataFrame()
    cab = [c.strip() for c in valores[0]]
    linhas = []
    for numero, l in enumerate(valores[1:], start=2):
        if not any(str(c).strip() for c in l):
            continue
        linhas.append((list(l) + [""] * len(cab))[:len(cab)] + [numero])
    df = pd.DataFrame(linhas, columns=cab + ["_linha"])
    colunas_cong = [c for c in df.columns if "Congregação -" in c]
    if colunas_cong:
        df["Congregação"] = df[colunas_cong].astype(str).agg("".join, axis=1)
        df = df.drop(columns=colunas_cong)
    elif "Congregação" not in df.columns:
        df["Congregação"] = "Não informada"
    finais = ["Data de Inicio da Festividade", "Data Final da Festividade", "Região da Congregação",
              "Congregação", "Nome da Festividade", "Tipo de Festividade", "Nome Completo",
              "Cargo/Função", "Whatsapp para Contato", "_linha"]
    return df[[c for c in finais if c in df.columns]]


def painel_choques(df_base):
    """Página Agenda: pares de eventos em choque (e qual remanejar) e a lista de todos os eventos."""
    if df_base is None or df_base.empty:
        st.info("Ainda não há eventos no calendário.")
        return
    pares = todos_os_choques(registros_da_planilha(df_base))
    if pares:
        st.error(f"Foram detectados {len(pares)} choque(s) de agenda.")
        linhas = []
        for a_, b_, motivo in pares:
            if a_["peso"] < b_["peso"]:
                remanejar = descrever(b_)
            elif b_["peso"] < a_["peso"]:
                remanejar = descrever(a_)
            else:
                remanejar = "Mesma prioridade: a liderança define"
            linhas.append({
                "Evento A": descrever(a_), "Prioridade A": NOME_PRIORIDADE[a_["peso"]],
                "Evento B": descrever(b_), "Prioridade B": NOME_PRIORIDADE[b_["peso"]],
                "Motivo": motivo, "Deve remanejar": remanejar,
            })
        st.dataframe(pd.DataFrame(linhas), use_container_width=True, hide_index=True)
        st.info("Para remarcar um evento, use **Ajustar datas** no menu lateral. O app sugere datas "
                "livres na região e evita feriados.")
    else:
        st.success("A agenda está limpa. Nenhum choque detectado.")
    st.markdown("#### Todos os eventos")
    regs = registros_da_planilha(df_base)
    em_choque = {x["linha"] for a_, b_, _m in pares for x in (a_, b_)}
    if regs:
        regs = sorted(regs, key=lambda r: (r["ini"], r["nome"]))
        st.caption(f"{len(regs)} evento(s) no calendário, em ordem de data.")
        st.dataframe(pd.DataFrame([{
            "Início": r["ini"].strftime("%d/%m/%Y"), "Fim": r["fim"].strftime("%d/%m/%Y"),
            "Evento": r["nome"], "Tipo": r["tipo"], "Prioridade": NOME_PRIORIDADE[r["peso"]],
            "Congregação": r["congregacao"], "Região": r["regiao"],
            "Choque": "Sim" if r["linha"] in em_choque else "—",
        } for r in regs]), use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum evento com data válida no calendário.")
    st.link_button("Abrir planilha do banco de dados", PLANILHA_URL)


def contar_choques(df_base):
    """(total de pares em choque, eventos em choque) para o painel inicial."""
    regs = registros_da_planilha(df_base)
    pares = todos_os_choques(regs)
    ids = {x["linha"] for a_, b_, _m in pares for x in (a_, b_) if x["linha"] is not None}
    return len(pares), len(ids)
