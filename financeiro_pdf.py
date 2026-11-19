"""PDFs do financeiro: relatório de caixa (igual ao modelo), relatório dos dizimistas (igual ao modelo),
relatório anual e anexo de comprovantes.

As medidas, cores e posições do caixa e dos dizimistas foram lidas dos PDFs de modelo da igreja.
Não depende do Streamlit.
"""
import base64
import io
from datetime import datetime

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

import financeiro_db as fdb

PRETO, BRANCO, VERMELHO = (0, 0, 0), (1, 1, 1), (1, 0, 0)
MARROM = (0.592157, 0.278431, 0.023529)      # barra de títulos do caixa
CINZA = (0.501961, 0.501961, 0.501961)       # barras de totais do caixa
CINZA_CLARO = (0.85098, 0.85098, 0.85098)    # divisórias de linhas do caixa
VERDE = (0.462745, 0.576471, 0.235294)       # barra de assinaturas do caixa
AZUL_CAB = (0.773, 0.851, 0.945)             # cabeçalhos do relatório de dizimistas
VERDE_TOT = (0.769, 0.843, 0.608)
VERDE_CLARO = (0.847, 0.894, 0.737)
TEAL = (0.573, 0.804, 0.863)


def _logo():
    return ImageReader(io.BytesIO(base64.b64decode(_LOGO_B64)))


def _cor(c, rgb, preencher=False):
    (c.setFillColorRGB if preencher else c.setStrokeColorRGB)(*rgb)


def _caber(c, txt, larg, fonte, tam, minimo=5.5):
    txt = str(txt)
    while tam > minimo and c.stringWidth(txt, fonte, tam) > larg:
        tam -= 0.25
    while len(txt) > 1 and c.stringWidth(txt, fonte, tam) > larg:
        txt = txt[:-1]
    return txt, tam


def _texto(c, x, base, txt, fonte="Helvetica", tam=8, cor=PRETO, alin="e", larg=None):
    """Escreve texto na linha de base 'base' (coordenada do PDF). alin: e=esquerda, c=centro, d=direita."""
    if txt is None or txt == "":
        return
    txt = str(txt).encode("cp1252", "replace").decode("cp1252")   # fontes padrão: alfabeto latino ocidental
    if larg:
        txt, tam = _caber(c, txt, larg, fonte, tam)
    c.setFont(fonte, tam)
    _cor(c, cor, True)
    {"e": c.drawString, "c": c.drawCentredString, "d": c.drawRightString}[alin](x, base, txt)
    _cor(c, PRETO, True)


def _retangulo(c, x0, y0, x1, y1, cor):
    _cor(c, cor, True)
    c.rect(x0, y0, x1 - x0, y1 - y0, stroke=0, fill=1)
    _cor(c, PRETO, True)


def _linha(c, x0, y0, x1, y1, larg=0.9, cor=PRETO):
    c.setLineWidth(larg)
    _cor(c, cor)
    c.line(x0, y0, x1, y1)
    _cor(c, PRETO)


def _agora(d):
    return d.get("emitido_em") or datetime.now()


# ===========================================================================
# 1. Relatório de caixa (igual ao modelo "movimento de caixa")
# ===========================================================================
_W, _H = 595.32, 841.92
_LINHAS_POR_PAGINA = 56
_ALT_LINHA = 10.73
_TOPO_CORPO = 90.95
_COLS = [39.25, 87.85, 126.7, 253.1, 428.05, 505.8, 583.55]   # bordas verticais das 6 colunas


