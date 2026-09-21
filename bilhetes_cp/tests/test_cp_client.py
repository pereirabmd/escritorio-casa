"""Cliente da CP: secções (transbordos), corpo do /sale, fiscalAddress opcional."""

import unittest
from unittest import mock

import _env  # noqa: F401
import cp_ticket
from cp_ticket import CPClient, pick_trip, trip_sections, find_section

TRANSBORDO = {"departureTime": "07:44", "arrivalTime": "11:22", "saleableOnline": True, "travelSections": [
    {"trainNumber": 4656, "serviceCode": {"code": "R", "designation": "Regional"},
     "departureStation": {"code": "94-38000", "designation": "Aveiro"}, "arrivalStation": {"code": "94-37002"}},
    {"trainNumber": 510, "serviceCode": {"code": "IC", "designation": "Intercidades"},
     "departureStation": {"code": "94-37002"}, "arrivalStation": {"code": "94-31039"}}]}
DIRETO = {"departureTime": "07:27", "saleableOnline": False, "travelSections": [
    {"trainNumber": 520, "serviceCode": {"code": "IC", "designation": "Intercidades"}}]}
J = {"outwardTrip": [DIRETO, TRANSBORDO]}


class SectionTests(unittest.TestCase):
    def test_pick_trip_encontra_o_comboio_em_qualquer_seccao(self):
        self.assertIs(pick_trip(J, train_number=510, require_saleable=False), TRANSBORDO)
        self.assertIs(pick_trip(J, train_number=4656, require_saleable=False), TRANSBORDO)
        with self.assertRaisesRegex(RuntimeError, "não encontrado.*510|Comboio nº 999"):
            pick_trip(J, train_number=999, require_saleable=False)

    def test_find_section_escolhe_pelo_numero_e_nao_a_primeira(self):
        self.assertEqual(find_section(TRANSBORDO, 510)["serviceCode"]["code"], "IC")

    def test_trip_sections_uma_por_comboio_com_as_suas_estacoes(self):
        s = trip_sections(TRANSBORDO)
        self.assertEqual([(x["train"], x["dep"], x["arr"]) for x in s],
                         [(4656, "94-38000", "94-37002"), (510, "94-37002", "94-31039")])

    def test_directo_sem_estacoes_usa_as_da_perna_mas_transbordo_nao(self):
        s = trip_sections(DIRETO, "94-38000", "94-31039")
        self.assertEqual((s[0]["dep"], s[0]["arr"]), ("94-38000", "94-31039"))
        semest = {"travelSections": [{"trainNumber": 1, "serviceCode": {"code": "R", "designation": "R"}},
                                     {"trainNumber": 2, "serviceCode": {"code": "R", "designation": "R"}}]}
        with self.assertRaisesRegex(RuntimeError, "sem estações"):
            trip_sections(semest, "a", "b")


class SaleBodyTests(unittest.TestCase):
    def client(self):
        c = CPClient("tok")
        c.request = mock.Mock(return_value="resp")
        return c

    def test_sale_leva_uma_entrada_de_outwardTrip_por_seccao(self):
        c = self.client()
        c.create_sale_request("2026-09-23", trip_sections(TRANSBORDO))
        args, kw = c.request.call_args
        trips = kw["body"]["outwardTrip"]
        self.assertEqual([t["trainNumber"] for t in trips], [4656, 510])
        self.assertEqual(trips[1]["departureStation"], {"code": "94-37002"})
        self.assertEqual(trips[1]["serviceCode"], {"code": "IC", "designation": "Intercidades"})
        self.assertEqual((args[0], args[1]), ("POST", "/ticketing-api/sale"))

    def test_fiscal_sem_morada_por_omissao(self):
        c = self.client()
        with mock.patch.dict("os.environ", {"CP_FISCAL_ADDRESS": ""}):
            c._checked = mock.Mock()
            c.set_fiscal(1)
        body = c._checked.call_args.kwargs["body"]
        self.assertNotIn("fiscalAddress", body)
        self.assertEqual(body["countryCode"], "PT")

    def test_fiscal_com_morada_opcional_em_json(self):
        c = self.client(); c._checked = mock.Mock()
        with mock.patch.dict("os.environ", {"CP_FISCAL_ADDRESS": '{"street": "Rua X", "postalCode": "3800-000"}'}):
            c.set_fiscal(1)
        self.assertEqual(c._checked.call_args.kwargs["body"]["fiscalAddress"], {"street": "Rua X", "postalCode": "3800-000"})

    def test_fiscal_com_morada_invalida_falha_de_forma_clara(self):
        c = self.client(); c._checked = mock.Mock()
        with mock.patch.dict("os.environ", {"CP_FISCAL_ADDRESS": "isto nao e json"}):
            with self.assertRaisesRegex(RuntimeError, "não é JSON válido"):
                c.set_fiscal(1)
        c._checked.assert_not_called()

    def test_journeys_e_pedido_sem_x_access_token_quando_pedido_sem_login(self):
        c = CPClient("")
        h = c._headers("k", with_token=False)
        self.assertNotIn("x-access-token", h)
        self.assertIn("x-access-token", c._headers("k", with_token=True))


if __name__ == "__main__":
    unittest.main()
