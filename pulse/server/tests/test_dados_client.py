import pytest

from pulse.clients.dados import DadosClient, ErroDoModulo, ModuloIndisponivel
from tests.conftest import FalsoDados


def test_envia_chave_e_utilizador(dados_falso):
    c = DadosClient(dados_falso, FalsoDados.CHAVE)
    status, corpo = c.pedir("GET", "/peso/registos", "eu@exemplo.pt", query={"desde": "2026-09-01"})
    assert (status, corpo) == (200, {"ok": True})
    assert FalsoDados.pedidos == [("/peso/registos?desde=2026-09-01", "eu@exemplo.pt")]


def test_4xx_do_modulo_mantem_codigo_e_mensagem(dados_falso):
    with pytest.raises(ErroDoModulo) as e:
        DadosClient(dados_falso, FalsoDados.CHAVE).pedir("GET", "/conflito", "eu@exemplo.pt")
    assert (e.value.status, e.value.codigo, e.value.mensagem) == (409, "conflito", "já existe")


def test_5xx_e_rede_sao_modulo_indisponivel(dados_falso):
    with pytest.raises(ModuloIndisponivel):
        DadosClient(dados_falso, FalsoDados.CHAVE).pedir("GET", "/avaria", "eu@exemplo.pt")
    with pytest.raises(ModuloIndisponivel):
        DadosClient("http://127.0.0.1:9", FalsoDados.CHAVE, timeout=1).pedir("GET", "/x", "eu@exemplo.pt")


def test_sem_chave_configurada_nem_tenta(dados_falso):
    with pytest.raises(ModuloIndisponivel):
        DadosClient(dados_falso, "").pedir("GET", "/peso/registos", "eu@exemplo.pt")
    assert FalsoDados.pedidos == []


def test_chave_errada_e_401_do_modulo(dados_falso):
    with pytest.raises(ErroDoModulo) as e:
        DadosClient(dados_falso, "x" * 40).pedir("GET", "/peso/registos", "eu@exemplo.pt")
    assert e.value.status == 401


def test_saude(dados_falso):
    assert DadosClient(dados_falso, "").saude() is True
    assert DadosClient("http://127.0.0.1:9", "").saude() is False
