from pulse import security


def test_hash_verifica_e_e_diferente_de_cada_vez():
    a, b = security.hash_password("segredo-1234"), security.hash_password("segredo-1234")
    assert a != b and a.startswith("scrypt$")
    assert security.verify_password("segredo-1234", a) and not security.verify_password("outro", a)


def test_hash_corrompido_nao_verifica_nem_rebenta():
    for mau in ("", "lixo", "scrypt$1$2$3", "md5$1$2$3$4$5", "scrypt$x$8$1$AAAA$AAAA"):
        assert security.verify_password("x", mau) is False


def test_token_so_guarda_hash():
    t = security.new_token()
    assert len(t) >= 40 and security.token_hash(t) != t and len(security.token_hash(t)) == 64
    assert security.new_token() != t
