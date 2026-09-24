"""Importa o histórico e a configuração do peso do Google Sheets para o SQLite,
com relatório de qualidade dos dados. Corre no Pi (a service account de lá só lê).

    python importar_peso.py            # só lê e mostra o relatório (nada é gravado)
    python importar_peso.py --gravar   # grava na BD e confirma linha a linha

Idempotente e compatível com o botão "Importar" da PWA: o `cid` de cada registo é
'imp-<linha da folha>', por isso repetir (aqui ou na app) nunca duplica.
Precisa das bibliotecas Google: correr com o python do venv de tarefas/pi
(~/tarefas/pi/.venv/bin/python).
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import db
from api import ApiError
from apps import peso

SHEET_ID = os.environ.get("PESO_SPREADSHEET_ID", "1UzEXtl7w6jMsk-c7Pkt3kq97AXL6XIiwTrjOYUaYFLs")
SA_FILE = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", str(Path.home() / "tarefas/pi/config/service-account.json"))
EPOCH = datetime(1899, 12, 30)
SALTO_SUSPEITO_KG = 5.0
LACUNA_DIAS = 14


def ler_sheets():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    cred = service_account.Credentials.from_service_account_file(
        SA_FILE, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    svc = build("sheets", "v4", credentials=cred, cache_discovery=False).spreadsheets().values()

    def get(rng):
        return svc.get(spreadsheetId=SHEET_ID, range=rng, valueRenderOption="UNFORMATTED_VALUE").execute().get("values", [])
    return get("Registos!A2:C100000"), get("Config!B2:B9")


def para_quando(v):
    """Serial do Sheets (ou texto) -> 'AAAA-MM-DD HH:MM:SS'. Mesma lógica da PWA (serialToDate)."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return (EPOCH + timedelta(seconds=round(v * 86400))).strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, str) and v.strip():
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(v.strip(), fmt).strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass
    return None


def preparar(linhas):
    """-> (validos, problemas, vazias). Cada válido: dict(linha, quando, peso, nota, cid)."""
    validos, problemas, vazias = [], [], 0
    for i, row in enumerate(linhas):
        n = i + 2
        row = list(row) + [""] * (3 - len(row))
        if row[0] in ("", None) and row[1] in ("", None):
            vazias += 1  # linha limpa (registo eliminado) — não é um problema
            continue
        quando = para_quando(row[0])
        if quando is None:
            problemas.append((n, f"data ilegível: {row[0]!r}"))
            continue
        try:
            peso_kg = peso._numero(row[1], "peso", 1, 1000)
        except ApiError as e:
            problemas.append((n, f"peso inválido {row[1]!r}: {e.mensagem}"))
            continue
        nota = str(row[2] or "")
        if len(nota) > 500:
            problemas.append((n, f"nota com {len(nota)} caracteres (truncada a 500)"))
        validos.append({"linha": n, "quando": quando, "peso": peso_kg, "nota": peso._nota(nota[:500]),
                        "cid": f"imp-{n:06d}"})
    return validos, problemas, vazias


def qualidade(validos):
    """Anomalias que merecem um olhar humano (não impedem a importação)."""
    avisos = []
    por_quando = {}
    for r in validos:
        por_quando.setdefault(r["quando"], []).append(r)
    for q, rs in por_quando.items():
        if len(rs) > 1:
            avisos.append(f"duplicado exato {q}: linhas {[r['linha'] for r in rs]} pesos {[r['peso'] for r in rs]}")
    fora_de_ordem = [b["linha"] for a, b in zip(validos, validos[1:]) if b["quando"] < a["quando"]]
    if fora_de_ordem:
        avisos.append(f"{len(fora_de_ordem)} linhas fora de ordem cronológica na folha (a app ordena; ex.: linhas {fora_de_ordem[:5]})")
    ordenados = sorted(validos, key=lambda r: (r["quando"], r["linha"]))
    for a, b in zip(ordenados, ordenados[1:]):
        salto = b["peso"] - a["peso"]
        dias = (datetime.fromisoformat(b["quando"]) - datetime.fromisoformat(a["quando"])).days
        if abs(salto) >= SALTO_SUSPEITO_KG and dias <= 3:
            avisos.append(f"salto de {salto:+.1f} kg em {dias} dia(s): linha {a['linha']} ({a['peso']}) -> linha {b['linha']} ({b['peso']})")
        if dias >= LACUNA_DIAS:
            avisos.append(f"lacuna de {dias} dias entre {a['quando'][:10]} e {b['quando'][:10]}")
    for r in validos:
        if r["peso"] < 30 or r["peso"] > 250:
            avisos.append(f"peso improvável na linha {r['linha']}: {r['peso']} kg")
    dias_mesmo = {}
    for r in validos:
        dias_mesmo.setdefault(r["quando"][:10], []).append(r["linha"])
    multi = {d: ls for d, ls in dias_mesmo.items() if len(ls) > 1}
    if multi:
        avisos.append(f"{len(multi)} dia(s) com mais de um registo (ex.: {list(multi.items())[:3]})")
    return avisos