def pdf_caixa(d, incluir_data=True, comprovantes=None):
    """d: titulo_igreja, caixa_nome, ano, mes, lancamentos, informativos, rec, pag, saldo_ant, saldo_atual
    (resumo_mes + dados do caixa). comprovantes: [(lançamento, [bytes das imagens])] para anexar no final."""
    normais, info = d["lancamentos"], d.get("informativos", [])
    cap_ultima = _LINHAS_POR_PAGINA - len(info)
    paginas, resto = [], list(normais)
    while len(resto) > cap_ultima:
        paginas.append(resto[:_LINHAS_POR_PAGINA])
        resto = resto[_LINHAS_POR_PAGINA:]
    paginas.append(resto)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Caixa - {d['caixa_nome']} - {fdb.MESES[d['mes'] - 1]}/{d['ano']}")
    c.setAuthor(d["titulo_igreja"])
    total = len(paginas)
    for i, linhas in enumerate(paginas):
        _pagina_caixa(c, d, linhas, info if i == total - 1 else [], i == total - 1, i + 1, total, incluir_data)
        c.showPage()
    if comprovantes:
        _anexo_comprovantes(c, d, comprovantes)
    c.save()
    return buf.getvalue()


def _topo(y):          # coordenada medida do topo da página -> coordenada do PDF
    return _H - y


