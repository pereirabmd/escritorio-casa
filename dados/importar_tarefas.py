"""Importa a Sheet das tarefas (Tarefas, Instancias, Config, Piscina, Auditoria) para o SQLite (tabelas
`tarefas_*` do dados.db), com relatório de qualidade e uma verificação de paridade: o motor de notificações do Pi
tem de decidir EXATAMENTE o mesmo, a partir da BD, que decidia a partir da Sheet.

    python importar_tarefas.py            # só lê e mostra o relatório (nada é gravado)
    python importar_tarefas.py --gravar   # grava e verifica

Corre no Pi, com o venv do tarefas/pi (bibliotecas Google) — usa a service account e o .env de lá.
Não migram: LogEnvios e Subscriptions (eram do Apps Script/FCM, que morreu com a Beta 48).

Limpezas que faz (todas reportadas, nunca em silêncio):
- linhas de "legenda" no meio das tabelas (texto solto na coluna ID/Chave) ignoram-se;
- um ID de tarefa repetido: o repetido que não está ativo (ou o 2.º) ganha um ID novo;
- (tarefa, data) repetido nas instâncias: fica a mais adiantada (Feita > Saltada > Atrasada > Pendente);
- as colunas Prioridade/RotacaoPessoas/DependeDe (K-M) que a app sempre escreveu mas a folha nunca teve com
  cabeçalho lêem-se por posição; DiaMes só se guarda nas mensais.
"""

from __future__ import annotations

import os
import re
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import db
from apps import tarefas as api_tarefas

PI = Path(os.environ.get("TAREFAS_PI_SCRIPTS", str(Path.home() / "tarefas" / "pi")))
sys.path.insert(0, str(PI))
os.environ.setdefault("TAREFAS_PI_HOME", str(PI))
EPOCH = date(1899, 12, 30)
RANK = {"Feita": 3, "Saltada": 2, "Atrasada": 1, "Pendente": 0}
ESTADOS = {e.lower(): e for e in api_tarefas.ESTADOS}


def _common():
    import common
    return common


def _s(v):
    return "" if v is None else str(v).strip()


def _bool(v) -> int:
    return 1 if (v is True or _s(v).upper() == "TRUE") else 0


def _data(v):
    c = _common()
    d = c.parse_sheet_date(v)
    return d.isoformat() if d else None


def _datahora(v):
    """Serial com hora ou texto 'AAAA-MM-DD HH:MM[:SS]' -> 'AAAA-MM-DD HH:MM' (ou None)."""
    if v in ("", None):
        return ""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        dt = datetime(1899, 12, 30) + timedelta(seconds=round(v * 86400))
        return dt.strftime("%Y-%m-%d %H:%M")
    m = re.match(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})", _s(v))
    return f"{m.group(1)} {m.group(2)}" if m else None


def ler_sheets():
    c = _common()
    sc = c.SheetsClient()
    v = sc._svc().spreadsheets().values()

    def get(rng):
        return v.get(spreadsheetId=sc.sheet_id, range=rng, valueRenderOption="UNFORMATTED_VALUE").execute(num_retries=3).get("values", [])
    return {
        "tarefas": get("Tarefas!A2:M1000"),          # por POSIÇÃO: K-M não têm cabeçalho na folha
        "instancias": sc.read_objects("Instancias"),
        "config": sc.read_objects("Config"),
        "piscina": sc.read_objects("Piscina"),
        "auditoria": get("Auditoria!A2:E5000"),
        "log_envios": len(get("LogEnvios!A2:A5000")),
        "subscriptions": len(get("Subscriptions!A2:A5000")),
        "tarefas_objs": sc.read_objects("Tarefas"),
        "_sc": sc,
    }


# --------------------------------------------------------------------------------

