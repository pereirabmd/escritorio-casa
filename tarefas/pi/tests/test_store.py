"""SqliteStore: mesma interface e mesmos formatos que a SheetsClient, sobre o esquema real
(dados/migrations/004_tarefas.sql). O teste que mais importa é o de PARIDADE: o mesmo conjunto de dados, passado
pelo motor de notificações (recalcular) e pelo gerador (instancias), dá exatamente o mesmo resultado com a
FakeSheetsClient e com a SQLite."""

import sqlite3
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import common
import instancias
import manutencao
import recalcular
import servidor
import store
from tests.base import TarefasTestCase
from tests.fakes import FakeSheetsClient

SCHEMA = Path(__file__).resolve().parents[3] / "dados" / "migrations" / "004_tarefas.sql"


class SqliteBase(TarefasTestCase):
    def setUp(self):
        super().setUp()
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name) / "dados.db"
        c = sqlite3.connect(self.path)
        c.executescript(SCHEMA.read_text())
        c.close()
        self.st = store.SqliteStore(self.path)

    def sql(self, q, *a):
        c = sqlite3.connect(self.path)
        try:
            r = c.execute(q, a).fetchall()
            c.commit()
            return r
        finally:
            c.close()


class AdaptadorTest(SqliteBase):
    def test_leitura_no_formato_da_sheet(self):
        self.sql("INSERT INTO tarefas_tarefas (id, nome, recorrencia, dias_semana, dia_mes, hora_notificacao, ativa) "
                 "VALUES ('T001', 'Limpar WC', 'Mensal', '', 5, '09:00', 1)")
        self.sql("INSERT INTO tarefas_tarefas (id, nome, recorrencia, ativa) VALUES ('T002', 'Off', 'Diaria', 0)")
        t1, t2 = self.st.read_objects("Tarefas")
        self.assertEqual((t1["ID"], t1["Ativa"], t1["DiaMes"], t1["HoraNotificacao"], t1["Prioridade"]), ("T001", "TRUE", 5, "09:00", "Media"))
        self.assertEqual((t2["Ativa"], t2["DiaMes"], t2["DependeDe"]), ("FALSE", "", ""))         # NULL lê-se como ''
        self.assertEqual([t1["_rowIndex"], t2["_rowIndex"]], [1, 2])

    def test_append_update_delete_e_erros(self):
        self.st.append_rows("Instancias", [["I0001", "T001", "2026-09-24", "Bruno", "Pendente", "", "FALSE"],
                                          ["I0002", "T001", "2026-09-25", "Bruno", "Pendente", "", "FALSE"]])
        rows = self.st.read_objects("Instancias")
        self.assertEqual([r["ID"] for r in rows], ["I0001", "I0002"])
        self.st.update_cells("Instancias", rows[0]["_rowIndex"], Estado="Feita", DataConclusao="2026-09-24 10:00", NotificacaoEnviada="TRUE")
        r = self.st.read_objects("Instancias")[0]
        self.assertEqual((r["Estado"], r["DataConclusao"], r["NotificacaoEnviada"]), ("Feita", "2026-09-24 10:00", "TRUE"))
        self.st.update_cells("Instancias", rows[0]["_rowIndex"], NotificacaoEnviada="FALSE")
        self.assertEqual(self.st.read_objects("Instancias")[0]["NotificacaoEnviada"], "FALSE")
        with self.assertRaises(ValueError):
            self.st.update_cells("Instancias", rows[0]["_rowIndex"], ColunaInventada="x")
        with self.assertRaises(ValueError):
            self.st.update_cells("Instancias", 999, Estado="Feita")
        self.st.delete_rows("Instancias", [rows[1]["_rowIndex"]])
        self.assertEqual([r["ID"] for r in self.st.read_objects("Instancias")], ["I0001"])

    def test_duplicados_sao_ignorados_e_nao_falham(self):
        linha = ["I0001", "T001", "2026-09-24", "Bruno", "Pendente", "", "FALSE"]
        self.st.append_rows("Instancias", [linha])
        self.st.append_rows("Instancias", [linha])                                                 # mesmo id
        self.st.append_rows("Instancias", [["I0002", "T001", "2026-09-24", "Camila", "Pendente", "", "FALSE"]])   # mesma (tarefa, data)
        self.assertEqual(len(self.st.read_objects("Instancias")), 1)

    def test_config_set_find_e_piscina_datas_vazias(self):
        self.st.set_config("HoraPadrao", "08:00", "nota")
        self.st.set_config("HoraPadrao", "09:00")
        self.assertEqual(self.st.find_config("HoraPadrao")["Valor"], "09:00")
        self.assertEqual(len(self.st.read_objects("Config")), 1)
        self.assertIsNone(self.st.find_config("NaoExiste"))
        self.st.append_rows("Piscina", [["P01", "Cloro", "FALSE", "", "", "FALSE", "FALSE"]])
        p = self.st.read_objects("Piscina")[0]
        self.assertEqual((p["UltimaData"], p["ProximaData"], p["AvisoLongo"]), ("", "", "FALSE"))
        self.st.update_cells("Piscina", p["_rowIndex"], UltimaData="2026-09-20", ProximaData="2026-09-27")
        self.assertEqual(self.sql("SELECT ultima_data, proxima_data FROM tarefas_piscina"), [("2026-09-20", "2026-09-27")])

    def test_abas_e_ausencia_da_bd(self):
        self.assertTrue(self.st.tab_exists("Tarefas"))
        self.assertFalse(self.st.tab_exists("Subscriptions"))
        self.assertFalse(self.st.rename_tab("Subscriptions", "x"))
        with self.assertRaises(ValueError):
            self.st.read_objects("Inventada")
        with self.assertRaises(FileNotFoundError):
            store.SqliteStore(Path(self.dir.name) / "nao_existe.db").read_objects("Tarefas")
        self.assertFalse((Path(self.dir.name) / "nao_existe.db").exists())

    def test_get_store_escolhe_pelo_ambiente(self):
        with mock.patch.dict("os.environ", {"TAREFAS_BACKEND": "sqlite", "DADOS_DB": str(self.path)}):
            self.assertIsInstance(common.get_store(), store.SqliteStore)
        with mock.patch.dict("os.environ", {"TAREFAS_BACKEND": "sheets"}), mock.patch.object(common, "SheetsClient") as sc:
            self.assertIs(common.get_store(), sc.return_value)
        with mock.patch.dict("os.environ", {"TAREFAS_BACKEND": ""}), mock.patch.object(common, "SheetsClient") as sc:
            self.assertIs(common.get_store(), sc.return_value)