def _pagina_caixa(c, d, linhas, info, ultima, n, total, incluir_data):
    # moldura dupla
    c.setLineWidth(1.0)
    c.rect(33.5, _topo(821.5), 589.3 - 33.5, 821.5 - 28.8)
    c.rect(35.4, _topo(819.6), 587.4 - 35.4, 819.6 - 29.9)

    # cabeçalho
    c.drawImage(_logo(), 139.1, _topo(63.5), width=33.9, height=30.9, mask="auto")
    centro = (_COLS[0] + _COLS[-1]) / 2
    _texto(c, centro, _topo(41.5), d["titulo_igreja"], "Helvetica", 10, alin="c")
    _texto(c, centro, _topo(54.0), d["caixa_nome"].upper(), "Helvetica-Bold", 10, alin="c")
    ini = f"01/{d['mes']:02d}/{d['ano']}"
    fim = f"{fdb.ultimo_dia(d['ano'], d['mes']):%d/%m/%Y}"
    _texto(c, centro, _topo(65.0), f"movimento de caixa periodo de {ini} A {fim}", "Helvetica", 8, alin="c")
    _texto(c, 40.9, _topo(54.5), "Portal da Congregação", "Helvetica", 7)
    _texto(c, 40.9, _topo(65.0), "Gestão financeira", "Helvetica", 7)
    _texto(c, 577, _topo(65.0), f"{_agora(d):%d/%m/%Y %H:%M}", "Helvetica", 7, alin="d")

    # barra de títulos
    _retangulo(c, 39.2, _topo(87.7), 583.7, _topo(73.1), MARROM)
    for x, txt, tam in ((63.0, "Data", 10), (107.3, "Doc. Nº", 8), (189.9, "Descrição das Contas", 10),
                        (340.6, "Histórico de Lançamentos", 10), (466.9, "Recebimentos", 9.5),
                        (544.7, "Pagamentos", 9.5)):
        _texto(c, x, _topo(84.0 if tam != 8 else 83.0), txt, "Helvetica-Bold", tam, BRANCO, "c")

    # grade
    fim_corpo = _TOPO_CORPO + _ALT_LINHA * _LINHAS_POR_PAGINA        # ~691.8
    _linha(c, _COLS[0], _topo(90.5), _COLS[-1], _topo(90.5))
    for i in range(_LINHAS_POR_PAGINA - 1):
        y = _TOPO_CORPO + _ALT_LINHA * (i + 1)
        _linha(c, _COLS[0] + 0.5, _topo(y), _COLS[-1] - 0.5, _topo(y), 0.9, CINZA_CLARO)
    _linha(c, _COLS[0], _topo(fim_corpo - 0.5), _COLS[-1], _topo(fim_corpo - 0.5))
    fundo_vert = 741.7 if ultima else fim_corpo
    for x in _COLS:
        _linha(c, x, _topo(90.5), x, _topo(fundo_vert if x in (_COLS[0], _COLS[-1]) else fim_corpo))

    # lançamentos
    def base(i):
        return _topo(_TOPO_CORPO + _ALT_LINHA * i + _ALT_LINHA / 2 + 2.7)

    def escrever(i, l, cor):
        b = base(i)
        if l.get("doc_numero") is not None and cor == PRETO:
            _texto(c, (_COLS[1] + _COLS[2]) / 2, b, f"{l['doc_numero']:02d}", "Helvetica", 7.6, alin="c")
        if incluir_data and cor == PRETO:
            _texto(c, (_COLS[0] + _COLS[1]) / 2, b, f"{l['data_lanc']:%d/%m/%Y}", "Helvetica", 7.2, alin="c")
        _texto(c, _COLS[2] + 1.4, b, l["categoria"], "Helvetica", 7.6, cor, larg=_COLS[3] - _COLS[2] - 2.5)
        _texto(c, _COLS[3] + 1.4, b, l.get("historico") or "", "Helvetica", 7.6, cor, larg=_COLS[4] - _COLS[3] - 2.5)
        v = fdb.fmt_valor(l["valor_centavos"])
        _texto(c, (_COLS[5] if l["tipo"] == "R" else _COLS[6]) - 1.2, b, v, "Helvetica", 7.6, cor, "d")

    for i, l in enumerate(linhas):
        escrever(i, l, PRETO)
    for k, l in enumerate(info):                       # informativos: últimas linhas da tabela, em vermelho
        escrever(_LINHAS_POR_PAGINA - len(info) + k, l, VERMELHO)

    # rodapé da página
    _texto(c, 40.8, _topo(830.0), d["caixa_nome"], "Helvetica", 7)
    if total > 1:
        _texto(c, 583, _topo(830.0), f"Página {n} de {total}", "Helvetica", 7, alin="d")
    if not ultima:
        _texto(c, (_COLS[0] + _COLS[-1]) / 2, _topo(703.0), "continua na próxima página", "Helvetica-Oblique",
               8, alin="c")
        return

    # totais
    ant, atual = d["saldo_ant"], d["saldo_atual"]
    rec_col = d["rec"] + max(ant, 0) + max(-atual, 0)
    pag_col = d["pag"] + max(-ant, 0) + max(atual, 0)
    _retangulo(c, 39.2, _topo(703.9), 583.7, _topo(691.3), CINZA)
    _retangulo(c, 39.2, _topo(716.4), 505.9, _topo(703.8), CINZA)
    _retangulo(c, 39.2, _topo(728.9), 583.7, _topo(716.3), CINZA)
    _retangulo(c, 39.2, _topo(741.4), 583.7, _topo(728.8), CINZA)
    ano_ant, mes_ant = fdb.mes_anterior(d["ano"], d["mes"])
    for top, rotulo in ((693.8, "Soma dos Recebimentos e Pagamentos"),
                        (706.3, f"SALDO ANTERIOR {fdb.MESES[mes_ant - 1].upper()} {ano_ant}"),
                        (718.8, "SALDO ATUAL"), (731.3, "SOMA GERAL DO CAIXA")):
        _texto(c, 48.7, _topo(top + 6.3), rotulo, "Helvetica-Bold", 8, BRANCO)

    def valor(top, centavos, col, recuo):
        _texto(c, col - recuo, _topo(top + 6.3), fdb.fmt_valor(centavos), "Helvetica-Bold", 8, BRANCO, "d")

    valor(693.8, d["rec"], _COLS[5], 11.0)
    valor(693.8, d["pag"], _COLS[6], 11.0)
    valor(706.3, abs(ant), _COLS[5] if ant >= 0 else _COLS[6], 7.5)
    valor(718.8, abs(atual), _COLS[6] if atual >= 0 else _COLS[5], 7.5)
    valor(731.3, rec_col, _COLS[5], 11.0)
    valor(731.3, pag_col, _COLS[6], 11.0)
    _linha(c, _COLS[0], _topo(741.25), _COLS[-1], _topo(741.25))

    # assinaturas
    _retangulo(c, 39.2, _topo(754.9), 583.7, _topo(744.1), VERDE)
    _texto(c, 48.6, _topo(751.8), "Assinaturas do Presidente / Tesoureiro / Obreiro", "Helvetica", 8, BRANCO)
    _texto(c, 311.0, _topo(751.8), "Vistos da Comissão de Exame de Contas", "Helvetica", 8, BRANCO)
    _linha(c, _COLS[0], _topo(757.7), _COLS[-1], _topo(757.7))
    _linha(c, _COLS[0], _topo(757.2), _COLS[0], _topo(816.2))
    _linha(c, _COLS[-1], _topo(757.2), _COLS[-1], _topo(816.2))
    _linha(c, 301.7, _topo(758.2), 301.7, _topo(816.2))
    _linha(c, _COLS[0], _topo(815.75), _COLS[-1], _topo(815.75))