def preparar_tarefas(linhas):
    c = _common()
    out, avisos, problemas = [], [], []
    for i, r in enumerate(linhas):
        n = i + 2
        r = list(r) + [""] * (13 - len(r))
        tid = _s(r[0])
        if not tid:
            continue
        if not re.fullmatch(r"T\d+", tid):
            problemas.append((n, f"linha ignorada (não é uma tarefa; ID = {tid[:50]!r})"))
            continue
        rec = _s(r[4])
        if rec not in api_tarefas.RECORRENCIAS:
            problemas.append((n, f"{tid}: recorrência inválida {rec!r} — tarefa NÃO importada"))
            continue
        dias, dia_mes = "", None
        if rec in api_tarefas.COM_DIAS:
            lista = [d.strip() for d in _s(r[5]).split(",") if d.strip()]
            if not lista or any(d not in api_tarefas.DIAS for d in lista):
                problemas.append((n, f"{tid}: dias da semana inválidos {r[5]!r} — tarefa NÃO importada"))
                continue
            dias = ",".join(dict.fromkeys(lista))
        elif rec in api_tarefas.COM_DATA:
            dias = _data(r[5])
            if not dias:
                problemas.append((n, f"{tid}: data inválida {r[5]!r} — tarefa NÃO importada"))
                continue
        elif rec == "Mensal":
            try:
                dia_mes = int(float(r[6]))
            except (TypeError, ValueError):
                problemas.append((n, f"{tid}: dia do mês inválido {r[6]!r} — tarefa NÃO importada"))
                continue
            if not 1 <= dia_mes <= 31:
                problemas.append((n, f"{tid}: dia do mês {dia_mes} inválido — tarefa NÃO importada"))
                continue
        nome = _s(r[1])
        if not nome:
            problemas.append((n, f"{tid}: sem nome — NÃO importada"))
            continue
        if len(nome) > 200 or re.search(r"[`<>\\?=]|https?:|/[a-z-]+/", nome):        # 'R/C' é legítimo; um URL/caminho colado não
            avisos.append(f"{tid} ({nome[:60]!r}): o nome parece um erro de colagem — importada tal como está, convém corrigi-la"
                          + (" [ATIVA: gera ocorrências e notificações]" if _bool(r[9]) else ""))
        prio = _s(r[10]).capitalize() if _s(r[10]) else "Media"
        if prio not in api_tarefas.PRIORIDADES:
            avisos.append(f"{tid}: prioridade {r[10]!r} inválida -> Media")
            prio = "Media"
        out.append({"linha": n, "id": tid, "nome": nome[:200], "categoria": _s(r[2])[:60], "icone": _s(r[3])[:8], "recorrencia": rec,
                    "dias_semana": dias, "dia_mes": dia_mes, "hora": c.normalizar_hora(r[7]), "pessoa": _s(r[8])[:60],
                    "ativa": _bool(r[9]), "prioridade": prio, "rotacao": _s(r[11])[:200], "depende": _s(r[12])[:12]})
        if _s(r[11]) or _s(r[12]) or (_s(r[10]) and prio != "Media"):
            avisos.append(f"{tid}: usa opções avançadas (prioridade={prio}, rotação={_s(r[11])!r}, dependeDe={_s(r[12])!r}) — "
                          "a folha nunca teve cabeçalho para estas colunas; agora passam a funcionar")
    # ids repetidos
    ids = Counter(t["id"] for t in out)
    proximo = max([int(t["id"][1:]) for t in out] + [0]) + 1
    remap = {}
    for tid, n in ids.items():
        if n < 2:
            continue
        copias = [t for t in out if t["id"] == tid]
        manter = next((t for t in copias if t["ativa"]), copias[0])
        for t in copias:
            if t is manter:
                continue
            novo = f"T{proximo}"
            proximo += 1
            avisos.append(f"ID {tid} repetido: a linha {t['linha']} ({t['nome'][:40]!r}, {'ativa' if t['ativa'] else 'inativa'}) passa a {novo}; "
                          f"a linha {manter['linha']} ({manter['nome'][:40]!r}) fica com {tid}")
            t["id"] = novo
            remap[tid] = manter["id"]
    dep_invalidas = [t for t in out if t["depende"] and t["depende"] not in {x["id"] for x in out}]
    for t in dep_invalidas:
        problemas.append((t["linha"], f"{t['id']}: DependeDe {t['depende']!r} não existe (limpo)"))
        t["depende"] = ""
    return out, avisos, problemas, remap