def dados_de_teste():
    """Um conjunto realista, em formato Sheet, para passar pelos dois backends."""
    hoje = common.now_local().date()
    d = lambda n: (hoje + timedelta(days=n)).isoformat()   # noqa: E731
    return {
        "Config": [{"Chave": "HoraPadrao", "Valor": "08:00"}, {"Chave": "DiasAntecedenciaGeracao", "Valor": "3"},
                   {"Chave": "NaoIncomodarInicio", "Valor": "22:00"}, {"Chave": "NaoIncomodarFim", "Valor": "07:00"},
                   {"Chave": "Pessoa1_Nome", "Valor": "Bruno"}, {"Chave": "Pessoa2_Nome", "Valor": "Camila"}],
        "Tarefas": [
            {"ID": "T001", "Nome": "Lixo", "Categoria": "Cozinha", "Recorrencia": "Diaria", "HoraNotificacao": "23:00",
             "PessoaPadrao": "Bruno", "Ativa": "TRUE", "RotacaoPessoas": "Bruno,Camila", "DiaMes": ""},
            {"ID": "T002", "Nome": "Regar", "Recorrencia": "Semanal", "DiasSemana": "Seg,Ter,Qua,Qui,Sex,Sab,Dom",
             "HoraNotificacao": "10:00", "PessoaPadrao": "Camila", "Ativa": "TRUE", "DiaMes": ""},
            {"ID": "T003", "Nome": "Off", "Recorrencia": "Diaria", "PessoaPadrao": "Bruno", "Ativa": "FALSE", "DiaMes": ""},
            {"ID": "T004", "Nome": "Depende", "Recorrencia": "Pontual", "DiasSemana": d(0), "HoraNotificacao": "12:00",
             "PessoaPadrao": "Bruno", "Ativa": "TRUE", "DependeDe": "T002", "DiaMes": ""},
        ],
        "Instancias": [
            {"ID": "I0001", "TarefaID": "T001", "Data": d(0), "Pessoa": "Bruno", "Estado": "Pendente", "DataConclusao": "", "NotificacaoEnviada": "FALSE"},
            {"ID": "I0002", "TarefaID": "T002", "Data": d(0), "Pessoa": "Camila", "Estado": "Pendente", "DataConclusao": "", "NotificacaoEnviada": "FALSE"},
            {"ID": "I0003", "TarefaID": "T002", "Data": d(1), "Pessoa": "Camila", "Estado": "Pendente", "DataConclusao": "", "NotificacaoEnviada": "FALSE"},
            {"ID": "I0004", "TarefaID": "T003", "Data": d(0), "Pessoa": "Bruno", "Estado": "Pendente", "DataConclusao": "", "NotificacaoEnviada": "FALSE"},
            {"ID": "I0005", "TarefaID": "T004", "Data": d(0), "Pessoa": "Bruno", "Estado": "Pendente", "DataConclusao": "", "NotificacaoEnviada": "FALSE"},
            {"ID": "I0006", "TarefaID": "T001", "Data": d(-1), "Pessoa": "Bruno", "Estado": "Feita", "DataConclusao": d(-1) + " 08:00", "NotificacaoEnviada": "TRUE"},
            {"ID": "I0007", "TarefaID": "T002", "Data": d(-1), "Pessoa": "Camila", "Estado": "Atrasada", "DataConclusao": "", "NotificacaoEnviada": "TRUE"},
        ],
        "Piscina": [
            {"ID": "P01", "Nome": "Cloro", "AvisoLongo": "FALSE", "UltimaData": d(-5), "ProximaData": d(0), "NotificacaoEnviada": "FALSE", "UsarIntervaloLongo": "FALSE"},
            {"ID": "P08", "Nome": "Areia", "AvisoLongo": "TRUE", "UltimaData": d(-300), "ProximaData": d(20), "NotificacaoEnviada": "FALSE", "UsarIntervaloLongo": "FALSE"},
            {"ID": "P09", "Nome": "Sem data", "AvisoLongo": "FALSE", "UltimaData": "", "ProximaData": "", "NotificacaoEnviada": "FALSE", "UsarIntervaloLongo": "FALSE"},
        ],
    }


