"""Banco de dados do financeiro da congregação: caixa mensal, dízimos e ofertas, comprovantes.

- Todo valor é guardado em centavos (inteiro), para nunca haver erro de arredondamento.
- Toda função recebe o id da congregação e só enxerga/altera dados dela.
- Não depende do Streamlit.
"""
import calendar
import io
from datetime import date

import gestao_db as db

MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro",
         "Outubro", "Novembro", "Dezembro"]
GRUPOS = ("dizimo_envelope", "dizimo_pix", "oferta_envelope", "oferta_pix")
ROTULO_GRUPO = {"dizimo_envelope": "Dizimistas - Envelope", "dizimo_pix": "Dizimistas - PIX",
                "oferta_envelope": "Ofertas - Envelopes", "oferta_pix": "Ofertas - PIX"}
# lançamentos que o relatório de dízimos e ofertas gera no caixa: (categoria, histórico)
ORIGENS = {"dizimos_envelope": ("DIZIMOS ENVELOPE", "ENTRADA DE DIZIMOS - ENVELOPES"),
           "dizimos_pix": ("DIZIMOS PIX", "ENTRADAS VIA PIX - VER RELATORIO"),
           "ofertas": ("OFERTAS", "OFERTAS DO MES")}
CATEGORIAS_PADRAO = ["OFERTAS", "DIZIMOS ENVELOPE", "DIZIMOS PIX", "COTA", "AJUDA COMBUSTIVEL", "PREBENDA",
                     "SALARIOS", "ENERGISA", "AGUA", "INTERNET", "ALUGUEL", "MANUTENCAO", "COMPRA"]
MAX_IMAGEM_BYTES = 15 * 1024 * 1024


# ---------------------------------------------------------------------------
# Valores e datas
# ---------------------------------------------------------------------------
def para_centavos(valor):
    """Converte um valor em reais (float, int ou texto '1.980,50') para centavos inteiros."""
    if isinstance(valor, str):
        texto = valor.strip().replace("R$", "").replace(" ", "")
        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
        valor = float(texto or 0)
    return int(round(float(valor or 0) * 100))


def fmt_valor(centavos, simbolo=False):
    """1980.5 reais (198050) -> '1.980,50'. Com simbolo=True -> 'R$ 1.980,50'."""
    centavos = int(centavos or 0)
    txt = f"{abs(centavos) / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if centavos < 0:
        txt = "-" + txt
    return f"R$ {txt}" if simbolo else txt


def limites_mes(ano, mes):
    """(primeiro dia do mês, primeiro dia do mês seguinte)."""
    ini = date(ano, mes, 1)
    return ini, (date(ano + 1, 1, 1) if mes == 12 else date(ano, mes + 1, 1))


def ultimo_dia(ano, mes):
    return date(ano, mes, calendar.monthrange(ano, mes)[1])


def mes_anterior(ano, mes):
    return (ano - 1, 12) if mes == 1 else (ano, mes - 1)


