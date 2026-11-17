"""Contas de acesso das congregações (login do portal da congregação).

Ficam numa tabela própria (contas_congregacao), separada das contas da liderança (usuarios):
uma conta de congregação NUNCA entra no sistema da liderança. Cada conta pertence a uma única
congregação. Quem cria as contas é a liderança, que entrega uma senha temporária (troca obrigatória).

Reaproveita do usuarios.py: hash de senha PBKDF2, regras de senha e o bloqueio por tentativas.
Não depende do Streamlit.
"""
import math
from datetime import timedelta

import usuarios as u
from usuarios import BLOQUEIO_MINUTOS, MAX_TENTATIVAS

_SELECT = """SELECT c.id, c.congregacao_id, c.nome, c.login, c.senha_hash, c.ativo, c.falhas,
                    c.bloqueado_ate, c.trocar_senha, c.ultimo_acesso, g.nome AS congregacao, g.regiao,
                    g.ativa AS congregacao_ativa
               FROM contas_congregacao c JOIN congregacoes g ON g.id = c.congregacao_id"""


def criar_tabela(banco):
    pk = "INTEGER PRIMARY KEY AUTOINCREMENT" if banco.sqlite else "SERIAL PRIMARY KEY"
    with banco.sessao() as s:
        s.executar(f"""CREATE TABLE IF NOT EXISTS contas_congregacao (
            id {pk},
            congregacao_id INTEGER NOT NULL REFERENCES congregacoes(id),
            nome TEXT NOT NULL,
            login TEXT NOT NULL UNIQUE,
            senha_hash TEXT NOT NULL,
            ativo INTEGER NOT NULL DEFAULT 1,
            falhas INTEGER NOT NULL DEFAULT 0,
            bloqueado_ate TIMESTAMP,
            trocar_senha INTEGER NOT NULL DEFAULT 1,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ultimo_acesso TIMESTAMP)""")


def _publica(c):
    return {"id": c["id"], "nome": c["nome"], "login": c["login"], "congregacao_id": c["congregacao_id"],
            "congregacao": c["congregacao"], "regiao": c["regiao"], "trocar_senha": bool(c["trocar_senha"])}


def _obter(s, login):
    linhas = s.consultar(_SELECT + " WHERE c.login = :l", {"l": u._norm_login(login)})
    return linhas[0] if linhas else None


# ---------------------------------------------------------------------------
# Criação e login
# ---------------------------------------------------------------------------
def criar_conta(banco, congregacao_id, nome, login):
    """Cria a conta com senha temporária. Devolve (id, senha_temporaria); a senha só aparece desta vez."""
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("Informe o nome do responsável.")
    erro = u.validar_login(login)
    if erro:
        raise ValueError(erro)
    senha = u.senha_temporaria()
    with banco.sessao() as s:
        if not s.consultar("SELECT id FROM congregacoes WHERE id = :i", {"i": congregacao_id}):
            raise ValueError("Congregação não encontrada.")
        if _obter(s, login):
            raise ValueError("Já existe um acesso de congregação com este e-mail.")
        novo_id = s.inserir(
            "INSERT INTO contas_congregacao (congregacao_id, nome, login, senha_hash, trocar_senha) "
            "VALUES (:c, :n, :l, :h, 1) RETURNING id",
            {"c": congregacao_id, "n": nome, "l": u._norm_login(login), "h": u._hash_senha(senha)})
    return novo_id, senha


