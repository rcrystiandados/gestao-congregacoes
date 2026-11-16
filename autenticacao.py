"""Telas de acesso do site de gestão: entrar, criar conta, redefinir senha, minha conta e usuários.

Segredos usados (Streamlit Cloud > Settings > Secrets):
    database_url    = "postgresql://..."        # obrigatório
    codigo_convite  = "codigo-da-lideranca"     # exigido para criar uma conta (se faltar, usa senha_gestao)
Opcionais, para redefinir a senha por e-mail:
    smtp_usuario    = "seu-email@gmail.com"
    smtp_senha      = "senha-de-app-do-gmail"
    smtp_servidor   = "smtp.gmail.com"          # padrão
    smtp_porta      = 465                       # padrão
"""
import hmac
import smtplib
import ssl
from email.message import EmailMessage

import streamlit as st

import gestao_db as db
import usuarios as us


# ---------------------------------------------------------------------------
# Banco e segredos
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def _banco(url):
    banco = db.Banco(url)
    banco.criar_tabelas()
    us.criar_tabela(banco)
    return banco


def obter_banco():
    """Devolve (banco, erro). erro = None, 'nao_configurado' ou o texto do problema."""
    try:
        url = st.secrets["database_url"]
    except Exception:
        return None, "nao_configurado"
    if not url:
        return None, "nao_configurado"
    try:
        return _banco(url), None
    except ImportError:
        return None, "Falta a biblioteca psycopg2-binary no requirements.txt."
    except Exception as erro:
        return None, f"Não foi possível conectar ao banco de dados: {erro}"


def _segredo(nome, padrao=None):
    try:
        return st.secrets.get(nome, padrao)
    except Exception:
        return padrao


def _codigo_convite():
    return _segredo("codigo_convite") or _segredo("senha_gestao")


def _smtp_configurado():
    return bool(_segredo("smtp_usuario") and _segredo("smtp_senha"))


def _enviar_codigo(destino, nome, codigo):
    usuario, senha = _segredo("smtp_usuario"), _segredo("smtp_senha")
    mensagem = EmailMessage()
    mensagem["Subject"] = "Código para redefinir sua senha - Gestão MEN"
    mensagem["From"] = usuario
    mensagem["To"] = destino
    mensagem.set_content(
        f"Olá, {nome}.\n\nSeu código para redefinir a senha é: {codigo}\n\n"
        f"Ele vale por {us.CODIGO_VALIDADE_MINUTOS} minutos. Se você não pediu a troca, ignore esta mensagem."
    )
    with smtplib.SMTP_SSL(_segredo("smtp_servidor", "smtp.gmail.com"), int(_segredo("smtp_porta", 465)),
                          context=ssl.create_default_context(), timeout=20) as servidor:
        servidor.login(usuario, senha)
        servidor.send_message(mensagem)


# ---------------------------------------------------------------------------
# Sessão
# ---------------------------------------------------------------------------
def _iniciar_sessao(usuario):
    st.session_state["usuario"] = usuario
    st.session_state["logado"] = True
    st.session_state["msg_login"] = True
    st.session_state["pagina"] = "Painel inicial"
    st.session_state["trocar_senha_obrigatoria"] = bool(usuario.get("trocar_senha"))
    st.session_state.pop("mostrar_reset", None)


def sair():
    for chave in ("usuario", "trocar_senha_obrigatoria", "mostrar_reset", "senha_temporaria_exibida"):
        st.session_state.pop(chave, None)
    st.session_state["logado"] = False


def usuario_atual():
    return st.session_state.get("usuario") or {}


