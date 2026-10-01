"""Consultas à conta da CP (ADR-075): bilhetes futuros, cancelar e validade do Passe Verde, contra uma CP falsa (sem rede)."""

import base64
import unittest

import _env  # noqa: F401
import consulta_cp
from cp_ticket import CPResponse

VENDA = {"reference": "CP-X", "status": {"code": "CONFIRMED"}, "travelData": {"outwardTrip": [{
    "trainNumber": 723, "departureTime": "19:39", "arrivalTime": "22:02", "service": {"designation": "Intercidades"},
    "seatData": [{"carriageNumber": 22, "seatNumber": 77}]}]}}
VIAGEM = {"saleID": "125951095", "departure": {"designation": "Lisboa Oriente"}, "arrival": {"designation": "Aveiro"}, "travelDate": "2026-10-01T19:39:00", "totalAmount": 0}
ELEGIVEIS = {"operatorData": {"agencyCode": "NETTICKET", "agencyName": "NETTICKET"}, "ticketData": [{"itemType": "TICKET", "itemData": {"documentNumber": "DOC-1"}}]}


class CPFalsa:
    """Responde por (método, caminho-prefixo); regista os pedidos."""
    cp_email = "ele@exemplo.pt"

    def __init__(self, rotas):
        self.rotas, self.pedidos = rotas, []

    def request(self, metodo, caminho, *, api_key, body=None, with_client_id=False, timeout=None, **kw):
        self.pedidos.append((metodo, caminho, body, with_client_id))
        for (m, prefixo), resposta in self.rotas.items():
            if m == metodo and caminho.startswith(prefixo):
                status, corpo = resposta if isinstance(resposta, tuple) else (200, resposta)
                return CPResponse(status=status, body=corpo, text="", date_header=None, sent_at=0, received_at=0, elapsed_ms=0, messages=[])
        raise AssertionError(f"pedido inesperado {metodo} {caminho}")


ROTAS_CANCELAR = {
    ("GET", "/ticketing-api/trips/"): [VIAGEM],
    ("GET", "/ticketing-api/sales/125951095/available-operations"): ["NULLIFY", "REFUND"],
    ("GET", "/ticketing-api/post-sale/refund/available/tickets/125951095"): ELEGIVEIS,
    ("POST", "/ticketing-api/post-sale/refund"): {"refundID": 77},
    ("PUT", "/ticketing-api/post-sale/refund/77"): {"status": {"code": "CONFIRMED"}, "totalRefundAmount": "€ 0,00"},
}


class FuturosTests(unittest.TestCase):
    def test_junta_a_lista_com_o_detalhe_e_nao_expoe_documentos(self):
        cli = CPFalsa({("GET", "/ticketing-api/trips/"): [VIAGEM], ("GET", "/ticketing-api/sales/125951095"): VENDA})
        b = consulta_cp.futuros(cli)["bilhetes"][0]
        self.assertEqual((b["venda"], b["origem"], b["destino"], b["data"], b["hora"], b["comboio"], b["carruagem"], b["lugar"], b["podeCancelar"]),
                         (125951095, "Lisboa Oriente", "Aveiro", "2026-10-01", "19:39", 723, 22, 77, True))
        self.assertNotIn("documentNumber", str(b))
        self.assertIn("filter=FUTURE", cli.pedidos[0][1])

    def test_sem_detalhe_a_viagem_aparece_na_mesma(self):
        cli = CPFalsa({("GET", "/ticketing-api/trips/"): [VIAGEM], ("GET", "/ticketing-api/sales/"): (500, None)})
        b = consulta_cp.futuros(cli)["bilhetes"][0]
        self.assertEqual((b["venda"], b["hora"], b["podeCancelar"]), (125951095, "", False))


