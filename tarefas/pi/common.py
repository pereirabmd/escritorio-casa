"""Biblioteca comum dos scripts do tarefas/pi (corre no Raspberry Pi).

Concentra o que é partilhado (mesmo espírito do bilhetes_cp/scripts/common.py,
propositadamente parecido para quem mexer nos dois projetos):
- carregamento do .env
- acesso à Sheet via service account (a mesma conta já usada pelo bilhetes_cp,
  que já tem acesso à pasta partilhada — confirmado, sem partilha extra)
- encriptação Fernet das credenciais ntfy por pessoa (a chave nunca sai daqui)
- normalização de horas vindas da Sheet (a mesma armadilha documentada no
  PROJECT-CONTEXT.md: valueInputOption=USER_ENTERED faz o Sheets devolver
  horas como fração de dia, não como texto)
- publicar/cancelar mensagens agendadas no ntfy (X-Delay + DELETE)
- estado local simples (ficheiro) e lock por ficheiro (fcntl.flock)

Nada aqui importa as bibliotecas Google ao nível do módulo, para os testes
correrem em qualquer máquina, sem rede.
"""

from __future__ import annotations

import fcntl
import json
import logging
import logging.handlers
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

BASE_DIR = Path(os.environ.get("TAREFAS_PI_HOME") or Path(__file__).resolve().parent)
TZ = ZoneInfo(os.environ.get("TZ", "Europe/Lisbon"))


# ---------------------------------------------------------------------------
# .env
# ---------------------------------------------------------------------------

def load_env(path: Path | None = None) -> None:
    """Carrega o .env para os.environ sem sobrepor variáveis já definidas."""
    path = path or (BASE_DIR / ".env")
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


load_env()


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


# ---------------------------------------------------------------------------
# Logging (mesmo padrão do bilhetes_cp: stdout + ficheiro com rotação)
# ---------------------------------------------------------------------------

_LOGGERS: dict[str, logging.Logger] = {}