def carregar_no_sqlite(st: store.SqliteStore, dados: dict) -> None:
    for tab, linhas in dados.items():
        cabs = [c for c, _, _ in store.TABELAS[tab][1]]
        padroes = {"Prioridade": "Media", "Estado": "Pendente"}          # o esquema exige valores válidos
        st.append_rows(tab, [[l.get(c, padroes.get(c, "")) or padroes.get(c, "") for c in cabs] for l in linhas])


class ParidadeTest(SqliteBase):
    def _contagens(self, sheets, plan_only):
        common._state_file("ntfy_agendados.json").unlink(missing_ok=True)       # o estado local é partilhado: cada corrida parte do zero
        with mock.patch.object(common, "ntfy_publish", return_value={"id": "m1"}), mock.patch.object(common, "ntfy_cancel", return_value=True):
            return recalcular.recalcular(sheets, plan_only=plan_only)

    def test_recalcular_da_o_mesmo_com_fake_e_com_sqlite(self):
        dados = dados_de_teste()
        fake = FakeSheetsClient(dados)
        carregar_no_sqlite(self.st, dados)
        self.assertEqual(self._contagens(fake, True), self._contagens(self.st, True))
        # e a sério (não plan_only): as mesmas instâncias ficam marcadas como notificadas
        estado_fake = self._contagens(fake, False)
        estado_sql = self._contagens(self.st, False)
        self.assertEqual(estado_fake, estado_sql)
        notif = lambda s: {(r["ID"]): r["NotificacaoEnviada"] for r in s.read_objects("Instancias")}   # noqa: E731
        self.assertEqual(notif(fake), notif(self.st))
        pis = lambda s: {r["ID"]: r["NotificacaoEnviada"] for r in s.read_objects("Piscina")}   # noqa: E731
        self.assertEqual(pis(fake), pis(self.st))

    def test_gerar_instancias_da_o_o_mesmo_com_fake_e_com_sqlite(self):
        dados = dados_de_teste()
        dados["Instancias"] = []
        fake = FakeSheetsClient(dados)
        carregar_no_sqlite(self.st, dados)
        n_fake, n_sql = instancias.gerar_instancias(fake), instancias.gerar_instancias(self.st)
        self.assertEqual(n_fake, n_sql)
        chave = lambda s: sorted((r["TarefaID"], r["Data"], r["Pessoa"], r["Estado"]) for r in s.read_objects("Instancias"))   # noqa: E731
        self.assertEqual(chave(fake), chave(self.st))
        self.assertGreater(n_sql, 0)
        self.assertEqual(instancias.gerar_instancias(self.st), 0)                                # idempotente
        # a rotação (T001: Bruno,Camila) funciona agora de verdade: as colunas existem
        pessoas = [r["Pessoa"] for r in sorted(self.st.read_objects("Instancias"), key=lambda r: r["Data"]) if r["TarefaID"] == "T001"]
        self.assertEqual(pessoas[:4], ["Bruno", "Camila", "Bruno", "Camila"])

    def test_marcar_atrasadas_da_o_mesmo_com_fake_e_com_sqlite(self):
        dados = dados_de_teste()
        fake = FakeSheetsClient(dados)
        carregar_no_sqlite(self.st, dados)
        self.assertEqual(instancias.marcar_atrasadas(fake), instancias.marcar_atrasadas(self.st))
        estados = lambda s: {r["ID"]: r["Estado"] for r in s.read_objects("Instancias")}   # noqa: E731
        self.assertEqual(estados(fake), estados(self.st))
        self.assertEqual(estados(self.st)["I0007"], "Atrasada")

    def test_manutencao_apaga_so_o_historico_antigo(self):
        hoje = common.now_local().date()
        antiga = (hoje - timedelta(days=manutencao.DIAS_RETER_HISTORICO + 5)).isoformat()
        recente = (hoje - timedelta(days=1)).isoformat()
        carregar_no_sqlite(self.st, {"Instancias": [
            {"ID": "I1", "TarefaID": "T1", "Data": antiga, "Estado": "Feita"},
            {"ID": "I2", "TarefaID": "T1", "Data": antiga + "", "Estado": "Pendente"},      # (mesma tarefa/dia falharia: mudar a tarefa)
            {"ID": "I3", "TarefaID": "T2", "Data": recente, "Estado": "Saltada"}]})
        self.sql("DELETE FROM tarefas_instancias WHERE id='I2'")
        self.st.append_rows("Instancias", [["I2", "T3", antiga, "", "Pendente", "", "FALSE"]])
        self.assertEqual(manutencao.limpar_historico_antigo(self.st, plan_only=True), 1)
        self.assertEqual(manutencao.limpar_historico_antigo(self.st), 1)
        self.assertEqual({r["ID"] for r in self.st.read_objects("Instancias")}, {"I2", "I3"})
        self.assertEqual(manutencao.manutencao(self.st), {"instancias_apagadas": 0, "subscricoes_apagadas": 0})   # 'Subscriptions' já não existe


