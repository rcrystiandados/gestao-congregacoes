"""Contas individuais da liderança (login por e-mail e senha), guardadas no banco de dados.

Regras de segurança:
- a senha nunca é guardada: só um hash PBKDF2-SHA256 com sal aleatório;
- 3 senhas erradas seguidas bloqueiam a conta por 15 minutos;
- a redefinição por e-mail usa um código de 6 dígitos válido por 15 minutos, com no máximo 5 tentativas;
- o primeiro usuário cadastrado vira administrador; só administradores gerenciam contas.

Não depende do Streamlit.
"""
import hashlib
import hmac
import math
import re
import secrets
from datetime import datetime, timedelta

MAX_TENTATIVAS = 3
BLOQUEIO_MINUTOS = 15
CODIGO_VALIDADE_MINUTOS = 15
CODIGO_MAX_TENTATIVAS = 5
ITERACOES = 600_000
ALFABETO_TEMPORARIO = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------
def _agora():
    return datetime.utcnow().replace(microsecond=0)


def _dt(valor):
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.replace(tzinfo=None)
    try:
        return datetime.fromisoformat(str(valor)).replace(tzinfo=None)
    except ValueError:
        return None


def _iso(momento):
    return momento.isoformat(sep=" ") if momento else None


def _norm_login(login):
    return (login or "").strip().lower()


def validar_login(login):
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", _norm_login(login)):
        return "Informe um e-mail válido."
    return None


def validar_senha(senha):
    senha = senha or ""
    if len(senha) < 8:
        return "A senha precisa ter pelo menos 8 caracteres."
    if not re.search(r"[A-Za-z]", senha) or not re.search(r"\d", senha):
        return "A senha precisa ter letras e números."
    return None


def _hash_senha(senha, sal=None):
    sal = sal or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), bytes.fromhex(sal), ITERACOES)
    return f"pbkdf2_sha256${ITERACOES}${sal}${h.hex()}"


def verificar_senha(senha, armazenado):
    try:
        _, iteracoes, sal, esperado = armazenado.split("$")
        h = hashlib.pbkdf2_hmac("sha256", (senha or "").encode("utf-8"), bytes.fromhex(sal), int(iteracoes))
        return hmac.compare_digest(h.hex(), esperado)
    except Exception:
        return False


def _hash_codigo(login, codigo):
    return hashlib.sha256(f"{_norm_login(login)}:{codigo}".encode("utf-8")).hexdigest()


def _publico(u):
    return {"id": u["id"], "nome": u["nome"], "login": u["login"], "perfil": u["perfil"],
            "trocar_senha": bool(u["trocar_senha"])}


def senha_temporaria():
    while True:
        senha = "".join(secrets.choice(ALFABETO_TEMPORARIO) for _ in range(10))
        if validar_senha(senha) is None:
            return senha


# ---------------------------------------------------------------------------
# Tabela
# ---------------------------------------------------------------------------
def criar_tabela(banco):
    pk = "INTEGER PRIMARY KEY AUTOINCREMENT" if banco.sqlite else "SERIAL PRIMARY KEY"
    with banco.sessao() as s:
        s.executar(f"""CREATE TABLE IF NOT EXISTS usuarios (
            id {pk},
            nome TEXT NOT NULL,
            login TEXT NOT NULL UNIQUE,
            senha_hash TEXT NOT NULL,
            perfil TEXT NOT NULL DEFAULT 'lider',
            ativo INTEGER NOT NULL DEFAULT 1,
            falhas INTEGER NOT NULL DEFAULT 0,
            bloqueado_ate TIMESTAMP,
            trocar_senha INTEGER NOT NULL DEFAULT 0,
            codigo_hash TEXT,
            codigo_expira TIMESTAMP,
            codigo_tentativas INTEGER NOT NULL DEFAULT 0,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ultimo_acesso TIMESTAMP)""")


def _obter(s, login):
    linhas = s.consultar("SELECT * FROM usuarios WHERE login = :l", {"l": _norm_login(login)})
    return linhas[0] if linhas else None


def _admins_ativos(s, excluindo_id=None):
    linhas = s.consultar("SELECT id FROM usuarios WHERE perfil = 'admin' AND ativo = 1")
    return [l for l in linhas if l["id"] != excluindo_id]


