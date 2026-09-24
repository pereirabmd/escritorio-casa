"""Importa a Sheet dos bilhetes (Config, Bilhetes, Logs, Pedidos) para `bilhetes.db`, com relatório de
qualidade e uma verificação que interessa a sério: o Pi tem de ver EXATAMENTE o mesmo plano de compras
a partir da BD que via a partir da Sheet. Corre no Pi (usa a service account e o .env do bilhetes_cp).

    python importar_bilhetes.py             # só lê e mostra o relatório (nada é gravado)
    python importar_bilhetes.py --gravar    # grava e verifica

Idempotente: viagens e pedidos entram com o MESMO id que tinham (o nº da linha na Sheet — `v12` continua
`v12`, para não mexer nos locks de compra existentes); bilhetes por referência; registos por
(ts, tipo, perna, resultado). Precisa do venv do bilhetes_cp (bibliotecas Google).
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

import db

SCRIPTS = Path(os.environ.get("BILHETES_CP_SCRIPTS", str(Path.home() / "bilhetes_cp" / "scripts")))
sys.path.insert(0, str(SCRIPTS))
os.environ.setdefault("BILHETES_CP_HOME", str(SCRIPTS.parent))


def _common():
    import common
    return common


def ler_sheet():
    common = _common()
    sc = common.SheetsClient()
    snap = sc.read_config()
    tickets = sc.read_tickets()
    requests = sc.read_requests()
    logs = sc._svc().spreadsheets().values().get(
        spreadsheetId=sc.sheet_id, range="Logs!A5:I3000", valueRenderOption="UNFORMATTED_VALUE",
        dateTimeRenderOption="FORMATTED_STRING").execute(num_retries=3).get("values", [])
    return snap, tickets, requests, logs


def _s(v):
    return "" if v is None else str(v).strip()


def _int(v):
    try:
        f = float(str(v).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    return int(f) if f == int(f) and f > 0 else None


def preparar_viagens(snap):
    """-> (viagens[dict], ignoradas[(linha, motivo)])"""
    common = _common()
    out, ign = [], []
    first = int(snap.get("first_row", 12))
    for i, raw in enumerate(snap["weekly"]):
        row = first + i
        cells = list(raw) + [""] * (6 - len(raw))
        if not any(_s(c) for c in cells):
            continue
        d, hora, train = common.parse_sheet_date(cells[0]), common.parse_sheet_time(cells[4]), _int(cells[3])
        if d is None:
            ign.append((row, f"não é uma viagem (data ilegível): {_s(cells[0])[:70]!r}"))
            continue
        ativo = _s(cells[5]).upper()
        if train is None or hora is None or not _s(cells[1]) or not _s(cells[2]):
            ign.append((row, f"viagem incompleta/inválida e NÃO importada: {cells[:6]!r}" + (" [estava ATIVA]" if ativo == "SIM" else "")))
            continue
        out.append({"id": row, "data": d.isoformat(), "origem": _s(cells[1])[:60], "destino": _s(cells[2])[:60],
                    "comboio": train, "hora": hora, "ativo": "SIM" if ativo == "SIM" else "NAO"})
    return out, ign


def preparar_compras(rows):
    common = _common()
    out, ign = [], []
    for i, raw in enumerate(rows):
        c = list(raw) + [""] * (8 - len(raw))
        if not any(_s(x) for x in c):
            continue
        d = common.parse_sheet_date(c[0])
        if d is None:
            ign.append((i + 5, f"bilhete com data ilegível: {c[:8]!r}"))
            continue
        hora = common.parse_sheet_time(c[4]) or _s(c[4])
        out.append({"data": d.isoformat(), "comboio": _int(c[1]), "origem": _s(c[2]), "destino": _s(c[3]), "hora": hora,
                    "carruagem": _s(c[5]), "lugar": _s(c[6]), "referencia": _s(c[7])})
    return out, ign


def preparar_pedidos(rows):
    common = _common()
    out, ign = [], []
    for i, raw in enumerate(rows):
        c = list(raw) + [""] * (13 - len(raw))
        if not any(_s(x) for x in c):
            continue
        row = 5 + i
        d = common.parse_sheet_date(c[0])
        if d is None:
            ign.append((row, f"pedido com data ilegível: {c[:13]!r}"))
            continue
        minutos = _int(c[7])
        out.append({"id": row, "data": d.isoformat(), "origem": _s(c[1]), "destino": _s(c[2]), "comboio": _int(c[3]),
                    "hora": common.parse_sheet_time(c[4]) or _s(c[4]), "ativo": "NAO" if _s(c[5]).upper() == "NAO" else "SIM",
                    "retry": "SIM" if _s(c[6]).upper() == "SIM" else "NAO",
                    "intervalo": minutos if minutos and 1 <= minutos <= 1440 else None,
                    "forcar": "SIM" if _s(c[8]).upper() == "SIM" else "NAO", "estado": _s(c[9]) or "PENDENTE",
                    "ultima": _s(c[10]), "referencia": _s(c[11]), "mensagem": _s(c[12])})
    return out, ign


def preparar_logs(rows):
    out = []
    for raw in rows:
        c = list(raw) + [""] * (9 - len(raw))
        if not _s(c[0]):
            continue
        out.append([_s(x) for x in c[:9]])
    return out


def preparar_passe(snap):
    common = _common()
    p = list(snap["passe"]) + [""] * 4
    ultima = common.parse_sheet_date(p[0])
    try:
        validade = int(float(p[1]))
    except (TypeError, ValueError):
        validade = 29
    return ultima, validade, common.parse_sheet_date(p[2])


def main(argv):
    gravar = "--gravar" in argv
    snap, tickets, requests, logs_raw = ler_sheet()
    viagens, ign_v = preparar_viagens(snap)
    compras, ign_c = preparar_compras(tickets)
    pedidos, ign_p = preparar_pedidos(requests)
    logs = preparar_logs(logs_raw)
    ultima, validade, expira_folha = preparar_passe(snap)

    print(f"Passe: último carregamento {ultima} + {validade} dias | expira (fórmula da folha): {expira_folha}")
    if ultima and expira_folha:
        calc = date.fromordinal(ultima.toordinal() + validade)
        print(f"  cálculo do Pi: {calc} -> {'IGUAL à folha' if calc == expira_folha else 'DIFERENTE da folha!'}")
    print(f"Viagens (Config): {len(viagens)} importáveis ({sum(1 for v in viagens if v['ativo'] == 'SIM')} ativas) | ids: {[v['id'] for v in viagens]}")
    for row, motivo in ign_v:
        print(f"  IGNORADA linha {row}: {motivo}")
    print(f"Bilhetes: {len(compras)} | referências repetidas: {[r for r, n in Counter(c['referencia'] for c in compras if c['referencia']).items() if n > 1]}")
    for row, motivo in ign_c:
        print(f"  IGNORADO linha {row}: {motivo}")
    print(f"Pedidos: {len(pedidos)} | estados: {dict(Counter(p['estado'] for p in pedidos))}")
    for row, motivo in ign_p:
        print(f"  IGNORADO linha {row}: {motivo}")
    print(f"Registos (Logs): {len(logs)} | por tipo: {dict(Counter(l[1] for l in logs))}"
          + (f" | de {logs[0][0][:10]} a {logs[-1][0][:10]}" if logs else ""))
    if not gravar:
        print("\n(nada gravado — usa --gravar)")
        return 0

    conn = db.connect_named("bilhetes")
    db.migrate(conn, db.BASE_DIR / db.DATABASES["bilhetes"][2])
    conn.execute("BEGIN IMMEDIATE")
    try:
        if ultima:
            conn.execute("UPDATE bilhetes_passe SET data_ultima_compra=?, validade_dias=? WHERE id=1", (ultima.isoformat(), validade))
        for v in viagens:
            conn.execute("INSERT OR IGNORE INTO bilhetes_viagens (id, data, origem, destino, comboio, hora, ativo) VALUES (?,?,?,?,?,?,?)",
                         (v["id"], v["data"], v["origem"], v["destino"], v["comboio"], v["hora"], v["ativo"]))
        for c in compras:
            existe = conn.execute("SELECT 1 FROM bilhetes_compras WHERE data=? AND comboio IS ? AND hora_partida=? AND referencia=?",
                                  (c["data"], c["comboio"], c["hora"], c["referencia"])).fetchone()
            if not existe:
                conn.execute("INSERT OR IGNORE INTO bilhetes_compras (data, comboio, origem, destino, hora_partida, carruagem, lugar, referencia) "
                             "VALUES (?,?,?,?,?,?,?,?)", (c["data"], c["comboio"], c["origem"], c["destino"], c["hora"], c["carruagem"], c["lugar"], c["referencia"]))
        for p in pedidos:
            conn.execute("INSERT OR IGNORE INTO bilhetes_pedidos (id, data, origem, destino, comboio, hora, ativo, retry, intervalo_minutos, forcar, "
                         "estado, ultima_tentativa, referencia, mensagem) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (p["id"], p["data"], p["origem"], p["destino"], p["comboio"], p["hora"], p["ativo"], p["retry"], p["intervalo"],
                          p["forcar"], p["estado"], p["ultima"], p["referencia"], p["mensagem"]))
        for l in logs:
            existe = conn.execute("SELECT 1 FROM bilhetes_logs WHERE ts=? AND tipo=? AND perna=? AND resultado=?", (l[0], l[1], l[3], l[6])).fetchone()
            if not existe:
                conn.execute("INSERT INTO bilhetes_logs (ts, tipo, data_viagem, perna, comboio, status_http, resultado, referencia, mensagem_erro) "
                             "VALUES (?,?,?,?,?,?,?,?,?)", l)
        # os ids novos continuam a começar acima de qualquer id importado
        for tabela, ids in (("bilhetes_viagens", [v["id"] for v in viagens]), ("bilhetes_pedidos", [p["id"] for p in pedidos])):
            seq = max([99] + ids)
            conn.execute("UPDATE sqlite_sequence SET seq = MAX(seq, ?) WHERE name = ?", (seq, tabela))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    conn.close()
    return verificar(snap, tickets, requests, viagens, compras, pedidos, logs)


def verificar(snap, tickets, requests, viagens, compras, pedidos, logs):
    """A verificação que importa: o Pi, alimentado pela BD, vê o mesmo que via na Sheet."""
    common = _common()
    import store
    st = store.SqliteStore(db.db_path("bilhetes"))
    erros = []
    hoje = common.now_local().date()
    # 1) o mesmo plano de viagens (mesmos ids 'vN', mesmos dados) — só as linhas que eram viagens
    legs_folha, _ = common.parse_snapshot(snap, hoje)
    legs_bd, _ = common.parse_snapshot(st.read_config(), hoje)
    chave = lambda l: (l.date, l.leg, l.origin, l.destination, l.train, l.hhmm, l.row)  # noqa: E731
    if sorted(map(chave, legs_folha)) != sorted(map(chave, legs_bd)):
        erros.append(f"plano diferente: folha={sorted(map(chave, legs_folha))} bd={sorted(map(chave, legs_bd))}")
    # 2) o passe expira no mesmo dia
    import pass_expiry_check
    if pass_expiry_check.expiry_date(snap["passe"]) != pass_expiry_check.expiry_date(st.read_config()["passe"]):
        erros.append("data de expiração do passe diferente")
    # 3) bilhetes: as mesmas (data, comboio) — o que a proteção contra compra dupla consulta
    bd_t = {(common.parse_sheet_date(r[0]), int(float(r[1]))) for r in st.read_tickets() if r[1] not in ("", None)}
    folha_t = {(common.parse_sheet_date(r[0]), int(float(r[1]))) for r in tickets if len(r) > 1 and r[1] not in ("", None)}
    if bd_t != folha_t:
        erros.append(f"bilhetes diferentes: só folha={folha_t - bd_t} só bd={bd_t - folha_t}")
    # 4) pedidos: mesmas pernas 'pedidoN'
    pl_f, _ = common.parse_request_rows(requests, hoje)
    pl_b, _ = common.parse_request_rows(st.read_requests(), hoje)
    ck = lambda l: (l.date, l.leg, l.train, l.hhmm, l.retry, l.retry_minutes)  # noqa: E731
    if sorted(map(ck, pl_f)) != sorted(map(ck, pl_b)):
        erros.append("pedidos diferentes")
    # 5) contagens
    conn = db.connect_named("bilhetes")
    n = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
         for t in ("bilhetes_viagens", "bilhetes_compras", "bilhetes_pedidos", "bilhetes_logs")}
    esperado = {"bilhetes_viagens": len(viagens), "bilhetes_compras": len(compras), "bilhetes_pedidos": len(pedidos), "bilhetes_logs": len(logs)}
    if n != esperado:
        erros.append(f"contagens: bd={n} esperado={esperado}")
    ic = conn.execute("PRAGMA integrity_check").fetchone()[0]
    seqs = dict(conn.execute("SELECT name, seq FROM sqlite_sequence WHERE name IN ('bilhetes_viagens','bilhetes_pedidos')").fetchall())
    conn.close()
    print(f"\nVerificação: viagens/plano: {len(legs_bd)} pernas ativas e válidas na BD vs {len(legs_folha)} na folha | bilhetes {len(bd_t)} vs {len(folha_t)} | "
          f"pedidos {len(pl_b)} vs {len(pl_f)} | contagens {n} | integrity_check={ic} | próximos ids: {seqs}")
    for e in erros:
        print(f"  ERRO: {e}")
    ok = not erros and ic == "ok" and all(s >= 99 for s in seqs.values())
    print("VERIFICAÇÃO " + ("OK" if ok else "FALHOU"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
