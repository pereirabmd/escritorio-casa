"""Regras puras: Calendário, Horário, Piscina e o resumo por pessoa da Config."""
from datetime import date, datetime

import pytest

from pulse.services import horario, piscina, tarefas

HOJE = date(2026, 9, 30)


def T(i, **k):
    return {"id": i, "nome": f"Tarefa {i}", "categoria": "Limpeza", "recorrencia": "Diaria", "diasSemana": "", "diaMes": None, "horaNotificacao": "",
            "pessoaPadrao": "Bruno", "ativa": True, "prioridade": "Media", **k}


def I(i, t, d, estado="Pendente", pessoa="Bruno", concl=""):
    return {"id": i, "tarefaId": t, "data": d, "pessoa": pessoa, "estado": estado, "dataConclusao": concl}


# --- calendário -------------------------------------------------------------------------------------------------------

def test_feriados_da_app_dedicada():
    f = tarefas.feriados(2026)
    assert f["2026-04-03"] == "Sexta-feira Santa" and f["2026-04-05"] == "Páscoa" and f["2026-06-04"] == "Corpo de Deus" and f["2026-12-25"] == "Natal"
    assert "2026-06-13" not in f and len(f) == 13            # sem o feriado municipal do RTO


def test_calendario_um_dia_por_data_com_feriado_e_ocorrencias_ordenadas():
    dados = {"tarefas": [T("T1", prioridade="Baixa"), T("T2", prioridade="Alta"), T("T3", ativa=False)], "config": [],
             "instancias": [I("I1", "T1", "2026-10-05"), I("I2", "T2", "2026-10-05"), I("I3", "T3", "2026-10-05"), I("I4", "T1", "2026-10-31")]}
    r = tarefas.calendario(dados, date(2026, 10, 1), date(2026, 10, 31), HOJE)
    assert [d["data"] for d in r["dias"]][:2] == ["2026-10-01", "2026-10-02"] and len(r["dias"]) == 31
    d5 = next(d for d in r["dias"] if d["data"] == "2026-10-05")
    assert d5["feriado"] == "Implantação da República" and [i["id"] for i in d5["itens"]] == ["I2", "I1"]      # a inativa não aparece; Alta antes de Baixa
    assert next(d for d in r["dias"] if d["data"] == "2026-10-31")["itens"][0]["id"] == "I4"


def test_calendario_intervalo_atravessa_o_ano_e_e_limitado():
    r = tarefas.calendario({"tarefas": [], "instancias": [], "config": []}, date(2026, 12, 28), date(2027, 1, 3), HOJE)
    assert {d["data"]: d["feriado"] for d in r["dias"] if d["feriado"]} == {"2027-01-01": "Ano Novo"}
    with pytest.raises(ValueError):
        tarefas.calendario({}, date(2026, 1, 1), date(2026, 12, 31), HOJE)
    with pytest.raises(ValueError):
        tarefas.calendario({}, date(2026, 10, 2), date(2026, 10, 1), HOJE)


# --- horário ----------------------------------------------------------------------------------------------------------

def aula(dia, ini, fim, disc, sala="", aluno="Ana", ano="2026/2027"):
    return {"id": 1, "aluno": aluno, "anoLetivo": ano, "diaSemana": dia, "horaInicio": ini, "horaFim": fim, "disciplina": disc, "sala": sala}


def test_horario_indisponivel_e_vazio():
    assert horario.visao(None, {}, HOJE)["disponivel"] is False
    v = horario.visao([], {}, HOJE)
    assert v["disponivel"] and v["alunos"] == [] and v["avisos"] == {"ativos": True, "minutos": 30}


def test_horario_dia_com_turma_dividida_saida_e_aviso():
    aulas = [aula(3, "08:15", "09:45", "Mat", "B1"), aula(3, "10:00", "11:30", "Fís", "L1"), aula(3, "10:00", "11:30", "Quím", "L2"),
             aula(3, "16:00", "17:00", "E.M.R."), aula(1, "09:00", "10:00", "Pt")]
    a = horario.visao(aulas, {"HorarioAvisoMinutos": "20"}, HOJE)["alunos"][0]
    assert a["nome"] == "Ana" and [d["dia"] for d in a["dias"]] == [1, 3]
    qua = a["dias"][1]
    assert (qua["entra"], qua["sai"], qua["aviso"], qua["totalAulas"]) == ("08:15", "11:30", "11:10", 4)     # a E.M.R. não conta como última aula
    assert [s["dividida"] for s in qua["slots"]] == [False, True, False] and [s["ultima"] for s in qua["slots"]] == [False, True, False]


def test_horario_escolhe_o_ano_letivo_em_curso_e_avisos_pausados():
    aulas = [aula(1, "09:00", "10:00", "Antigo", ano="2025/2026"), aula(1, "09:00", "10:00", "Novo", ano="2026/2027")]
    v = horario.visao(aulas, {"HorarioAvisos": "false"}, HOJE)
    assert v["anoLetivo"] == "2026/2027" and v["alunos"][0]["dias"][0]["slots"][0]["aulas"][0]["disciplina"] == "Novo" and v["avisos"]["ativos"] is False
    assert horario.visao(aulas, {}, date(2026, 8, 15))["anoLetivo"] == "2026/2027"        # verão: fica o último ano conhecido


# --- piscina ----------------------------------------------------------------------------------------------------------

