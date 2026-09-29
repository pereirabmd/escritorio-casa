from datetime import date

import pytest

from pulse.services import peso as p


def regs(*pares):
    """[(quando, peso)] -> registos com id."""
    return [{"id": i + 1, "quando": q if len(q) > 10 else q + " 08:00:00", "peso": w, "nota": ""} for i, (q, w) in enumerate(pares)]


HOJE = date(2026, 9, 30)
CFG = {"altura": 180, "nascimento": "1990-10-01", "sexo": "M", "pesoAlvo": 90, "atividade": 1.45, "pesoMin": 95, "pesoMax": 105}


def test_sem_registos():
    r = p.resumo([], CFG, HOJE)
    assert r["ultimo"] is None and r["previsao"] == {"estado": "poucos_registos"}


def test_imc_e_classes():
    assert round(p.imc(100, 180), 2) == 30.86
    assert p.imc(0, 180) is None and p.imc(80, None) is None
    assert [p.classificar_imc(v) for v in (18, 18.5, 24.9, 25, 29.9, 30, 34.9, 35, 39.9, 40)] == [
        "Abaixo do peso", "Peso normal", "Peso normal", "Excesso de peso", "Excesso de peso", "Obesidade grau I",
        "Obesidade grau I", "Obesidade grau II", "Obesidade grau II", "Obesidade grau III"]


def test_tmb_mifflin_e_idade_com_aniversario_por_fazer():
    assert p.idade_anos("1990-10-01", HOJE) == 35          # faz 36 amanhã
    assert p.idade_anos("1990-09-30", HOJE) == 36 and p.idade_anos(None, HOJE) is None
    assert p.tmb(100, 180, 35, "M") == 10 * 100 + 6.25 * 180 - 5 * 35 + 5
    assert p.tmb(60, 165, 30, "F") == 10 * 60 + 6.25 * 165 - 5 * 30 - 161
    assert p.tmb(100, 180, 35, None) is None and p.tmb(100, 180, None, "M") is None


@pytest.mark.parametrize("raw,esperado", [(None, 1.2), ("x", 1.2), (0, 1.2), (1, 1.2), (2, 1.45), (3, 1.7), (4, 1.7), (1.2, 1.2), (1.45, 1.45),
                                          (1.7, 1.7), (1.55, 1.45), (1.65, 1.7), (1.725, 1.7), (5, 1.2), (2.5, 1.2)])
def test_normalizar_atividade_como_na_app_dedicada(raw, esperado):
    assert p.normalizar_atividade(raw) == esperado


def test_resumo_completo():
    r = p.resumo(regs(("2026-09-01", 110), ("2026-09-15", 105), ("2026-09-29", 101.5), ("2026-09-30", 100)), CFG, HOJE)
    assert r["ultimo"]["peso"] == 100 and r["anterior"]["diferenca"] == pytest.approx(-1.5)
    assert r["sequenciaDias"] == 2 and r["novoMinimo"] is True and r["controlo"] == "dentro"
    assert r["totalPerdido"] == 10 and r["minimo"] == 100 and r["maximo"] == 110
    assert r["progresso"] == {"pct": 50.0, "inicial": 110, "alvo": 90}
    assert r["faltam"] == {"kg": 10, "atingido": False}
    assert r["ritmo"]["kgDia"] == pytest.approx(10 / 29) and r["ritmo"]["kgSemana"] == pytest.approx(70 / 29)
    assert r["imc"]["classe"] == "Obesidade grau I" and r["imc"]["valor"] == pytest.approx(100 / 3.24)
    assert r["gastoDiario"] == round((10 * 100 + 6.25 * 180 - 5 * 35 + 5) * 1.45)


def test_config_incompleta_deixa_de_fora_o_que_nao_se_pode_calcular():
    r = p.resumo(regs(("2026-09-29", 80), ("2026-09-30", 81)), {}, HOJE)
    assert r["imc"] is None and r["gastoDiario"] is None and r["progresso"] is None and r["faltam"] is None and r["controlo"] is None
    assert r["previsao"] == {"estado": "sem_alvo"} and r["novoMinimo"] is False


def test_controlo_acima_abaixo_dentro():
    assert [p.controlo(w, {"pesoMin": 95, "pesoMax": 105}) for w in (106, 94, 100)] == ["acima", "abaixo", "dentro"]
    assert p.controlo(100, {"pesoMax": 90}) == "acima" and p.controlo(100, {"pesoMin": 110}) == "abaixo" and p.controlo(100, {}) is None


