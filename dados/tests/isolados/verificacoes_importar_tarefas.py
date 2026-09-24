import os
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3] / "tarefas" / "pi"
os.environ["TAREFAS_PI_SCRIPTS"] = str(_REPO)
os.environ["TAREFAS_PI_HOME"] = tempfile.mkdtemp(prefix="imp_tarefas_")
os.environ.setdefault("TZ", "Europe/Lisbon")

import importar_tarefas as it  # noqa: E402


def linha(id_="T001", nome="Limpar WC", cat="Limpeza", icone="", rec="Semanal", dias="Sab", diames="", hora="09:00", pessoa="Bruno",
          ativa="TRUE", prio="", rot="", dep=""):
    return [id_, nome, cat, icone, rec, dias, diames, hora, pessoa, ativa, prio, rot, dep]


class ImportarTarefasTest(unittest.TestCase):
    def test_tarefas_tipos_da_sheet_e_limpezas(self):
        linhas = [
            linha(),
            linha("T002", "Aspirar", rec="Dias especificos", dias="Seg,Qua,Sex", diames=1, hora=0.3333333333333333, ativa=True, prio="Media"),
            linha("T003", "Lavar telhados", rec="Pontual", dias=46473, hora=0.5, ativa=True),        # serial da data, fração de hora
            linha("T004", "Mensal", rec="Mensal", dias="", diames=15),
            ["Legenda: linhas em italico/cinza sao exemplos...", "", "", "", "", "", "", "", "", ""],
            linha("T005", "Sem dias", rec="Semanal", dias=""),
            linha("T006", "Dia mau", rec="Dias especificos", dias="Seg,Xpto"),
            linha("T007", "Anual", rec="Anual"),
            linha("T008", "Prio", prio="Alta", rot="Bruno,Camila", dep="T001"),
            linha("T009", "Dep fantasma", dep="T999"),
            linha("T011", "Aspirar R/C"),
            linha("T010", "/ticketing-api/trips/<email>?filter=FUTURE` (exige o cabeçalho", rec="Trimestral", dias=46270),
        ]
        t, avisos, prob, remap = it.preparar_tarefas(linhas)
        por = {x["id"]: x for x in t}
        self.assertEqual(sorted(por), ["T001", "T002", "T003", "T004", "T008", "T009", "T010", "T011"])
        self.assertEqual((por["T002"]["hora"], por["T002"]["dia_mes"], por["T002"]["ativa"]), ("08:00", None, 1))          # DiaMes só nas mensais
        self.assertEqual((por["T003"]["dias_semana"], por["T003"]["hora"]), ("2027-03-27", "12:00"))
        self.assertEqual(por["T004"]["dia_mes"], 15)
        self.assertEqual((por["T008"]["prioridade"], por["T008"]["rotacao"], por["T008"]["depende"]), ("Alta", "Bruno,Camila", "T001"))
        self.assertEqual(por["T009"]["depende"], "")                                                                       # DependeDe inexistente: limpo
        textos = " | ".join(m for _, m in prob) + " | ".join(avisos)
        self.assertNotIn("T011", textos)                                                              # 'R/C' não é um erro de colagem
        for esperado in ("linha ignorada", "dias da semana inválidos", "recorrência inválida", "DependeDe", "erro de colagem", "ATIVA", "opções avançadas"):
            self.assertIn(esperado, textos)

    def test_id_repetido_fica_com_o_ativo_e_o_outro_ganha_id_novo(self):
        t, avisos, _, remap = it.preparar_tarefas([linha("T1135", "Teste 123", ativa=False), linha("T1135", "Frigorífico", ativa=True), linha("T1144", "X")])
        ids = {x["nome"]: x["id"] for x in t}
        self.assertEqual((ids["Frigorífico"], ids["Teste 123"], ids["X"]), ("T1135", "T1145", "T1144"))
        self.assertTrue(any("repetido" in a for a in avisos))

    def test_instancias(self):
        objs = [
            {"ID": "I0001", "TarefaID": "T001", "Data": 46285, "Pessoa": "Bruno", "Estado": "Feita", "DataConclusao": 46285.5631944, "NotificacaoEnviada": True, "_rowIndex": 2},
            {"ID": "I0002", "TarefaID": "T001", "Data": "2026-09-21", "Pessoa": "Bruno", "Estado": "Pendente", "DataConclusao": "", "NotificacaoEnviada": "FALSE", "_rowIndex": 3},
            {"ID": "I0003", "TarefaID": "T001", "Data": 46285, "Pessoa": "Bruno", "Estado": "Pendente", "DataConclusao": "", "NotificacaoEnviada": "FALSE", "_rowIndex": 4},   # duplicado de I0001
            {"ID": "Esta tab e gerada automaticamente...", "TarefaID": "", "Data": "", "Estado": "", "_rowIndex": 5},
            {"ID": "I0004", "TarefaID": "T999", "Data": "2026-09-24", "Estado": "Pendente", "_rowIndex": 6},
            {"ID": "I0005", "TarefaID": "T001", "Data": "lixo", "Estado": "Pendente", "_rowIndex": 7},
            {"ID": "I0006", "TarefaID": "T001", "Data": "2026-09-22", "Estado": "pendente", "DataConclusao": "", "_rowIndex": 8},
            {"ID": "I1789929447364", "TarefaID": "T001", "Data": "2026-09-23", "Estado": "Atrasada", "DataConclusao": "2026-08-26 21:05", "_rowIndex": 9},
        ]
        inst, avisos, prob = it.preparar_instancias(objs, {"T001"})
        inst = it.resolver_duplicadas(inst, avisos)
        self.assertEqual(sorted(i["id"] for i in inst), ["I0001", "I0002", "I0006", "I1789929447364"])       # I0003 (duplicado) e os inválidos fora
        i1 = next(i for i in inst if i["id"] == "I0001")
        self.assertEqual((i1["data"], i1["estado"], i1["concl"], i1["notif"]), ("2026-09-20", "Feita", "2026-09-20 13:31", 1))   # serial -> ISO, 'Feita' vence o duplicado
        self.assertEqual(next(i for i in inst if i["id"] == "I0006")["estado"], "Pendente")                # 'pendente' normalizado
        self.assertEqual(next(i for i in inst if i["id"] == "I1789929447364")["concl"], "2026-08-26 21:05")
        textos = " | ".join(m for _, m in prob) + " | ".join(avisos)
        for esperado in ("linha ignorada", "inexistente", "data inválida", "duplicada"):
            self.assertIn(esperado, textos)

    def test_config_piscina_auditoria(self):
        cfg, _, prob = it.preparar_config([
            {"Chave": "HoraPadrao", "Valor": 0.3333333333333333, "Notas": "", "_rowIndex": 2}, {"Chave": "DiasAntecedenciaGeracao", "Valor": 30.0, "_rowIndex": 3},
            {"Chave": "Pessoa1_NtfyPasswordEnc", "Valor": "gAAAAAB-xyz==", "_rowIndex": 4}, {"Chave": "Segue o mesmo padrao das outras apps", "Valor": "", "_rowIndex": 5},
            {"Chave": "Pessoa3_Nome", "Valor": "", "_rowIndex": 6}, {"Chave": "NaoIncomodarInicio", "Valor": "22:00", "_rowIndex": 7}])
        m = {c["chave"]: c["valor"] for c in cfg}
        self.assertEqual(m, {"HoraPadrao": "08:00", "DiasAntecedenciaGeracao": "30", "Pessoa1_NtfyPasswordEnc": "gAAAAAB-xyz==", "NaoIncomodarInicio": "22:00"})
        self.assertEqual(len(prob), 1)
        p, _ = it.preparar_piscina([{"ID": "P09", "Nome": "Repor", "AvisoLongo": False, "UltimaData": 46271, "ProximaData": "", "NotificacaoEnviada": "TRUE", "UsarIntervaloLongo": False, "_rowIndex": 2}])
        self.assertEqual((p[0]["ultima"], p[0]["proxima"], p[0]["notif"]), ("2026-09-06", None, 1))
        a = it.preparar_auditoria([["Timestamp", "Acao", "Tarefa", "Pessoa", "InstanciaID"], ["2026-08-28T20:50:05.253Z", "notificacao_enviada", "Lixo", "Bruno", "I0005"], []])
        self.assertEqual(len(a), 1)


if __name__ == "__main__":
    unittest.main()
