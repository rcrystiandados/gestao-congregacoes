"""Ficha de membro da IECCG (Batismo e Transferência): dados no banco e PDF igual ao modelo em Word.

- A ficha guarda só o que o cadastro de membros ainda não tem (pai, mãe, estado civil, profissão...).
  Nome, nascimento, telefone, e-mail, data de batismo continuam na tabela membros.
- O PDF sai com duas cópias por folha A4, como nos modelos (uma para o membro e outra para a igreja).
- Não depende do Streamlit.
"""
import base64
import io

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

import gestao_db as db

TIPOS = ("Batismo", "Transferência")
ESTADOS_CIVIS = ("Solteiro", "Casado civilmente", "Viúvo(a)", "Divorciado(a)")
LOCAIS = ("Congregação", "Igreja Sede")

_COLUNAS = ["tipo", "local_tipo", "local_nome", "data_conversao", "estado_civil", "nome_conjuge", "nome_pai",
            "nome_mae", "nacionalidade", "cidade_natal", "estado_natal", "residencia", "profissao",
            "batizado_por", "igreja_origem", "pastor_origem", "exercia_funcao", "funcao_anterior",
            "inicio_membro"]
_DATAS = ("data_conversao", "inicio_membro")


# ---------------------------------------------------------------------------
# Banco de dados
# ---------------------------------------------------------------------------
def criar_tabela(banco):
    pk = "INTEGER PRIMARY KEY AUTOINCREMENT" if banco.sqlite else "SERIAL PRIMARY KEY"
    with banco.sessao() as s:
        s.executar(f"""CREATE TABLE IF NOT EXISTS fichas_membro (
            id {pk},
            membro_id INTEGER NOT NULL UNIQUE REFERENCES membros(id) ON DELETE CASCADE,
            tipo TEXT NOT NULL,
            local_tipo TEXT, local_nome TEXT,
            data_conversao DATE, estado_civil TEXT, nome_conjuge TEXT,
            nome_pai TEXT, nome_mae TEXT, nacionalidade TEXT, cidade_natal TEXT, estado_natal TEXT,
            residencia TEXT, profissao TEXT, batizado_por TEXT,
            igreja_origem TEXT, pastor_origem TEXT, exercia_funcao TEXT, funcao_anterior TEXT,
            inicio_membro DATE,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")


def salvar_ficha(banco, membro_id, congregacao_id, dados):
    """Grava (ou substitui) a ficha de um membro DA congregação informada."""
    if dados.get("tipo") not in TIPOS:
        raise ValueError("Escolha se a entrada é por batismo ou por transferência.")
    with banco.sessao() as s:
        if not s.consultar("SELECT id FROM membros WHERE id = :m AND congregacao_id = :c",
                           {"m": membro_id, "c": congregacao_id}):
            raise ValueError("Membro não encontrado nesta congregação.")
        s.executar("DELETE FROM fichas_membro WHERE membro_id = :m", {"m": membro_id})
        params = {c: (db._iso(dados.get(c)) if c in _DATAS else db._texto(dados.get(c))) for c in _COLUNAS}
        params["m"] = membro_id
        s.executar(f"INSERT INTO fichas_membro (membro_id, {', '.join(_COLUNAS)}) "
                   f"VALUES (:m, {', '.join(':' + c for c in _COLUNAS)})", params)


def obter_ficha(banco, membro_id, congregacao_id):
    """Dados completos para o PDF (cadastro + ficha), só se o membro for da congregação. None se não for."""
    campos_f = ", ".join(f"f.{c}" for c in _COLUNAS)
    with banco.sessao() as s:
        linhas = s.consultar(
            f"""SELECT m.id AS membro_id, m.nome, m.data_nascimento, m.telefone, m.email, m.data_batismo,
                       g.nome AS congregacao, {campos_f}
                  FROM membros m
                  JOIN congregacoes g ON g.id = m.congregacao_id
                  LEFT JOIN fichas_membro f ON f.membro_id = m.id
                 WHERE m.id = :m AND m.congregacao_id = :c""", {"m": membro_id, "c": congregacao_id})
    if not linhas:
        return None
    d = db._normalizar(linhas, ["data_nascimento", "data_batismo", *_DATAS])[0]
    d["local_tipo"] = d["local_tipo"] or "Congregação"
    d["local_nome"] = d["local_nome"] or d["congregacao"]
    return d


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
_LARG_CAIXA = 539
_X_CAIXA = 28
# topo de cada cópia (em pontos, de baixo para cima) e altura da moldura, por tipo
_GEOMETRIA = {"Batismo": ((820, 415), 394), "Transferência": ((827, 429), 388)}
# linha de base de cada linha da ficha (em pontos, a partir do topo da moldura)
_LINHAS = {
    "Batismo": dict(nome=119, nasc=139, ec=162, ec1=176, ec2=192, conj=207, ec3=224, ec4=239, pais=269,
                    nac=300, res=328, email=349, bat=375),
    "Transferência": dict(nome=96, nasc=121, ec=138, ec1=152, ec2=167, conj=183, ec3=199, ec4=214, pais=234,
                          nac=252, res=276, email=295, vindo=318, exercia=338, bat=360, inicio=379),
}


def _fmt(d):
    return d.strftime("%d/%m/%Y") if hasattr(d, "strftime") else (d or "")


def _caber(c, txt, larg, fonte, tam, minimo=6.0):
    while tam > minimo and c.stringWidth(txt, fonte, tam) > larg:
        tam -= 0.25
    while len(txt) > 1 and c.stringWidth(txt, fonte, tam) > larg:
        txt = txt[:-1]
    return txt, tam


def _linha_texto(c, X, Y, x, y, valor, w, tam):
    c.setLineWidth(0.5)
    c.line(X(x), Y(y) - 1.8, X(x + w), Y(y) - 1.8)
    if valor:
        # fontes padrão do PDF só têm o alfabeto latino ocidental: o resto vira "?"
        valor = str(valor).encode("cp1252", "replace").decode("cp1252")
        txt, t = _caber(c, valor, w - 2, "Helvetica", tam)
        c.setFont("Helvetica", t)
        c.drawString(X(x) + 1, Y(y), txt)


def _campo_data(c, X, Y, x, y, d, padrao, tam):
    larg = c.stringWidth(padrao, "Helvetica", tam)
    if d:
        _linha_texto(c, X, Y, x, y, _fmt(d), larg, tam)
    else:
        c.setFont("Helvetica", tam)
        c.drawString(X(x), Y(y), padrao)
    return larg


def _caixa(c, X, Y, x, y, marcado, tam):
    c.setFont("Helvetica", tam)
    c.drawString(X(x), Y(y), "(")
    c.drawString(X(x + 13), Y(y), ")")
    if marcado:
        c.setFont("Helvetica-Bold", tam)
        c.drawCentredString(X(x + 8.5), Y(y), "X")
    return 16


def _sequencia(c, X, Y, y, itens, x0=6, x_fim=524, gap=7):
    """Desenha, da esquerda para a direita, rótulos em negrito seguidos de linha, data ou caixa de marcar."""
    x = x0
    for it in itens:
        tam = it.get("tam", 9)
        if it.get("r"):
            c.setFont("Helvetica-Bold", tam)
            c.drawString(X(x), Y(y), it["r"])
            x += c.stringWidth(it["r"], "Helvetica-Bold", tam) + 3
        tipo = it.get("tipo", "txt")
        if tipo == "txt":
            w = it.get("w") or max(30, x_fim - x)
            _linha_texto(c, X, Y, x, y, it.get("v"), w, it.get("vt", tam))
            x += w + gap
        elif tipo == "data":
            x += _campo_data(c, X, Y, x, y, it.get("v"), it["padrao"], tam) + gap
        elif tipo == "caixa":
            x += _caixa(c, X, Y, x, y, it.get("m"), tam) + gap
        elif tipo == "nota":
            c.setFont("Helvetica", tam)
            c.drawString(X(x), Y(y), it["texto"])
            x += c.stringWidth(it["texto"], "Helvetica", tam) + gap


def _logo():
    return ImageReader(io.BytesIO(base64.b64decode("".join(_LOGO_B64))))


def _local(c, X, Y, y, d):
    """'Igreja Sede (  ) Congregação (  ) – Qual: ____' centralizado."""
    sede = d.get("local_tipo") == "Igreja Sede"
    cong = d.get("local_tipo") == "Congregação"
    partes = [("Igreja Sede", sede), ("Congregação", cong)]
    tam, w_linha = 9, 125
    total = (c.stringWidth("Igreja Sede ", "Helvetica-Bold", tam) + 16 + c.stringWidth("  Congregação ", "Helvetica-Bold", tam)
             + 16 + c.stringWidth(" – Qual: ", "Helvetica-Bold", tam) + w_linha)
    x = 270 - total / 2
    c.setFont("Helvetica-Bold", tam)
    c.drawString(X(x), Y(y), "Igreja Sede ")
    x += c.stringWidth("Igreja Sede ", "Helvetica-Bold", tam)
    x += _caixa(c, X, Y, x, y, partes[0][1], tam)
    c.setFont("Helvetica-Bold", tam)
    c.drawString(X(x), Y(y), "  Congregação ")
    x += c.stringWidth("  Congregação ", "Helvetica-Bold", tam)
    x += _caixa(c, X, Y, x, y, partes[1][1], tam)
    c.setFont("Helvetica-Bold", tam)
    c.drawString(X(x), Y(y), " – Qual: ")
    x += c.stringWidth(" – Qual: ", "Helvetica-Bold", tam)
    _linha_texto(c, X, Y, x, y, d.get("local_nome"), w_linha, tam)


def _desenhar(c, d, tipo, topo, altura):
    ox = _X_CAIXA
    X = lambda x: ox + x
    Y = lambda y: topo - y
    L = _LINHAS[tipo]
    c.setLineWidth(0.8)
    c.rect(ox, topo - altura, _LARG_CAIXA, altura)

    # ---- cabeçalho ----
    logo = _logo()
    if tipo == "Batismo":
        c.drawImage(logo, X(54), Y(3 + 72), width=70, height=72)
        c.setFont("Helvetica-Bold", 9.5)
        c.drawCentredString(X(270), Y(23), "IGREJA EVANGÉLICA CONGREGACIONAL")
        c.drawCentredString(X(270), Y(38), "DE CAMPINA GRANDE – CENTRO")
        c.setFont("Helvetica", 12)
        c.drawString(X(407), Y(56), "BATISMO")
        y_ficha, y_local = 66, 91
    else:
        c.drawImage(logo, X(452), Y(6 + 63), width=62, height=63)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(X(270), Y(23), "IGREJA EVANGÉLICA CONGREGACIONAL DE CAMPINA GRANDE – CENTRO")
        c.setFont("Helvetica", 12)
        c.drawString(X(19), Y(43), "TRANSFERÊNCIA")
        y_ficha, y_local = 47, 72
    c.setFont("Helvetica-Bold", 10.5)
    c.drawCentredString(X(269), Y(y_ficha), "Ficha de MEMBRO")
    w = c.stringWidth("Ficha de MEMBRO", "Helvetica-Bold", 10.5)
    c.setLineWidth(0.6)
    c.line(X(269 - w / 2), Y(y_ficha) - 1.8, X(269 + w / 2), Y(y_ficha) - 1.8)
    _local(c, X, Y, y_local, d)

    # ---- dados pessoais ----
    _sequencia(c, X, Y, L["nome"], [{"r": "Nome Completo:", "v": d.get("nome")}])
    _sequencia(c, X, Y, L["nasc"], [{"r": "Data de Nascimento:", "tipo": "data", "v": d.get("data_nascimento"),
                                     "padrao": "_____/____/____"}])
    _sequencia(c, X, Y, L["nasc"], [{"r": "Data de sua Conversão:", "tipo": "data", "v": d.get("data_conversao"),
                                     "padrao": "____/____/______"}], x0=327)

    ec = d.get("estado_civil")
    c.setFont("Helvetica-Bold", 9)
    c.drawString(X(6), Y(L["ec"]), "Estado Civil:")
    for chave, num, texto, marcado in (("ec1", "1-", "Solteiro", ec == "Solteiro"),
                                       ("ec2", "2-", "Casado Civilmente", ec == "Casado civilmente"),
                                       ("ec3", "3-", "Viúvo (a)", ec == "Viúvo(a)"),
                                       ("ec4", "4-", "Divorciado (a)", ec == "Divorciado(a)")):
        y = L[chave]
        c.setFont("Helvetica", 9)
        c.drawString(X(18), Y(y), num)
        c.drawString(X(36), Y(y), texto)
        x = 36 + c.stringWidth(texto + " ", "Helvetica", 9)
        x += _caixa(c, X, Y, x, y, marcado, 9)
        if chave == "ec2":
            c.setFont("Helvetica-Bold", 9)
            c.drawString(X(x + 6), Y(y), "Obs.:")
            c.setFont("Helvetica", 9)
            c.drawString(X(x + 6 + 25), Y(y),
                         "Caso esteja casado civilmente, trazer uma cópia da certidão de casamento.")
    _sequencia(c, X, Y, L["conj"], [{"r": "Nome do Conjugue:",
                                     "v": d.get("nome_conjuge") if ec == "Casado civilmente" else None}],
               x0=36, x_fim=490)

    _sequencia(c, X, Y, L["pais"], [{"r": "Nome do Pai:", "v": d.get("nome_pai"), "w": 190}])
    _sequencia(c, X, Y, L["pais"], [{"r": "Nome da Mãe:", "v": d.get("nome_mae")}], x0=278)
    _sequencia(c, X, Y, L["nac"], [{"r": "Nacionalidade:", "v": d.get("nacionalidade"), "w": 100},
                                   {"r": "Cidade onde Nasceu:", "v": d.get("cidade_natal"), "w": 135},
                                   {"r": "Estado:", "v": d.get("estado_natal")}])
    _sequencia(c, X, Y, L["res"], [{"r": "Residência:", "v": d.get("residencia")}])
    _sequencia(c, X, Y, L["email"], [{"r": "Email:", "v": d.get("email"), "w": 165},
                                     {"r": "Telefone:", "v": d.get("telefone"), "w": 105},
                                     {"r": "Profissão:", "v": d.get("profissao")}])

    # ---- só na transferência ----
    if tipo == "Transferência":
        _sequencia(c, X, Y, L["vindo"], [{"r": "ESTÁ VINDO DE QUAL IGREJA:", "v": d.get("igreja_origem"),
                                          "w": 165, "tam": 7.8, "vt": 8.5},
                                         {"r": "NOME DO PASTOR:", "v": d.get("pastor_origem"),
                                          "tam": 7.8, "vt": 8.5}])
        ex = d.get("exercia_funcao")
        _sequencia(c, X, Y, L["exercia"], [{"r": "EXERCIA ALGUMA FUNÇÃO NESTA IGREJA:", "tipo": "nota", "texto": "", "tam": 7.8},
                                           {"r": "SIM", "tipo": "caixa", "m": ex == "Sim", "tam": 8.5},
                                           {"r": "NÃO", "tipo": "caixa", "m": ex == "Não", "tam": 8.5},
                                           {"r": "- QUAL:", "v": d.get("funcao_anterior") if ex == "Sim" else None,
                                            "tam": 7.8, "vt": 8.5}])
    _sequencia(c, X, Y, L["bat"], [{"r": "BATISMO EM:", "tipo": "data", "v": d.get("data_batismo"),
                                    "padrao": "_______/_______/__________"},
                                   {"r": "BATIZADO PELO REV:", "v": d.get("batizado_por")}])
    if tipo == "Transferência":
        _sequencia(c, X, Y, L["inicio"], [{"r": "Início como Membro da IECCG:", "tipo": "data",
                                           "v": d.get("inicio_membro"), "padrao": "____/_____/_______", "tam": 8},
                                          {"tipo": "nota", "texto": "(esta informação será preenchida pela secretaria da igreja)",
                                           "tam": 8}], x0=36)


def gerar_pdf(dados, tipo):
    """PDF (bytes) da ficha, com duas cópias por folha. 'dados' vazio gera a ficha em branco."""
    if tipo not in TIPOS:
        raise ValueError("Tipo de ficha inválido.")
    dados = dados or {}
    topos, altura = _GEOMETRIA[tipo]
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Ficha de membro - {tipo}" + (f" - {dados['nome']}" if dados.get("nome") else ""))
    c.setAuthor("IEC Campina Grande - Centro")
    for topo in topos:
        _desenhar(c, dados, tipo, topo, altura)
    c.showPage()
    c.save()
    return buf.getvalue()


# Logo da igreja (JPEG em base64), embutido para o app não depender de arquivo de imagem.
_LOGO_B64 = (
    "/9j/4AAQSkZJRgABAQEA3ADcAAD/2wBDAAIBAQEBAQIBAQECAgICAgQDAgICAgUEBAMEBgUGBgYFBgYGBwkIBgcJBwYGCAsI"
    "CQoKCgoKBggLDAsKDAkKCgr/2wBDAQICAgICAgUDAwUKBwYHCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoK"
    "CgoKCgoKCgoKCgoKCgr/wAARCADXANIDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAA"
    "AgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6"
    "Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXG"
    "x8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREA"
    "AgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5"
    "OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPE"
    "xcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD95oLUFBx271J9jB7CrNvGNuNp6VJ5XoDQ"
    "BR+wp/dH50fYU/uj86veV7GjyvY0AUfsKf3R+dH2FP7o/Or3lexo8r2NAFH7Cn90fnR9hT+6Pzq95XsaPK9jQBR+wp/dH50f"
    "YU/uj86veV7GjyvY0AUfsKf3R+dH2FP7o/Or3lexo8r2NAFH7Cn90fnR9hT+6Pzq95XsaQooOCeT0oApfYU/uj86PsKf3R+d"
    "XvK9jR5XsaAKP2FP7o/Oj7Cn90fnV7yvY0eV7GgCj9hT+6Pzo+wp/dH51e8r2NHlexoAo/YU/uj86PsKf3R+dXvK9jR5XsaA"
    "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"
)