def _anexo_comprovantes(c, d, comprovantes):
    """Uma página por imagem, com a identificação do lançamento no topo."""
    for lanc, imagens in comprovantes:
        for k, bruto in enumerate(imagens):
            c.setLineWidth(1.0)
            c.rect(33.5, _topo(821.5), 589.3 - 33.5, 821.5 - 28.8)
            _texto(c, _W / 2, _topo(52), d["titulo_igreja"], "Helvetica-Bold", 11, alin="c")
            _texto(c, _W / 2, _topo(66), f"{d['caixa_nome']} · {fdb.MESES[d['mes'] - 1]}/{d['ano']} · Comprovantes",
                   "Helvetica", 9, alin="c")
            tipo = "Recebimento" if lanc["tipo"] == "R" else "Pagamento"
            legenda = (f"Doc. Nº {lanc['doc_numero']:02d} · {tipo} · {lanc['categoria']}"
                       if lanc.get("doc_numero") is not None else f"{tipo} · {lanc['categoria']}")
            _texto(c, 48, _topo(92), legenda, "Helvetica-Bold", 10, larg=500)
            _texto(c, 48, _topo(106), f"{lanc['data_lanc']:%d/%m/%Y} · {lanc.get('historico') or ''} · "
                                      f"{fdb.fmt_valor(lanc['valor_centavos'], True)}", "Helvetica", 9, larg=500)
            if len(imagens) > 1:
                _texto(c, 547, _topo(92), f"imagem {k + 1} de {len(imagens)}", "Helvetica", 8, alin="d")
            img = ImageReader(io.BytesIO(bruto))
            iw, ih = img.getSize()
            caixa_w, caixa_h = 499.0, 680.0
            esc = min(caixa_w / iw, caixa_h / ih)
            w, h = iw * esc, ih * esc
            c.drawImage(img, (_W - w) / 2, _topo(122) - h, width=w, height=h)
            c.showPage()


# ===========================================================================
# 2. Relatório dos dizimistas (igual ao modelo)
# ===========================================================================
_X0, _X1, _XM = 64.6, 532.1, 400.9
_ALT_ITEM, _ALT_CAB, _ALT_TOT = 14.5, 15.4, 14.6
_LIM_PAG = 772.0