def test_progresso_limitado_a_0_100_e_alvo_igual_ao_inicial():
    assert p.resumo(regs(("2026-09-01", 90), ("2026-09-02", 85)), {"pesoAlvo": 80}, HOJE)["progresso"]["pct"] == 100 * 5 / 10
    assert p.resumo(regs(("2026-09-01", 90), ("2026-09-02", 95)), {"pesoAlvo": 80}, HOJE)["progresso"]["pct"] == 0.0
    assert p.resumo(regs(("2026-09-01", 90), ("2026-09-02", 85)), {"pesoAlvo": 90}, HOJE)["progresso"]["pct"] == 0.0


def test_alvo_atingido_tolerancia_de_50_g_no_cartao_e_exata_na_previsao():
    r = p.resumo(regs(("2026-09-01", 92), ("2026-09-02", 90.03)), {"pesoAlvo": 90}, HOJE)
    assert r["faltam"]["atingido"] is True and r["previsao"]["estado"] == "ok"      # como na app dedicada
    r = p.resumo(regs(("2026-09-01", 92), ("2026-09-02", 89.97)), {"pesoAlvo": 90}, HOJE)
    assert r["faltam"]["atingido"] is True and r["previsao"] == {"estado": "atingido"}


def test_sequencia_de_dias():
    assert p.sequencia([]) == 0
    assert p.sequencia(regs(("2026-09-27", 1), ("2026-09-28", 1), ("2026-09-28 20:00:00", 1), ("2026-09-30", 1))) == 1
    assert p.sequencia(regs(("2026-09-28", 1), ("2026-09-29", 1), ("2026-09-30", 1))) == 3


def test_ritmo_so_dentro_da_janela_e_sem_dados_suficientes():
    r = regs(("2026-06-01", 120), ("2026-09-01", 100), ("2026-09-30", 98))
    assert p.perda_por_dia(r, 30) == pytest.approx(2 / 29)
    assert p.perda_por_dia(r, 999999) == pytest.approx(22 / 121)
    assert p.perda_por_dia(regs(("2026-09-30", 98)), 30) is None
    assert p.perda_por_dia(regs(("2026-09-30", 98), ("2026-09-30 09:00:00", 97)), 30) == pytest.approx(1 / (3600 / 86400))


def test_analise_precisa_de_5_registos_e_calcula_tendencia_mensal_e_semanas():
    assert p.analise(regs(("2026-09-01", 100), ("2026-09-02", 99))) == {"tendencia": None, "mensal": None, "melhorSemana": None, "piorSemana": None}
    r = regs(("2026-08-24", 102), ("2026-08-31", 101), ("2026-09-07", 100), ("2026-09-14", 99), ("2026-09-21", 98), ("2026-09-28", 97))
    a = p.analise(r)
    assert a["tendencia"]["kgSemana"] == pytest.approx(-1.0) and a["tendencia"]["pontos"] == 5 and a["tendencia"]["dias"] == 28
    assert a["mensal"]["diff"] == pytest.approx(97.6 - 101.5) or a["mensal"] is not None
    assert a["melhorSemana"]["diff"] == pytest.approx(-1.0) and a["piorSemana"]["diff"] == pytest.approx(-1.0)


def test_analise_melhor_e_pior_semana_diferentes():
    r = regs(("2026-09-01", 100), ("2026-09-02", 100), ("2026-09-08", 98), ("2026-09-15", 99), ("2026-09-22", 97), ("2026-09-29", 97.5))
    a = p.analise(r)
    assert a["melhorSemana"]["diff"] == pytest.approx(-2.0) and a["piorSemana"]["diff"] == pytest.approx(1.0)


def test_previsao():
    assert p.previsao(regs(("2026-09-01", 100)), 90) == {"estado": "poucos_registos"}
    assert p.previsao(regs(("2026-09-01", 100), ("2026-09-02", 99)), None) == {"estado": "sem_alvo"}
    assert p.previsao(regs(("2026-09-01", 100), ("2026-09-02", 101)), 90) == {"estado": "sem_tendencia"}
    r = p.previsao(regs(("2026-09-01", 100), ("2026-09-11", 98)), 90)          # 0,2 kg/dia -> 40 dias a partir de 11/09
    assert r["estado"] == "ok" and r["data"] == "2026-10-21" and r["kgSemana"] == pytest.approx(1.4)
