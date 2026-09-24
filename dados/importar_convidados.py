"""Importa a lista de convidados e as listas Fase/Estado do Google Sheets para o SQLite, com relatório de
qualidade. Corre no Pi (a service account de lá só lê). Igual aos outros importadores:

    python importar_convidados.py             # só lê e mostra o relatório (nada é gravado)
    python importar_convidados.py --gravar    # grava (INSERT OR IGNORE por linha de origem) e confirma
    python importar_convidados.py --gravar --atualizar   # PRÉ-MIGRAÇÃO: volta a copiar a folha por cima do já importado

Replica as regras de leitura da PWA antiga (loadGuests): linhas sem Nome ignoram-se (no Sheets eram restos de
um preenchimento por modelo), a mesa legada '#mesa:N' das Notas passa para a coluna Mesa, e só os
"Confirmado" ficam com mesa.
Precisa das bibliotecas Google: correr com o python do venv de tarefas/pi.
"""

from __future__ import annotations

import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import db
from apps import convidados as cv
from api import ApiError

SHEET_ID = os.environ.get("CONVIDADOS_SPREADSHEET_ID", "1UcjSO3P7RbreTtKeg4T8jsoRa2KwzTEPE4Wsrkf2Eos")
SA_FILE = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", str(Path.home() / "tarefas/pi/config/service-account.json"))
EPOCH = datetime(1899, 12, 30)