def autenticar(banco, login, senha, agora=None):
    """Confere e-mail e senha. Devolve dict com ok, usuario, erro, restantes, bloqueado e minutos."""
    agora = agora or u._agora()
    generico = {"ok": False, "bloqueado": False, "restantes": None, "erro": "E-mail ou senha incorretos."}
    with banco.sessao() as s:
        c = _obter(s, login)
        if not c:
            u._hash_senha(senha or "x")  # mesmo tempo de resposta, para não revelar se o e-mail existe
            return generico
        bloqueio = u._dt(c["bloqueado_ate"])
        if bloqueio and bloqueio > agora:
            minutos = max(1, math.ceil((bloqueio - agora).total_seconds() / 60))
            return {"ok": False, "bloqueado": True, "minutos": minutos, "restantes": 0,
                    "erro": f"Acesso bloqueado por {minutos} minuto(s) após {MAX_TENTATIVAS} tentativas erradas."}
        if u.verificar_senha(senha, c["senha_hash"]):
            if not c["ativo"] or not c["congregacao_ativa"]:
                return {"ok": False, "bloqueado": False, "restantes": None,
                        "erro": "Este acesso está desativado. Procure a liderança."}
            s.executar("UPDATE contas_congregacao SET falhas = 0, bloqueado_ate = NULL, ultimo_acesso = :a "
                       "WHERE id = :i", {"a": u._iso(agora), "i": c["id"]})
            return {"ok": True, "usuario": _publica(c)}
        falhas = (0 if bloqueio else c["falhas"]) + 1
        if falhas >= MAX_TENTATIVAS:
            fim = agora + timedelta(minutes=BLOQUEIO_MINUTOS)
            s.executar("UPDATE contas_congregacao SET falhas = 0, bloqueado_ate = :b WHERE id = :i",
                       {"b": u._iso(fim), "i": c["id"]})
            return {"ok": False, "bloqueado": True, "minutos": BLOQUEIO_MINUTOS, "restantes": 0,
                    "erro": f"Acesso bloqueado por {BLOQUEIO_MINUTOS} minutos após {MAX_TENTATIVAS} tentativas erradas."}
        s.executar("UPDATE contas_congregacao SET falhas = :f, bloqueado_ate = NULL WHERE id = :i",
                   {"f": falhas, "i": c["id"]})
        return {"ok": False, "bloqueado": False, "restantes": MAX_TENTATIVAS - falhas,
                "erro": "E-mail ou senha incorretos."}


def conta_ativa(banco, conta_id):
    """Dados atuais da conta, ou None se ela foi desativada (usada a cada tela, para encerrar a sessão)."""
    with banco.sessao() as s:
        linhas = s.consultar(_SELECT + " WHERE c.id = :i", {"i": conta_id})
    if not linhas or not linhas[0]["ativo"] or not linhas[0]["congregacao_ativa"]:
        return None
    return _publica(linhas[0])


# ---------------------------------------------------------------------------
# Senhas
# ---------------------------------------------------------------------------
def definir_nova_senha(banco, conta_id, nova):
    """Troca obrigatória depois de uma senha temporária."""
    erro = u.validar_senha(nova)
    if erro:
        raise ValueError(erro)
    with banco.sessao() as s:
        s.executar("UPDATE contas_congregacao SET senha_hash = :h, trocar_senha = 0, falhas = 0, "
                   "bloqueado_ate = NULL WHERE id = :i", {"h": u._hash_senha(nova), "i": conta_id})


def alterar_senha_propria(banco, conta_id, senha_atual, nova):
    erro = u.validar_senha(nova)
    if erro:
        raise ValueError(erro)
    with banco.sessao() as s:
        linhas = s.consultar("SELECT senha_hash FROM contas_congregacao WHERE id = :i", {"i": conta_id})
        if not linhas or not u.verificar_senha(senha_atual, linhas[0]["senha_hash"]):
            raise ValueError("A senha atual está incorreta.")
        s.executar("UPDATE contas_congregacao SET senha_hash = :h, trocar_senha = 0 WHERE id = :i",
                   {"h": u._hash_senha(nova), "i": conta_id})


# ---------------------------------------------------------------------------
# Administração (feita pela liderança)
# ---------------------------------------------------------------------------
def listar_contas(banco, congregacao_id=None):
    with banco.sessao() as s:
        linhas = s.consultar(
            _SELECT + " WHERE (:cid IS NULL OR c.congregacao_id = :cid) ORDER BY g.nome, c.nome",
            {"cid": congregacao_id})
    for l in linhas:
        l.pop("senha_hash", None)
        l["bloqueado_ate"] = u._dt(l["bloqueado_ate"])
        l["ultimo_acesso"] = u._dt(l["ultimo_acesso"])
    return linhas


def definir_ativo(banco, conta_id, ativo):
    with banco.sessao() as s:
        s.executar("UPDATE contas_congregacao SET ativo = :a WHERE id = :i", {"a": 1 if ativo else 0, "i": conta_id})


def desbloquear(banco, conta_id):
    with banco.sessao() as s:
        s.executar("UPDATE contas_congregacao SET falhas = 0, bloqueado_ate = NULL WHERE id = :i", {"i": conta_id})


def redefinir_temporaria(banco, conta_id):
    """Nova senha temporária (mostrada uma única vez); a troca é obrigatória no próximo acesso."""
    senha = u.senha_temporaria()
    with banco.sessao() as s:
        s.executar("UPDATE contas_congregacao SET senha_hash = :h, trocar_senha = 1, falhas = 0, "
                   "bloqueado_ate = NULL WHERE id = :i", {"h": u._hash_senha(senha), "i": conta_id})
    return senha