def preparar_instancias(objs, tarefas_ids):
    out, avisos, problemas = [], [], []
    for o in objs:
        n = o["_rowIndex"]
        iid = _s(o.get("ID"))
        if not re.fullmatch(r"I\d+", iid):
            if iid:
                problemas.append((n, f"linha ignorada (não é uma ocorrência; ID = {iid[:50]!r})"))
            continue
        d = _data(o.get("Data"))
        if not d:
            problemas.append((n, f"{iid}: data inválida {o.get('Data')!r} — NÃO importada"))
            continue
        tid = _s(o.get("TarefaID"))
        if tid not in tarefas_ids:
            problemas.append((n, f"{iid}: tarefa {tid!r} inexistente — NÃO importada"))
            continue
        est_raw = _s(o.get("Estado"))
        est = ESTADOS.get(est_raw.lower())
        if est is None:
            avisos.append(f"{iid}: estado {est_raw!r} desconhecido -> Pendente")
            est = "Pendente"
        concl = _datahora(o.get("DataConclusao"))
        if concl is None:
            avisos.append(f"{iid}: DataConclusao ilegível {o.get('DataConclusao')!r} (limpa)")
            concl = ""
        out.append({"linha": n, "id": iid, "tarefa_id": tid, "data": d, "pessoa": _s(o.get("Pessoa"))[:60], "estado": est,
                    "concl": concl, "notif": _bool(o.get("NotificacaoEnviada"))})
    return out, avisos, problemas


def resolver_duplicadas(inst, avisos):
    por_chave = {}
    for i in inst:
        por_chave.setdefault((i["tarefa_id"], i["data"]), []).append(i)
    fora = set()
    for (tid, d), grupo in por_chave.items():
        if len(grupo) < 2:
            continue
        melhor = max(grupo, key=lambda x: (RANK[x["estado"]], -x["linha"]))
        for x in grupo:
            if x is not melhor:
                fora.add(x["id"])
                avisos.append(f"ocorrência duplicada {tid} em {d}: fica {melhor['id']} ({melhor['estado']}), descarta-se {x['id']} ({x['estado']})")
    return [i for i in inst if i["id"] not in fora]


def preparar_config(objs):
    c = _common()
    out, avisos, problemas = [], [], []
    horas = re.compile(r"(Hora|Inicio|Fim)")
    for o in objs:
        n, chave = o["_rowIndex"], _s(o.get("Chave"))
        if not chave:
            continue
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", chave):
            problemas.append((n, f"linha ignorada (não é uma chave; Chave = {chave[:50]!r})"))
            continue
        v = o.get("Valor")
        if v in ("", None):
            continue                                   # pessoa apagada / chave vazia
        if isinstance(v, float) and v == int(v):
            v = int(v)
        valor = c.normalizar_hora(v) if horas.search(chave) and not chave.endswith("Enc") else _s(v)
        out.append({"chave": chave, "valor": valor[:500], "notas": _s(o.get("Notas"))[:500]})
    return out, avisos, problemas


def preparar_piscina(objs):
    out, problemas = [], []
    for o in objs:
        pid = _s(o.get("ID"))
        if not pid:
            continue
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,19}", pid):
            problemas.append((o["_rowIndex"], f"linha ignorada (ID = {pid[:40]!r})"))
            continue
        out.append({"id": pid, "nome": _s(o.get("Nome")), "aviso": _bool(o.get("AvisoLongo")), "ultima": _data(o.get("UltimaData")),
                    "proxima": _data(o.get("ProximaData")), "notif": _bool(o.get("NotificacaoEnviada")), "longo": _bool(o.get("UsarIntervaloLongo"))})
    return out, problemas


def preparar_auditoria(linhas):
    out = []
    for r in linhas:
        r = list(r) + [""] * (5 - len(r))
        if not _s(r[0]) or _s(r[0]) == "Timestamp":
            continue
        out.append([_s(x)[:200] for x in r[:5]])
    return out


# --------------------------------------------------------------------------------