def ler_sheets():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    cred = service_account.Credentials.from_service_account_file(
        SA_FILE, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    v = build("sheets", "v4", credentials=cred, cache_discovery=False).spreadsheets().values()

    def get(rng, modo="UNFORMATTED_VALUE"):
        return v.get(spreadsheetId=SHEET_ID, range=rng, valueRenderOption=modo).execute().get("values", [])
    return get("Config!A2:B50"), get("Convidados!A2:I1000")


def opcoes_do_sheets(linhas):
    """Colunas A (fases) e B (estados): sem vazios nem repetidos, pela ordem da folha."""
    def col(i):
        vistos, out = set(), []
        for r in linhas:
            x = str(r[i]).strip() if len(r) > i and r[i] is not None else ""
            if x and x.lower() not in vistos:
                vistos.add(x.lower()); out.append(x)
        return out
    return col(0), col(1)


def para_data_convite(v):
    """Serial do Sheets ou texto pt-PT ('15/09/2026, 23:00:56') -> 'AAAA-MM-DD HH:MM:SS' (ou None)."""
    if v in ("", None):
        return ""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return (EPOCH + timedelta(seconds=round(v * 86400))).strftime("%Y-%m-%d %H:%M:%S")
    s = str(v).strip()
    for fmt in ("%d/%m/%Y, %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y, %H:%M", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    return None


def _int(v):
    try:
        return max(0, int(float(v)))
    except (TypeError, ValueError):
        return 0


def preparar(linhas):
    """-> (convidados[dict], sem_nome, avisos[str], problemas[(linha,msg)])"""
    out, avisos, problemas, sem_nome = [], [], [], 0
    for i, r in enumerate(linhas):
        n = i + 2
        r = list(r) + [""] * (9 - len(r))
        nome = str(r[0]).strip()
        if not nome:
            if any(str(x).strip() for x in r):
                sem_nome += 1
            continue
        notas = str(r[5])
        mesa = str(r[6]).strip()
        m = re.search(r"#mesa:(\d{1,2})\b", notas)
        if not mesa and m and m.group(1) in cv.MESAS:
            mesa = m.group(1)
            avisos.append(f"linha {n} ({nome}): mesa {mesa} vinha embutida nas Notas (formato antigo #mesa:N)")
        notas = re.sub(r"\s*#mesa:\d{1,2}\b", "", notas, count=1).strip()
        if mesa and mesa not in cv.MESAS:
            problemas.append((n, f"mesa inválida {mesa!r} em {nome} (ignorada)"))
            mesa = ""
        estado = str(r[4]).strip()
        if mesa and estado != cv.ESTADO_COM_MESA:
            avisos.append(f"linha {n} ({nome}): tem mesa {mesa} mas o estado é {estado!r} (não Confirmado) — a mesa não se importa")
            mesa = ""
        tel = str(r[7]).strip()
        if not cv._TEL_RE.match(tel):
            limpo = re.sub(r"[^0-9+()\-. ]", "", tel).strip()[:30]
            problemas.append((n, f"telefone com caracteres inesperados {tel!r} em {nome} (importado como {limpo!r})"))
            tel = limpo
        data = para_data_convite(r[8])
        if data is None:
            problemas.append((n, f"data do convite ilegível {r[8]!r} em {nome} (ignorada)"))
            data = ""
        pessoas, confirmados = _int(r[1]), _int(r[2])
        g = {"linha": n, "nome": nome[:200], "pessoas": min(pessoas, cv.MAX_PESSOAS), "confirmados": min(confirmados, cv.MAX_PESSOAS),
             "fase": str(r[3]).strip(), "estado": estado, "notas": notas[:1000], "mesa": mesa, "telefone": tel, "dataConvite": data}
        try:
            for c in cv.CAMPOS:
                cv._validar(c, g[c])
        except ApiError as e:
            problemas.append((n, f"{nome}: {e.mensagem} — linha ignorada"))
            continue
        out.append(g)
    return out, sem_nome, avisos, problemas


def qualidade(gs, fases, estados):
    a = []
    nomes = Counter(g["nome"].lower() for g in gs)
    a += [f"nome repetido: {n!r} ({c}x)" for n, c in nomes.items() if c > 1]
    a += [f"{g['nome']!r}: {g['confirmados']} confirmados > {g['pessoas']} pessoas" for g in gs if g["confirmados"] > g["pessoas"]]
    a += [f"{g['nome']!r}: fase {g['fase']!r} não está na lista de Fases" for g in gs if g["fase"] and g["fase"] not in fases]
    a += [f"{g['nome']!r}: estado {g['estado']!r} não está na lista de Estados" for g in gs if g["estado"] and g["estado"] not in estados]
    a += [f"{g['nome']!r}: sem estado" for g in gs if not g["estado"]]
    por_mesa = Counter()
    for g in gs:
        if g["mesa"]:
            por_mesa[g["mesa"]] += g["pessoas"]
    a += [f"mesa {m}: {n} pessoas (capacidade 10)" for m, n in sorted(por_mesa.items()) if n > 10]
    return a


def main(argv):
    gravar, atualizar = "--gravar" in argv, "--atualizar" in argv
    l_cfg, l_g = ler_sheets()
    fases, estados = opcoes_do_sheets(l_cfg)
    gs, sem_nome, avisos, problemas = preparar(l_g)
    print(f"Convidados: {len(l_g)} linhas lidas | com nome (importam-se): {len(gs)} | sem nome mas com restos de dados (ignoradas): {sem_nome} | problemas: {len(problemas)}")
    print(f"Pessoas: {sum(g['pessoas'] for g in gs)} previstas, {sum(g['confirmados'] for g in gs)} confirmadas | "
          f"estados: {dict(Counter(g['estado'] for g in gs))} | fases: {dict(Counter(g['fase'] for g in gs))}")
    print(f"Listas: fases={fases} estados={estados}")
    faltam = {cv.ESTADO_COM_MESA, cv.ESTADO_APOS_ENVIO} - set(estados)
    for n, m in problemas:
        print(f"  PROBLEMA linha {n}: {m}")
    for a in avisos + qualidade(gs, fases, estados):
        print(f"  AVISO: {a}")
    if faltam:
        print(f"  PROBLEMA: a lista de Estados não tem {sorted(faltam)} — a API recusa-a; corrige na folha ou aqui")
    if not gravar:
        print("\n(nada gravado — usa --gravar)")
        return 0
    if faltam:
        return 1

    conn = db.connect()
    db.migrate(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        novos = alterados = 0
        for g in gs:
            args = (g["nome"], g["pessoas"], g["confirmados"], g["fase"], g["estado"], g["notas"], g["mesa"], g["telefone"], g["dataConvite"], g["linha"])
            if atualizar:
                cur = conn.execute(
                    "INSERT INTO convidados_lista (nome, pessoas, confirmados, fase, estado, notas, mesa, telefone, data_convite, linha_origem) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(linha_origem) DO UPDATE SET nome=excluded.nome, pessoas=excluded.pessoas, "
                    "confirmados=excluded.confirmados, fase=excluded.fase, estado=excluded.estado, notas=excluded.notas, mesa=excluded.mesa, "
                    "telefone=excluded.telefone, data_convite=excluded.data_convite", args)
                alterados += cur.rowcount
            else:
                novos += conn.execute(
                    "INSERT OR IGNORE INTO convidados_lista (nome, pessoas, confirmados, fase, estado, notas, mesa, telefone, data_convite, linha_origem) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", args).rowcount
        if atualizar or not conn.execute("SELECT 1 FROM convidados_opcoes LIMIT 1").fetchone():   # não pisa listas já editadas na app
            conn.execute("DELETE FROM convidados_opcoes")
            conn.executemany("INSERT INTO convidados_opcoes (tipo, posicao, valor) VALUES (?, ?, ?)",
                             [("fase", i, v) for i, v in enumerate(fases)] + [("estado", i, v) for i, v in enumerate(estados)])
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    print(f"\nGravado: {novos + alterados if atualizar else novos} convidados {'gravados (novos ou atualizados)' if atualizar else 'novos'} "
          f"({'' if atualizar else f'{len(gs) - novos} já existiam'})")

    erros = []
    bd = {r["linha_origem"]: r for r in conn.execute("SELECT * FROM convidados_lista WHERE linha_origem IS NOT NULL")}
    for g in gs:
        d = bd.get(g["linha"])
        if not d:
            erros.append(f"linha {g['linha']} ({g['nome']}) em falta na BD")
            continue
        esperado = (g["nome"], g["pessoas"], g["confirmados"], g["fase"], g["estado"], g["notas"], g["mesa"], g["telefone"], g["dataConvite"])
        obtido = (d["nome"], d["pessoas"], d["confirmados"], d["fase"], d["estado"], d["notas"], d["mesa"], d["telefone"], d["data_convite"])
        if esperado != obtido:
            erros.append(f"linha {g['linha']} diferente: folha={esperado} bd={obtido} (se a folha mudou depois de importar, usa --atualizar)")
    opc = ([r["valor"] for r in conn.execute("SELECT valor FROM convidados_opcoes WHERE tipo='fase' ORDER BY posicao")],
           [r["valor"] for r in conn.execute("SELECT valor FROM convidados_opcoes WHERE tipo='estado' ORDER BY posicao")])
    if opc != (fases, estados):
        erros.append(f"listas diferentes: folha={(fases, estados)} bd={opc}")
    ic = conn.execute("PRAGMA integrity_check").fetchone()[0]
    fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    print(f"Verificação: {len(gs)} da folha vs {len(bd)} importados na BD | listas iguais: {opc == (fases, estados)} | integrity_check={ic} | fk_violacoes={len(fk)}")
    for e in erros:
        print(f"  ERRO: {e}")
    print("VERIFICAÇÃO " + ("OK" if not erros and ic == "ok" and not fk else "FALHOU"))
    return 0 if not erros else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
