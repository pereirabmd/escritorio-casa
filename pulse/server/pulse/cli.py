"""Administração de contas no servidor (ADR-037: não há auto-registo; as contas criam-se aqui).

    python -m pulse.cli criar --email a@b.pt [--nome Nome] [--admin]     # a password provisória vem do stdin
    python -m pulse.cli repor --email a@b.pt                             # nova password provisória (stdin); termina as sessões
    python -m pulse.cli desativar --email a@b.pt | ativar --email a@b.pt
    python -m pulse.cli listar

A password nunca vai na linha de comandos (ficaria no histórico e no `ps`). A conta fica a exigir a mudança da
password no primeiro acesso.
"""

from __future__ import annotations

import argparse
import sys

from pulse import accounts, config, db


def main(argv: list[str], stdin=sys.stdin) -> int:
    p = argparse.ArgumentParser(prog="pulse.cli", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    for nome in ("criar", "repor", "desativar", "ativar"):
        s = sub.add_parser(nome)
        s.add_argument("--email", required=True)
        if nome == "criar":
            s.add_argument("--nome", default="")
            s.add_argument("--admin", action="store_true")
    sub.add_parser("listar")
    a = p.parse_args(argv)

    conn = db.connect(config.load().db_path)
    db.migrate(conn)
    try:
        if a.cmd == "listar":
            for u in conn.execute("SELECT email, nome, admin, ativo, must_change_password, ultimo_login FROM pulse_users ORDER BY id"):
                print(f"{u['email']}\t{u['nome']}\tadmin={u['admin']}\tativo={u['ativo']}\tmudar_password={u['must_change_password']}")
            return 0
        if a.cmd in ("desativar", "ativar"):
            email = accounts.normalizar_email(a.email)
            cur = conn.execute("UPDATE pulse_users SET ativo=? WHERE email=?", (int(a.cmd == "ativar"), email))
            if not cur.rowcount:
                print("não existe essa conta", file=sys.stderr); return 1
            if a.cmd == "desativar":
                accounts.revogar_todas(conn, conn.execute("SELECT id FROM pulse_users WHERE email=?", (email,)).fetchone()["id"])
            print(f"{email}: {'ativada' if a.cmd == 'ativar' else 'desativada'}")
            return 0
        password = stdin.readline().rstrip("\n")
        if a.cmd == "criar":
            accounts.criar_utilizador(conn, a.email, password, a.nome, admin=a.admin)
            print(f"conta criada: {accounts.normalizar_email(a.email)} (tem de mudar a password no primeiro acesso)")
        else:
            accounts.repor_password(conn, a.email, password)
            print(f"password reposta: {accounts.normalizar_email(a.email)} (sessões terminadas; tem de mudar no primeiro acesso)")
        return 0
    except accounts.ContaErro as e:
        print(f"erro: {e.mensagem}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