def main(argv):
    gravar = "--gravar" in argv
    d = ler_sheets()
    tarefas, av_t, pr_t, remap = preparar_tarefas(d["tarefas"])
    ids_t = {t["id"] for t in tarefas}
    # instâncias que apontavam para um ID repetido passam a apontar para a tarefa que ficou com esse ID (já é a mesma string)
    inst, av_i, pr_i = preparar_instancias(d["instancias"], ids_t | set(remap))
    inst = resolver_duplicadas(inst, av_i)
    cfg, av_c, pr_c = preparar_config(d["config"])
    pisc, pr_p = preparar_piscina(d["piscina"])
    aud = preparar_auditoria(d["auditoria"])

    print(f"Tarefas: {len(tarefas)} importáveis ({sum(t['ativa'] for t in tarefas)} ativas) | recorrências: {dict(Counter(t['recorrencia'] for t in tarefas))}")
    print(f"Instâncias: {len(inst)} | estados: {dict(Counter(i['estado'] for i in inst))} | "
          f"datas: {min((i['data'] for i in inst), default='-')} a {max((i['data'] for i in inst), default='-')}")
    print(f"Config: {len(cfg)} chaves | Piscina: {len(pisc)} | Auditoria: {len(aud)} entradas")
    print(f"NÃO migram (Apps Script/FCM): LogEnvios ({d['log_envios']} linhas), Subscriptions ({d['subscriptions']} linhas)")
    for n, m in pr_t + pr_i + pr_c + pr_p:
        print(f"  PROBLEMA linha {n}: {m}")
    for a in av_t + av_i + av_c:
        print(f"  AVISO: {a}")
    # a password ntfy cifrada tem de ser decifrável com a chave do Pi (nunca se imprime)
    c = _common()
    for k in cfg:
        if k["chave"].endswith("_NtfyPasswordEnc"):
            try:
                c.decrypt(k["valor"])
                print(f"  {k['chave']}: decifra com a chave do Pi (ok)")
            except Exception as e:
                print(f"  PROBLEMA {k['chave']}: NÃO decifra com a FERNET_KEY do Pi ({type(e).__name__})")
    if not gravar:
        print("\n(nada gravado — usa --gravar)")
        return 0

    conn = db.connect()
    db.migrate(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        for t in tarefas:
            conn.execute("INSERT OR IGNORE INTO tarefas_tarefas (id, nome, categoria, icone, recorrencia, dias_semana, dia_mes, hora_notificacao, "
                         "pessoa_padrao, ativa, prioridade, rotacao_pessoas, depende_de) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (t["id"], t["nome"], t["categoria"], t["icone"], t["recorrencia"], t["dias_semana"], t["dia_mes"], t["hora"],
                          t["pessoa"], t["ativa"], t["prioridade"], t["rotacao"], t["depende"]))
        for i in inst:
            conn.execute("INSERT OR IGNORE INTO tarefas_instancias (id, tarefa_id, data, pessoa, estado, data_conclusao, notificacao_enviada) "
                         "VALUES (?,?,?,?,?,?,?)", (i["id"], i["tarefa_id"], i["data"], i["pessoa"], i["estado"], i["concl"], i["notif"]))
        for k in cfg:
            conn.execute("INSERT OR IGNORE INTO tarefas_config (chave, valor, notas) VALUES (?,?,?)", (k["chave"], k["valor"], k["notas"]))
        for p in pisc:
            conn.execute("INSERT OR IGNORE INTO tarefas_piscina (id, nome, aviso_longo, ultima_data, proxima_data, notificacao_enviada, usar_intervalo_longo) "
                         "VALUES (?,?,?,?,?,?,?)", (p["id"], p["nome"], p["aviso"], p["ultima"], p["proxima"], p["notif"], p["longo"]))
        if not conn.execute("SELECT 1 FROM tarefas_auditoria LIMIT 1").fetchone():
            conn.executemany("INSERT INTO tarefas_auditoria (ts, acao, tarefa, pessoa, instancia_id) VALUES (?,?,?,?,?)", aud)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    conn.close()
    return verificar(d, tarefas, inst, cfg, pisc, aud)