def _blocos_dizimistas(contrib):
    """Linhas do relatório. Cada linha: (tipo, texto, valor, fundo, destaque)."""
    t = fdb.totais_contribuicoes(contrib)
    L = []

    def lista(grupo, minimo):
        itens = contrib.get(grupo, [])
        for it in itens:
            L.append(("item", it["nome"], it["valor_centavos"], None, False))
        for _ in range(max(0, minimo - len(itens))):
            L.append(("vazio", "", None, None, False))

    L.append(("cab", "DIZIMISTAS - ENVELOPE", None, AZUL_CAB, False))
    lista("dizimo_envelope", 15)
    L.append(("total", "TOTAL DIZIMOS ENVELOPE", t["dizimo_envelope"], VERDE_TOT, False))
    L.append(("cab", "DIZIMISTAS - PIX", None, AZUL_CAB, False))
    lista("dizimo_pix", 6)
    L.append(("total", "TOTAL DIZIMOS PIX", t["dizimo_pix"], VERDE_TOT, False))
    L.append(("total", "TOTAL DIZIMOS ENVELOPE E PIX", t["dizimos"], VERDE_CLARO, False))
    L.append(("vazio", "", None, None, False))
    L.append(("cab", "OFERTAS - ENVELOPES", None, AZUL_CAB, False))
    semanas = {it["nome"].strip().upper(): it["valor_centavos"] for it in contrib.get("oferta_envelope", [])}
    for n in range(1, 6):
        v = semanas.get(f"SEMANA {n}")
        L.append(("item", f"SEMANA {n}", v if v else None, None, True))
    outras = [it for it in contrib.get("oferta_envelope", []) if it["nome"].strip().upper() not in
              {f"SEMANA {n}" for n in range(1, 6)}]
    for it in outras:
        L.append(("item", it["nome"], it["valor_centavos"], None, True))
    L.append(("total", "TOTAL OFERTAS - ENVELOPES", t["oferta_envelope"], VERDE_TOT, False))
    L.append(("cab", "OFERTAS - PIX", None, AZUL_CAB, False))
    pix = contrib.get("oferta_pix", []) or [{"nome": "OFERTA MENSAL - PIX", "valor_centavos": 0}]
    for it in pix:
        L.append(("item", it["nome"] or "OFERTA MENSAL - PIX", it["valor_centavos"] or None, None, True))
    L.append(("total", "TOTAL OFERTAS ENVELOPE E PIX", t["ofertas"], VERDE_TOT, False))
    L.append(("vazio", "", None, None, False))
    L.append(("total", "TOTAL GERAL DE ENTRADAS", t["geral"], TEAL, False))
    return L