class CancelarTests(unittest.TestCase):
    def test_pede_e_confirma_a_devolucao_com_os_documentos_da_cp(self):
        cli = CPFalsa(dict(ROTAS_CANCELAR))
        r = consulta_cp.cancelar(cli, 125951095)
        self.assertEqual((r["estado"], r["venda"]), ("CONFIRMED", 125951095))
        post = next(p for p in cli.pedidos if p[0] == "POST")[2]
        self.assertEqual((post["saleId"], post["tickets"], post["type"], post["username"]), (125951095, ["DOC-1"], "REFUND", "ele@exemplo.pt"))
        self.assertEqual([p[0] for p in cli.pedidos], ["GET", "GET", "GET", "POST", "PUT"])

    def test_aceita_a_lista_de_bilhetes_dentro_de_travelData_como_na_resposta_real(self):
        # resposta real da CP (01/10/2026): `ticketData` vem dentro de `travelData`, não no topo
        rotas = dict(ROTAS_CANCELAR)
        for k, v in rotas.items():
            if isinstance(v, dict) and "ticketData" in v:
                rotas[k] = {"operatorData": v["operatorData"], "travelData": {"ticketData": v["ticketData"]}}
        cli = CPFalsa(rotas)
        r = consulta_cp.cancelar(cli, 125951095)
        self.assertEqual(r["estado"], "CONFIRMED")
        self.assertEqual(next(p for p in cli.pedidos if p[0] == "POST")[2]["tickets"], ["DOC-1"])

    def test_nao_cancela_uma_venda_que_nao_e_futura_desta_conta(self):
        cli = CPFalsa(dict(ROTAS_CANCELAR))
        with self.assertRaises(consulta_cp.ConsultaErro) as e:
            consulta_cp.cancelar(cli, 999)
        self.assertEqual(e.exception.codigo, "nao_encontrado")
        self.assertTrue(all(p[0] == "GET" for p in cli.pedidos))            # nada foi pedido à CP além da consulta

    def test_sem_a_operacao_refund_nao_avanca(self):
        cli = CPFalsa({**ROTAS_CANCELAR, ("GET", "/ticketing-api/sales/125951095/available-operations"): ["EXCHANGE"]})
        with self.assertRaises(consulta_cp.ConsultaErro) as e:
            consulta_cp.cancelar(cli, 125951095)
        self.assertEqual(e.exception.codigo, "nao_cancelavel")
        self.assertFalse(any(p[0] in ("POST", "PUT") for p in cli.pedidos))

    def test_devolucao_que_nao_confirma_e_um_erro(self):
        cli = CPFalsa({**ROTAS_CANCELAR, ("PUT", "/ticketing-api/post-sale/refund/77"): {"status": {"code": "PENDING"}}})
        with self.assertRaises(consulta_cp.ConsultaErro) as e:
            consulta_cp.cancelar(cli, 125951095)
        self.assertEqual(e.exception.codigo, "erro_cp")


class PasseTests(unittest.TestCase):
    def test_o_email_cifra_como_o_site_da_cp(self):
        # valor observado no site para este e-mail (AES-ECB, PKCS7, chave pública do JavaScript da CP)
        self.assertEqual(consulta_cp._cifrar_email("niculae@gmail.com"), "tWWe8vSKZhhF8Dj3H4i2drKYMFfit/4xuuyZtkRUc9k=")

    def test_validade_do_passe_sem_dados_do_cartao(self):
        cartao = {"card_type_name": "Cartão CP", "id_card_number": "SEGREDO", "photo": "xxx", "qr_code_string": "yyy", "contracts": [{
            "designation": "Passe Verde", "init_station": {"designation": "Aveiro"}, "end_station": {"designation": "Lisboa Oriente"},
            "init_date": "21/09/2026", "expiration_date": "20/10/2026", "allow_renewal": False}]}
        cli = CPFalsa({("GET", "/mobility-cards-api/cards/client/"): [cartao]})
        r = consulta_cp.passe(cli)
        self.assertEqual(r["passes"], [{"cartao": "Cartão CP", "designacao": "Passe Verde", "origem": "Aveiro", "destino": "Lisboa Oriente",
                                         "inicio": "2026-09-21", "validade": "2026-10-20", "renovavel": False}])
        self.assertNotIn("SEGREDO", str(r))
        self.assertNotIn("@", cli.pedidos[0][1])                              # o e-mail vai cifrado no caminho


class LinhaDeComandosTests(unittest.TestCase):
    def test_erro_de_credenciais_sai_como_json_e_nunca_como_traceback(self):
        import unittest.mock as mock
        with mock.patch.object(consulta_cp, "cliente", side_effect=consulta_cp.ConsultaErro("credenciais", "faltam dados")):
            self.assertEqual(consulta_cp.correr(2, "futuros"), {"ok": False, "erro": "credenciais", "mensagem": "faltam dados"})
        with mock.patch.object(consulta_cp, "cliente", side_effect=KeyError("x")):
            self.assertEqual(consulta_cp.correr(2, "passe")["erro"], "interno")


if __name__ == "__main__":
    unittest.main()
