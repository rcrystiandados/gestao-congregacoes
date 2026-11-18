"""Banco do portal da congregação: pedidos de remarcação, dados de contato e financeiro da congregação.

Não depende do Streamlit. Usa a mesma conexão (gestao_db.Banco) do sistema da liderança.

Correções desta versão:
- o valor em dinheiro passa a ser NUMERIC(12,2) no PostgreSQL (REAL perdia centavos em valores grandes);
- o membro de um dízimo precisa pertencer à congregação do lançamento;
- categoria e forma de pagamento são conferidas no servidor, e não só na tela;
- novos recursos do caixa: saldo inicial, nome do caixa, lançamentos informativos e saldo anterior.
"""
from datetime import date, datetime, timedelta

import contas_congregacao
import gestao_db as db

STATUS = ("pendente", "aprovado", "recusado", "cancelado")
_COLUNAS_CONTATO = ("contato_nome", "contato_telefone", "contato_email")

CATEGORIAS_ENTRADA = (
    "Dízimo",
    "Oferta de Culto",
    "Oferta de Departamento",
    "Oferta Especial / Campanha",
    "Outras Entradas",
)

CATEGORIAS_SAIDA = (
    "Água / Energia / Internet",
    "Manutenção e Reforma",
    "Material de Limpeza / Consumo",
    "Eventos e Departamentos",
    "Assistência Social",
    "Repasse à Sede",
    "Outras Despesas",
)

FORMAS_PAGAMENTO = ("PIX", "Dinheiro", "Transferência / Cartão")
TIPOS_LANCAMENTO = ("Entrada", "Saída", "Informativo")
NOME_CAIXA_PADRAO = "PATRIMÔNIO DA IGREJA"


def _num(valor):
    """Número com 2 casas (o PostgreSQL devolve Decimal em colunas NUMERIC)."""
    return round(float(valor or 0), 2)