# ---------------------------------------------------------------------------
# Tabelas
# ---------------------------------------------------------------------------
def criar_tabelas(banco):
    pk = "INTEGER PRIMARY KEY AUTOINCREMENT" if banco.sqlite else "SERIAL PRIMARY KEY"
    blob = "BLOB" if banco.sqlite else "BYTEA"
    with banco.sessao() as s:
        s.executar(f"""CREATE TABLE IF NOT EXISTS fin_caixas (
            id {pk},
            congregacao_id INTEGER NOT NULL REFERENCES congregacoes(id),
            nome TEXT NOT NULL,
            titulo_igreja TEXT,
            saldo_inicial BIGINT NOT NULL DEFAULT 0,
            data_inicial DATE NOT NULL,
            ativo INTEGER NOT NULL DEFAULT 1,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        s.executar(f"""CREATE TABLE IF NOT EXISTS fin_lancamentos (
            id {pk},
            congregacao_id INTEGER NOT NULL REFERENCES congregacoes(id),
            caixa_id INTEGER NOT NULL REFERENCES fin_caixas(id),
            data_lanc DATE NOT NULL,
            doc_numero INTEGER,
            tipo TEXT NOT NULL,
            categoria TEXT NOT NULL,
            historico TEXT,
            valor_centavos BIGINT NOT NULL,
            informativo INTEGER NOT NULL DEFAULT 0,
            origem TEXT,
            criado_por TEXT,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        s.executar("CREATE INDEX IF NOT EXISTS idx_finl_caixa_data ON fin_lancamentos(caixa_id, data_lanc)")
        s.executar(f"""CREATE TABLE IF NOT EXISTS fin_comprovantes (
            id {pk},
            lancamento_id INTEGER NOT NULL REFERENCES fin_lancamentos(id),
            congregacao_id INTEGER NOT NULL,
            nome_arquivo TEXT,
            mime TEXT,
            tamanho INTEGER,
            conteudo {blob} NOT NULL,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        s.executar("CREATE INDEX IF NOT EXISTS idx_finp_lanc ON fin_comprovantes(lancamento_id)")
        s.executar(f"""CREATE TABLE IF NOT EXISTS fin_contribuicoes (
            id {pk},
            congregacao_id INTEGER NOT NULL REFERENCES congregacoes(id),
            mes DATE NOT NULL,
            grupo TEXT NOT NULL,
            nome TEXT,
            valor_centavos BIGINT NOT NULL DEFAULT 0,
            ordem INTEGER NOT NULL DEFAULT 0)""")
        s.executar("CREATE INDEX IF NOT EXISTS idx_finc_mes ON fin_contribuicoes(congregacao_id, mes)")


# ---------------------------------------------------------------------------
# Caixas
# ---------------------------------------------------------------------------
def titulo_padrao(nome_congregacao):
    """'IEC - São Tomé' -> 'Igreja Evangélica Congregacional em São Tomé'."""
    n = (nome_congregacao or "").strip()
    if n.upper().startswith("IEC"):
        resto = n.split("-", 1)[1].strip() if "-" in n else n[3:].strip()
        return f"Igreja Evangélica Congregacional em {resto}" if resto else n
    return n


def listar_caixas(banco, cid, so_ativos=True):
    with banco.sessao() as s:
        linhas = s.consultar(
            "SELECT id, nome, titulo_igreja, saldo_inicial, data_inicial, ativo FROM fin_caixas "
            "WHERE congregacao_id = :c AND (:t = 0 OR ativo = 1) ORDER BY id",
            {"c": cid, "t": 1 if so_ativos else 0})
    for l in linhas:
        l["saldo_inicial"] = int(l["saldo_inicial"] or 0)
    return db._normalizar(linhas, ["data_inicial"])


def garantir_caixa(banco, cid, nome_congregacao, hoje=None):
    """Devolve os caixas da congregação, criando o 'Patrimônio da Igreja' na primeira vez."""
    caixas = listar_caixas(banco, cid)
    if caixas:
        return caixas
    hoje = hoje or date.today()
    criar_caixa(banco, cid, "Patrimônio da Igreja", titulo_padrao(nome_congregacao), 0, date(hoje.year, 1, 1))
    return listar_caixas(banco, cid)


def criar_caixa(banco, cid, nome, titulo_igreja, saldo_inicial, data_inicial):
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("Informe o nome do caixa.")
    with banco.sessao() as s:
        return s.inserir(
            "INSERT INTO fin_caixas (congregacao_id, nome, titulo_igreja, saldo_inicial, data_inicial) "
            "VALUES (:c, :n, :t, :s, :d) RETURNING id",
            {"c": cid, "n": nome, "t": db._texto(titulo_igreja), "s": int(saldo_inicial or 0),
             "d": db._iso(data_inicial)})


def atualizar_caixa(banco, cid, caixa_id, nome, titulo_igreja, saldo_inicial, data_inicial):
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("Informe o nome do caixa.")
    with banco.sessao() as s:
        if not s.consultar("SELECT id FROM fin_caixas WHERE id = :i AND congregacao_id = :c",
                           {"i": caixa_id, "c": cid}):
            raise ValueError("Caixa não encontrado.")
        antes = s.consultar(
            "SELECT COUNT(*) AS n FROM fin_lancamentos WHERE caixa_id = :i AND informativo = 0 AND data_lanc < :d",
            {"i": caixa_id, "d": db._iso(data_inicial)})[0]["n"]
        if antes:
            raise ValueError(f"Há {antes} lançamento(s) anteriores a essa data inicial. "
                             "Escolha uma data igual ou anterior ao primeiro lançamento.")
        s.executar("UPDATE fin_caixas SET nome = :n, titulo_igreja = :t, saldo_inicial = :s, data_inicial = :d "
                   "WHERE id = :i AND congregacao_id = :c",
                   {"n": nome, "t": db._texto(titulo_igreja), "s": int(saldo_inicial or 0),
                    "d": db._iso(data_inicial), "i": caixa_id, "c": cid})


def _caixa(s, cid, caixa_id):
    linhas = s.consultar("SELECT id, nome, titulo_igreja, saldo_inicial, data_inicial FROM fin_caixas "
                         "WHERE id = :i AND congregacao_id = :c", {"i": caixa_id, "c": cid})
    if not linhas:
        raise ValueError("Caixa não encontrado.")
    linhas[0]["saldo_inicial"] = int(linhas[0]["saldo_inicial"] or 0)
    return db._normalizar(linhas, ["data_inicial"])[0]


# ---------------------------------------------------------------------------
# Lançamentos
# ---------------------------------------------------------------------------
_SEL_LANC = """SELECT l.id, l.caixa_id, l.data_lanc, l.doc_numero, l.tipo, l.categoria, l.historico,
                      l.valor_centavos, l.informativo, l.origem,
                      (SELECT COUNT(*) FROM fin_comprovantes f WHERE f.lancamento_id = l.id) AS n_comprovantes
                 FROM fin_lancamentos l"""


def _tratar(linhas):
    for l in linhas:
        l["valor_centavos"] = int(l["valor_centavos"])
        l["informativo"] = bool(l["informativo"])
        l["n_comprovantes"] = int(l["n_comprovantes"] or 0)
    return db._normalizar(linhas, ["data_lanc"])


def listar_lancamentos(banco, cid, caixa_id, ano, mes):
    ini, fim = limites_mes(ano, mes)
    with banco.sessao() as s:
        linhas = s.consultar(
            _SEL_LANC + """ WHERE l.congregacao_id = :c AND l.caixa_id = :x AND l.data_lanc >= :i
                              AND l.data_lanc < :f
                          ORDER BY l.informativo, COALESCE(l.doc_numero, 999999), l.data_lanc, l.id""",
            {"c": cid, "x": caixa_id, "i": db._iso(ini), "f": db._iso(fim)})
    return _tratar(linhas)


def proximo_doc(banco, cid, caixa_id, ano, mes):
    ini, fim = limites_mes(ano, mes)
    with banco.sessao() as s:
        r = s.consultar(
            "SELECT MAX(doc_numero) AS m FROM fin_lancamentos WHERE congregacao_id = :c AND caixa_id = :x "
            "AND data_lanc >= :i AND data_lanc < :f AND informativo = 0",
            {"c": cid, "x": caixa_id, "i": db._iso(ini), "f": db._iso(fim)})
    return int(r[0]["m"] or 0) + 1


def _validar_lancamento(d, caixa):
    if d.get("tipo") not in ("R", "P"):
        raise ValueError("Escolha se é recebimento ou pagamento.")
    if not (d.get("categoria") or "").strip():
        raise ValueError("Informe a descrição da conta (categoria).")
    if int(d.get("valor_centavos") or 0) <= 0:
        raise ValueError("Informe um valor maior que zero.")
    if not isinstance(d.get("data_lanc"), date):
        raise ValueError("Informe a data do lançamento.")
    if not d.get("informativo") and d["data_lanc"] < caixa["data_inicial"]:
        raise ValueError(f"A data é anterior ao início do caixa ({caixa['data_inicial']:%d/%m/%Y}). "
                         "Ajuste a data inicial na configuração do caixa.")


def criar_lancamento(banco, cid, d):
    """d: caixa_id, data_lanc, tipo ('R' recebimento / 'P' pagamento), categoria, historico, valor_centavos,
    informativo (não entra nos totais), doc_numero (opcional), origem (opcional), criado_por."""
    with banco.sessao() as s:
        caixa = _caixa(s, cid, d["caixa_id"])
        _validar_lancamento(d, caixa)
        doc = d.get("doc_numero")
        if doc is None and not d.get("informativo"):
            ini, fim = limites_mes(d["data_lanc"].year, d["data_lanc"].month)
            r = s.consultar("SELECT MAX(doc_numero) AS m FROM fin_lancamentos WHERE congregacao_id = :c "
                            "AND caixa_id = :x AND data_lanc >= :i AND data_lanc < :f AND informativo = 0",
                            {"c": cid, "x": caixa["id"], "i": db._iso(ini), "f": db._iso(fim)})
            doc = int(r[0]["m"] or 0) + 1
        return s.inserir(
            """INSERT INTO fin_lancamentos (congregacao_id, caixa_id, data_lanc, doc_numero, tipo, categoria,
                      historico, valor_centavos, informativo, origem, criado_por)
               VALUES (:c, :x, :d, :n, :t, :cat, :h, :v, :inf, :o, :p) RETURNING id""",
            {"c": cid, "x": caixa["id"], "d": db._iso(d["data_lanc"]), "n": None if d.get("informativo") else doc,
             "t": d["tipo"], "cat": d["categoria"].strip().upper(), "h": db._texto(d.get("historico")),
             "v": int(d["valor_centavos"]), "inf": 1 if d.get("informativo") else 0, "o": d.get("origem"),
             "p": d.get("criado_por")})


def atualizar_lancamento(banco, cid, lancamento_id, d):
    with banco.sessao() as s:
        atual = s.consultar("SELECT id, caixa_id FROM fin_lancamentos WHERE id = :i AND congregacao_id = :c",
                            {"i": lancamento_id, "c": cid})
        if not atual:
            raise ValueError("Lançamento não encontrado.")
        caixa = _caixa(s, cid, atual[0]["caixa_id"])
        _validar_lancamento(d, caixa)
        s.executar(
            """UPDATE fin_lancamentos SET data_lanc = :d, doc_numero = :n, tipo = :t, categoria = :cat,
                      historico = :h, valor_centavos = :v, informativo = :inf
                WHERE id = :i AND congregacao_id = :c""",
            {"d": db._iso(d["data_lanc"]), "n": None if d.get("informativo") else d.get("doc_numero"),
             "t": d["tipo"], "cat": d["categoria"].strip().upper(), "h": db._texto(d.get("historico")),
             "v": int(d["valor_centavos"]), "inf": 1 if d.get("informativo") else 0, "i": lancamento_id, "c": cid})


def excluir_lancamento(banco, cid, lancamento_id):
    with banco.sessao() as s:
        if not s.consultar("SELECT id FROM fin_lancamentos WHERE id = :i AND congregacao_id = :c",
                           {"i": lancamento_id, "c": cid}):
            raise ValueError("Lançamento não encontrado.")
        s.executar("DELETE FROM fin_comprovantes WHERE lancamento_id = :i", {"i": lancamento_id})
        s.executar("DELETE FROM fin_lancamentos WHERE id = :i AND congregacao_id = :c", {"i": lancamento_id, "c": cid})


def categorias_usadas(banco, cid, caixa_id):
    with banco.sessao() as s:
        linhas = s.consultar("SELECT DISTINCT categoria FROM fin_lancamentos WHERE congregacao_id = :c "
                             "AND caixa_id = :x ORDER BY categoria", {"c": cid, "x": caixa_id})
    usadas = [l["categoria"] for l in linhas]
    return usadas + [c for c in CATEGORIAS_PADRAO if c not in usadas]


# ---------------------------------------------------------------------------
# Saldos e resumos
# ---------------------------------------------------------------------------
def _soma(linhas):
    return sum(l["valor_centavos"] for l in linhas)


def saldo_anterior(banco, cid, caixa_id, ano, mes):
    """Saldo inicial do caixa + tudo o que entrou e saiu antes do primeiro dia do mês."""
    ini, _ = limites_mes(ano, mes)
    with banco.sessao() as s:
        caixa = _caixa(s, cid, caixa_id)
        r = s.consultar(
            "SELECT COALESCE(SUM(CASE WHEN tipo = 'R' THEN valor_centavos ELSE -valor_centavos END), 0) AS s "
            "FROM fin_lancamentos WHERE congregacao_id = :c AND caixa_id = :x AND informativo = 0 "
            "AND data_lanc < :i", {"c": cid, "x": caixa_id, "i": db._iso(ini)})
    return caixa["saldo_inicial"] + int(r[0]["s"] or 0)


def resumo_mes(banco, cid, caixa_id, ano, mes):
    """Tudo o que o relatório de caixa do mês precisa."""
    todos = listar_lancamentos(banco, cid, caixa_id, ano, mes)
    normais = [l for l in todos if not l["informativo"]]
    rec = _soma([l for l in normais if l["tipo"] == "R"])
    pag = _soma([l for l in normais if l["tipo"] == "P"])
    ant = saldo_anterior(banco, cid, caixa_id, ano, mes)
    return {"lancamentos": normais, "informativos": [l for l in todos if l["informativo"]],
            "rec": rec, "pag": pag, "saldo_ant": ant, "saldo_atual": ant + rec - pag}


def resumo_ano(banco, cid, caixa_id, ano):
    """Resumo mês a mês e matrizes por categoria (12 meses) de recebimentos e pagamentos."""
    ini, fim = date(ano, 1, 1), date(ano + 1, 1, 1)
    with banco.sessao() as s:
        linhas = s.consultar(
            "SELECT tipo, categoria, data_lanc, valor_centavos FROM fin_lancamentos WHERE congregacao_id = :c "
            "AND caixa_id = :x AND informativo = 0 AND data_lanc >= :i AND data_lanc < :f",
            {"c": cid, "x": caixa_id, "i": db._iso(ini), "f": db._iso(fim)})
    linhas = db._normalizar(linhas, ["data_lanc"])
    rec_cat, pag_cat = {}, {}
    rec_mes, pag_mes = [0] * 12, [0] * 12
    for l in linhas:
        m, v = l["data_lanc"].month - 1, int(l["valor_centavos"])
        alvo, tot = (rec_cat, rec_mes) if l["tipo"] == "R" else (pag_cat, pag_mes)
        alvo.setdefault(l["categoria"], [0] * 12)[m] += v
        tot[m] += v
    saldo = saldo_anterior(banco, cid, caixa_id, ano, 1)
    meses = []
    for i in range(12):
        meses.append({"mes": i + 1, "saldo_ant": saldo, "rec": rec_mes[i], "pag": pag_mes[i],
                      "saldo_atual": saldo + rec_mes[i] - pag_mes[i]})
        saldo += rec_mes[i] - pag_mes[i]
    return {"meses": meses, "rec_por_categoria": dict(sorted(rec_cat.items())),
            "pag_por_categoria": dict(sorted(pag_cat.items()))}


# ---------------------------------------------------------------------------
# Dízimos e ofertas
# ---------------------------------------------------------------------------
def obter_contribuicoes(banco, cid, ano, mes):
    """{grupo: [{'nome', 'valor_centavos'}]} do mês, na ordem em que foram digitados."""
    with banco.sessao() as s:
        linhas = s.consultar(
            "SELECT grupo, nome, valor_centavos FROM fin_contribuicoes WHERE congregacao_id = :c AND mes = :m "
            "ORDER BY ordem, id", {"c": cid, "m": db._iso(date(ano, mes, 1))})
    saida = {g: [] for g in GRUPOS}
    for l in linhas:
        if l["grupo"] in saida:
            saida[l["grupo"]].append({"nome": l["nome"] or "", "valor_centavos": int(l["valor_centavos"])})
    return saida


def salvar_contribuicoes(banco, cid, ano, mes, grupos):
    """Substitui todas as linhas do mês. grupos: {grupo: [{'nome', 'valor_centavos'}]}.
    Linhas sem nome e sem valor são ignoradas."""
    mes_iso = db._iso(date(ano, mes, 1))
    with banco.sessao() as s:
        s.executar("DELETE FROM fin_contribuicoes WHERE congregacao_id = :c AND mes = :m", {"c": cid, "m": mes_iso})
        for grupo in GRUPOS:
            for ordem, linha in enumerate(grupos.get(grupo, [])):
                nome = (linha.get("nome") or "").strip()
                valor = int(linha.get("valor_centavos") or 0)
                if not nome and valor == 0:
                    continue
                if valor < 0:
                    raise ValueError("Os valores não podem ser negativos.")
                s.executar("INSERT INTO fin_contribuicoes (congregacao_id, mes, grupo, nome, valor_centavos, ordem) "
                           "VALUES (:c, :m, :g, :n, :v, :o)",
                           {"c": cid, "m": mes_iso, "g": grupo, "n": nome or None, "v": valor, "o": ordem})


def totais_contribuicoes(contrib):
    t = {g: sum(l["valor_centavos"] for l in contrib.get(g, [])) for g in GRUPOS}
    t["dizimos"] = t["dizimo_envelope"] + t["dizimo_pix"]
    t["ofertas"] = t["oferta_envelope"] + t["oferta_pix"]
    t["geral"] = t["dizimos"] + t["ofertas"]
    return t


def nomes_do_mes(banco, cid, ano, mes, grupo):
    """Nomes de um grupo num mês (para copiar a lista do mês anterior)."""
    return [l["nome"] for l in obter_contribuicoes(banco, cid, ano, mes)[grupo] if l["nome"]]


def contribuicoes_do_ano(banco, cid, ano):
    """Linhas (mes, grupo, nome, valor) do ano inteiro, para o relatório anual."""
    with banco.sessao() as s:
        linhas = s.consultar(
            "SELECT mes, grupo, nome, valor_centavos FROM fin_contribuicoes WHERE congregacao_id = :c "
            "AND mes >= :i AND mes < :f", {"c": cid, "i": db._iso(date(ano, 1, 1)), "f": db._iso(date(ano + 1, 1, 1))})
    linhas = db._normalizar(linhas, ["mes"])
    for l in linhas:
        l["valor_centavos"] = int(l["valor_centavos"])
    return linhas


def sincronizar_receitas(banco, cid, caixa_id, ano, mes, criado_por=""):
    """Lança (ou atualiza) no caixa os totais do relatório de dízimos e ofertas do mês:
    dízimos de envelope, dízimos por PIX e ofertas. Devolve {'criados', 'atualizados', 'removidos'}."""
    tot = totais_contribuicoes(obter_contribuicoes(banco, cid, ano, mes))
    alvo = {"dizimos_envelope": tot["dizimo_envelope"], "dizimos_pix": tot["dizimo_pix"], "ofertas": tot["ofertas"]}
    ini, fim = limites_mes(ano, mes)
    resultado = {"criados": 0, "atualizados": 0, "removidos": 0}
    with banco.sessao() as s:
        caixa = _caixa(s, cid, caixa_id)
        existentes = {l["origem"]: l for l in s.consultar(
            "SELECT id, origem, valor_centavos FROM fin_lancamentos WHERE congregacao_id = :c AND caixa_id = :x "
            "AND data_lanc >= :i AND data_lanc < :f AND origem IS NOT NULL",
            {"c": cid, "x": caixa_id, "i": db._iso(ini), "f": db._iso(fim)})}
    for origem, valor in alvo.items():
        ex = existentes.get(origem)
        if valor > 0 and ex:
            if int(ex["valor_centavos"]) != valor:
                with banco.sessao() as s:
                    s.executar("UPDATE fin_lancamentos SET valor_centavos = :v WHERE id = :i AND congregacao_id = :c",
                               {"v": valor, "i": ex["id"], "c": cid})
                resultado["atualizados"] += 1
        elif valor > 0:
            categoria, historico = ORIGENS[origem]
            criar_lancamento(banco, cid, {"caixa_id": caixa_id, "data_lanc": max(ultimo_dia(ano, mes), caixa["data_inicial"]),
                                          "tipo": "R", "categoria": categoria, "historico": historico,
                                          "valor_centavos": valor, "origem": origem, "criado_por": criado_por})
            resultado["criados"] += 1
        elif ex:
            excluir_lancamento(banco, cid, ex["id"])
            resultado["removidos"] += 1
    return resultado


# ---------------------------------------------------------------------------
# Comprovantes (imagens)
# ---------------------------------------------------------------------------
def preparar_imagem(conteudo, lado_max=1800, qualidade=82):
    """Valida que é uma imagem, corrige a rotação do celular e reduz o tamanho. Devolve JPEG em bytes."""
    from PIL import Image, ImageOps  # Pillow já vem com o Streamlit
    if not conteudo or len(conteudo) > MAX_IMAGEM_BYTES:
        raise ValueError("Imagem vazia ou maior que 15 MB.")
    try:
        img = Image.open(io.BytesIO(conteudo))
        img = ImageOps.exif_transpose(img)
        if img.mode in ("RGBA", "LA", "P"):
            fundo = Image.new("RGB", img.size, (255, 255, 255))
            img = img.convert("RGBA")
            fundo.paste(img, mask=img.split()[3])
            img = fundo
        else:
            img = img.convert("RGB")
    except Exception:
        raise ValueError("O arquivo não é uma imagem válida (use JPG, PNG ou WEBP).")
    img.thumbnail((lado_max, lado_max))
    saida = io.BytesIO()
    img.save(saida, "JPEG", quality=qualidade, optimize=True)
    return saida.getvalue()


def adicionar_comprovante(banco, cid, lancamento_id, nome_arquivo, conteudo):
    jpeg = preparar_imagem(conteudo)
    with banco.sessao() as s:
        if not s.consultar("SELECT id FROM fin_lancamentos WHERE id = :i AND congregacao_id = :c",
                           {"i": lancamento_id, "c": cid}):
            raise ValueError("Lançamento não encontrado.")
        return s.inserir(
            "INSERT INTO fin_comprovantes (lancamento_id, congregacao_id, nome_arquivo, mime, tamanho, conteudo) "
            "VALUES (:l, :c, :n, 'image/jpeg', :t, :b) RETURNING id",
            {"l": lancamento_id, "c": cid, "n": (nome_arquivo or "comprovante")[:120], "t": len(jpeg), "b": jpeg})


def listar_comprovantes(banco, cid, lancamento_id):
    with banco.sessao() as s:
        return s.consultar("SELECT id, nome_arquivo, tamanho FROM fin_comprovantes WHERE lancamento_id = :l "
                           "AND congregacao_id = :c ORDER BY id", {"l": lancamento_id, "c": cid})


def obter_comprovante(banco, cid, comprovante_id):
    with banco.sessao() as s:
        linhas = s.consultar("SELECT id, nome_arquivo, mime, conteudo FROM fin_comprovantes WHERE id = :i "
                             "AND congregacao_id = :c", {"i": comprovante_id, "c": cid})
    if not linhas:
        return None
    linhas[0]["conteudo"] = bytes(linhas[0]["conteudo"])
    return linhas[0]


def excluir_comprovante(banco, cid, comprovante_id):
    with banco.sessao() as s:
        return s.executar("DELETE FROM fin_comprovantes WHERE id = :i AND congregacao_id = :c",
                          {"i": comprovante_id, "c": cid}) > 0


def comprovantes_do_mes(banco, cid, caixa_id, ano, mes):
    """[(lançamento, [bytes das imagens])] do mês, em ordem de Doc. Nº, para anexar ao PDF."""
    ini, fim = limites_mes(ano, mes)
    with banco.sessao() as s:
        linhas = s.consultar(
            """SELECT f.lancamento_id, f.conteudo FROM fin_comprovantes f
                 JOIN fin_lancamentos l ON l.id = f.lancamento_id
                WHERE l.congregacao_id = :c AND l.caixa_id = :x AND l.data_lanc >= :i AND l.data_lanc < :f
                ORDER BY COALESCE(l.doc_numero, 999999), l.id, f.id""",
            {"c": cid, "x": caixa_id, "i": db._iso(ini), "f": db._iso(fim)})
    por_lanc = {}
    for l in linhas:
        por_lanc.setdefault(l["lancamento_id"], []).append(bytes(l["conteudo"]))
    todos = {l["id"]: l for l in listar_lancamentos(banco, cid, caixa_id, ano, mes)}
    return [(todos[i], imgs) for i, imgs in por_lanc.items() if i in todos]
