import pytest

from pulse import actions, db
from pulse.accounts import ContaErro
from pulse.clients.dados import DadosClient
from tests.conftest import FalsoDados
from tests.test_actions import AGORA, EMAIL


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "teste-f.db"); db.migrate(c)
    yield c
    c.close()


def correr(conn, dados_falso, nome, params, **kw):
    return actions.executar(conn, actions.Contexto(DadosClient(dados_falso, FalsoDados.CHAVE), EMAIL, AGORA), nome, params, **kw)


def test_criar_traduz_para_o_formato_do_modulo_com_cid(conn, dados_falso):
    correr(conn, dados_falso, "financas.criar", {"tipo": "despesa", "descricao": " Luz ", "valor": 45.678, "categoriaId": 3,
                                                 "dataVencimento": "2026-10-05", "recorrente": True, "cid": "abcdefgh-1"})
    assert FalsoDados.escritas == [("POST", "/financas/lancamentos", {"tipo": "despesa", "descricao": "Luz", "valor": 45.68, "categoria_id": 3,
                                                                     "data_vencimento": "2026-10-05", "data_pagamento": None, "recorrente": True, "cid": "abcdefgh-1"}, EMAIL)]


def test_criar_recusa_valor_zero_e_campos_desconhecidos(conn, dados_falso):
    base = {"tipo": "despesa", "descricao": "x", "valor": 1, "categoriaId": 1, "dataVencimento": "2026-10-05"}
    for mau in ({**base, "valor": 0}, {**base, "valor": float("nan")}, {**base, "extra": 1}, {**base, "tipo": "outro"}):
        with pytest.raises(ContaErro) as e:
            correr(conn, dados_falso, "financas.criar", mau)
        assert e.value.codigo == "parametros_invalidos"
    assert FalsoDados.escritas == []


def test_editar_envia_so_os_campos_indicados_e_anula_o_pagamento_com_null(conn, dados_falso):
    correr(conn, dados_falso, "financas.editar", {"lancamento": 7, "valor": 50, "dataPagamento": None})
    assert FalsoDados.escritas == [("PUT", "/financas/lancamentos/7", {"valor": 50.0, "data_pagamento": None}, EMAIL)]
    FalsoDados.escritas.clear()
    correr(conn, dados_falso, "financas.editar", {"lancamento": 7, "descricao": "Água"})
    assert FalsoDados.escritas[0][2] == {"descricao": "Água"}
    with pytest.raises(ContaErro):
        correr(conn, dados_falso, "financas.editar", {"lancamento": 7})


def test_apagar_e_sensivel_e_devolve_o_lancamento(conn, dados_falso):
    FalsoDados.respostas["DELETE /financas/lancamentos/7"] = (200, {"id": 7, "descricao": "Luz"})
    with pytest.raises(ContaErro) as e:
        correr(conn, dados_falso, "financas.apagar", {"lancamento": 7})
    assert e.value.codigo == "confirmacao_necessaria" and FalsoDados.escritas == []
    assert correr(conn, dados_falso, "financas.apagar", {"lancamento": 7}, confirmado=True)["descricao"] == "Luz"


def test_preparar_mes_e_categorias_e_lembretes(conn, dados_falso):
    correr(conn, dados_falso, "financas.preparar_mes", {"mes": "2026-10"})
    correr(conn, dados_falso, "financas.categoria_criar", {"nome": "Ginásio"})
    correr(conn, dados_falso, "financas.categoria_editar", {"categoria": 4, "cor": "#112233"})
    correr(conn, dados_falso, "financas.categoria_eliminar", {"categoria": 4}, confirmado=True)
    correr(conn, dados_falso, "financas.lembrete_criar", {"titulo": "IRS", "data": "2026-10-20", "hora": "09:00", "repeticao": "mensal"})
    correr(conn, dados_falso, "financas.lembrete_editar", {"lembrete": 2, "ativo": False})
    correr(conn, dados_falso, "financas.lembrete_eliminar", {"lembrete": 2}, confirmado=True)
    assert [(m, c, b) for m, c, b, _ in FalsoDados.escritas] == [
        ("POST", "/financas/meses/2026-10/preparar", None), ("POST", "/financas/categorias", {"nome": "Ginásio"}),
        ("PUT", "/financas/categorias/4", {"cor": "#112233"}), ("DELETE", "/financas/categorias/4", None),
        ("POST", "/financas/lembretes", {"titulo": "IRS", "nota": "", "data": "2026-10-20", "hora": "09:00", "repeticao": "mensal"}),
        ("PUT", "/financas/lembretes/2", {"ativo": False}), ("DELETE", "/financas/lembretes/2", None)]


def test_mes_invalido_e_cor_invalida_sao_recusados(conn, dados_falso):
    for nome, p in (("financas.preparar_mes", {"mes": "2026-13"}), ("financas.categoria_criar", {"nome": "x", "cor": "vermelho"})):
        with pytest.raises(ContaErro):
            correr(conn, dados_falso, nome, p)