def criar_tabelas(banco):
    """Cria o que o portal precisa (pode ser chamada quantas vezes quiser)."""
    contas_congregacao.criar_tabela(banco)
    pk = "INTEGER PRIMARY KEY AUTOINCREMENT" if banco.sqlite else "SERIAL PRIMARY KEY"
    tipo_valor = "REAL" if banco.sqlite else "NUMERIC(12,2)"
    with banco.sessao() as s:
        s.executar(f"""CREATE TABLE IF NOT EXISTS pedidos_remarcacao (
            id {pk},
            congregacao_id INTEGER NOT NULL REFERENCES congregacoes(id),
            conta_id INTEGER,
            evento_linha INTEGER NOT NULL,
            evento_nome TEXT NOT NULL,
            evento_regiao TEXT,
            ini_atual DATE NOT NULL,
            fim_atual DATE NOT NULL,
            ini_novo DATE NOT NULL,
            fim_novo DATE NOT NULL,
            motivo TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pendente',
            resposta TEXT,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            decidido_em TIMESTAMP,
            decidido_por TEXT)""")
        s.executar("CREATE INDEX IF NOT EXISTS idx_ped_cong ON pedidos_remarcacao(congregacao_id)")

        s.executar(f"""CREATE TABLE IF NOT EXISTS lancamentos_financeiros (
            id {pk},
            congregacao_id INTEGER NOT NULL REFERENCES congregacoes(id),
            conta_id INTEGER,
            tipo TEXT NOT NULL,
            categoria TEXT NOT NULL,
            membro_id INTEGER,
            membro_nome TEXT,
            descricao TEXT,
            valor {tipo_valor} NOT NULL,
            forma_pagamento TEXT,
            data_lancamento DATE NOT NULL,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        s.executar("CREATE INDEX IF NOT EXISTS idx_fin_cong_data "
                   "ON lancamentos_financeiros(congregacao_id, data_lancamento)")

        s.executar(f"""CREATE TABLE IF NOT EXISTS financeiro_config (
            congregacao_id INTEGER PRIMARY KEY REFERENCES congregacoes(id),
            nome_caixa TEXT,
            saldo_inicial {tipo_valor},
            saldo_inicial_data DATE)""")

        if not banco.sqlite:
            # Bancos criados com a versão anterior tinham o valor em REAL (perde centavos).
            tipo_atual = s.consultar(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = 'lancamentos_financeiros' AND column_name = 'valor'")
            if tipo_atual and tipo_atual[0]["data_type"] in ("real", "double precision"):
                s.executar("ALTER TABLE lancamentos_financeiros ALTER COLUMN valor TYPE NUMERIC(12,2) "
                           "USING ROUND(CAST(valor AS NUMERIC), 2)")

        # contato da congregação (a tabela congregacoes original não tem estes campos)
        if banco.sqlite:
            existentes = {l["name"] for l in s.consultar("PRAGMA table_info(congregacoes)")}
            for col in _COLUNAS_CONTATO:
                if col not in existentes:
                    s.executar(f"ALTER TABLE congregacoes ADD COLUMN {col} TEXT")
        else:
            for col in _COLUNAS_CONTATO:
                s.executar(f"ALTER TABLE congregacoes ADD COLUMN IF NOT EXISTS {col} TEXT")


# ---------------------------------------------------------------------------
# Dados da congregação
# ---------------------------------------------------------------------------
def dados_congregacao(banco, congregacao_id):
    with banco.sessao() as s:
        linhas = s.consultar(
            "SELECT id, nome, regiao, endereco, data_fundacao, contato_nome, contato_telefone, contato_email "
            "FROM congregacoes WHERE id = :i", {"i": congregacao_id})
    return db._normalizar(linhas, ["data_fundacao"])[0] if linhas else None


def atualizar_dados_congregacao(banco, congregacao_id, endereco, data_fundacao,
                                contato_nome, contato_telefone, contato_email):
    """Nome e região só a liderança altera (a região define a regra de choque do calendário)."""
    with banco.sessao() as s:
        s.executar(
            """UPDATE congregacoes SET endereco = :e, data_fundacao = :d, contato_nome = :cn,
                      contato_telefone = :ct, contato_email = :ce WHERE id = :i""",
            {"e": db._texto(endereco), "d": db._iso(data_fundacao), "cn": db._texto(contato_nome),
             "ct": db._texto(contato_telefone), "ce": db._texto(contato_email), "i": congregacao_id})


# ---------------------------------------------------------------------------
# Pedidos de remarcação
# ---------------------------------------------------------------------------
def criar_pedido(banco, d):
    """d: congregacao_id, conta_id, evento_linha, evento_nome, evento_regiao, ini_atual, fim_atual,
    ini_novo, fim_novo, motivo. Só um pedido pendente por evento."""
    motivo = (d.get("motivo") or "").strip()
    if len(motivo) < 5:
        raise ValueError("Explique o motivo do pedido.")
    if d["ini_novo"] > d["fim_novo"]:
        raise ValueError("A data final não pode ser antes da data de início.")
    with banco.sessao() as s:
        if s.consultar("SELECT id FROM pedidos_remarcacao WHERE congregacao_id = :c AND evento_linha = :l "
                       "AND status = 'pendente'", {"c": d["congregacao_id"], "l": d["evento_linha"]}):
            raise ValueError("Já existe um pedido pendente para este evento.")
        return s.inserir(
            """INSERT INTO pedidos_remarcacao (congregacao_id, conta_id, evento_linha, evento_nome, evento_regiao,
                      ini_atual, fim_atual, ini_novo, fim_novo, motivo)
               VALUES (:c, :conta, :l, :n, :r, :ia, :fa, :in_, :fn, :m) RETURNING id""",
            {"c": d["congregacao_id"], "conta": d.get("conta_id"), "l": d["evento_linha"],
             "n": d["evento_nome"], "r": d.get("evento_regiao"), "ia": db._iso(d["ini_atual"]),
             "fa": db._iso(d["fim_atual"]), "in_": db._iso(d["ini_novo"]), "fn": db._iso(d["fim_novo"]),
             "m": motivo})


def listar_pedidos(banco, congregacao_id=None, status=None, limite=None):
    with banco.sessao() as s:
        linhas = s.consultar(
            """SELECT p.*, g.nome AS congregacao, g.regiao AS regiao_congregacao
                 FROM pedidos_remarcacao p JOIN congregacoes g ON g.id = p.congregacao_id
                WHERE (:cid IS NULL OR p.congregacao_id = :cid) AND (:st IS NULL OR p.status = :st)
                ORDER BY p.id DESC""", {"cid": congregacao_id, "st": status})
    if limite:
        linhas = linhas[:limite]
    return db._normalizar(linhas, ["ini_atual", "fim_atual", "ini_novo", "fim_novo"])


def cancelar_pedido(banco, pedido_id, congregacao_id):
    """A congregação só cancela pedido seu e ainda pendente. Devolve True se cancelou."""
    with banco.sessao() as s:
        n = s.executar(
            "UPDATE pedidos_remarcacao SET status = 'cancelado', decidido_em = CURRENT_TIMESTAMP "
            "WHERE id = :i AND congregacao_id = :c AND status = 'pendente'",
            {"i": pedido_id, "c": congregacao_id})
    return n > 0


def decidir_pedido(banco, pedido_id, status, resposta, decidido_por):
    """A liderança aprova ou recusa. Só vale para pedido pendente. Devolve True se registrou."""
    if status not in ("aprovado", "recusado"):
        raise ValueError("Status inválido.")
    with banco.sessao() as s:
        n = s.executar(
            "UPDATE pedidos_remarcacao SET status = :st, resposta = :r, decidido_por = :p, "
            "decidido_em = CURRENT_TIMESTAMP WHERE id = :i AND status = 'pendente'",
            {"st": status, "r": db._texto(resposta), "p": decidido_por, "i": pedido_id})
    return n > 0


def contar_pendentes(banco):
    with banco.sessao() as s:
        return s.consultar("SELECT COUNT(*) AS n FROM pedidos_remarcacao WHERE status = 'pendente'")[0]["n"]


# ---------------------------------------------------------------------------
# Financeiro da congregação
# ---------------------------------------------------------------------------
def criar_lancamento(banco, d):
    """Registra uma entrada, saída ou lançamento informativo (que não entra nas somas do caixa)."""
    tipo = d.get("tipo")
    if tipo not in TIPOS_LANCAMENTO:
        raise ValueError("Tipo de lançamento inválido.")
    categoria = (d.get("categoria") or "").strip()
    if not categoria:
        raise ValueError("Selecione a categoria.")
    if tipo == "Entrada" and categoria not in CATEGORIAS_ENTRADA:
        raise ValueError("Categoria de entrada inválida.")
    if tipo == "Saída" and categoria not in CATEGORIAS_SAIDA:
        raise ValueError("Categoria de saída inválida.")
    if tipo == "Informativo" and len(categoria) > 60:
        raise ValueError("O nome da conta pode ter no máximo 60 caracteres.")
    try:
        valor = round(float(d.get("valor") or 0), 2)
    except (TypeError, ValueError):
        raise ValueError("Informe um valor válido.")
    if not valor > 0:  # também recusa NaN
        raise ValueError("O valor deve ser maior que zero.")
    if valor >= 10_000_000:
        raise ValueError("O valor informado é grande demais. Confira os centavos.")
    if not d.get("data_lancamento"):
        raise ValueError("Informe a data do lançamento.")

    forma = (d.get("forma_pagamento") or "").strip() or ("PIX" if tipo != "Informativo" else "")
    if forma and forma not in FORMAS_PAGAMENTO:
        raise ValueError("Forma de pagamento inválida.")

    descricao = (d.get("descricao") or "").strip()
    if tipo in ("Saída", "Informativo") and len(descricao) < 3:
        raise ValueError("Descreva o motivo ou referente do lançamento.")

    with banco.sessao() as s:
        membro_id, membro_nome = d.get("membro_id"), db._texto(d.get("membro_nome"))
        if membro_id is not None:
            achado = s.consultar("SELECT nome FROM membros WHERE id = :m AND congregacao_id = :c",
                                 {"m": membro_id, "c": d["congregacao_id"]})
            if not achado:
                raise ValueError("O membro escolhido não pertence a esta congregação.")
            membro_nome = achado[0]["nome"]
        return s.inserir(
            """INSERT INTO lancamentos_financeiros (
                congregacao_id, conta_id, tipo, categoria, membro_id, membro_nome,
                descricao, valor, forma_pagamento, data_lancamento
            ) VALUES (:c, :conta, :t, :cat, :mid, :mnome, :desc, :val, :fp, :dt) RETURNING id""",
            {"c": d["congregacao_id"], "conta": d.get("conta_id"), "t": tipo, "cat": categoria,
             "mid": membro_id, "mnome": membro_nome, "desc": db._texto(descricao), "val": valor,
             "fp": db._texto(forma), "dt": db._iso(d["data_lancamento"])},
        )


def _intervalo(ano, mes):
    """(inicio, fim_exclusivo) em ISO para um ano ou um mês; (None, None) se não houver ano."""
    if ano is None:
        return None, None
    ano = int(ano)
    if mes is None:
        return date(ano, 1, 1).isoformat(), date(ano + 1, 1, 1).isoformat()
    mes = int(mes)
    inicio = date(ano, mes, 1)
    fim = date(ano + (mes == 12), 1 if mes == 12 else mes + 1, 1)
    return inicio.isoformat(), fim.isoformat()


def listar_lancamentos(banco, congregacao_id, ano=None, mes=None, tipo=None):
    """Lançamentos da congregação, do mais recente para o mais antigo (filtros opcionais)."""
    ini, fim = _intervalo(ano, mes)
    with banco.sessao() as s:
        linhas = s.consultar(
            """SELECT id, congregacao_id, conta_id, tipo, categoria, membro_id, membro_nome,
                      descricao, valor, forma_pagamento, data_lancamento, criado_em
                 FROM lancamentos_financeiros
                WHERE congregacao_id = :cid
                  AND (:t IS NULL OR tipo = :t)
                  AND (:ini IS NULL OR data_lancamento >= :ini)
                  AND (:fim IS NULL OR data_lancamento < :fim)
                ORDER BY data_lancamento DESC, id DESC""",
            {"cid": congregacao_id, "t": tipo, "ini": ini, "fim": fim})
    regs = db._normalizar(linhas, ["data_lancamento"])
    for r in regs:
        r["valor"] = _num(r["valor"])
    if ano is None and mes is not None:  # mês sem ano: filtra aqui
        regs = [r for r in regs if r["data_lancamento"] and r["data_lancamento"].month == int(mes)]
    return regs


def anos_com_lancamentos(banco, congregacao_id):
    with banco.sessao() as s:
        linhas = s.consultar("SELECT DISTINCT data_lancamento FROM lancamentos_financeiros "
                             "WHERE congregacao_id = :c", {"c": congregacao_id})
    datas = db._normalizar(linhas, ["data_lancamento"])
    return sorted({l["data_lancamento"].year for l in datas if l["data_lancamento"]})


def excluir_lancamento(banco, lancamento_id, congregacao_id):
    """Permite à congregação excluir um lançamento próprio."""
    with banco.sessao() as s:
        n = s.executar(
            "DELETE FROM lancamentos_financeiros WHERE id = :i AND congregacao_id = :c",
            {"i": lancamento_id, "c": congregacao_id},
        )
    return n > 0


# ---------------------------------------------------------------------------
# Configuração e saldos do caixa
# ---------------------------------------------------------------------------
def obter_config_financeiro(banco, congregacao_id):
    with banco.sessao() as s:
        linhas = s.consultar("SELECT nome_caixa, saldo_inicial, saldo_inicial_data FROM financeiro_config "
                             "WHERE congregacao_id = :c", {"c": congregacao_id})
    if not linhas:
        return {"nome_caixa": NOME_CAIXA_PADRAO, "saldo_inicial": 0.0, "saldo_inicial_data": None}
    l = db._normalizar(linhas, ["saldo_inicial_data"])[0]
    return {"nome_caixa": l["nome_caixa"] or NOME_CAIXA_PADRAO, "saldo_inicial": _num(l["saldo_inicial"]),
            "saldo_inicial_data": l["saldo_inicial_data"]}


def salvar_config_financeiro(banco, congregacao_id, nome_caixa, saldo_inicial, saldo_inicial_data):
    nome = (nome_caixa or "").strip() or NOME_CAIXA_PADRAO
    if len(nome) > 60:
        raise ValueError("O nome do caixa pode ter no máximo 60 caracteres.")
    try:
        saldo = round(float(saldo_inicial or 0), 2)
    except (TypeError, ValueError):
        raise ValueError("Informe um saldo inicial válido.")
    with banco.sessao() as s:
        s.executar("DELETE FROM financeiro_config WHERE congregacao_id = :c", {"c": congregacao_id})
        s.executar("INSERT INTO financeiro_config (congregacao_id, nome_caixa, saldo_inicial, saldo_inicial_data) "
                   "VALUES (:c, :n, :s, :d)",
                   {"c": congregacao_id, "n": nome, "s": saldo, "d": db._iso(saldo_inicial_data)})


def saldo_antes_de(banco, congregacao_id, data_limite):
    """Saldo do caixa no início de `data_limite`: saldo inicial + entradas - saídas anteriores a essa data.
    Se o saldo inicial tem data, só contam os lançamentos a partir dela."""
    cfg = obter_config_financeiro(banco, congregacao_id)
    with banco.sessao() as s:
        linhas = s.consultar(
            """SELECT tipo, SUM(valor) AS total FROM lancamentos_financeiros
                WHERE congregacao_id = :c AND data_lancamento < :fim
                  AND (:ini IS NULL OR data_lancamento >= :ini) AND tipo IN ('Entrada', 'Saída')
                GROUP BY tipo""",
            {"c": congregacao_id, "fim": db._iso(data_limite), "ini": db._iso(cfg["saldo_inicial_data"])})
    totais = {l["tipo"]: _num(l["total"]) for l in linhas}
    return round(cfg["saldo_inicial"] + totais.get("Entrada", 0.0) - totais.get("Saída", 0.0), 2)
