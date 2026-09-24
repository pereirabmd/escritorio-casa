"""Biblioteca comum dos scripts do bilhetes_cp (corre no Raspberry Pi).

Concentra o que é partilhado e crítico (ver PLANO_FINAL.md):
- carregamento do .env e da configuração não-secreta (app_config)
- cálculo do instante de disparo T-24h, timezone-aware (3.4)
- validação forte dos dados da Config (3.10.3) e cache da última leitura boa (3.10.2)
- sanitização de logs (3.10.8) e logging com rotação (3.10.9)
- notificações ntfy que nunca falham em silêncio (1.1), sempre com popup
- lock + estado interno de cada compra (3.3.1, 3.10.5, 3.10.6)

Nada aqui importa as bibliotecas Google ao nível do módulo, para que os testes
unitários corram em qualquer máquina.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import logging.handlers
import os
import re
import sys
import time
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

BASE_DIR = Path(os.environ.get("BILHETES_CP_HOME") or Path(__file__).resolve().parent.parent)


# ---------------------------------------------------------------------------
# .env e configuração não-secreta
# ---------------------------------------------------------------------------

def load_env(path: Path | None = None) -> None:
    """Carrega o .env para os.environ sem sobrepor variáveis já definidas.

    Aceita valores entre aspas (obrigatórias quando têm espaços) e não trata
    '#' a meio do valor como comentário (podia cortar uma password).
    """
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

_APP_CONFIG: dict | None = None


def app_config() -> dict:
    """config/app_config.json (se existir) ou config/app_config.example.json."""
    global _APP_CONFIG
    if _APP_CONFIG is None:
        for name in ("app_config.json", "app_config.example.json"):
            p = BASE_DIR / "config" / name
            if p.is_file():
                _APP_CONFIG = json.loads(p.read_text(encoding="utf-8"))
                break
        else:
            raise FileNotFoundError("config/app_config.example.json não encontrado")
    return _APP_CONFIG


TZ = ZoneInfo(os.environ.get("TZ") or app_config().get("timezone", "Europe/Lisbon"))
UTC = timezone.utc


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


# ---------------------------------------------------------------------------
# Sanitização de logs (3.10.8) e logging (3.10.9)
# ---------------------------------------------------------------------------

_SENSITIVE_ENV = (
    "CP_PASSWORD", "CP_EMAIL", "CP_PASSENGER_NAME", "CP_PASSENGER_CC",
    "CP_PASSENGER_PHONE", "CP_PASSENGER_NIF", "CP_GREEN_PASS_NUMBER",
    "CP_CONNECT_ID", "CP_CONNECT_SECRET", "CP_API_KEY_TRAVEL",
    "CP_API_KEY_TICKETING", "NTFY_PASSWORD", "NTFY_TOKEN",
)

_REGEXES = [
    (re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*"), "[JWT]"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"), "Bearer [REDIGIDO]"),
    (re.compile(r"(?i)(x-access-token|x-api-key|x-cp-connect-secret|x-cp-connect-id|"
                r"x-cp-client-id|authorization|password|refresh_token|access_token|"
                r"code_verifier|passengerID|fiscalID|clientMobile)([\"']?\s*[:=]\s*[\"']?)"
                r"[^\s\"',}]+"), r"\1\2[REDIGIDO]"),
    (re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+"), "[email]"),
    (re.compile(r"\btk_[a-z0-9]{20,}\b"), "[TOKEN-NTFY]"),
]


def _sensitive_values() -> list[str]:
    values: set[str] = set()
    for key in _SENSITIVE_ENV:
        v = os.environ.get(key, "").strip()
        if len(v) >= 4:
            values.add(v)
            compact = re.sub(r"[\s+]", "", v)
            if compact.upper().startswith("PT") and compact[2:].isdigit():
                compact = compact[2:]
            if len(compact) >= 6:
                values.add(compact)
    return sorted(values, key=len, reverse=True)


def sanitize(text: Any) -> str:
    """Remove de qualquer texto os dados pessoais e credenciais conhecidos."""
    s = str(text)
    for v in _sensitive_values():
        s = s.replace(v, "[REDIGIDO]")
    for rx, repl in _REGEXES:
        s = rx.sub(repl, s)
    return s


class _SanitizeFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = sanitize(record.getMessage())
        record.args = ()
        return True


_LOGGERS: dict[str, logging.Logger] = {}


def get_logger(name: str) -> logging.Logger:
    """Logger para stdout (journald) e ficheiro com rotação em logs/<name>.log."""
    if name in _LOGGERS:
        return _LOGGERS[name]
    logger = logging.getLogger(f"cp.{name}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    try:
        log_dir = BASE_DIR / "logs"
        log_dir.mkdir(exist_ok=True)
        handlers.append(logging.handlers.RotatingFileHandler(
            log_dir / f"{name}.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8"))
    except OSError as e:  # sem disco/permissões: continua só em stdout, mas visível
        print(f"AVISO: sem log em ficheiro ({e})", file=sys.stderr)
    for h in handlers:
        h.setFormatter(fmt)
        h.addFilter(_SanitizeFilter())
        logger.addHandler(h)
    _LOGGERS[name] = logger
    return logger


# ---------------------------------------------------------------------------
# Notificações ntfy (nunca em silêncio; todas com popup — Priority high)
# ---------------------------------------------------------------------------

def notify(title: str, message: str, *, tags: Iterable[str] = (), at: datetime | None = None,
           logger: logging.Logger | None = None) -> bool:
    """Publica no ntfy com Priority high (popup no Android). Devolve True se 2xx.

    Tenta primeiro NTFY_SERVER_URL e depois o ntfy local do RPi. `at` agenda a
    entrega no servidor (ntfy `delay`), por isso sobrevive a reboots do RPi.
    Se tudo falhar regista o erro em log — nunca engole a falha calada.
    """
    import requests

    log = logger or get_logger("notify")
    payload: dict[str, Any] = {
        "topic": env("NTFY_TOPIC"),
        "title": sanitize(title),
        "message": sanitize(message),
        "priority": 4,
        "tags": list(tags),
    }
    if at is not None:
        payload["delay"] = str(int(at.timestamp()))
    urls = [u for u in (env("NTFY_SERVER_URL"), env("NTFY_LOCAL_URL", "http://127.0.0.1:8080")) if u]
    # Preferir o token de acesso (revogável, sem password); a password fica de reserva.
    creds: list[dict] = []
    if env("NTFY_TOKEN"):
        creds.append({"headers": {"Authorization": f"Bearer {env('NTFY_TOKEN')}"}})
    if env("NTFY_PASSWORD"):
        creds.append({"auth": (env("NTFY_USERNAME"), env("NTFY_PASSWORD"))})
    last_err = ""
    for base in urls:
        for cred in creds or [{}]:
            try:
                r = requests.post(base.rstrip("/") + "/", json=payload, timeout=(4, 10), **cred)
                if 200 <= r.status_code < 300:
                    return True
                last_err = f"{base} -> HTTP {r.status_code}"
                if r.status_code not in (401, 403):
                    break           # erro do servidor: trocar de credencial não ajuda
            except requests.RequestException as e:
                last_err = f"{base} -> {type(e).__name__}"
                break
    log.error("NOTIFICAÇÃO NÃO ENTREGUE (%s): %s | %s", last_err, title, message)
    return False


# ---------------------------------------------------------------------------
# Estado persistente simples: avisos já enviados (evita repetir de 5 em 5 min)
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
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def notify_once(key: str, title: str, message: str, *, cooldown_s: float = 6 * 3600,
                tags: Iterable[str] = (), logger: logging.Logger | None = None) -> bool:
    """Notifica no máximo uma vez por `cooldown_s` para a mesma chave.

    A chave deve identificar a situação (ex.: hash do problema), não a hora. Só
    marca como enviado se a entrega funcionou, para tentar de novo se falhar.
    """
    path = _state_file("notified.json")
    seen = _read_json(path, {})
    now = time.time()
    if now - seen.get(key, 0) < cooldown_s:
        return False
    if notify(title, message, tags=tags, logger=logger):
        seen[key] = now
        seen = {k: v for k, v in seen.items() if now - v < 30 * 86400}
        _write_json_atomic(path, seen)
        return True
    return False


def short_hash(*parts: Any) -> str:
    return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Datas e horas: T-24h timezone-aware (3.4)
# ---------------------------------------------------------------------------

def local_dt(d: date, hhmm: str) -> datetime:
    """Data + 'HH:MM' locais, como datetime com fuso (normalizado via UTC)."""
    h, m = (int(x) for x in hhmm.split(":"))
    naive = datetime(d.year, d.month, d.day, h, m)
    return naive.replace(tzinfo=TZ).astimezone(UTC).astimezone(TZ)


def departure_dt(d: date, hhmm: str) -> datetime:
    return local_dt(d, hhmm)


def fire_time(d: date, hhmm: str) -> datetime:
    """Instante de disparo: dia de calendário anterior, MESMA hora local.

    Não é `partida - 86400s`: nas mudanças de hora (DST) o intervalo real é 23h
    ou 25h, e a janela de venda da CP acompanha a hora do relógio.
    """
    return local_dt(d - timedelta(days=1), hhmm)


def now_local() -> datetime:
    return datetime.now(TZ)


def parse_sheet_date(v: Any) -> date | None:
    """Data vinda da Sheet: serial do Sheets (nº), ISO ou dd/mm/aaaa."""
    if isinstance(v, bool) or v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        try:
            return date(1899, 12, 30) + timedelta(days=int(v))
        except (OverflowError, ValueError):
            return None
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_sheet_time(v: Any) -> str | None:
    """Hora vinda da Sheet: fração do dia (nº) ou 'H:MM'/'HH:MM'[':SS']. Devolve 'HH:MM'."""
    if isinstance(v, bool) or v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        if not 0 <= v < 1:
            return None
        minutes = round(v * 24 * 60)
        if minutes >= 24 * 60:
            return None
        return f"{minutes // 60:02d}:{minutes % 60:02d}"
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})(?::\d{2})?\s*", str(v))
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return None
    return f"{h:02d}:{mi:02d}"


# ---------------------------------------------------------------------------
# Config semanal: leitura, validação forte (3.10.3)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Leg:
    date: date
    leg: str            # id estável da viagem: 'vN' (linha N da Config) ou 'pedidoN' (linha N dos Pedidos)
    origin: str         # chave em app_config.stations
    destination: str
    train: int
    hhmm: str           # partida na estação onde Bruno embarca
    row: int            # linha na Sheet (para mensagens de erro)
    # A janela de venda abre 24 h antes da partida do comboio na sua PRIMEIRA estação, que pode
    # ser anterior à de embarque (o comboio das 07:27 em Aveiro parte do Porto às 06:45). Preenchido
    # por timetable.apply_anchor(); sem estes campos usa-se a hora da Config.
    anchor: str | None = None          # 'HH:MM' da partida na 1.ª estação
    anchor_date: date | None = None    # data dessa partida
    # A hora da Config é a da 1.ª estação (a que abre a venda); a de embarque real (Aveiro 07:27) só é
    # usada para o lembrete, o bilhete e saber se a viagem já passou.
    board: str | None = None           # 'HH:MM' da partida na estação de embarque
    board_date: date | None = None     # data dessa partida
    # Só para pedidos avulsos (3.2.1, leg começa por 'pedido'): Retry/Intervalo_Minutos da aba
    # Pedidos. None em retry_minutes cai no valor de reserva de app_config (pedido_retry_interval_minutes).
    retry: bool = False
    retry_minutes: float | None = None

    @property
    def key(self) -> str:
        return f"{self.date.isoformat()}-{self.leg}"

    @property
    def lock_key(self) -> str:
        return f"{self.date.isoformat()}-{self.leg}-{self.train}"

    @property
    def is_request(self) -> bool:
        """True se vier da aba Pedidos, não da Config semanal (3.2.1)."""
        return self.leg.startswith("pedido")

    @property
    def fire(self) -> datetime:
        if self.is_request:
            return now_local()   # um pedido dispara "agora", recalculado a cada acesso
        return fire_time(self.anchor_date or self.date, self.anchor or self.hhmm)

    @property
    def departure(self) -> datetime:
        return departure_dt(self.board_date or self.date, self.board or self.hhmm)


def norm_station(name: Any) -> str:
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    return re.sub(r"[\s\-]+", "_", s.strip().lower())


def station_code(key: str) -> str | None:
    stations = app_config().get("stations", {})
    if key in stations:
        return stations[key]
    return key if re.fullmatch(r"\d{2}-\d{5}", key) else None


def station_label(key: str) -> str:
    """Nome bonito de uma estação para logs/notificações/Sheet (espelha o `stationLabel` da PWA)."""
    names = app_config().get("station_names", {})
    return names.get(key) or str(key).replace("_", " ").title()


def _to_train(v: Any) -> int | None:
    if isinstance(v, bool) or v in (None, ""):
        return None
    try:
        f = float(str(v).strip().replace(",", "."))
    except ValueError:
        return None
    return int(f) if f == int(f) and f > 0 else None


def _row_id(raw: list[Any], i: int, first_row: int, id_col: int) -> int:
    """Número da viagem (`vN` / `pedidoN`). Na Sheet era a linha (`first_row + i`); na base de dados
    a linha traz o `id` explícito numa coluna extra (`id_col`), estável mesmo que se apaguem outras."""
    if len(raw) > id_col and raw[id_col] not in (None, ""):
        try:
            return int(raw[id_col])
        except (TypeError, ValueError):
            pass
    return first_row + i


def parse_config_rows(rows: list[list[Any]], today: date, first_row: int = 12
                      ) -> tuple[list[Leg], list[str]]:
    """Valida a tabela semanal. Devolve (viagens válidas, problemas em texto).

    Colunas: Data, Origem, Destino, Comboio, Hora, Ativo — uma linha = uma
    viagem, sem par ida/volta (decisão de Bruno, 22/09): mais do que uma
    viagem no mesmo dia é só mais do que uma linha com a mesma Data. Só
    linhas com Ativo=SIM são validadas. Uma linha inválida gera problema e
    não bloqueia as restantes. `leg.leg` é `f"v{linha}"` — um id estável pela
    própria linha da Sheet, não pelo papel (ida/volta) da viagem.
    """
    legs: list[Leg] = []
    issues: list[str] = []
    seen: dict[tuple[date, int, str], int] = {}

    for i, raw in enumerate(rows):
        row = _row_id(raw, i, first_row, 6)
        cells = list(raw) + [""] * (6 - len(raw))
        data_v, org_v, dst_v, train_v, hora_v, ativo = cells[:6]
        if str(ativo).strip().upper() != "SIM":
            continue
        problems: list[str] = []

        d = parse_sheet_date(data_v)
        if d is None:
            problems.append(f"data inválida ({data_v!r})")
        elif d < today:
            problems.append(f"data {d.isoformat()} já passou (linha ativa mas sem efeito)")

        org, dst = norm_station(org_v), norm_station(dst_v)
        if station_code(org) is None:
            problems.append(f"origem desconhecida ({org_v!r})")
        if station_code(dst) is None:
            problems.append(f"destino desconhecido ({dst_v!r})")
        if org and org == dst:
            problems.append("origem igual ao destino")

        train, hora = _to_train(train_v), parse_sheet_time(hora_v)
        if train is None:
            problems.append(f"comboio inválido ({train_v!r})")
        if hora is None:
            problems.append(f"hora inválida ({hora_v!r})")

        if d is not None and train is not None and hora is not None:
            dup_key = (d, train, hora)
            if dup_key in seen:
                problems.append(f"mesmo comboio {train} às {hora} já na linha {seen[dup_key]}")
            else:
                seen[dup_key] = row

        if problems:
            issues.append(f"Linha {row}: " + "; ".join(problems))
            continue

        legs.append(Leg(d, f"v{row}", org, dst, train, hora, row))
    return legs, issues


PASSE_HEADERS = ["Data_Ultima_Compra", "Validade_Dias", "Data_Expira", "Dias_Restantes"]
WEEKLY_HEADERS = ["Data", "Origem", "Destino", "Comboio", "Hora", "Ativo"]


def _hnorm(c: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(c).lower())


def locate_config(values: list[list[Any]]) -> tuple[list[Any], list[list[Any]], int]:
    """Procura os blocos da aba Config pelo NOME dos cabeçalhos, não por posição fixa
    (PLANO_FINAL secção 4): inserir uma linha na Sheet não pode desalinhar a leitura.

    `values` é Config!A1:L300. Devolve (linha do passe nas colunas canónicas,
    linhas semanais nas colunas canónicas, nº da 1ª linha semanal na Sheet).
    Levanta ValueError (nunca lê às cegas) se faltar um cabeçalho.
    """
    def find(heads: list[str]):
        hs = [_hnorm(h) for h in heads]
        for i, row in enumerate(values):
            cells = [_hnorm(c) for c in row]
            if all(h in cells for h in hs):
                return i, [cells.index(h) for h in hs]
        return None

    p, w = find(PASSE_HEADERS), find(WEEKLY_HEADERS)
    if not p or not w:
        falta = [n for n, f in (("bloco do passe", p), ("tabela semanal", w)) if not f]
        raise ValueError("Cabeçalhos da aba Config não encontrados: " + " e ".join(falta))
    pass_row = values[p[0] + 1] if p[0] + 1 < len(values) else []
    passe = [pass_row[i] if i < len(pass_row) else "" for i in p[1]]
    weekly = [[r[i] if i < len(r) else "" for i in w[1]] for r in values[w[0] + 1:]]
    return passe, weekly, w[0] + 2


def parse_snapshot(snap: dict, today: date) -> tuple[list[Leg], list[str]]:
    """parse_config_rows sobre uma leitura da Config (com o nº real da 1ª linha)."""
    return parse_config_rows(snap["weekly"], today, first_row=int(snap.get("first_row", 12)))


# ---------------------------------------------------------------------------
# Pedidos avulsos (3.2.1): retentativa leve de viagens da Config que esgotaram o retry
# ---------------------------------------------------------------------------

REQUEST_HEADERS = ["Data", "Origem", "Destino", "Comboio", "Hora", "Ativo", "Retry",
                   "Intervalo_Minutos", "Forcar", "Estado", "Ultima_Tentativa", "Referencia", "Mensagem"]
REQUEST_TERMINAL = {"CONFIRMADO", "AMBIGUO"}   # nunca se relançam sozinhos, nem por Retry nem por Forçar


def _to_minutes(v: Any) -> float | None:
    if isinstance(v, bool) or v in (None, ""):
        return None
    try:
        f = float(str(v).strip().replace(",", "."))
    except ValueError:
        return None
    return f if f > 0 else None


def parse_request_rows(rows: list[list[Any]], today: date, first_row: int = 5
                       ) -> tuple[list[Leg], list[str]]:
    """Valida a aba Pedidos. Cada linha ativa e válida vira uma `Leg` com `leg='pedidoN'`
    (N = linha na Sheet — chave por si só única, sem par ida/volta). Mesmas regras de validação
    da Config (data/estação/comboio/hora); uma linha inválida gera problema e não bloqueia as
    restantes."""
    legs: list[Leg] = []
    issues: list[str] = []
    for i, raw in enumerate(rows):
        row = _row_id(raw, i, first_row, 13)
        cells = list(raw) + [""] * 13
        data_v, org_v, dst_v, train_v, hora_v, ativo, retry_v, interval_v = cells[:8]
        if str(ativo).strip().upper() != "SIM":
            continue
        problems: list[str] = []

        d = parse_sheet_date(data_v)
        if d is None:
            problems.append(f"data inválida ({data_v!r})")
        elif d < today:
            problems.append(f"data {d.isoformat()} já passou")

        org, dst = norm_station(org_v), norm_station(dst_v)
        if station_code(org) is None:
            problems.append(f"origem desconhecida ({org_v!r})")
        if station_code(dst) is None:
            problems.append(f"destino desconhecido ({dst_v!r})")
        if org and org == dst:
            problems.append("origem igual ao destino")

        train = _to_train(train_v)
        if train is None:
            problems.append(f"comboio inválido ({train_v!r})")
        hora = parse_sheet_time(hora_v)
        if hora is None:
            problems.append(f"hora inválida ({hora_v!r})")

        if problems:
            issues.append(f"Linha {row} (Pedidos): " + "; ".join(problems))
            continue

        legs.append(Leg(d, f"pedido{row}", org, dst, train, hora, row,
                        retry=str(retry_v).strip().upper() == "SIM", retry_minutes=_to_minutes(interval_v)))
    return legs, issues


def request_row(rows: list[list[Any]], row: int, first_row: int = 5) -> list[Any] | None:
    """A linha crua do pedido `row` (o `N` de `pedidoN`), procurada pelo id — nunca por posição."""
    for i, raw in enumerate(rows):
        if _row_id(raw, i, first_row, 13) == row:
            return raw
    return None


# ---------------------------------------------------------------------------
# Onde vivem os dados (Config, Bilhetes, Logs, Pedidos): Google Sheets ou SQLite
# ---------------------------------------------------------------------------

def get_store():
    """A camada de dados atual. `BILHETES_BACKEND=sqlite` usa a base de dados local (bilhetes.db);
    qualquer outro valor (por omissão) usa a Sheet, como sempre. Voltar atrás é mudar esta variável
    no .env e reiniciar o daemon. Ambas têm a mesma interface (read_config, read_tickets, read_requests,
    append_log, append_ticket, append_request, update_request)."""
    if env("BILHETES_BACKEND", "sheets").strip().lower() == "sqlite":
        import store
        return store.SqliteStore()
    return SheetsClient()


# ---------------------------------------------------------------------------
# Google Sheets (bibliotecas oficiais; importadas só quando necessárias)
# ---------------------------------------------------------------------------

class SheetsClient:
    """Acesso à Sheet via service account (google-api-python-client)."""

    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

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
                str(cred_path), scopes=self.SCOPES)
            self._service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        return self._service

    def read_config(self) -> dict:
        res = self._svc().spreadsheets().values().get(
            spreadsheetId=self.sheet_id, range="Config!A1:L300",
            valueRenderOption="UNFORMATTED_VALUE", dateTimeRenderOption="SERIAL_NUMBER",
        ).execute(num_retries=3)
        passe, weekly, first_row = locate_config(res.get("values", []))
        return {
            "fetched_at": datetime.now(UTC).isoformat(),
            "passe": passe,
            "weekly": weekly,
            "first_row": first_row,
        }

    def read_tickets(self) -> list[list[Any]]:
        res = self._svc().spreadsheets().values().get(
            spreadsheetId=self.sheet_id, range="Bilhetes!A5:H1000",
            valueRenderOption="UNFORMATTED_VALUE", dateTimeRenderOption="FORMATTED_STRING",
        ).execute(num_retries=3)
        return res.get("values", [])

    def _append(self, tab: str, row: list[Any]) -> None:
        # RAW: nunca interpretar texto de erro como fórmula
        self._svc().spreadsheets().values().append(
            spreadsheetId=self.sheet_id, range=f"{tab}!A5", valueInputOption="RAW",
            insertDataOption="INSERT_ROWS", body={"values": [[sanitize(c) if isinstance(c, str) else c for c in row]]},
        ).execute(num_retries=3)

    def append_log(self, tipo: str, data_viagem: str = "", perna: str = "", comboio: Any = "",
                   status_http: Any = "", resultado: str = "", referencia: str = "",
                   mensagem_erro: str = "") -> None:
        self._append("Logs", [datetime.now(TZ).isoformat(timespec="milliseconds"), tipo,
                              data_viagem, perna, comboio, status_http, resultado,
                              referencia, mensagem_erro])

    def append_ticket(self, data: str, comboio: Any, origem: str, destino: str,
                      hora: str, carruagem: Any, lugar: Any, referencia: str) -> None:
        self._append("Bilhetes", [data, comboio, origem, destino, hora, carruagem, lugar, referencia])

    def read_requests(self) -> list[list[Any]]:
        res = self._svc().spreadsheets().values().get(
            spreadsheetId=self.sheet_id, range="Pedidos!A5:M1000",
            valueRenderOption="UNFORMATTED_VALUE", dateTimeRenderOption="SERIAL_NUMBER",
        ).execute(num_retries=3)
        return res.get("values", [])

    def append_request(self, data: str, origem: str, destino: str, comboio: Any, hora: str,
                       ativo: str = "SIM", retry: str = "NAO", intervalo: Any = "",
                       estado: str = "PENDENTE") -> None:
        self._append("Pedidos", [data, origem, destino, comboio, hora, ativo, retry, intervalo,
                                 "NAO", estado, "", "", ""])

    _REQUEST_COLS = {"data": "A", "origem": "B", "destino": "C", "comboio": "D", "hora": "E",
                     "ativo": "F", "retry": "G", "intervalo_minutos": "H", "forcar": "I",
                     "estado": "J", "ultima_tentativa": "K", "referencia": "L", "mensagem": "M"}

    def update_request(self, row: int, **fields: Any) -> None:
        """Escreve só os campos dados (uma célula por campo, nunca reescreve a linha toda)."""
        data = []
        for name, value in fields.items():
            col = self._REQUEST_COLS.get(name)
            if col is None:
                raise ValueError(f"coluna de Pedidos desconhecida: {name!r}")
            data.append({"range": f"Pedidos!{col}{row}", "values": [[sanitize(value) if isinstance(value, str) else value]]})
        if not data:
            return
        self._svc().spreadsheets().values().batchUpdate(
            spreadsheetId=self.sheet_id,
            body={"valueInputOption": "RAW", "data": data},
        ).execute(num_retries=3)


TOKEN_FILE = BASE_DIR / "token.json"


def save_tokens(tokens: dict) -> None:
    """Guarda os tokens mais recentes em token.json (chmod 600, fora do git; PLANO_FINAL 3.1)."""
    now = time.time()
    _write_json_atomic(TOKEN_FILE, {
        "access_token": tokens.get("access_token"), "refresh_token": tokens.get("refresh_token"),
        "access_expires_at": now + float(tokens.get("expires_in", 300)),
        "refresh_expires_at": now + float(tokens.get("refresh_expires_in", 1799)),
        "saved_at": datetime.now(TZ).isoformat(timespec="seconds"),
    })


def load_tokens() -> dict | None:
    data = _read_json(TOKEN_FILE, None)
    return data if isinstance(data, dict) and data.get("access_token") else None


CACHE_FILE = BASE_DIR / "config_cache.json"


def save_config_cache(snapshot: dict) -> None:
    _write_json_atomic(CACHE_FILE, snapshot)


def load_config_cache() -> dict | None:
    data = _read_json(CACHE_FILE, None)
    return data if isinstance(data, dict) and "weekly" in data else None


# ---------------------------------------------------------------------------
# Lock + estado interno de cada compra (3.3.1, 3.10.5, 3.10.6)
# ---------------------------------------------------------------------------

STATES = ["SCHEDULED", "WARMING", "SALE_CREATED", "PASSENGERS_OK", "CLIENT_OK",
          "FISCAL_OK", "DISCOUNT_OK", "CONFIRMED"]
TERMINAL = {"CONFIRMED", "SOLD_OUT", "FAILED", "AMBIGUOUS"}


def lock_path(lock_key: str) -> Path:
    d = BASE_DIR / "locks"
    d.mkdir(mode=0o700, exist_ok=True)
    return d / f"{lock_key}.json"


def peek_state(lock_key: str) -> dict:
    """Lê o estado sem adquirir o lock (para o Scheduler)."""
    return _read_json(lock_path(lock_key), {})


class PurchaseLock:
    """flock exclusivo por data+perna+comboio; o mesmo ficheiro guarda o estado."""

    def __init__(self, lock_key: str) -> None:
        self.path = lock_path(lock_key)
        self._fd: int | None = None
        self.state: dict = {}

    def acquire(self) -> bool:
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return False
        self._fd = fd
        raw = os.read(fd, 1_000_000).decode("utf-8") if os.fstat(fd).st_size else ""
        try:
            self.state = json.loads(raw) if raw.strip() else {}
        except ValueError:
            self.state = {"corrupted_state_backup": raw[:200]}
        return True

    def update(self, **fields: Any) -> None:
        assert self._fd is not None, "lock não adquirido"
        self.state.update(fields)
        self.state["updated_at"] = datetime.now(TZ).isoformat(timespec="milliseconds")
        data = json.dumps(self.state, ensure_ascii=False, indent=1).encode("utf-8")
        os.lseek(self._fd, 0, os.SEEK_SET)
        os.ftruncate(self._fd, 0)
        os.write(self._fd, data)
        os.fsync(self._fd)

    def release(self) -> None:
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> "PurchaseLock":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.release()