def test_estacao_pela_config():
    assert piscina.estacao({}, date(2026, 6, 1)) == "quente" and piscina.estacao({}, date(2026, 10, 1)) == "fria"
    assert piscina.estacao({"PiscinaMesFimQuente": "10"}, date(2026, 10, 1)) == "quente"


def test_proxima_data_e_alternancia_de_intervalo():
    item = piscina.POR_ID["P02"]                       # quente: 3 e 4 dias alternados
    a = piscina.novo_estado(item, "quente", {"usarIntervaloLongo": False}, HOJE)
    assert (a["proximaData"], a["usarIntervaloLongo"]) == ("2026-10-04", True)      # alt (4) primeiro
    b = piscina.novo_estado(item, "quente", {"usarIntervaloLongo": True}, HOJE)
    assert (b["proximaData"], b["usarIntervaloLongo"]) == ("2026-10-03", False)
    fixa = piscina.novo_estado(piscina.POR_ID["P01"], "fria", None, HOJE)
    assert (fixa["proximaData"], fixa["usarIntervaloLongo"]) == ("2026-10-14", False)
    log = piscina.novo_estado(piscina.POR_ID["P13"], "quente", None, HOJE)
    assert log["proximaData"] is None and log["ultimaData"] == "2026-09-30"


def test_catalogo_em_falta_e_estados():
    assert [i["id"] for i in piscina.em_falta([{"id": "P01"}])][:2] == ["P02", "P03"] and len(piscina.em_falta([])) == len(piscina.CATALOGO)
    linhas = [{"id": "P01", "ultimaData": "2026-09-20", "proximaData": "2026-09-27"},          # sugerida no passado, dentro da folga (10 <= 14?)
              {"id": "P04", "ultimaData": "2026-09-01", "proximaData": "2026-09-04"},          # 29 dias > atraso 4 -> atrasada
              {"id": "P05", "ultimaData": "2026-09-27", "proximaData": "2026-09-30"},          # hoje
              {"id": "P06", "ultimaData": "2026-09-29", "proximaData": "2026-10-06"},          # em dia
              {"id": "P13", "ultimaData": "2026-08-01", "proximaData": ""}]
    v = piscina.visao(linhas, {}, HOJE)
    est = {c["id"]: c for c in v["periodicas"] + v["outras"]}
    assert v["estacao"] == "quente"
    assert (est["P04"]["estado"], est["P04"]["diasDesde"]) == ("atrasada", 29)
    assert est["P05"]["estado"] == "hoje" and est["P05"]["sugeridoHoje"] and est["P06"]["estado"] == "ok" and est["P02"]["estado"] == "nunca"
    assert est["P13"]["estado"] == "registo" and est["P13"]["ultima"] == "2026-08-01"
    # nunca registadas primeiro; depois pela próxima data
    ordem = [c["id"] for c in v["periodicas"]]
    feitas = [i for i in ordem if est[i]["ultima"]]
    assert ordem[:len(ordem) - len(feitas)] == [i for i in ordem if not est[i]["ultima"]] and feitas == ["P04", "P01", "P05", "P06"]


# --- config: resumo por pessoa -----------------------------------------------------------------------------------------

def cfg(*nomes):
    return [{"chave": f"Pessoa{i + 1}_Nome", "valor": n} for i, n in enumerate(nomes)]


def test_resumo_conta_os_ultimos_7_dias_e_avisa_desequilibrio():
    agora = datetime(2026, 9, 30, 12, 0)
    feitas = [I(f"I{k}", "T1", "2026-09-28", "Feita", "Bruno", f"2026-09-28 1{k}:00") for k in range(1, 5)]      # 4 do Bruno
    feitas += [I("I9", "T1", "2026-09-29", "Feita", "Camila", "2026-09-29 09:00"), I("I10", "T1", "2026-09-10", "Feita", "Camila", "2026-09-10 09:00")]
    r = tarefas.resumo_pessoas({"config": cfg("Bruno", "Camila"), "instancias": feitas}, agora)
    assert r["pessoas"] == [{"nome": "Bruno", "feitas": 4}, {"nome": "Camila", "feitas": 1}] and r["desequilibrio"] == "Bruno"      # a de 10/09 já não conta
    assert tarefas.resumo_pessoas({"config": cfg("Bruno"), "instancias": feitas}, agora)["desequilibrio"] is None                # uma pessoa só
    assert tarefas.resumo_pessoas({"config": cfg("Bruno", "Camila"), "instancias": feitas[:2]}, agora)["desequilibrio"] is None  # poucas para avisar


def test_preferencias_e_numeracao_de_pessoas():
    p = tarefas.preferencias({"NaoIncomodarInicio": "22:00", "NaoIncomodarFim": "07:00", "HorarioAvisos": "FALSE", "HorarioAvisoMinutos": "x"})
    assert p == {"horaPadrao": "08:00", "naoIncomodarInicio": "22:00", "naoIncomodarFim": "07:00", "horarioAvisos": False, "horarioAvisoMinutos": 30}
    c = tarefas.config_de([{"chave": "Pessoa1_Nome", "valor": "A"}, {"chave": "Pessoa3_Email", "valor": "x@y.z"}])
    assert tarefas.proximo_numero_pessoa(c) == 4 and tarefas.proximo_numero_pessoa({}) == 1 and tarefas.numero_da_pessoa(c, "A") == 1
