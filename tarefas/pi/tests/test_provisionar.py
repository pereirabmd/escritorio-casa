import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import common
import provisionar_ntfy as pv


class Falso:
    """Regista os comandos `ntfy ...`; `contas` é o que `ntfy user list` devolve."""
    def __init__(self, contas=()):
        self.contas, self.chamadas, self.falha = contas, [], None

    def __call__(self, *args, password=None):
        self.chamadas.append((args, password))
        if args[:2] == ("user", "list"):
            return SimpleNamespace(returncode=0, stdout="".join(f"user {c} (role: user, tier: none)\n- x\n" for c in self.contas), stderr="")
        if self.falha and args[0] == self.falha:
            return SimpleNamespace(returncode=1, stdout="", stderr="boom")
        return SimpleNamespace(returncode=0, stdout="", stderr="")


class ValidarTests(unittest.TestCase):
    def test_aceita_e_deriva_o_topico(self):
        self.assertEqual(pv.validar({"user": " Camila ", "password": "abcdef"}), ("camila", "abcdef", "tarefas_camila"))
        self.assertEqual(pv.validar({"user": "tarefas_bruno", "password": "abcdef"})[2], "tarefas_bruno")

    def test_recusa(self):
        for p in ({"user": "tarefas-pi", "password": "abcdef"}, {"user": "bpereira", "password": "abcdef"},
                  {"user": "a b", "password": "abcdef"}, {"user": "x", "password": "abcdef"}, {"user": "../x", "password": "abcdef"},
                  {"user": "camila", "password": "curta"}, {"user": "camila", "password": "abc\ndef"},
                  {"user": "camila", "password": "abcdef", "extra": 1}, "texto", {"user": 1, "password": "abcdef"}):
            with self.assertRaises(ValueError, msg=p):
                pv.validar(p)

    def test_mesma_regra_do_topico_que_o_pi(self):
        for user in ("camila", "tarefas_bruno", "Bruno"):
            cfg = {"Pessoa1_Nome": "X", "Pessoa1_NtfyUser": user}
            self.assertEqual(pv.topico_de(user.lower()), common.topico_da_pessoa(cfg, "X"))


class AplicarTests(unittest.TestCase):
    def test_cria_conta_nova_so_leitura(self):
        f = Falso()
        self.assertEqual(pv.aplicar("camila", "abcdef", "tarefas_camila", f), "criada")
        self.assertEqual(f.chamadas[1], (("user", "add", "--role=user", "camila"), "abcdef"))
        self.assertEqual(f.chamadas[2][0], ("access", "camila", "tarefas_camila", "ro"))

    def test_conta_existente_muda_a_password(self):
        f = Falso(contas=["camila"])
        self.assertEqual(pv.aplicar("camila", "abcdef", "tarefas_camila", f), "atualizada")
        self.assertEqual(f.chamadas[1], (("user", "change-pass", "camila"), "abcdef"))

    def test_falha_do_ntfy_levanta(self):
        f = Falso(); f.falha = "access"
        with self.assertRaises(RuntimeError):
            pv.aplicar("camila", "abcdef", "tarefas_camila", f)


class ProcessarTests(unittest.TestCase):
    def test_processa_apaga_sempre_e_nao_segue_links(self):
        with tempfile.TemporaryDirectory() as d:
            pasta = Path(d)
            (pasta / "a.json").write_text(json.dumps({"user": "camila", "password": "abcdef"}))
            (pasta / "b.json").write_text(json.dumps({"user": "tarefas-pi", "password": "abcdef"}))
            (pasta / "c.json").write_text("x" * 5000)
            alvo = pasta.parent / "fora.json"; alvo.write_text(json.dumps({"user": "outro", "password": "abcdef"}))
            (pasta / "d.json").symlink_to(alvo)
            f = Falso()
            saidas = pv.processar(pasta, f)
            self.assertEqual(len(saidas), 4)
            self.assertIn("criada", saidas[0])
            self.assertTrue(all(s.startswith("ERRO") for s in saidas[1:]), saidas)
            self.assertEqual(list(pasta.glob("*.json")), [])            # nada com passwords fica
            self.assertTrue(alvo.exists())                              # o link apagou-se, o alvo não
            self.assertEqual([c[0][:2] for c in f.chamadas if c[0][0] == "user" and c[0][1] != "list"], [("user", "add")])   # só a conta válida foi tocada


class PedidoTests(unittest.TestCase):
    def test_ficheiro_600_numa_pasta_700(self):
        with tempfile.TemporaryDirectory() as d:
            from unittest import mock
            with mock.patch.object(common, "_state_file", return_value=Path(d) / "ntfy_provision"):
                f = common.pedir_provisionamento_ntfy("camila", "abcdef")
            self.assertEqual(oct(f.stat().st_mode & 0o777), "0o600")
            self.assertEqual(oct(f.parent.stat().st_mode & 0o777), "0o700")
            self.assertEqual(json.loads(f.read_text()), {"user": "camila", "password": "abcdef"})


if __name__ == "__main__":
    unittest.main()