def normaliza_atividade(raw):
    """Igual a normalizaAtividade() da PWA: escala 1-4 antiga, ou o multiplicador válido mais próximo; o resto = 1.2."""
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 1.2
    if not v or v != v:
        return 1.2
    escala = {1: 1.2, 2: 1.45, 3: 1.7, 4: 1.7}
    if v == int(v) and int(v) in escala:
        return escala[int(v)]
    if 1.2 <= v <= 1.725:
        return min([1.2, 1.45, 1.7], key=lambda x: abs(x - v))
    return 1.2


def config_do_sheets(valores):
    v = [(l[0] if l else "") for l in valores] + [""] * 8
    cfg, problemas = {}, []
    nomes = ["altura", "nascimento", "sexo", "pesoAlvo", "atividade", "diaControlo", "pesoMin", "pesoMax"]
    for nome, bruto in zip(nomes, v):
        if bruto in ("", None):
            continue
        if nome == "nascimento":
            quando = para_quando(bruto)
            bruto = quando[:10] if quando else bruto
        if nome == "atividade":
            norm = normaliza_atividade(bruto)
            if norm != bruto:
                problemas.append(f"AVISO config atividade={bruto!r} não é um nível válido (no Sheets isto costuma ser um valor "
                                 f"convertido em data); a app já o tratava como {norm} e é isso que se importa")
            bruto = norm
        try:
            cfg[nome] = peso.CONFIG[nome][0](bruto)
        except ApiError as e:
            problemas.append(f"config {nome}={bruto!r} inválido: {e.mensagem}")
    return cfg, problemas


def main(argv):
    gravar = "--gravar" in argv
    linhas, cfg_raw = ler_sheets()
    validos, problemas, vazias = preparar(linhas)
    avisos = qualidade(validos)
    cfg, cfg_problemas = config_do_sheets(cfg_raw)

    print(f"Registos lidos: {len(linhas)} linhas | válidos: {len(validos)} | vazias (eliminadas): {vazias} | com problema: {len(problemas)}")
    if validos:
        pesos = [r["peso"] for r in validos]
        print(f"Período: {min(r['quando'] for r in validos)[:10]} .. {max(r['quando'] for r in validos)[:10]} | "
              f"peso min/máx: {min(pesos)}/{max(pesos)} kg | notas: {sum(1 for r in validos if r['nota'])}")
    for n, msg in problemas:
        print(f"  PROBLEMA linha {n}: {msg}")
    for a in avisos:
        print(f"  AVISO: {a}")
    print(f"Config lida: {cfg}")
    for p in cfg_problemas:
        print(f"  {'' if p.startswith('AVISO') else 'PROBLEMA '}{p}")
    if not gravar:
        print("\n(nada gravado — usa --gravar)")
        return 0

    conn = db.connect()
    db.migrate(conn)
    conn.execute("BEGIN IMMEDIATE")
    criados = 0
    try:
        for r in validos:
            criados += conn.execute("INSERT OR IGNORE INTO peso_registos (quando, peso, nota, cid) VALUES (?, ?, ?, ?)",
                                    (r["quando"], r["peso"], r["nota"], r["cid"])).rowcount
        if not conn.execute("SELECT 1 FROM peso_config LIMIT 1").fetchone():  # não pisa config já alterada
            for k, val in cfg.items():
                conn.execute("INSERT INTO peso_config (chave, valor) VALUES (?, ?)", (k, val))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    print(f"\nGravado: {criados} novos, {len(validos) - criados} já existiam.")

    # --- verificação: a BD tem exatamente o que a folha tem ---
    erros = []
    na_bd = {r["cid"]: r for r in conn.execute("SELECT cid, quando, peso, nota FROM peso_registos WHERE cid LIKE 'imp-%'")}
    for r in validos:
        d = na_bd.get(r["cid"])
        if not d:
            erros.append(f"linha {r['linha']} em falta na BD")
        elif (d["quando"], d["peso"], d["nota"]) != (r["quando"], r["peso"], r["nota"]):
            erros.append(f"linha {r['linha']} diferente: folha={(r['quando'], r['peso'], r['nota'])} bd={tuple(d)}")
    extra = set(na_bd) - {r["cid"] for r in validos}
    if extra:
        erros.append(f"registos importados na BD que já não estão na folha: {sorted(extra)[:5]}")
    ic = conn.execute("PRAGMA integrity_check").fetchone()[0]
    fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    total = conn.execute("SELECT COUNT(*) FROM peso_registos").fetchone()[0]
    print(f"Verificação: {len(validos)} da folha vs {len(na_bd)} importados na BD (total na tabela: {total}) | integrity_check={ic} | fk_violacoes={len(fk)}")
    for e in erros:
        print(f"  ERRO: {e}")
    print("VERIFICAÇÃO " + ("OK" if not erros and ic == "ok" and not fk and len(na_bd) == len(validos) else "FALHOU"))
    return 0 if not erros else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