# ---------------------------------------------------------------------------
# Redefinir senha (por e-mail)
# ---------------------------------------------------------------------------
def _fluxo_redefinir(banco, prefixo, login_inicial=""):
    if not _smtp_configurado():
        st.info("Para trocar a senha, peça a um administrador da liderança. Ele abre **Usuários** no menu, "
                "escolhe o seu nome e gera uma senha temporária, que você troca no primeiro acesso.")
        return
    etapa = st.session_state.get(f"{prefixo}_etapa", 1)
    login = st.text_input("E-mail da sua conta", value=login_inicial, key=f"{prefixo}_login")
    if etapa == 1:
        if st.button("Enviar código por e-mail", key=f"{prefixo}_enviar"):
            resultado = us.gerar_codigo_reset(banco, login)
            if resultado:
                codigo, usuario = resultado
                try:
                    _enviar_codigo(usuario["login"], usuario["nome"], codigo)
                except Exception as erro:
                    st.error(f"Não foi possível enviar o e-mail agora. Tente de novo em instantes. ({erro})")
                    return
            st.session_state[f"{prefixo}_etapa"] = 2
            st.rerun()
        return

    st.caption("Se o e-mail estiver cadastrado, enviamos um código de 6 dígitos válido por "
               f"{us.CODIGO_VALIDADE_MINUTOS} minutos. Confira também a caixa de spam.")
    codigo = st.text_input("Código recebido", key=f"{prefixo}_codigo", max_chars=6)
    nova = st.text_input("Nova senha", type="password", key=f"{prefixo}_nova")
    repete = st.text_input("Repita a nova senha", type="password", key=f"{prefixo}_repete")
    b1, b2 = st.columns(2)
    if b1.button("Trocar senha", key=f"{prefixo}_trocar", use_container_width=True):
        if nova != repete:
            st.error("As senhas não são iguais.")
        else:
            ok, mensagem = us.redefinir_com_codigo(banco, login, codigo, nova)
            if ok:
                st.session_state[f"{prefixo}_etapa"] = 1
                st.session_state.pop("mostrar_reset", None)
                st.success("Senha alterada. Agora entre com a nova senha.")
            else:
                st.error(mensagem)
    if b2.button("Pedir novo código", key=f"{prefixo}_novo", use_container_width=True):
        st.session_state[f"{prefixo}_etapa"] = 1
        st.rerun()


# ---------------------------------------------------------------------------
# Telas de acesso
# ---------------------------------------------------------------------------
def _form_entrar(banco):
    with st.form("form_entrar"):
        login = st.text_input("E-mail", key="ent_login")
        senha = st.text_input("Senha", type="password", key="ent_senha")
        entrar = st.form_submit_button("Entrar", use_container_width=True)
    if entrar:
        r = us.autenticar(banco, login, senha)
        if r["ok"]:
            _iniciar_sessao(r["usuario"])
            st.rerun()
        elif r.get("bloqueado"):
            st.error(r["erro"])
            st.session_state["mostrar_reset"] = login
        else:
            restantes = r.get("restantes")
            st.error(r["erro"] + (f" Tentativas restantes: {restantes}." if restantes is not None else ""))
    if st.session_state.get("mostrar_reset") is not None:
        st.warning("Você errou a senha 3 vezes. Se esqueceu, troque a senha agora:")
        with st.expander("Trocar minha senha", expanded=True):
            _fluxo_redefinir(banco, "apos3", st.session_state.get("mostrar_reset") or "")


def _form_criar(banco):
    esperado = _codigo_convite()
    if not esperado:
        st.warning("A criação de contas está desativada: falta o segredo `codigo_convite` no site.")
        return
    st.caption("Peça o código de convite à liderança. Use o seu e-mail como login.")
    with st.form("form_criar"):
        nome = st.text_input("Nome completo", key="cri_nome")
        login = st.text_input("E-mail", key="cri_login")
        senha = st.text_input("Senha (mínimo 8 caracteres, com letras e números)", type="password", key="cri_senha")
        repete = st.text_input("Repita a senha", type="password", key="cri_repete")
        convite = st.text_input("Código de convite", type="password", key="cri_convite")
        criar = st.form_submit_button("Criar conta", use_container_width=True)
    if not criar:
        return
    if st.session_state.get("convite_falhas", 0) >= 5:
        st.error("Muitas tentativas com código incorreto. Atualize a página e tente mais tarde.")
    elif not hmac.compare_digest(str(convite), str(esperado)):
        st.session_state["convite_falhas"] = st.session_state.get("convite_falhas", 0) + 1
        st.error("Código de convite incorreto.")
    elif senha != repete:
        st.error("As senhas não são iguais.")
    else:
        try:
            _, perfil = us.criar_usuario(banco, nome, login, senha)
        except ValueError as erro:
            st.error(str(erro))
        else:
            st.success("Conta criada! Agora entre na aba **Entrar**."
                       + (" Você é o primeiro usuário e será o administrador." if perfil == "admin" else ""))


