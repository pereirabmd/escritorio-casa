import pytest

from pulse import accounts, db


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "teste-a.db"); db.migrate(c)
    yield c
    c.close()


def criar(conn, **kw):
    return accounts.criar_utilizador(conn, kw.pop("email", "Eu@Exemplo.pt"), kw.pop("password", "1234qweR"), **kw)


def test_email_normalizado_e_unico_sem_maiusculas(conn):
    criar(conn)
    assert conn.execute("SELECT email FROM pulse_users").fetchone()[0] == "eu@exemplo.pt"
    with pytest.raises(accounts.ContaErro) as e:
        criar(conn, email="EU@exemplo.PT")
    assert e.value.status == 409


@pytest.mark.parametrize("mau", ["", "sem-arroba", "a@b", "a b@c.pt", "@x.pt"])
def test_email_invalido(conn, mau):
    with pytest.raises(accounts.ContaErro) as e:
        criar(conn, email=mau)
    assert e.value.codigo == "email_invalido"


def test_login_certo_e_erros_genericos_iguais(conn):
    criar(conn)
    assert accounts.autenticar(conn, "eu@exemplo.pt", "1234qweR")["email"] == "eu@exemplo.pt"
    for email, pw in (("eu@exemplo.pt", "errada"), ("naoexiste@x.pt", "1234qweR"), ("lixo", "x")):
        with pytest.raises(accounts.ContaErro) as e:
            accounts.autenticar(conn, email, pw)
        assert (e.value.status, e.value.codigo) == (401, "credenciais_invalidas")


def test_conta_desativada_nao_entra(conn):
    criar(conn)
    conn.execute("UPDATE pulse_users SET ativo=0")
    with pytest.raises(accounts.ContaErro) as e:
        accounts.autenticar(conn, "eu@exemplo.pt", "1234qweR")
    assert e.value.codigo == "credenciais_invalidas"


def test_bloqueio_apos_falhas_e_desbloqueio_com_o_tempo(conn):
    criar(conn)
    for _ in range(accounts.MAX_FALHAS):
        with pytest.raises(accounts.ContaErro):
            accounts.autenticar(conn, "eu@exemplo.pt", "errada", agora=1000)
    with pytest.raises(accounts.ContaErro) as e:   # mesmo com a password certa, está bloqueada
        accounts.autenticar(conn, "eu@exemplo.pt", "1234qweR", agora=1001)
    assert (e.value.status, e.value.codigo) == (429, "conta_bloqueada")
    assert accounts.autenticar(conn, "eu@exemplo.pt", "1234qweR", agora=1000 + accounts.BLOQUEIO_S + 1)


def test_sessao_valida_expira_e_revoga(conn):
    uid = criar(conn)
    t = accounts.criar_sessao(conn, uid, "Firefox", "1.2.3.4", "web", 30, agora=1000)
    assert accounts.resolver_sessao(conn, t, 30, agora=2000)
    assert accounts.resolver_sessao(conn, "outro-token", 30, agora=2000) is None
    assert accounts.resolver_sessao(conn, t, 30, agora=1000 + 30 * 86400 + 1) is None
    sid = conn.execute("SELECT id FROM pulse_sessions").fetchone()[0]
    assert accounts.revogar_sessao(conn, sid, uid) and accounts.resolver_sessao(conn, t, 30, agora=2000) is None
    assert not accounts.revogar_sessao(conn, sid, uid)


def test_sessao_e_deslizante_no_maximo_uma_vez_por_hora(conn):
    uid = criar(conn)
    t = accounts.criar_sessao(conn, uid, "", "", "web", 30, agora=1000)
    accounts.resolver_sessao(conn, t, 30, agora=1500)
    assert conn.execute("SELECT ultimo_uso FROM pulse_sessions").fetchone()[0] == 1000
    accounts.resolver_sessao(conn, t, 30, agora=1000 + 3600)
    assert conn.execute("SELECT expira FROM pulse_sessions").fetchone()[0] == 1000 + 3600 + 30 * 86400


def test_sessao_de_conta_desativada_deixa_de_valer(conn):
    uid = criar(conn)
    t = accounts.criar_sessao(conn, uid, "", "", "web", 30)
    conn.execute("UPDATE pulse_users SET ativo=0")
    assert accounts.resolver_sessao(conn, t, 30) is None


def test_alterar_password_regras_e_revoga_as_outras_sessoes(conn):
    uid = criar(conn)
    u = lambda: conn.execute("SELECT * FROM pulse_users").fetchone()
    t1 = accounts.criar_sessao(conn, uid, "", "", "web", 30); t2 = accounts.criar_sessao(conn, uid, "", "", "android", 30)
    atual = accounts.resolver_sessao(conn, t1, 30)[1]["id"]
    for nova, codigo in (("curta", "password_fraca"), ("1234qweR", "password_atual_errada")):
        with pytest.raises(accounts.ContaErro) as e:
            accounts.alterar_password(conn, u(), "1234qweR" if codigo == "password_fraca" else "x", nova, atual)
        assert e.value.codigo == codigo
    with pytest.raises(accounts.ContaErro) as e:
        accounts.alterar_password(conn, u(), "1234qweR", "1234qweR", atual)
    assert e.value.codigo == "password_fraca" or e.value.codigo == "password_igual"
    accounts.alterar_password(conn, u(), "1234qweR", "Nova-Palavra-Passe-9", atual)
    assert u()["must_change_password"] == 0
    assert accounts.resolver_sessao(conn, t1, 30) and accounts.resolver_sessao(conn, t2, 30) is None
    assert accounts.autenticar(conn, "eu@exemplo.pt", "Nova-Palavra-Passe-9")


@pytest.mark.parametrize("pw", ["curta", "aaaaaaaaaaaa", "eu@exemplo.pt", "1234567890", "eu"])
def test_politica_recusa_fracas(pw):
    with pytest.raises(accounts.ContaErro):
        accounts.validar_password_nova(pw, "eu@exemplo.pt")


def test_repor_password_obriga_a_mudar_e_termina_sessoes(conn):
    uid = criar(conn, password="antiga-1234")
    t = accounts.criar_sessao(conn, uid, "", "", "web", 30)
    conn.execute("UPDATE pulse_users SET must_change_password=0")
    accounts.repor_password(conn, "eu@exemplo.pt", "provisoria-1")
    assert conn.execute("SELECT must_change_password FROM pulse_users").fetchone()[0] == 1
    assert accounts.resolver_sessao(conn, t, 30) is None
    assert accounts.autenticar(conn, "eu@exemplo.pt", "provisoria-1")
    with pytest.raises(accounts.ContaErro):
        accounts.repor_password(conn, "nao@existe.pt", "x")