# ---------------------------------------------------------------------------
# Cadastro e login
# ---------------------------------------------------------------------------
def criar_usuario(banco, nome, login, senha):
    """Cria a conta. O primeiro usuário vira administrador. Devolve (id, perfil)."""
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("Informe o seu nome.")
    erro = validar_login(login) or validar_senha(senha)
    if erro:
        raise ValueError(erro)
    with banco.sessao() as s:
        if _obter(s, login):
            raise ValueError("Já existe uma conta com este e-mail.")
        total = s.consultar("SELECT COUNT(*) AS n FROM usuarios")[0]["n"]
        perfil = "admin" if total == 0 else "lider"
        novo_id = s.inserir(
            "INSERT INTO usuarios (nome, login, senha_hash, perfil) VALUES (:n, :l, :h, :p) RETURNING id",
            {"n": nome, "l": _norm_login(login), "h": _hash_senha(senha), "p": perfil})
    return novo_id, perfil


def autenticar(banco, login, senha, agora=None):
    """Confere e-mail e senha. Devolve um dicionário com ok, usuario, erro, restantes, bloqueado e minutos."""
    agora = agora or _agora()
    generico = {"ok": False, "bloqueado": False, "restantes": None, "erro": "E-mail ou senha incorretos."}
    with banco.sessao() as s:
        u = _obter(s, login)
        if not u:
            _hash_senha(senha or "x")  # gasta o mesmo tempo, para não revelar se o e-mail existe
            return generico
        bloqueio = _dt(u["bloqueado_ate"])
        if bloqueio and bloqueio > agora:
            minutos = max(1, math.ceil((bloqueio - agora).total_seconds() / 60))
            return {"ok": False, "bloqueado": True, "minutos": minutos, "restantes": 0,
                    "erro": f"Conta bloqueada por {minutos} minuto(s) após {MAX_TENTATIVAS} tentativas erradas."}

        if verificar_senha(senha, u["senha_hash"]):
            if not u["ativo"]:
                return {"ok": False, "bloqueado": False, "restantes": None,
                        "erro": "Esta conta está desativada. Procure um administrador."}
            s.executar("UPDATE usuarios SET falhas = 0, bloqueado_ate = NULL, ultimo_acesso = :a WHERE id = :i",
                       {"a": _iso(agora), "i": u["id"]})
            return {"ok": True, "usuario": _publico(u)}

        falhas = (0 if bloqueio else u["falhas"]) + 1  # bloqueio vencido: contagem recomeça
        if falhas >= MAX_TENTATIVAS:
            fim = agora + timedelta(minutes=BLOQUEIO_MINUTOS)
            s.executar("UPDATE usuarios SET falhas = 0, bloqueado_ate = :b WHERE id = :i",
                       {"b": _iso(fim), "i": u["id"]})
            return {"ok": False, "bloqueado": True, "minutos": BLOQUEIO_MINUTOS, "restantes": 0,
                    "limite": True,
                    "erro": f"Conta bloqueada por {BLOQUEIO_MINUTOS} minutos após {MAX_TENTATIVAS} tentativas erradas."}
        s.executar("UPDATE usuarios SET falhas = :f, bloqueado_ate = NULL WHERE id = :i",
                   {"f": falhas, "i": u["id"]})
        return {"ok": False, "bloqueado": False, "restantes": MAX_TENTATIVAS - falhas,
                "erro": "E-mail ou senha incorretos."}


# ---------------------------------------------------------------------------
# Troca e redefinição de senha
# ---------------------------------------------------------------------------
def _gravar_nova_senha(s, usuario_id, nova):
    s.executar(
        """UPDATE usuarios SET senha_hash = :h, trocar_senha = 0, falhas = 0, bloqueado_ate = NULL,
                  codigo_hash = NULL, codigo_expira = NULL, codigo_tentativas = 0 WHERE id = :i""",
        {"h": _hash_senha(nova), "i": usuario_id})


def definir_nova_senha(banco, usuario_id, nova):
    """Usada na troca obrigatória (depois de uma senha temporária)."""
    erro = validar_senha(nova)
    if erro:
        raise ValueError(erro)
    with banco.sessao() as s:
        _gravar_nova_senha(s, usuario_id, nova)


def alterar_senha_propria(banco, usuario_id, senha_atual, nova):
    erro = validar_senha(nova)
    if erro:
        raise ValueError(erro)
    with banco.sessao() as s:
        linhas = s.consultar("SELECT senha_hash FROM usuarios WHERE id = :i", {"i": usuario_id})
        if not linhas or not verificar_senha(senha_atual, linhas[0]["senha_hash"]):
            raise ValueError("A senha atual está incorreta.")
        _gravar_nova_senha(s, usuario_id, nova)