def pdf_dizimistas(d):
    """d: titulo_igreja, ano, mes, contrib ({grupo: [{'nome','valor_centavos'}]})."""
    linhas = _blocos_dizimistas(d["contrib"])
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Relatório dos Dizimistas - {fdb.MESES[d['mes'] - 1]} {d['ano']}")
    c.setAuthor(d["titulo_igreja"])

    def cabecalho_pagina(n):
        c.drawImage(_logo(), 87.5, _topo(61.7) - 33.5, width=36.7, height=33.5, mask="auto")
        _texto(c, 153.0, _topo(86.0), d["titulo_igreja"].upper(), "Helvetica-BoldOblique", 14)
        sub = f"Relatório dos Dizimistas / {fdb.MESES[d['mes'] - 1]} – {d['ano']}"
        _texto(c, _W / 2, _topo(127.0), sub + (f"  (continuação {n})" if n > 1 else ""),
               "Times-Italic" if n == 1 else "Times-Italic", 20 if n == 1 else 15, alin="c")
        return 146.6

    def fechar_tabela(y_ini, y_fim):
        for x in (64.6, _XM, 532.1):
            _linha(c, x, _topo(y_ini), x, _topo(y_fim), 0.9)
        _linha(c, _X0, _topo(y_fim), _X1, _topo(y_fim), 0.9)

    n, y = 1, cabecalho_pagina(1)
    y_ini, cab_atual = y, None
    _linha(c, _X0, _topo(y), _X1, _topo(y), 0.9)

    def desenhar(linha, y):
        tipo, texto, valor, fundo, destaque = linha
        h = {"cab": _ALT_CAB, "total": _ALT_TOT}.get(tipo, _ALT_ITEM)
        if fundo:
            _retangulo(c, _X0, _topo(y + h), _X1, _topo(y), fundo)
        base = _topo(y + h / 2 + 3.9)
        if tipo == "cab":
            _texto(c, (_X0 + _XM) / 2, base, texto, "Helvetica-Bold", 11.5, alin="c")
            _texto(c, (_XM + _X1) / 2, base, "Valor", "Helvetica-Bold", 11.5, alin="c")
        elif tipo == "total":
            _texto(c, _X0 + 2, base, texto, "Helvetica-Bold", 10.2, VERMELHO, larg=_XM - _X0 - 4)
            _texto(c, _X1 - 1.5, base, fdb.fmt_valor(valor, True), "Helvetica-Bold", 10.2, VERMELHO, "d")
        elif tipo == "item":
            if destaque:
                _texto(c, (_X0 + _XM) / 2, base, texto, "Helvetica-Bold", 10.2, alin="c", larg=_XM - _X0 - 6)
            else:
                _texto(c, _X0 + 2, base, texto, "Helvetica", 10.2, larg=_XM - _X0 - 4)
            if valor:
                _texto(c, _X1 - 1.5, base, fdb.fmt_valor(valor, True), "Helvetica", 10.2, alin="d")
        _linha(c, _X0, _topo(y + h), _X1, _topo(y + h), 0.75)
        return y + h

    for linha in linhas:
        h = {"cab": _ALT_CAB, "total": _ALT_TOT}.get(linha[0], _ALT_ITEM)
        if y + h > _LIM_PAG:                                   # quebra de página
            fechar_tabela(y_ini, y)
            c.showPage()
            n += 1
            y = cabecalho_pagina(n)
            y_ini = y
            _linha(c, _X0, _topo(y), _X1, _topo(y), 0.9)
            if linha[0] != "cab" and cab_atual:
                y = desenhar(("cab", cab_atual + " (cont.)", None, AZUL_CAB, False), y)
        if linha[0] == "cab":
            cab_atual = linha[1]
        y = desenhar(linha, y)
    fechar_tabela(y_ini, y)

    if y + 50 > 825:
        c.showPage()
        y = 100
    base = y + 30
    for x0, x1, rot in ((104, 240, "Tesouraria"), (367, 506, "Obreiro da Igreja")):
        _linha(c, x0, _topo(base), x1, _topo(base), 0.7)
        _texto(c, (x0 + x1) / 2, _topo(base + 12), rot, "Helvetica-Bold", 10.2, alin="c")
    c.showPage()
    c.save()
    return buf.getvalue()


# ===========================================================================
# 3. Relatório anual (horizontal, no mesmo estilo do caixa)
# ===========================================================================
_AW, _AH = landscape(A4)
_AM = 28.0
_MES_ABREV = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def pdf_anual(d):
    """d: titulo_igreja, caixa_nome, ano, resumo (resumo_ano), contrib_ano (contribuicoes_do_ano)."""
    contagem = _render_anual(d, None)
    return _render_anual(d, contagem)