def _acesso_provisorio():
    """Só enquanto o banco não está configurado: entra com a senha antiga (senha_gestao)."""
    st.warning("O banco de dados ainda não está configurado, então as contas individuais não estão ativas. "
               "Entre com a senha provisória e configure o `database_url` nos Secrets.")
    with st.form("form_provisorio"):
        senha = st.text_input("Senha provisória", type="password")
        entrar = st.form_submit_button("Entrar", use_container_width=True)
    if entrar:
        esperado = _segredo("senha_gestao")
        if esperado and hmac.compare_digest(senha, str(esperado)):
            _iniciar_sessao({"id": None, "nome": "Acesso provisório", "login": "", "perfil": "admin",
                             "trocar_senha": False})
            st.rerun()
        else:
            st.error("Senha incorreta.")


def tela_acesso():
    banco, erro = obter_banco()
    _, centro, _ = st.columns([1, 1.8, 1])
    with centro:
        st.markdown(
            '<div class="login-topo"><div class="login-icone">🔒</div>'
            '<h2>Gestão MEN</h2><p>Acesso restrito à liderança. Cada pessoa usa a sua própria conta.</p></div>',
            unsafe_allow_html=True,
        )
        if erro == "nao_configurado":
            _acesso_provisorio()
            return
        if erro:
            st.error(erro)
            return
        aba_entrar, aba_criar, aba_esqueci = st.tabs(["Entrar", "Criar conta", "Esqueci minha senha"])
        with aba_entrar:
            _form_entrar(banco)
        with aba_criar:
            _form_criar(banco)
        with aba_esqueci:
            _fluxo_redefinir(banco, "esq")


def tela_troca_obrigatoria():
    """Mostrada depois do login com senha temporária."""
    banco, erro = obter_banco()
    if erro:
        st.error(erro if erro != "nao_configurado" else "Banco de dados não configurado.")
        return
    _, centro, _ = st.columns([1, 1.8, 1])
    with centro:
        st.markdown(
            '<div class="login-topo"><div class="login-icone">🔑</div>'
            '<h2>Defina uma nova senha</h2><p>Você entrou com uma senha temporária. '
            'Crie agora a sua senha pessoal.</p></div>',
            unsafe_allow_html=True,
        )
        with st.form("form_troca_obrigatoria"):
            nova = st.text_input("Nova senha (mínimo 8 caracteres, com letras e números)", type="password")
            repete = st.text_input("Repita a nova senha", type="password")
            salvar = st.form_submit_button("Salvar nova senha", use_container_width=True)
        if salvar:
            if nova != repete:
                st.error("As senhas não são iguais.")
            else:
                try:
                    us.definir_nova_senha(banco, usuario_atual()["id"], nova)
                except ValueError as erro_senha:
                    st.error(str(erro_senha))
                else:
                    st.session_state["trocar_senha_obrigatoria"] = False
                    st.rerun()
        if st.button("Sair", key="sair_troca"):
            sair()
            st.rerun()


