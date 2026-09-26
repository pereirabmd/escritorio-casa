"""Carrega lançamentos da app financas a partir de um CSV (';'), p.ex. para o arranque inicial.

    python importar_financas.py carga.csv                                  # só valida e mostra o relatório
    python importar_financas.py carga.csv --gravar                         # grava (idempotente: repetir não duplica)
    python importar_financas.py carga.csv --gravar --preparados 2026-09,2026-10

Formato (com cabeçalho): tipo;descricao;valor;categoria;data_vencimento;data_pagamento;recorrente;mes_referencia
  tipo: despesa|rendimento · valor: 1234,56 ou 1234.56 · datas AAAA-MM-DD (data_pagamento e mes_referencia
  podem ir vazios; mes_referencia vazio = mês do vencimento) · recorrente: sim|não · categoria: por nome
  (as que não existirem são criadas).
`--preparados`: meses já completos no ficheiro. Ficam marcados como preparados para a app não lhes copiar
os recorrentes do mês anterior por cima. Não marcar meses futuros que só tenham algumas linhas.

O CSV tem dados pessoais: guardá-lo FORA do repositório (que é público).
Idempotência: cada linha ganha um `cid` derivado do seu conteúdo.
"""

from __future__ import annotations

import csv
import hashlib
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import db
from api import ApiError
from apps.financas import CORES_NOVAS, _data, _mes, _tipo, _valor

CABECALHO = ["tipo", "descricao", "valor", "categoria", "data_vencimento", "data_pagamento", "recorrente", "mes_referencia"]


def ler(caminho: Path) -> tuple[list[dict], list[str]]:
    """(linhas, problemas). Nada é gravado aqui."""
    linhas, problemas = [], []
    with open(caminho, encoding="utf-8-sig", newline="") as f:
        leitor = csv.reader(f, delimiter=";")
        cab = [c.strip() for c in next(leitor, [])]
        if cab != CABECALHO:
            return [], [f"cabeçalho inesperado: {cab} (esperado {CABECALHO})"]
        for n, r in enumerate(leitor, start=2):
            if not any(c.strip() for c in r):
                continue
            try:
                if len(r) != len(CABECALHO):
                    raise ValueError(f"{len(r)} colunas em vez de {len(CABECALHO)}")
                tipo, desc, valor, cat, venc, pag, rec, mes = (c.strip() for c in r)
                rec_l = rec.lower()
                if rec_l not in ("sim", "não", "nao"):
                    raise ValueError(f"recorrente tem de ser sim|não, veio {rec!r}")
                if not desc or not cat:
                    raise ValueError("descrição e categoria são obrigatórias")
                venc = _data(venc, "data_vencimento")
                linha = {"tipo": _tipo(tipo), "descricao": desc, "valor": _valor(float(valor.replace(",", "."))),
                         "categoria": cat, "data_vencimento": venc,
                         "data_pagamento": _data(pag, "data_pagamento") if pag else None,
                         "recorrente": int(rec_l == "sim"), "mes_referencia": _mes(mes, "mes_referencia") if mes else venc[:7]}
            except (ValueError, ApiError) as e:
                problemas.append(f"linha {n}: {getattr(e, 'mensagem', e)}")
                continue
            chave = "|".join(str(linha[k]) for k in ("tipo", "descricao", "valor", "categoria", "data_vencimento", "mes_referencia"))
            linha["cid"] = "imp-" + hashlib.sha1(chave.encode()).hexdigest()[:20]
            linhas.append(linha)
    cids = [l["cid"] for l in linhas]
    if len(set(cids)) != len(cids):
        problemas.append("há linhas repetidas (mesmo tipo, descrição, valor, categoria, vencimento e mês)")
    return linhas, problemas


def gravar(conn, linhas: list[dict], preparados: list[str], agora: datetime) -> dict:
    """Devolve {criadas, existentes, categorias_novas}. Tudo ou nada."""
    criadas = existentes = 0
    novas: list[str] = []
    conn.execute("BEGIN IMMEDIATE")
    try:
        cats = {r["nome"].lower(): r["id"] for r in conn.execute("SELECT id, nome FROM financas_categorias")}
        for l in linhas:
            if l["categoria"].lower() not in cats:
                cor = CORES_NOVAS[len(cats) % len(CORES_NOVAS)]
                cats[l["categoria"].lower()] = conn.execute("INSERT INTO financas_categorias (nome, cor) VALUES (?, ?)",
                                                            (l["categoria"], cor)).lastrowid
                novas.append(l["categoria"])
            cur = conn.execute(
                "INSERT OR IGNORE INTO financas_lancamentos (tipo, descricao, valor, categoria_id, data_vencimento, "
                "data_pagamento, recorrente, mes_referencia, cid) VALUES (?,?,?,?,?,?,?,?,?)",
                (l["tipo"], l["descricao"], l["valor"], cats[l["categoria"].lower()], l["data_vencimento"],
                 l["data_pagamento"], l["recorrente"], l["mes_referencia"], l["cid"]))
            criadas += cur.rowcount
        existentes = len(linhas) - criadas
        for m in preparados:
            conn.execute("INSERT OR IGNORE INTO financas_meses (mes, preparado_em) VALUES (?, ?)",
                         (m, agora.strftime("%Y-%m-%d %H:%M:%S")))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return {"criadas": criadas, "existentes": existentes, "categorias_novas": novas}


def relatorio(linhas: list[dict]) -> str:
    por_mes: dict[str, dict[str, float]] = defaultdict(lambda: {"despesa": 0.0, "rendimento": 0.0, "n": 0})
    for l in linhas:
        m = por_mes[l["mes_referencia"]]
        m[l["tipo"]] += l["valor"]; m["n"] += 1
    out = [f"{len(linhas)} lançamentos:"]
    for mes in sorted(por_mes):
        m = por_mes[mes]
        out.append(f"  {mes}: {m['n']:>2} lançamentos · despesas {m['despesa']:>9.2f} · rendimentos {m['rendimento']:>9.2f}")
    pagos = sum(1 for l in linhas if l["data_pagamento"])
    out.append(f"  com data de pagamento: {pagos} · por pagar/receber: {len(linhas) - pagos} · recorrentes: {sum(l['recorrente'] for l in linhas)}")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    preparados: list[str] = []
    if "--preparados" in argv:
        i = argv.index("--preparados")
        preparados = [_mes(m.strip(), "preparados") for m in argv[i + 1].split(",") if m.strip()]
        args = [a for a in args if a != argv[i + 1]]
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    linhas, problemas = ler(Path(args[0]))
    print(relatorio(linhas) if linhas else "nenhuma linha válida")
    for p in problemas:
        print("PROBLEMA:", p)
    if problemas:
        print("Há problemas: nada foi gravado.")
        return 1
    if "--gravar" not in argv:
        print("(simulação: use --gravar para gravar)")
        return 0
    conn = db.connect_named("dados")
    try:
        r = gravar(conn, linhas, preparados, datetime.now(ZoneInfo("Europe/Lisbon")))
    finally:
        conn.close()
    print(f"gravadas {r['criadas']} novas ({r['existentes']} já existiam); categorias novas: {', '.join(r['categorias_novas']) or 'nenhuma'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