class ServidorTest(SqliteBase):
    def setUp(self):
        super().setUp()
        carregar_no_sqlite(self.st, dados_de_teste())

    def test_marcar_feita_e_snooze(self):
        with mock.patch.object(common, "ntfy_publish", return_value={"id": "m"}), mock.patch.object(common, "ntfy_cancel", return_value=True):
            self.assertEqual(servidor.handle_marcar_feita(self.st, {"instanciaId": "I0001", "s": recalcular.assinar_instancia("I0001")}), {"ok": True})
            self.assertEqual(servidor.handle_marcar_feita(self.st, {"instanciaId": "I0001", "s": "errada"}), {"ok": False, "erro": "assinatura inválida"})
            self.assertEqual(servidor.handle_marcar_feita(self.st, {"instanciaId": "I999"}), {"ok": False, "erro": "instância não encontrada"})
            r = servidor.handle_snooze(self.st, {"instanciaId": "I0002", "minutos": 30})
        self.assertTrue(r["ok"])
        self.assertEqual(self.sql("SELECT estado, data_conclusao <> '' FROM tarefas_instancias WHERE id='I0001'"), [("Feita", 1)])
        self.assertEqual(self.sql("SELECT notificacao_enviada FROM tarefas_instancias WHERE id='I0002'")[0][0], 0)

    def test_configurar_ntfy_cifra_e_grava_nas_chaves_da_pessoa(self):
        r = servidor.handle_configurar_ntfy(self.st, {"pessoa": "Camila", "ntfyUser": "tarefas_camila", "ntfyPassword": "segredo123"})
        self.assertEqual(r, {"ok": True})
        cfg = {x["Chave"]: x["Valor"] for x in self.st.read_objects("Config")}
        self.assertEqual(cfg["Pessoa2_NtfyUser"], "tarefas_camila")
        self.assertNotIn("segredo123", cfg["Pessoa2_NtfyPasswordEnc"])
        self.assertEqual(common.decrypt(cfg["Pessoa2_NtfyPasswordEnc"]), "segredo123")
        self.assertEqual(servidor.handle_configurar_ntfy(self.st, {"pessoa": "Ninguém", "ntfyUser": "x", "ntfyPassword": "y"})["ok"], False)


if __name__ == "__main__":
    unittest.main()
