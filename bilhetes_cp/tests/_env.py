"""Ambiente hermético para os testes: importar ESTE módulo antes de qualquer script.

Aponta o projeto para uma pasta temporária (sem .env, sem locks reais) e define
credenciais falsas, para que nenhum teste toque em dados ou serviços reais.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="cp_test_"))
shutil.copytree(REPO / "config", TMP / "config",
                ignore=shutil.ignore_patterns("service-account.json"))

os.environ["BILHETES_CP_HOME"] = str(TMP)
os.environ["TZ"] = "Europe/Lisbon"
FAKE = {
    "CP_EMAIL": "teste.pessoa@exemplo.pt",
    "CP_PASSWORD": "senha-de-teste-123",
    "CP_PASSENGER_NAME": "Nome Completo De Teste",
    "CP_PASSENGER_CC": "12345678",
    "CP_PASSENGER_PHONE": "PT912345678",
    "CP_PASSENGER_NIF": "123456789",
    "CP_GREEN_PASS_NUMBER": "9999999999",
    "CP_CONNECT_ID": "connect-id-falso",
    "CP_CONNECT_SECRET": "connect-secret-falso",
    "CP_API_KEY_TRAVEL": "chave-travel-falsa",
    "CP_API_KEY_TICKETING": "chave-ticketing-falsa",
    "GOOGLE_SHEET_ID": "sheet-falsa",
    "NTFY_SERVER_URL": "https://ntfy.invalido.test",
    "NTFY_TOPIC": "topico_teste",
    "NTFY_USERNAME": "utilizador_teste",
    "NTFY_PASSWORD": "password-ntfy-falsa",
}
os.environ.update(FAKE)
sys.path.insert(0, str(REPO / "scripts"))