def _plano(store_, hoje):
    """O que o Pi decidiria a partir de `store_` (a Sheet ou a BD): alvo de cada ocorrência e da piscina + o que o
    gerador criaria. Sem escrever nada."""
    c = _common()
    import instancias
    import recalcular
    config = {str(r.get("Chave", "")).strip(): r.get("Valor") for r in store_.read_objects("Config")}
    tarefas = store_.read_objects("Tarefas")
    tmap = {t.get("ID"): t for t in tarefas}
    insts = store_.read_objects("Instancias")
    hoje_por_t = {i.get("TarefaID"): i for i in insts if c.parse_sheet_date(i.get("Data")) == hoje}
    alvos = {}
    for i in insts:
        a = recalcular.alvo_instancia(i, tmap.get(i.get("TarefaID")), config, hoje, hoje_por_t)
        alvos[str(i["ID"])] = a.isoformat() if a else None
    pis = {}
    for p in store_.read_objects("Piscina"):
        a = recalcular.alvo_piscina(p, config)
        pis[str(p["ID"])] = a.isoformat() if a else None
    gerar = set()
    horizonte = int(config.get("DiasAntecedenciaGeracao") or 30)
    for off in range(horizonte + 1):
        dia = hoje + timedelta(days=off)
        for t in tarefas:
            if str(t.get("Ativa", "")).strip().upper() == "TRUE" and instancias.ocorre_nesta_data(
                    t, dia, instancias.DIAS_SEMANA[(dia.weekday() + 1) % 7], dia.day):
                gerar.add((str(t["ID"]), dia.isoformat()))
    return alvos, pis, gerar


def verificar(d, tarefas, inst, cfg, pisc, aud):
    c = _common()
    import store
    st = store.SqliteStore(db.db_path("dados"))
    erros = []
    hoje = c.now_local().date()
    a_f, p_f, g_f = _plano(d["_sc"], hoje)
    a_b, p_b, g_b = _plano(st, hoje)
    # só as ocorrências/tarefas efetivamente importadas contam para a comparação
    ids_bd = {str(r["ID"]) for r in st.read_objects("Instancias")}
    dif_a = {k: (a_f.get(k), a_b.get(k)) for k in ids_bd if a_f.get(k) != a_b.get(k)}
    if dif_a:
        erros.append(f"alvos de notificação diferentes em {len(dif_a)} ocorrência(s): {dict(list(dif_a.items())[:5])}")
    if p_f != p_b:
        erros.append(f"alvos da piscina diferentes: {({k: (p_f.get(k), p_b.get(k)) for k in set(p_f) | set(p_b) if p_f.get(k) != p_b.get(k)})}")
    tarefas_bd = {str(t["ID"]) for t in st.read_objects("Tarefas")}
    g_f = {(t, dia) for t, dia in g_f if t in tarefas_bd}
    if g_f != g_b:
        erros.append(f"o gerador criaria coisas diferentes: só folha={sorted(g_f - g_b)[:5]} só bd={sorted(g_b - g_f)[:5]}")
    conn = db.connect()
    n = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
         for t in ("tarefas_tarefas", "tarefas_instancias", "tarefas_config", "tarefas_piscina", "tarefas_auditoria")}
    esperado = {"tarefas_tarefas": len(tarefas), "tarefas_instancias": len(inst), "tarefas_config": len(cfg),
                "tarefas_piscina": len(pisc), "tarefas_auditoria": len(aud)}
    if n != esperado:
        erros.append(f"contagens: bd={n} esperado={esperado}")
    ic = conn.execute("PRAGMA integrity_check").fetchone()[0]
    conn.close()
    print(f"\nVerificação: {len(a_b)} alvos de ocorrências, {len(p_b)} da piscina e {len(g_b)} geráveis vs a folha | contagens {n} | integrity_check={ic}")
    for e in erros:
        print(f"  ERRO: {e}")
    print("VERIFICAÇÃO " + ("OK" if not erros and ic == "ok" else "FALHOU"))
    return 0 if not erros else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
