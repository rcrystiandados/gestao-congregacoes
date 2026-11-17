"""Banco do portal da congregação: pedidos de remarcação e dados de contato da congregação.

Não depende do Streamlit. Usa a mesma conexão (gestao_db.Banco) do sistema da liderança.
"""
import contas_congregacao
import gestao_db as db

STATUS = ("pendente", "aprovado", "recusado", "cancelado")
_COLUNAS_CONTATO = ("contato_nome", "contato_telefone", "contato_email")


def criar_tabelas(banco):
    """Cria o que o portal precisa (pode ser chamada quantas vezes quiser)."""
    contas_congregacao.criar_tabela(banco)
    pk = "INTEGER PRIMARY KEY AUTOINCREMENT" if banco.sqlite else "SERIAL PRIMARY KEY"
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
