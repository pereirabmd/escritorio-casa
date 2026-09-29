from datetime import date

import pytest

from pulse.services import rto


def nota(ini=None, fim=None, cat="", desc="", id=1):
    return {"id": id, "dataInicio": ini, "dataFim": fim, "categoria": cat, "descricao": desc}


def test_pascoa_e_feriados_moveis():
    assert rto.pascoa(2026) == date(2026, 4, 5) and rto.pascoa(2025) == date(2025, 4, 20) and rto.pascoa(2024) == date(2024, 3, 31)
    f = rto.feriados(2026)
    assert f["2026-04-03"] == "Sexta-feira Santa" and f["2026-06-04"] == "Corpo de Deus" and f["2026-12-25"] == "Natal"
    assert len(f) == 13 and f["2026-06-13"] == "Santo António (Lisboa)"


@pytest.mark.parametrize("cat,esperado", [("Férias", "ferias"), ("ferias", "ferias"), ("FÉRIAS de verão", "ferias"), ("Astreinte", "astreinte"),
                                          ("astrainte", "astreinte"), ("RTO Suspensão", "suspensao"), ("suspensao", "suspensao"),
                                          ("Validação", None), ("", None), ("Férias suspensas", "suspensao")])
def test_categorias_tolerantes(cat, esperado):
    assert rto.categoria_de(nota(cat=cat)) == esperado


def test_classificar_ferias_astreinte_e_suspensao_com_fins_de_semana():
    # 2026-09-25 sexta .. 2026-09-28 segunda
    c = rto.classificar([nota("2026-09-25", "2026-09-28", "Férias"), nota("2026-09-26", "2026-09-27", "Astreinte", id=2),
                         nota("2026-10-01", None, "Suspensão", id=3), nota("2026-10-05", None, "Validação", id=4)])
    assert c["ferias"] == {"2026-09-25", "2026-09-26", "2026-09-27", "2026-09-28"}          # inclui o fim de semana
    assert c["marcas"] == {"2026-09-25": "F", "2026-09-28": "F", "2026-09-26": "A", "2026-09-27": "A"}   # F não aparece ao fim de semana; A sim
    assert c["astreinte"] == {"2026-09-26", "2026-09-27"} and c["suspensao"] == {"2026-10-01"}


def test_nota_so_com_uma_data_ou_intervalo_invalido():
    c = rto.classificar([nota(None, "2026-03-03", "Férias"), nota("2026-03-05", None, "Férias", id=2), nota("2026-03-10", "2026-03-01", "Férias", id=3)])
    assert c["ferias"] == {"2026-03-03", "2026-03-05"}
    assert rto.intervalo(nota("2000-01-01", "2030-01-01", "Férias")) is None                 # intervalo absurdo


def test_totais_com_ferias_astreinte_suspensao_e_quota_pro_rata():
    dias = {"2026-01-05": "C", "2026-01-06": "T", "2026-02-02": "C", "2026-02-03": "C", "2026-03-02": "C", "2026-03-09": "C", "2025-12-30": "C"}
    cls = rto.classificar([nota("2026-02-03", "2026-02-03", "Férias"), nota("2026-03-02", "2026-03-02", "Suspensão", id=2),
                           nota("2026-01-20", "2026-01-21", "Astreinte", id=3), nota("2026-03-02", "2026-03-02", "Astreinte", id=4)])
    t = rto.totais(dias, cls, 2026, date(2026, 7, 1))
    assert (t["T"], t["C"]) == (1, 4)                        # 02/02, 02/03 (suspensa mas conta em C), 09/03, 05/01; férias e 2025 fora
    assert t["CCondicional"] == 4 - 1 - 2                    # menos a suspensa, menos 2 créditos de astreinte (a de 02/03 não conta: suspensão)
    assert t["creditosAstreinte"] == 2 and t["decorridos"] == 182 and t["diasAno"] == 365
    assert t["quotaProRata"] == 59.8 and t["saldo"] == 55.8 and t["saldoCondicional"] == 59.8 - 1


def test_quota_antes_e_depois_do_ano_e_ano_bissexto():
    assert rto.totais({}, rto.classificar([]), 2026, date(2025, 12, 31))["quotaProRata"] == 0.0
    assert rto.totais({}, rto.classificar([]), 2026, date(2027, 1, 1))["quotaProRata"] == 120.0
    t = rto.totais({}, rto.classificar([]), 2024, date(2024, 12, 31))
    assert t["diasAno"] == 366 and t["decorridos"] == 366 and t["quotaProRata"] == 120.0


