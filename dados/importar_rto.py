"""Importa os dias (T/C) e as notas do RTO do Google Sheets para o SQLite, com relatório de qualidade.
Corre no Pi (a service account de lá só lê). Igual ao importar_peso.py:

    python importar_rto.py            # só lê e mostra o relatório (nada é gravado)
    python importar_rto.py --gravar   # grava na BD e confirma linha a linha

Idempotente: os dias são chaves (INSERT OR IGNORE — nunca pisa um dia já editado na app) e cada
nota leva um `cid` 'imp-nota-<linha>' — repetir nunca duplica.
Precisa das bibliotecas Google: correr com o python do venv de tarefas/pi.
"""

from __future__ import annotations

import os
import re
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import db
from apps import rto

SHEET_ID = os.environ.get("RTO_SPREADSHEET_ID", "1u4QOqKMEOe8qq_kU_Cw5c8Vj4qQ0AHE5gXj9hPood9c")
SA_FILE = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", str(Path.home() / "tarefas/pi/config/service-account.json"))
EPOCH = date(1899, 12, 30)


def ler_sheets():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    cred = service_account.Credentials.from_service_account_file(
        SA_FILE, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    v = build("sheets", "v4", credentials=cred, cache_discovery=False).spreadsheets().values()

    def get(rng, modo="UNFORMATTED_VALUE"):
        return v.get(spreadsheetId=SHEET_ID, range=rng, valueRenderOption=modo).execute().get("values", [])
    return get("Dados!A2:B4000"), get("Notas!A2:D1000"), get("Resumo!A1:B2", "FORMATTED_VALUE")


def para_data(v):
    """Serial do Sheets, 'AAAA-MM-DD' ou 'DD/MM/AAAA' -> 'AAAA-MM-DD' (ou None)."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return (EPOCH + timedelta(days=int(v))).isoformat()
    if isinstance(v, str):
        s = v.strip()
        m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", s)
        if m:
            s = f"{m[3]}-{m[2]}-{m[1]}"
        try:
            return date.fromisoformat(s).isoformat() if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s) else None
        except ValueError:
            return None
    return None


def preparar_dias(linhas):
    """-> (dias {iso: marca}, sem_marca, problemas[(linha, msg)])"""
    dias, problemas, sem_marca, vistos = {}, [], 0, Counter()
    for i, row in enumerate(linhas):
        n = i + 2
        row = list(row) + [""] * (2 - len(row))
        d = para_data(row[0])
        if d is None:
            if row[0] not in ("", None):
                problemas.append((n, f"data ilegível: {row[0]!r}"))
            continue
        vistos[d] += 1
        marca = str(row[1]).strip()
        if marca == "":
            sem_marca += 1
        elif marca.upper() in ("T", "C"):
            if marca != marca.upper():
                problemas.append((n, f"marca {marca!r} em minúscula (importada como {marca.upper()})"))
            dias[d] = marca.upper()
        else:
            problemas.append((n, f"marca desconhecida {marca!r} em {d} (ignorada)"))
    for d, c in vistos.items():
        if c > 1:
            problemas.append((0, f"data repetida na folha: {d} ({c}x) — fica a última marca"))
    return dias, sem_marca, problemas


def preparar_notas(linhas):
    """-> (notas [dict com linha, dataInicio, dataFim, categoria, descricao, cid], vazias, problemas)"""
    notas, problemas, vazias = [], [], 0
    for i, row in enumerate(linhas):
        n = i + 2
        row = list(row) + [""] * (4 - len(row))
        if all(c in ("", None) for c in row):
            vazias += 1
            continue
        ini, fim = para_data(row[0]), para_data(row[1])
        for nome, bruto, val in (("início", row[0], ini), ("fim", row[1], fim)):
            if bruto not in ("", None) and val is None:
                problemas.append((n, f"data de {nome} ilegível: {bruto!r}"))
        nota = {"linha": n, "dataInicio": ini, "dataFim": fim, "categoria": str(row[2] or "").strip(),
                "descricao": str(row[3] or "").strip()}
        try:
            rto._nota_valida({k: nota[k] for k in ("dataInicio", "dataFim", "categoria", "descricao")})
        except Exception as e:
            problemas.append((n, f"nota inválida, ignorada: {getattr(e, 'mensagem', e)}"))
            continue
        nota["cid"] = f"imp-nota-{n:06d}"
        notas.append(nota)
    return notas, vazias, problemas


def _norm(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn").strip()


def qualidade(dias, notas):
    avisos = []
    fins_de_semana = sorted(d for d in dias if date.fromisoformat(d).weekday() >= 5)
    if fins_de_semana:
        avisos.append(f"{len(fins_de_semana)} marca(s) ao fim de semana (a app só marca dias úteis): {fins_de_semana[:5]}")
    ferias = set()
    for n in notas:
        if "feria" in _norm(n["categoria"]):
            ini = n["dataInicio"] or n["dataFim"]
            if not ini:
                continue
            d, fim = date.fromisoformat(ini), date.fromisoformat(n["dataFim"] or ini)
            while d <= fim:
                ferias.add(d.isoformat()); d += timedelta(days=1)
    em_ferias = sorted(d for d in dias if d in ferias)
    if em_ferias:
        avisos.append(f"{len(em_ferias)} dia(s) com marca T/C dentro de Férias (a app limpa a marca ao pôr férias): {em_ferias[:5]}")
    vistos = Counter((n["dataInicio"], n["dataFim"], _norm(n["categoria"])) for n in notas)
    for k, c in vistos.items():
        if c > 1:
            avisos.append(f"nota duplicada {k}: {c}x")
    cats = Counter(n["categoria"] for n in notas)
    avisos.append(f"categorias de notas: {dict(cats)}")
    anos = Counter(d[:4] for d in dias)
    avisos.append(f"dias marcados por ano: {dict(anos)}")
    return avisos


def main(argv):
    gravar = "--gravar" in argv
    l_dias, l_notas, resumo = ler_sheets()
    dias, sem_marca, p_dias = preparar_dias(l_dias)
    notas, vazias, p_notas = preparar_notas(l_notas)
    cont = Counter(dias.values())
    print(f"Dados: {len(l_dias)} linhas | com marca: {len(dias)} (T={cont['T']}, C={cont['C']}) | sem marca: {sem_marca} | problemas: {len(p_dias)}")
    print(f"Notas: {len(l_notas)} linhas | válidas: {len(notas)} | vazias (eliminadas): {vazias} | problemas: {len(p_notas)}")
    for n, m in p_dias + p_notas:
        print(f"  PROBLEMA linha {n}: {m}")
    for a in qualidade(dias, notas):
        print(f"  INFO/AVISO: {a}")
    # conferência independente: os totais que a própria folha calcula (Resumo!B1/B2 = COUNTIF)
    try:
        r_t, r_c = int(resumo[0][1]), int(resumo[1][1])
        ok = (r_t, r_c) == (cont["T"], cont["C"])
        print(f"Conferência com a folha (Resumo): escritório {r_t} / casa {r_c} vs importado {cont['T']} / {cont['C']} -> {'IGUAIS' if ok else 'DIFERENTES'}")
    except (IndexError, ValueError):
        print("Conferência com o Resumo: não foi possível ler os totais")
    if not gravar:
        print("\n(nada gravado — usa --gravar)")
        return 0

    conn = db.connect()
    db.migrate(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        novos_dias = sum(conn.execute("INSERT OR IGNORE INTO rto_dias (data, marca) VALUES (?, ?)", (d, m)).rowcount
                         for d, m in dias.items())
        novas_notas = sum(conn.execute(
            "INSERT OR IGNORE INTO rto_notas (data_inicio, data_fim, categoria, descricao, cid) VALUES (?, ?, ?, ?, ?)",
            (n["dataInicio"], n["dataFim"], n["categoria"], n["descricao"], n["cid"])).rowcount for n in notas)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    print(f"\nGravado: {novos_dias} dias novos ({len(dias) - novos_dias} já existiam) | {novas_notas} notas novas ({len(notas) - novas_notas} já existiam)")

    erros = []
    na_bd = {r["data"]: r["marca"] for r in conn.execute("SELECT data, marca FROM rto_dias")}
    for d, m in dias.items():
        if na_bd.get(d) != m:
            erros.append(f"dia {d}: folha={m} bd={na_bd.get(d)}")
    nb = {r["cid"]: (r["data_inicio"], r["data_fim"], r["categoria"], r["descricao"])
          for r in conn.execute("SELECT cid, data_inicio, data_fim, categoria, descricao FROM rto_notas WHERE cid LIKE 'imp-nota-%'")}
    for n in notas:
        esperado = (n["dataInicio"], n["dataFim"], n["categoria"], n["descricao"])
        if nb.get(n["cid"]) != esperado:
            erros.append(f"nota linha {n['linha']}: folha={esperado} bd={nb.get(n['cid'])}")
    ic = conn.execute("PRAGMA integrity_check").fetchone()[0]
    fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    print(f"Verificação: dias {len(dias)} folha vs {sum(1 for d in dias if d in na_bd)} na BD | notas {len(notas)} folha vs {len(nb)} na BD | "
          f"integrity_check={ic} | fk_violacoes={len(fk)}")
    for e in erros:
        print(f"  ERRO: {e}")
    print("VERIFICAÇÃO " + ("OK" if not erros and ic == "ok" and not fk else "FALHOU"))
    return 0 if not erros else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