def _render_anual(d, total_paginas):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A4))
    c.setTitle(f"Relatório anual {d['ano']} - {d['caixa_nome']}")
    c.setAuthor(d["titulo_igreja"])
    est = {"pag": 1, "y": 0}
    larg_util = _AW - 2 * _AM

    def topo(y):
        return _AH - y

    def nova_pagina(primeira=False):
        if not primeira:
            _rodape()
            c.showPage()
            est["pag"] += 1
        c.drawImage(_logo(), _AM + 4, topo(58), width=33.0, height=30.0, mask="auto")
        _texto(c, _AW / 2, topo(30), d["titulo_igreja"], "Helvetica", 11, alin="c")
        _texto(c, _AW / 2, topo(44), d["caixa_nome"].upper(), "Helvetica-Bold", 11, alin="c")
        _texto(c, _AW / 2, topo(57), f"relatório anual de caixa · exercício {d['ano']}", "Helvetica", 9, alin="c")
        _texto(c, _AW - _AM - 4, topo(57), f"{_agora(d):%d/%m/%Y %H:%M}", "Helvetica", 7, alin="d")
        est["y"] = 72.0

    def _rodape():
        _texto(c, _AM, topo(_AH - 18), d["caixa_nome"], "Helvetica", 7)
        txt = f"Página {est['pag']}" + (f" de {total_paginas}" if total_paginas else "")
        _texto(c, _AW - _AM, topo(_AH - 18), txt, "Helvetica", 7, alin="d")

    def tabela(titulo, colunas, larguras, linhas, total=None, alin_primeira="e"):
        """colunas: títulos; linhas: listas de textos; total: lista de textos (barra cinza)."""
        altura, alt_cab = 11.5, 14.0
        x0 = _AM
        xs = [x0]
        for w in larguras:
            xs.append(xs[-1] + w)

        def cabeca(suf=""):
            _texto(c, x0, topo(est["y"] + 8), titulo + suf, "Helvetica-Bold", 9.5, MARROM)
            est["y"] += 12
            _retangulo(c, x0, topo(est["y"] + alt_cab), xs[-1], topo(est["y"]), MARROM)
            for i, t in enumerate(colunas):
                if i == 0:
                    _texto(c, xs[0] + 3, topo(est["y"] + 10), t, "Helvetica-Bold", 8, BRANCO)
                else:
                    _texto(c, xs[i + 1] - 3, topo(est["y"] + 10), t, "Helvetica-Bold", 8, BRANCO, "d")
            est["y"] += alt_cab

        precisa = 12 + alt_cab + len(linhas) * altura + (altura + 2 if total else 0)
        cabe_numa_pagina = precisa < _AH - 72 - 40
        if est["y"] + (precisa if cabe_numa_pagina else 12 + alt_cab + 2 * altura) > _AH - 40:
            nova_pagina()          # tabela pequena que não cabe no que sobrou: começa na página seguinte
        cabeca()
        y_ini = est["y"]
        for k, linha in enumerate(linhas):
            if est["y"] + altura > _AH - 40:
                _linha(c, x0, topo(est["y"]), xs[-1], topo(est["y"]), 0.6)
                nova_pagina()
                cabeca(" (continuação)")
            for i, t in enumerate(linha):
                if i == 0:
                    _texto(c, xs[0] + 3, topo(est["y"] + 8.3), t, "Helvetica", 7.6, larg=larguras[0] - 6)
                else:
                    _texto(c, xs[i + 1] - 3, topo(est["y"] + 8.3), t, "Helvetica", 7.6, alin="d")
            est["y"] += altura
            _linha(c, x0, topo(est["y"]), xs[-1], topo(est["y"]), 0.6, CINZA_CLARO)
        if total:
            if est["y"] + altura + 2 > _AH - 40:
                nova_pagina()
                cabeca(" (continuação)")
            _retangulo(c, x0, topo(est["y"] + altura + 1.5), xs[-1], topo(est["y"]), CINZA)
            for i, t in enumerate(total):
                if i == 0:
                    _texto(c, xs[0] + 3, topo(est["y"] + 8.8), t, "Helvetica-Bold", 7.8, BRANCO)
                else:
                    _texto(c, xs[i + 1] - 3, topo(est["y"] + 8.8), t, "Helvetica-Bold", 7.8, BRANCO, "d")
            est["y"] += altura + 1.5
        for x in xs:
            _linha(c, x, topo(y_ini - alt_cab), x, topo(est["y"]), 0.6)
        _linha(c, x0, topo(est["y"]), xs[-1], topo(est["y"]), 0.9)
        est["y"] += 16

    f = fdb.fmt_valor
    resumo = d["resumo"]
    nova_pagina(primeira=True)

    # A. resumo mensal
    meses = resumo["meses"]
    lin = [[fdb.MESES[m["mes"] - 1], f(m["saldo_ant"]), f(m["rec"]), f(m["pag"]), f(m["saldo_atual"])] for m in meses]
    tot = ["TOTAL DO ANO", f(meses[0]["saldo_ant"]), f(sum(m["rec"] for m in meses)), f(sum(m["pag"] for m in meses)),
           f(meses[-1]["saldo_atual"])]
    resto = larg_util - 170
    tabela("RESUMO MENSAL DO CAIXA", ["Mês", "Saldo anterior", "Recebimentos", "Pagamentos", "Saldo atual"],
           [170] + [resto / 4] * 4, lin, tot)

    # B/C. por conta
    larg12 = [150] + [(larg_util - 150) / 13] * 13
    cols12 = ["Conta"] + _MES_ABREV + ["Total"]

    def matriz(titulo, dados):
        lin = [[cat] + [f(v) if v else "" for v in vals] + [f(sum(vals))] for cat, vals in dados.items()]
        somas = [sum(v[i] for v in dados.values()) for i in range(12)]
        tabela(titulo, cols12, larg12, lin or [["(sem lançamentos)"] + [""] * 13],
               ["TOTAL"] + [f(s) if s else "" for s in somas] + [f(sum(somas))])

    matriz("RECEBIMENTOS POR CONTA", resumo["rec_por_categoria"])
    matriz("PAGAMENTOS POR CONTA", resumo["pag_por_categoria"])

    # D. dízimos e ofertas por mês
    contrib = d.get("contrib_ano", [])
    grupos = {g: [0] * 12 for g in fdb.GRUPOS}
    por_nome = {}
    for l in contrib:
        m = l["mes"].month - 1
        grupos[l["grupo"]][m] += l["valor_centavos"]
        if l["grupo"] in ("dizimo_envelope", "dizimo_pix") and (l["nome"] or "").strip():
            chave = " ".join(l["nome"].split()).upper()
            por_nome.setdefault(chave, {"nome": " ".join(l["nome"].split()), "v": [0] * 12})["v"][m] += l["valor_centavos"]
    lin = [[fdb.ROTULO_GRUPO[g].replace("Dizimistas", "Dízimos")] + [f(v) if v else "" for v in grupos[g]] +
           [f(sum(grupos[g]))] for g in fdb.GRUPOS]
    somas = [sum(grupos[g][i] for g in fdb.GRUPOS) for i in range(12)]
    tabela("DÍZIMOS E OFERTAS (RELATÓRIO DOS DIZIMISTAS)", cols12, larg12, lin,
           ["TOTAL DE ENTRADAS"] + [f(s) if s else "" for s in somas] + [f(sum(somas))])

    # E. dizimistas no ano
    if por_nome:
        itens = sorted(por_nome.values(), key=lambda x: x["nome"].lower())
        lin = [[i["nome"]] + [f(v) if v else "" for v in i["v"]] + [f(sum(i["v"]))] for i in itens]
        somas = [sum(i["v"][k] for i in itens) for k in range(12)]
        tabela("DIZIMISTAS NO ANO (ENVELOPE + PIX)", ["Nome"] + _MES_ABREV + ["Total"], larg12, lin,
               ["TOTAL"] + [f(s) if s else "" for s in somas] + [f(sum(somas))])

    # assinaturas
    if est["y"] + 60 > _AH - 30:
        nova_pagina()
    base = est["y"] + 34
    for x0, x1, rot in ((_AM + 90, _AM + 270, "Tesouraria"), (_AW / 2 - 90, _AW / 2 + 90, "Presidente"),
                        (_AW - _AM - 270, _AW - _AM - 90, "Comissão de Exame de Contas")):
        _linha(c, x0, topo(base), x1, topo(base), 0.7)
        _texto(c, (x0 + x1) / 2, topo(base + 11), rot, "Helvetica-Bold", 8.5, alin="c")
    _rodape()
    c.showPage()
    c.save()
    return est["pag"] if total_paginas is None else buf.getvalue()


# Logo da igreja (PNG com transparência, em base64), embutido para o app não depender de arquivo de imagem.
_LOGO_B64 = (
    "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"
    "HxkZac9n/xNbKxl3fgl5PAAAAABJRU5ErkJggg=="
)