def get_logger(name: str) -> logging.Logger:
    if name in _LOGGERS:
        return _LOGGERS[name]
    logger = logging.getLogger(f"tarefas.{name}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    try:
        log_dir = BASE_DIR / "logs"
        log_dir.mkdir(exist_ok=True)
        handlers.append(logging.handlers.RotatingFileHandler(
            log_dir / f"{name}.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8"))
    except OSError as e:
        print(f"AVISO: sem log em ficheiro ({e})", file=sys.stderr)
    for h in handlers:
        h.setFormatter(fmt)
        logger.addHandler(h)
    _LOGGERS[name] = logger
    return logger


# ---------------------------------------------------------------------------
# Encriptação das credenciais ntfy por pessoa (Fernet — chave só no .env)
# ---------------------------------------------------------------------------

def encrypt(plain: str) -> str:
    from cryptography.fernet import Fernet
    key = env("FERNET_KEY")
    if not key:
        raise RuntimeError("FERNET_KEY em falta no .env — não posso encriptar.")
    return Fernet(key.encode()).encrypt(plain.encode()).decode()


def decrypt(token: str) -> str:
    from cryptography.fernet import Fernet
    key = env("FERNET_KEY")
    if not key:
        raise RuntimeError("FERNET_KEY em falta no .env — não posso decifrar.")
    return Fernet(key.encode()).decrypt(token.encode()).decode()


# ---------------------------------------------------------------------------
# Horas/datas vindas da Sheet (ver PROJECT-CONTEXT.md: armadilha do
# valueInputOption=USER_ENTERED — uma hora "20:10" volta como fração de dia)
# ---------------------------------------------------------------------------

def normalizar_hora(valor: Any) -> str:
    """Sempre 'HH:MM' (ou '' se vazio) — nunca comparar a hora crua da Sheet."""
    if valor is None or valor == "" or isinstance(valor, bool):
        return ""
    if isinstance(valor, (int, float)):
        if valor < 0 or valor >= 1:
            return ""
        mins = round(valor * 1440)
        if mins >= 1440:
            return ""
        return f"{mins // 60:02d}:{mins % 60:02d}"
    m = re.match(r"^(\d{1,2}):(\d{2})", str(valor).strip())
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        return ""
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def parse_sheet_date(valor: Any) -> date | None:
    """'YYYY-MM-DD' (texto) ou serial da Sheet (dias desde 1899-12-30)."""
    if valor is None or valor == "" or isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        try:
            return date(1899, 12, 30) + timedelta(days=int(valor))
        except (OverflowError, ValueError):
            return None
    s = str(valor).strip()[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def now_local() -> datetime:
    return datetime.now(TZ)


# ---------------------------------------------------------------------------
# Estado local simples (mesmo padrão do bilhetes_cp) e lock por ficheiro
# ---------------------------------------------------------------------------

def _state_file(name: str) -> Path:
    d = BASE_DIR / "state"
    d.mkdir(mode=0o700, exist_ok=True)
    return d / name


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write_json_atomic(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


class FileLock:
    """Exclusão mútua simples por fcntl.flock — sem estado, ao contrário do
    PurchaseLock do bilhetes_cp (aqui não há um *state machine* a guardar)."""

    def __init__(self, chave: str) -> None:
        d = BASE_DIR / "locks"
        d.mkdir(mode=0o700, exist_ok=True)
        self.path = d / f"{chave}.lock"
        self._fd: int | None = None

    def acquire(self, timeout_s: float = 0) -> bool:
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        deadline = time.monotonic() + timeout_s
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._fd = fd
                return True
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    os.close(fd)
                    return False
                time.sleep(0.2)

    def release(self) -> None:
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> "FileLock":
        if not self.acquire(timeout_s=15):
            raise TimeoutError(f"não consegui o lock {self.path} a tempo")
        return self

    def __exit__(self, *exc: Any) -> None:
        self.release()


# ---------------------------------------------------------------------------
# ntfy: publicar (com agendamento opcional) e cancelar
# ---------------------------------------------------------------------------

TOPICO_LEGADO = "tarefas"     # tópico partilhado antigo: fica de reserva para quem ainda não tem utilizador ntfy
_TOPICO_OK = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def topico_da_pessoa(config: dict[str, Any], nome: str) -> str | None:
    """Tópico ntfy de uma pessoa, por convenção `tarefas_<utilizador>`. O utilizador (Pessoa<N>_NtfyUser) configura-se
    na app; se já vier como `tarefas_bruno` usa-se tal e qual, se vier `bruno` o tópico é `tarefas_bruno`.
    None se a pessoa não existe ou ainda não tem utilizador ntfy (as mensagens vão então para o tópico legado)."""
    nome = str(nome or "").strip()
    if not nome:
        return None
    for chave, valor in config.items():
        m = re.fullmatch(r"Pessoa(\d+)_Nome", str(chave).strip())
        if m and str(valor or "").strip() == nome:
            user = str(config.get(f"Pessoa{m.group(1)}_NtfyUser") or "").strip().lower()
            if not user:
                return None
            topico = user if user.startswith("tarefas_") else f"tarefas_{user}"
            return topico if _TOPICO_OK.match(topico) else None
    return None


NTFY_ICON_URL = "https://pereirabmd.github.io/escritorio-casa/tarefas/icon-192.png"


def ntfy_publish(*, title: str, message: str, delay_at: datetime | None = None,
                 actions: list[dict] | None = None, tags: list[str] | None = None,
                 priority: int = 4, click: str | None = None, topic: str | None = None) -> dict | None:
    """Publica no tópico do .env (NTFY_TOPIC), autenticado com as credenciais de
    ESCRITA do próprio Pi (NTFY_WRITE_USER/NTFY_WRITE_PASSWORD — nunca as de
    leitura por pessoa, essas só servem para a app de cada um subscrever).
    `delay_at`: agenda a entrega (X-Delay) em vez de publicar já — devolve
    sempre o corpo JSON da resposta (tem o "id" da mensagem, para cancelar
    depois) ou None se falhar. Nunca falha em silêncio: regista o erro."""
    import requests

    log = get_logger("ntfy")
    base = env("NTFY_SERVER_URL").rstrip("/")
    topic = topic or env("NTFY_TOPIC", TOPICO_LEGADO)
    body: dict[str, Any] = {"topic": topic, "title": title, "message": message,
                            "priority": priority,
                            # ícone da app na notificação (GitHub Pages serve-o ao telemóvel)
                            "icon": env("NTFY_ICON_URL", NTFY_ICON_URL)}
    if tags:
        body["tags"] = tags
    if click:
        body["click"] = click
    if actions:
        body["actions"] = actions
    if delay_at is not None:
        body["delay"] = str(int(delay_at.timestamp()))
    auth = (env("NTFY_WRITE_USER"), env("NTFY_WRITE_PASSWORD"))
    try:
        r = requests.post(base + "/", json=body, auth=auth, timeout=(4, 10))
        if 200 <= r.status_code < 300:
            return r.json()
        log.error("Publicação no ntfy falhou (HTTP %s): %s", r.status_code, r.text[:300])
    except requests.RequestException as e:
        log.error("Publicação no ntfy falhou: %s: %s", type(e).__name__, e)
    return None


# ---------------------------------------------------------------------------
# Sheets — service account (a mesma conta do bilhetes_cp, já com acesso à
# pasta partilhada; nenhuma partilha extra foi precisa). Cabeçalhos lidos
# pelo NOME da coluna (mesmo princípio do sheetToObjects em Code.gs) — nunca
# por posição fixa, para inserir/reordenar colunas na Sheet não desalinhar.
# ---------------------------------------------------------------------------

def _col_letter(i: int) -> str:
    """0-indexed -> 'A', 'B', ... 'Z', 'AA', ... (o suficiente para esta app)."""
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


class SheetsClient:
    def __init__(self) -> None:
        self.sheet_id = env("GOOGLE_SHEET_ID")
        self._service = None

    def _svc(self):
        if self._service is None:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
            cred_path = Path(env("GOOGLE_SERVICE_ACCOUNT_FILE", "./config/service-account.json"))
            if not cred_path.is_absolute():
                cred_path = BASE_DIR / cred_path
            creds = service_account.Credentials.from_service_account_file(
                str(cred_path), scopes=["https://www.googleapis.com/auth/spreadsheets"])
            self._service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        return self._service

    def read_objects(self, tab: str, last_col: str = "Z") -> list[dict[str, Any]]:
        """Linhas de `tab` como dicts {cabeçalho: valor}, com _rowIndex (1-indexed,
        linha real na folha — a linha 1 é sempre o cabeçalho, como em todas as
        abas desta app)."""
        res = self._svc().spreadsheets().values().get(
            spreadsheetId=self.sheet_id, range=f"{tab}!A1:{last_col}5000",
            valueRenderOption="UNFORMATTED_VALUE",
        ).execute(num_retries=3)
        rows = res.get("values", [])
        if not rows:
            return []
        headers = [str(h).strip() for h in rows[0]]
        out = []
        for i, row in enumerate(rows[1:]):
            obj: dict[str, Any] = {}
            for idx, h in enumerate(headers):
                obj[h] = row[idx] if idx < len(row) else ""
            if not any(v not in ("", None) for v in obj.values()):
                continue
            obj["_rowIndex"] = i + 2
            out.append(obj)
        return out

    def append_rows(self, tab: str, rows: list[list[Any]]) -> None:
        """UM pedido só com todas as linhas (nunca várias em paralelo — ver a
        lição da Beta 35 no PROJECT-CONTEXT.md: appends concorrentes ao mesmo
        intervalo corrompem-se uns aos outros)."""
        if not rows:
            return
        self._svc().spreadsheets().values().append(
            spreadsheetId=self.sheet_id, range=f"{tab}!A1", valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS", body={"values": rows},
        ).execute(num_retries=3)

    def update_cells(self, tab: str, row_index: int, **col_valor: Any) -> None:
        """Escreve só as colunas dadas (uma célula por coluna, pelo NOME —
        resolvido contra o cabeçalho real —, nunca reescreve a linha toda)."""
        if not col_valor:
            return
        cols = self._header(tab)
        data = []
        for nome, valor in col_valor.items():
            if nome not in cols:
                raise ValueError(f"coluna {nome!r} não existe em {tab!r}")
            col = _col_letter(cols.index(nome))
            data.append({"range": f"{tab}!{col}{row_index}", "values": [[valor]]})
        self._svc().spreadsheets().values().batchUpdate(
            spreadsheetId=self.sheet_id,
            body={"valueInputOption": "USER_ENTERED", "data": data},
        ).execute(num_retries=3)

    def _header(self, tab: str) -> list[str]:
        res = self._svc().spreadsheets().values().get(
            spreadsheetId=self.sheet_id, range=f"{tab}!A1:Z1",
            valueRenderOption="UNFORMATTED_VALUE").execute(num_retries=3)
        rows = res.get("values", [])
        return [str(h).strip() for h in (rows[0] if rows else [])]

    def _tab_gid(self, tab: str) -> int | None:
        """gid (id interno) da aba pelo título, ou None se não existir — usado
        para apagar linhas/renomear, que a API pede pelo gid, não pelo nome."""
        res = self._svc().spreadsheets().get(
            spreadsheetId=self.sheet_id, fields="sheets.properties").execute(num_retries=3)
        for s in res.get("sheets", []):
            props = s.get("properties", {})
            if props.get("title") == tab:
                return props.get("sheetId")
        return None

    def tab_exists(self, tab: str) -> bool:
        return self._tab_gid(tab) is not None

    def delete_rows(self, tab: str, row_indices: list[int]) -> None:
        """Apaga as linhas dadas (1-indexed, número real na folha). Um só
        pedido para todas, ordenado de baixo para cima para nenhum deletion
        desalinhar os índices das seguintes dentro do mesmo pedido."""
        if not row_indices:
            return
        gid = self._tab_gid(tab)
        if gid is None:
            raise ValueError(f"aba {tab!r} não existe")
        requests_body = [
            {"deleteDimension": {"range": {
                "sheetId": gid, "dimension": "ROWS",
                "startIndex": i - 1, "endIndex": i,
            }}}
            for i in sorted(row_indices, reverse=True)
        ]
        self._svc().spreadsheets().batchUpdate(
            spreadsheetId=self.sheet_id, body={"requests": requests_body},
        ).execute(num_retries=3)

    def rename_tab(self, old: str, new: str) -> bool:
        """Usado só uma vez, manualmente, para marcar abas descontinuadas
        (ex.: "Subscriptions" -> "Subscriptions (deprecated)") — ver PLANO."""
        gid = self._tab_gid(old)
        if gid is None:
            return False
        self._svc().spreadsheets().batchUpdate(
            spreadsheetId=self.sheet_id,
            body={"requests": [{"updateSheetProperties": {
                "properties": {"sheetId": gid, "title": new},
                "fields": "title",
            }}]},
        ).execute(num_retries=3)
        return True

    # ---- atalhos específicos desta app ----

    def find_config(self, chave: str) -> dict[str, Any] | None:
        return next((r for r in self.read_objects("Config") if str(r.get("Chave", "")).strip() == chave), None)

    def set_config(self, chave: str, valor: Any, notas: str = "") -> None:
        """Encontra a linha pela Chave e atualiza o Valor; se não existir, cria
        uma linha nova — nunca por edição manual da Sheet (ver PLANO)."""
        existente = self.find_config(chave)
        if existente:
            self.update_cells("Config", existente["_rowIndex"], Valor=valor)
        else:
            self.append_rows("Config", [[chave, valor, notas]])


def get_store():
    """Onde vivem os dados (Tarefas, Instancias, Config, Piscina). `TAREFAS_BACKEND=sqlite` usa a base de dados
    local (dados.db, tabelas tarefas_*); qualquer outro valor (por omissão) usa a Sheet, como sempre — é o plano
    de recuo: mudar a variável no .env e reiniciar. As duas têm a mesma interface (read_objects, append_rows,
    update_cells, delete_rows, tab_exists, find_config, set_config)."""
    if env("TAREFAS_BACKEND", "sheets").strip().lower() == "sqlite":
        import store
        return store.SqliteStore()
    return SheetsClient()


def ntfy_cancel(message_id: str, topic: str | None = None) -> bool:
    """Cancela uma mensagem ainda agendada (antes da hora). Uma mensagem que já
    foi entregue não pode ser cancelada — a resposta é simplesmente ignorada
    nesse caso (não é um erro, só já não há nada a fazer)."""
    import requests

    log = get_logger("ntfy")
    base = env("NTFY_SERVER_URL").rstrip("/")
    topic = topic or env("NTFY_TOPIC", TOPICO_LEGADO)
    auth = (env("NTFY_WRITE_USER"), env("NTFY_WRITE_PASSWORD"))
    try:
        r = requests.delete(f"{base}/{topic}/{message_id}", auth=auth, timeout=(4, 10))
        return r.status_code < 500
    except requests.RequestException as e:
        log.warning("Cancelar mensagem %s falhou: %s: %s", message_id, type(e).__name__, e)
        return False
