import io

import pytest

from pulse import accounts, cli, db


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    caminho = tmp_path / "teste-pulse.db"
    monkeypatch.setenv("PULSE_ENV", "test"); monkeypatch.setenv("PULSE_DB_PATH", str(caminho))
    return caminho


def corre(*args, stdin=""):
    return cli.main(list(args), stdin=io.StringIO(stdin))


def test_criar_repor_desativar_e_listar(ambiente, capsys):
    assert corre("criar", "--email", "Eu@Exemplo.pt", "--nome", "Eu", "--admin", stdin="1234qweR\n") == 0
    conn = db.connect(ambiente)
    u = accounts.autenticar(conn, "eu@exemplo.pt", "1234qweR")
    assert (u["admin"], u["must_change_password"]) == (1, 1)
    assert corre("criar", "--email", "eu@exemplo.pt", stdin="x\n") == 1                     # duplicado
    assert corre("repor", "--email", "eu@exemplo.pt", stdin="provisoria-9\n") == 0
    assert accounts.autenticar(conn, "eu@exemplo.pt", "provisoria-9")
    assert corre("desativar", "--email", "eu@exemplo.pt") == 0
    with pytest.raises(accounts.ContaErro):
        accounts.autenticar(conn, "eu@exemplo.pt", "provisoria-9")
    assert corre("ativar", "--email", "eu@exemplo.pt") == 0 and corre("desativar", "--email", "nao@existe.pt") == 1
    capsys.readouterr(); corre("listar")
    assert "eu@exemplo.pt" in capsys.readouterr().out
    conn.close()


def test_a_password_nao_aparece_na_saida(ambiente, capsys):
    corre("criar", "--email", "eu@exemplo.pt", stdin="segredo-provisorio\n")
    saida = capsys.readouterr()
    assert "segredo-provisorio" not in saida.out + saida.err