def gerar_codigo_reset(banco, login, agora=None):
    """Gera o código de 6 dígitos. Devolve (codigo, usuario) ou None se o e-mail não existe ou está desativado."""
    agora = agora or _agora()
    with banco.sessao() as s:
        u = _obter(s, login)
        if not u or not u["ativo"]:
            return None
        codigo = f"{secrets.randbelow(1_000_000):06d}"
        s.executar(
            "UPDATE usuarios SET codigo_hash = :h, codigo_expira = :e, codigo_tentativas = 0 WHERE id = :i",
            {"h": _hash_codigo(login, codigo), "e": _iso(agora + timedelta(minutes=CODIGO_VALIDADE_MINUTOS)),
             "i": u["id"]})
        return codigo, _publico(u)


def redefinir_com_codigo(banco, login, codigo, nova, agora=None):
    """Troca a senha usando o código recebido por e-mail. Devolve (ok, mensagem)."""
    agora = agora or _agora()
    erro = validar_senha(nova)
    if erro:
        return False, erro
    invalido = (False, "Código inválido ou expirado. Peça um novo código.")
    with banco.sessao() as s:
        u = _obter(s, login)
        if not u or not u["codigo_hash"]:
            return invalido
        validade = _dt(u["codigo_expira"])
        if not validade or validade < agora or u["codigo_tentativas"] >= CODIGO_MAX_TENTATIVAS:
            return invalido
        if not hmac.compare_digest(_hash_codigo(login, (codigo or "").strip()), u["codigo_hash"]):
            tentativas = u["codigo_tentativas"] + 1
            s.executar("UPDATE usuarios SET codigo_tentativas = :t WHERE id = :i", {"t": tentativas, "i": u["id"]})
            restantes = CODIGO_MAX_TENTATIVAS - tentativas
            return False, (f"Código incorreto. Restam {restantes} tentativa(s)." if restantes > 0
                           else "Muitas tentativas. Peça um novo código.")
        _gravar_nova_senha(s, u["id"], nova)
    return True, "Senha alterada com sucesso."


# ---------------------------------------------------------------------------
# Administração das contas
# ---------------------------------------------------------------------------
def listar_usuarios(banco):
    with banco.sessao() as s:
        linhas = s.consultar(
            "SELECT id, nome, login, perfil, ativo, falhas, bloqueado_ate, trocar_senha, ultimo_acesso "
            "FROM usuarios ORDER BY nome")
    for l in linhas:
        l["bloqueado_ate"] = _dt(l["bloqueado_ate"])
        l["ultimo_acesso"] = _dt(l["ultimo_acesso"])
    return linhas


def definir_ativo(banco, usuario_id, ativo):
    with banco.sessao() as s:
        if not ativo and not _admins_ativos(s, excluindo_id=usuario_id) \
                and any(a["id"] == usuario_id for a in _admins_ativos(s)):
            raise ValueError("Não é possível desativar o último administrador.")
        s.executar("UPDATE usuarios SET ativo = :a WHERE id = :i", {"a": 1 if ativo else 0, "i": usuario_id})


def definir_perfil(banco, usuario_id, perfil):
    if perfil not in ("admin", "lider"):
        raise ValueError("Perfil inválido.")
    with banco.sessao() as s:
        if perfil != "admin" and not _admins_ativos(s, excluindo_id=usuario_id) \
                and any(a["id"] == usuario_id for a in _admins_ativos(s)):
            raise ValueError("Não é possível remover o último administrador.")
        s.executar("UPDATE usuarios SET perfil = :p WHERE id = :i", {"p": perfil, "i": usuario_id})


def desbloquear(banco, usuario_id):
    with banco.sessao() as s:
        s.executar("UPDATE usuarios SET falhas = 0, bloqueado_ate = NULL WHERE id = :i", {"i": usuario_id})


def redefinir_temporaria(banco, usuario_id):
    """Gera uma senha temporária (mostrada uma única vez). A pessoa será obrigada a trocá-la no próximo acesso."""
    senha = senha_temporaria()
    with banco.sessao() as s:
        s.executar(
            """UPDATE usuarios SET senha_hash = :h, trocar_senha = 1, falhas = 0, bloqueado_ate = NULL,
                      codigo_hash = NULL, codigo_expira = NULL WHERE id = :i""",
            {"h": _hash_senha(senha), "i": usuario_id})
    return senha
