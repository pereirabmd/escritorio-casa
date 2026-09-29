from datetime import date

from pulse.services import tarefas as t

HOJE = date(2026, 9, 30)


def tarefa(id, nome="X", cat="Casa", rec="Diaria", ativa=True, prio="Media", hora="", dias="", dia_mes=None, pessoa="Bruno"):
    return {"id": id, "nome": nome, "categoria": cat, "recorrencia": rec, "diasSemana": dias, "diaMes": dia_mes, "horaNotificacao": hora,
            "pessoaPadrao": pessoa, "ativa": ativa, "prioridade": prio, "icone": "", "rotacaoPessoas": "", "dependeDe": ""}


def inst(id, tid, data, estado="Pendente", pessoa="Bruno", concl=""):
    return {"id": id, "tarefaId": tid, "data": data, "pessoa": pessoa, "estado": estado, "dataConclusao": concl, "notificacaoEnviada": False}


CONFIG = [{"chave": "Pessoa1_Nome", "valor": "Bruno"}, {"chave": "Pessoa1_Email", "valor": "PereiraBMD@gmail.com"},
          {"chave": "Pessoa2_Nome", "valor": "Camila"}, {"chave": "Pessoa2_Email", "valor": "camila@exemplo.pt"}, {"chave": "Pessoa3_Nome", "valor": ""},
          {"chave": "Categoria2", "valor": "Limpeza"}, {"chave": "Categoria1", "valor": "Casa"}, {"chave": "HoraPadrao", "valor": "09:30"},
          {"chave": "Pessoa1_NtfyPasswordEnc", "valor": "segredo"}]


def test_pessoas_categorias_e_pessoa_do_utilizador():
    cfg = t.config_de(CONFIG)
    assert [p["nome"] for p in t.pessoas(cfg)] == ["Bruno", "Camila"]
    assert t.categorias(cfg) == ["Casa", "Limpeza"]
    assert t.pessoa_do_utilizador(cfg, "pereirabmd@gmail.com") == "Bruno" and t.pessoa_do_utilizador(cfg, "outro@x.pt") is None


def test_resumo_de_recorrencia():
    assert t.resumo_recorrencia(tarefa("T1", rec="Diaria")) == "Todos os dias"
    assert t.resumo_recorrencia(tarefa("T1", rec="Semanal", dias="Seg,Qua")) == "Seg,Qua"
    assert t.resumo_recorrencia(tarefa("T1", rec="Mensal", dia_mes=5)) == "Dia 5 de cada mês"
    assert t.resumo_recorrencia(tarefa("T1", rec="Trimestral", dias="2026-10-01")) == "A cada 3 meses, desde 01/10/2026"
    assert t.resumo_recorrencia(tarefa("T1", rec="Semestral", dias="x")) == "A cada 6 meses, desde ?"
    assert t.resumo_recorrencia(tarefa("T1", rec="Pontual", dias="2026-10-05")) == "Uma vez, 05/10/2026"


def test_atrasada_so_a_mais_recente_de_cada_tarefa():
    r = t.ultima_atrasada_por_tarefa([inst("I1", "T1", "2026-09-25", "Atrasada"), inst("I2", "T1", "2026-09-27", "Atrasada"), inst("I3", "T2", "2026-09-20", "Atrasada")])
    assert sorted(i["id"] for i in r) == ["I2", "I3"]


def test_visao_listas_ordem_e_filtros():
    dados = {"tarefas": [tarefa("T1", "Limpar WC", hora="09:00"), tarefa("T2", "Lixo", prio="Alta"), tarefa("T3", "Desativada", ativa=False)], "config": CONFIG,
             "instancias": [inst("I1", "T1", "2026-09-30"), inst("I2", "T2", "2026-09-30"), inst("I3", "T2", "2026-09-30", "Saltada"),
                            inst("I4", "T1", "2026-09-30", "Feita", concl="2026-09-30 08:00"), inst("I5", "T1", "2026-09-28", "Atrasada"), inst("I6", "T1", "2026-09-29", "Atrasada"),
                            inst("I7", "T2", "2026-10-01"), inst("I8", "T2", "2026-10-01", "Saltada"), inst("I9", "T3", "2026-09-30")]}
    v = t.visao(dados, HOJE, "pereirabmd@gmail.com")
    assert v["pessoa"] == "Bruno" and v["pessoas"] == ["Bruno", "Camila"] and v["horaPadrao"] == "09:30"
    assert [i["id"] for i in v["hoje"]] == ["I1", "I2", "I3"]                       # 09:00, depois 09:30 (padrão) por prioridade; a saltada continua a aparecer
    assert v["hoje"][1]["hora"] == "09:30" and [i["id"] for i in v["feitas"]] == ["I4"] and v["feitas"][0]["dataConclusao"] == "2026-09-30 08:00"
    assert [i["id"] for i in v["atrasadas"]] == ["I6"]                              # só a mais recente
    assert [i["id"] for i in v["amanha"]] == ["I7"]                                 # sem feitas nem saltadas
    assert [x["id"] for x in v["tarefas"]] == ["T1", "T2"] and v["tarefas"][0]["resumo"] == "Todos os dias"      # só as ativas


def test_segredos_da_config_nunca_saem():
    v = t.visao({"tarefas": [], "instancias": [], "config": CONFIG}, HOJE, "x@y.pt")
    assert "segredo" not in str(v) and "Ntfy" not in str(v)
