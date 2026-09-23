"""Base comum aos testes: isola cada teste num BASE_DIR temporário (para
state/locks não tocarem no BASE_DIR real) e define as variáveis de
ambiente mínimas (FERNET_KEY, ACAO_SEGREDO, NTFY_*) sem precisar de rede."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from unittest import mock

from cryptography.fernet import Fernet

import common

ENV_TESTE = {
    "FERNET_KEY": Fernet.generate_key().decode(),
    "ACAO_SEGREDO": "segredo-de-teste",
    "NTFY_SERVER_URL": "https://ntfy.exemplo.invalido",
    "NTFY_TOPIC": "tarefas",
    "NTFY_WRITE_USER": "pi-escreve",
    "NTFY_WRITE_PASSWORD": "xxx",
    "TAREFAS_API_URL": "https://exemplo.invalido/tarefas-api",
}


class TarefasTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="tarefas-pi-test-")
        self._base_dir_original = common.BASE_DIR
        common.BASE_DIR = __import__("pathlib").Path(self._tmp)
        self._env_patch = mock.patch.dict("os.environ", ENV_TESTE)
        self._env_patch.start()

    def tearDown(self) -> None:
        self._env_patch.stop()
        common.BASE_DIR = self._base_dir_original
        shutil.rmtree(self._tmp, ignore_errors=True)