def test_arredondamento_como_o_javascript():
    assert rto._arred1(0.25) == 0.3 and rto._arred1(2.35) == 2.4 and rto._arred1(-0.25) == -0.2


def test_mensal_ignora_ferias_e_outros_anos():
    m = rto.mensal({"2026-01-05": "T", "2026-01-06": "C", "2026-01-07": "C", "2026-02-02": "T", "2025-01-01": "T"}, {"2026-01-07"}, 2026)
    assert m[0] == {"t": 1, "c": 1} and m[1] == {"t": 1, "c": 0} and m[2] == {"t": 0, "c": 0} and len(m) == 12


@pytest.mark.parametrize("hoje,dias,notas,esperado", [
    (date(2026, 9, 30), {"2026-09-30": "T"}, [], {"estado": "escritorio", "astreinte": False}),
    (date(2026, 9, 30), {"2026-09-30": "C"}, [nota("2026-09-30", None, "Astreinte")], {"estado": "casa", "astreinte": True}),
    (date(2026, 9, 30), {}, [nota("2026-09-28", "2026-10-02", "Férias")], {"estado": "ferias", "astreinte": False}),
    (date(2026, 12, 25), {}, [], {"estado": "feriado", "nome": "Natal", "astreinte": False}),
    (date(2026, 9, 27), {}, [], {"estado": "fim_de_semana", "astreinte": False}),
    (date(2026, 9, 27), {}, [nota("2026-09-27", None, "Astreinte")], {"estado": "fim_de_semana", "astreinte": True}),
    (date(2026, 9, 30), {}, [nota("2026-09-30", None, "Astreinte")], {"estado": "astreinte", "astreinte": True}),
    (date(2026, 9, 30), {}, [], {"estado": "por_definir", "astreinte": False}),
])
def test_estado_de_hoje(hoje, dias, notas, esperado):
    assert rto.estado_hoje(dias, rto.classificar(notas), hoje) == esperado


def test_proxima_mudanca_feriado_ferias_e_nada():
    c = rto.classificar([nota("2026-10-20", "2026-10-22", "Férias")])
    assert rto.proxima_mudanca(c, date(2026, 10, 1)) == {"tipo": "feriado", "dias": 4, "nome": "Implantação da República", "data": "2026-10-05"}
    assert rto.proxima_mudanca(c, date(2026, 10, 6)) == {"tipo": "ferias", "dias": 14, "data": "2026-10-20"}
    assert rto.proxima_mudanca(c, date(2026, 10, 21)) == {"tipo": "feriado", "dias": 11, "nome": "Todos os Santos", "data": "2026-11-01"}   # já em férias: ignora as férias
    assert rto.proxima_mudanca(rto.classificar([]), date(2026, 8, 20)) == {"tipo": "feriado", "dias": 46, "nome": "Implantação da República", "data": "2026-10-05"}
    assert rto.proxima_mudanca(rto.classificar([]), date(2026, 5, 2)) == {"tipo": "feriado", "dias": 33, "nome": "Corpo de Deus", "data": "2026-06-04"}


def test_dias_uteis():
    assert rto.dia_util_anterior(date(2026, 9, 28)) == date(2026, 9, 25)      # segunda -> sexta
    assert rto.dia_util_seguinte(date(2026, 9, 25)) == date(2026, 9, 28)      # sexta -> segunda
    assert rto.dia_util_seguinte(date(2026, 9, 28)) == date(2026, 9, 29)


def test_visao_junta_tudo():
    v = rto.visao({"2026-01-05": "C", "2025-12-01": "T"}, [nota("2026-01-06", "2026-01-06", "Férias")], 2026, date(2026, 9, 30))
    assert v["ano"] == 2026 and v["totais"]["C"] == 1 and v["dezembroAnterior"] == {"t": 1, "c": 0}
    assert v["ferias"] == ["2026-01-06"] and v["marcasNotas"] == {"2026-01-06": "F"} and v["hoje"]["estado"] == "por_definir"
    assert v["feriados"]["2026-04-03"] == "Sexta-feira Santa"