# ---------------------------------------------------------------------------
# Páginas internas
# ---------------------------------------------------------------------------
def pagina_minha_conta():
    u = usuario_atual()
    st.markdown(f"**{u.get('nome', '')}**  \n{u.get('login', '')}  \nPerfil: "
                f"{'administrador' if u.get('perfil') == 'admin' else 'liderança'}")
    banco, erro = obter_banco()
    if erro or not u.get("id"):
        st.info("Contas individuais não estão ativas neste acesso.")
        return
    st.markdown("#### Alterar minha senha")
    versao = st.session_state.get("conta_versao", 0)
    atual = st.text_input("Senha atual", type="password", key=f"conta_atual_{versao}")
    nova = st.text_input("Nova senha (mínimo 8 caracteres, com letras e números)", type="password",
                         key=f"conta_nova_{versao}")
    repete = st.text_input("Repita a nova senha", type="password", key=f"conta_repete_{versao}")
    if st.button("Alterar senha", key="conta_salvar"):
        if nova != repete:
            st.error("As senhas não são iguais.")
        else:
            try:
                us.alterar_senha_propria(banco, u["id"], atual, nova)
            except ValueError as erro_senha:
                st.error(str(erro_senha))
            else:
                st.session_state["conta_versao"] = versao + 1
                st.success("Senha alterada com sucesso.")


def _situacao(usuario, agora):
    if not usuario["ativo"]:
        return "Desativada"
    if usuario["bloqueado_ate"] and usuario["bloqueado_ate"] > agora:
        return "Bloqueada"
    return "Ativa"


def pagina_usuarios():
    u = usuario_atual()
    if u.get("perfil") != "admin":
        st.warning("Só administradores acessam esta página.")
        return
    banco, erro = obter_banco()
    if erro or not u.get("id"):
        st.info("Contas individuais não estão ativas neste acesso.")
        return

    msg = st.session_state.pop("usr_msg", None)
    if msg:
        st.success(msg)
    temporaria = st.session_state.pop("senha_temporaria_exibida", None)
    if temporaria:
        st.warning(f"Senha temporária de **{temporaria[0]}**: `{temporaria[1]}`  \n"
                   "Mostrada só agora. Envie à pessoa por um canal seguro. Ela terá de trocá-la ao entrar.")

    lista = us.listar_usuarios(banco)
    agora = us._agora()
    import pandas as pd
    st.dataframe(pd.DataFrame([{
        "Nome": x["nome"], "E-mail": x["login"], "Perfil": "Administrador" if x["perfil"] == "admin" else "Liderança",
        "Situação": _situacao(x, agora),
        "Último acesso": x["ultimo_acesso"].strftime("%d/%m/%Y %H:%M") if x["ultimo_acesso"] else "",
    } for x in lista]), use_container_width=True, hide_index=True)

    st.markdown("#### Gerenciar conta")
    por_id = {x["id"]: x for x in lista}
    escolhido = st.selectbox("Pessoa", list(por_id.keys()), key="usr_sel",
                             format_func=lambda i: f"{por_id[i]['nome']} · {por_id[i]['login']}")
    alvo = por_id[escolhido]
    c1, c2, c3, c4 = st.columns(4)

    def acao(rotulo, chave, funcao, mensagem, **kwargs):
        if rotulo is None:
            return
        if kwargs.get("coluna").button(rotulo, key=f"usr_{chave}_{escolhido}", use_container_width=True):
            try:
                funcao()
            except ValueError as erro_acao:
                st.error(str(erro_acao))
            else:
                st.session_state["usr_msg"] = mensagem
                st.rerun()

    acao("Desativar" if alvo["ativo"] else "Reativar", "ativo",
         lambda: us.definir_ativo(banco, escolhido, not alvo["ativo"]),
         f"Conta de {alvo['nome']} {'desativada' if alvo['ativo'] else 'reativada'}.", coluna=c1)
    acao("Tornar liderança" if alvo["perfil"] == "admin" else "Tornar administrador", "perfil",
         lambda: us.definir_perfil(banco, escolhido, "lider" if alvo["perfil"] == "admin" else "admin"),
         f"Perfil de {alvo['nome']} atualizado.", coluna=c2)
    acao("Desbloquear", "desb", lambda: us.desbloquear(banco, escolhido),
         f"Conta de {alvo['nome']} desbloqueada.", coluna=c3)
    if c4.button("Redefinir senha", key=f"usr_senha_{escolhido}", use_container_width=True):
        senha = us.redefinir_temporaria(banco, escolhido)
        st.session_state["senha_temporaria_exibida"] = (alvo["nome"], senha)
        st.rerun()
