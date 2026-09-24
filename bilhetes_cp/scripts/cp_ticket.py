"""
Cliente da API da CP (Comboios de Portugal) para compra com Passe Ferroviário Verde.

Fluxo: login (Keycloak/OAuth2 PKCE) -> pesquisa -> criar venda -> preencher
passageiro/cliente/dados fiscais -> aplicar desconto/passe -> confirmar.

Este módulo é a biblioteca usada por `hot_buy.py` (o processo de compra
agendado). Continua a poder ser corrido à mão (`python cp_ticket.py --origem ...`)
para comprar de imediato, mas o uso normal é via Scheduler (ver PLANO_FINAL.md).

IMPORTANTE:
- Usa a API interna do site cp.pt, obtida a partir de um HAR capturado
  manualmente. A CP pode alterá-la a qualquer momento sem aviso.
- Todos os dados pessoais vêm de variáveis de ambiente (.env), nunca hardcoded.
- Só para a tua própria conta/passe. Uso abusivo ou em nome de terceiros pode
  violar os Termos e Condições da Bilheteira Online da CP.
- Nunca há retries automáticos escondidos: a sessão HTTP tem max_retries=0 e é
  a política de 3.3.1 (em hot_buy.py) que decide se e quando repetir.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import sys
import time
import urllib.parse as up
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import requests
from requests.adapters import HTTPAdapter

import common  # noqa: F401  (carrega o .env antes de ler os.environ)

# ---------------------------------------------------------------------------
# Configuração - lida de variáveis de ambiente (ver ficheiro .env.example)
# ---------------------------------------------------------------------------

CP_EMAIL = os.environ["CP_EMAIL"]
CP_PASSWORD = os.environ["CP_PASSWORD"]

PASSENGER_NAME = os.environ["CP_PASSENGER_NAME"]
PASSENGER_CC = os.environ["CP_PASSENGER_CC"]          # nº Cartão de Cidadão
PASSENGER_PHONE = os.environ["CP_PASSENGER_PHONE"]     # ex: PT9XXXXXXXX
PASSENGER_NIF = os.environ["CP_PASSENGER_NIF"]
GREEN_PASS_NUMBER = os.environ["CP_GREEN_PASS_NUMBER"]  # nº do Passe Ferroviário Verde

# Só para o uso manual (CLI). O sistema agendado lê as estações de app_config.
STATION_CODES = {
    "aveiro": "94-38000",
    "lisboa_oriente": "94-31039",
}

TRAVEL_CLASS = 2  # 2 = 2ª classe / turística

# --- Endpoints ---
LOGIN_BASE = "https://login.cp.pt/realms/cpclients"
AUTH_ENDPOINT = f"{LOGIN_BASE}/protocol/openid-connect/auth"
TOKEN_ENDPOINT = f"{LOGIN_BASE}/protocol/openid-connect/token"
API_BASE = "https://api-gateway.cp.pt/cp/services"

CLIENT_ID = "websitecp"
REDIRECT_URI = "https://cp.pt/pt/login-check"

# Chaves/headers estáticos observados no tráfego do site (embutidos no JS do
# frontend, não são segredos pessoais).
X_CP_CONNECT_ID = os.environ.get("CP_CONNECT_ID", "")
X_CP_CONNECT_SECRET = os.environ.get("CP_CONNECT_SECRET", "")
X_API_KEY_TRAVEL = os.environ.get("CP_API_KEY_TRAVEL", "")
X_API_KEY_TICKETING = os.environ.get("CP_API_KEY_TICKETING", "")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
)

# (ligar, ler) em segundos. Curtos: no caminho crítico um pedido pendurado é pior
# do que um erro claro.
TIMEOUT_CONNECT_READ = (4.0, 12.0)


def make_session() -> requests.Session:
    """Sessão com ligação reutilizável e SEM retries automáticos."""
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    adapter = HTTPAdapter(max_retries=0, pool_connections=2, pool_maxsize=2)
    s.mount("https://", adapter)
    return s


# ---------------------------------------------------------------------------
# Respostas e erros
# ---------------------------------------------------------------------------

class CPError(Exception):
    """Falha numa chamada à CP.

    kind:
      'not_sent'  — falhou antes do pedido chegar ao servidor (retry seguro)
      'ambiguous' — o pedido pode ter sido entregue e a resposta perdeu-se
      'http'      — o servidor respondeu com erro (ver .response)
    """

    def __init__(self, kind: str, message: str, response: "CPResponse | None" = None):
        super().__init__(message)
        self.kind = kind
        self.response = response


@dataclass
class CPResponse:
    status: int
    body: Any
    text: str
    date_header: str | None
    sent_at: float          # time.time() imediatamente antes de enviar
    received_at: float      # time.time() ao receber a resposta
    elapsed_ms: float
    messages: list[str] = field(default_factory=list)
    new_conn: bool | None = None   # True = este pedido abriu uma ligação nova (DNS+TCP+TLS ≈ 250 ms no Pi); None = desconhecido
    retry_after_s: float | None = None

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


def extract_messages(body: Any) -> list[str]:
    """Extrai o(s) aviso/erro da resposta. A CP usa dois formatos vistos até agora: um campo
    `messages` (lista, previsto no HAR original) ou, numa recusa real de 22/09 (HTTP 500,
    `error: WS:RES:116`, comboio esgotado), campos `error`/`description`/`message` ao nível de topo,
    sem `messages` nenhuns. Ler os dois, para nunca cair no `resp.text` cru sem necessidade."""
    if not isinstance(body, dict):
        return []
    if body.get("messages"):
        raw = body["messages"]
        entries = raw if isinstance(raw, list) else [raw]
        out: list[str] = []
        for e in entries:
            if isinstance(e, dict):
                parts = [str(e[k]) for k in ("type", "level", "severity", "code", "message", "text",
                                               "description", "detail") if e.get(k)]
                out.append(" | ".join(parts) if parts else str(e))
            else:
                out.append(str(e))
        return out
    parts = [str(body[k]) for k in ("error", "message", "description") if body.get(k)]
    return [" | ".join(parts)] if parts else []


def has_error_message(messages: list[str]) -> bool:
    return any(re.search(r"\b(error|erro|fatal|blocking)\b", m, re.I) for m in messages)


_NOT_SENT_REASONS = ("NewConnectionError", "NameResolutionError", "ConnectTimeoutError",
                     "SSLError", "ProtocolError")


def _is_not_sent(exc: Exception) -> bool:
    """True se a falha aconteceu ao estabelecer a ligação (o pedido nunca saiu)."""
    if isinstance(exc, (requests.ConnectTimeout, requests.exceptions.SSLError)):
        return True
    if isinstance(exc, requests.ConnectionError):
        reason = getattr(exc.args[0], "reason", None) if exc.args else None
        name = type(reason).__name__ if reason is not None else ""
        return name in ("NewConnectionError", "NameResolutionError", "ConnectTimeoutError",
                        "SSLError")
    return False


# Só o que diz inequivocamente "sem lugares". "Indisponível" fica de fora de propósito: pode ser
# "ainda não aberto", e tratá-lo como esgotado seria perder o bilhete; repetir por engano não custa nada.
SOLD_OUT_RX = re.compile(r"esgotad|sem\s+lugar|n[aã]o\s+h[aá]\s+lugar|lotad|sold.?out|no\s+seats", re.I)

# Código de erro visto numa recusa real (22/09, HTTP 500): esgotado, sem ambiguidade nenhuma —
# mais fiável do que qualquer padrão de texto, e cobre o caso de vir traduzido de outra forma.
SOLD_OUT_CODES = {"WS:RES:116"}

# "Ainda não aberto" (venda que abre mais tarde do que o previsto). O formato real da resposta da CP
# ainda não foi observado (PLANO_FINAL 2.7): estes padrões são um palpite a confirmar com os logs.
NOT_OPEN_RX = re.compile(
    r"ainda\s+n[aã]o|n[aã]o\s+(est[aá]\s+)?abert|not\s+yet|too\s+early|fora\s+d[oa]\s+(prazo|per[ií]odo)|"
    r"anteced[eê]ncia|per[ií]odo\s+de\s+venda|sale\s+(is\s+)?not\s+open|indispon[ií]vel|opens?\s+(at|on|in)", re.I)


def classify_sale_response(resp: CPResponse) -> tuple[str, str]:
    """Classifica a resposta do POST /sale (3.3.1).

    Devolve (categoria, detalhe) com categoria em:
      'ok'         — venda criada (há saleID)
      'sold_out'   — esgotado: notificar e parar
      'not_open'   — a venda ainda não abriu (nada foi criado): repetir na iteração seguinte
      'known'      — recusa não reconhecida (4xx): repete-se só durante uma janela curta, depois falha
      'transient'  — 5xx/429: retry seguro
    O critério de sucesso é POSITIVO (existir saleID), não só o HTTP 200.
    """
    body = resp.body if isinstance(resp.body, dict) else {}
    text = " ".join(resp.messages) or resp.text[:300]
    if resp.ok and body.get("saleID"):
        return "ok", f"saleID={body['saleID']}"
    # A mensagem de negócio manda mais do que o código HTTP de transporte: um 500 real (22/09,
    # WS:RES:116) veio a dizer "sem lugares", não erro de servidor — verificar SEMPRE antes do 5xx.
    if body.get("error") in SOLD_OUT_CODES or SOLD_OUT_RX.search(text) or SOLD_OUT_RX.search(resp.text[:2000]):
        return "sold_out", text
    if NOT_OPEN_RX.search(text) or NOT_OPEN_RX.search(resp.text[:2000]):
        return "not_open", text
    if resp.status >= 500 or resp.status == 429:
        return "transient", f"HTTP {resp.status}"
    if resp.ok:
        return "known", f"HTTP {resp.status} sem saleID: {text}"
    return "known", f"HTTP {resp.status}: {text}"


# ---------------------------------------------------------------------------
# Mapa de lugares (24/09/2026)
# ---------------------------------------------------------------------------
# Cada carruagem tem `rows` = LINHAS da disposição (não filas): num 2+2 são 5 — duas de lugares, uma de CORREDOR (todos os
# `places` sem `seatNumber`), duas de lugares. Os lugares nas linhas vizinhas do corredor são «corredor»; os das pontas, «janela».
# `statusCode`: 0 livre · 1 e 3 ocupado/fora de venda («lugar ocupado») · 2 o lugar desta venda. `placeType` 1/2 = os lugares
# normais (7/9 = lugares especiais: não os escolher).

FREE, MINE = 0, 2


def seat_position(rows: list[dict], i: int) -> str | None:
    """'corredor' | 'janela' | None para a linha i de uma carruagem (None se a linha for o próprio corredor ou não há corredor)."""
    def is_aisle(r: dict) -> bool:
        return bool(r.get("places")) and all("seatNumber" not in p for p in r["places"])
    if is_aisle(rows[i]):
        return None
    aisles = [k for k, r in enumerate(rows) if is_aisle(r)]
    if not aisles:
        return None
    return "corredor" if any(abs(i - k) == 1 for k in aisles) else "janela"


def seats_by_position(seat_map: Any) -> list[dict]:
    """Todos os lugares normais do mapa como dicts {carriage, seat, position, status, placeType, table, plug}."""
    out: list[dict] = []
    for c in (seat_map or {}).get("carriages", []) if isinstance(seat_map, dict) else []:
        rows = c.get("rows") or []
        for i, r in enumerate(rows):
            pos = seat_position(rows, i)
            for p in r.get("places", []):
                if "seatNumber" not in p:
                    continue
                out.append({"carriage": c.get("number"), "seat": p["seatNumber"], "position": pos, "status": p.get("statusCode"),
                            "placeType": p.get("placeType"), "table": bool(p.get("withTable")), "plug": bool(p.get("plugType"))})
    return out


def pick_aisle_seats(seat_map: Any, cur_carriage: Any, cur_seat: Any, limit: int = 6) -> list[tuple[int, int]]:
    """Lugares livres ao corredor, do melhor para o pior: na mesma carruagem primeiro e depois os mais perto do lugar
    atual. [] se o lugar atual já é corredor (ou não se percebe o mapa): nada a mudar."""
    seats = seats_by_position(seat_map)
    mine = next((s for s in seats if s["carriage"] == cur_carriage and s["seat"] == cur_seat), None)
    if mine is None or mine["position"] in (None, "corredor"):
        return []
    livres = [s for s in seats if s["status"] == FREE and s["position"] == "corredor" and s["placeType"] in (1, 2)]
    livres.sort(key=lambda s: (s["carriage"] != cur_carriage, abs((s["seat"] or 0) - (cur_seat or 0))))
    return [(s["carriage"], s["seat"]) for s in livres[:limit]]


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------

def make_pkce_pair():
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode()
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return verifier, challenge


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def login() -> dict:
    """Login via Keycloak com PKCE; devolve os tokens (access/refresh)."""
    session = make_session()

    verifier, challenge = make_pkce_pair()
    state = secrets.token_hex(16)
    nonce = secrets.token_hex(16)

    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "state": state,
        "response_mode": "fragment",
        "response_type": "code",
        "scope": "openid",
        "nonce": nonce,
        "ui_locales": "pt",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    r = session.get(AUTH_ENDPOINT, params=params, timeout=TIMEOUT_CONNECT_READ)
    r.raise_for_status()

    match = re.search(r'action="([^"]+)"', r.text)
    if not match:
        raise RuntimeError(
            "Não encontrei o formulário de login na página (a CP pode ter "
            "mudado o HTML, ou pode haver CAPTCHA/MFA ativo)."
        )
    form_action = match.group(1).replace("&amp;", "&")

    r = session.post(
        form_action,
        data={"username": CP_EMAIL, "password": CP_PASSWORD, "credentialId": ""},
        allow_redirects=False,
        timeout=TIMEOUT_CONNECT_READ,
    )
    if r.status_code != 302 or "location" not in r.headers:
        raise RuntimeError(
            f"Login falhou (status {r.status_code}). Verifica as credenciais "
            "ou se apareceu algum passo extra (CAPTCHA/MFA) que o script não sabe tratar."
        )

    location = r.headers["location"]
    fragment_params = up.parse_qs(up.urlsplit(location).fragment)
    if "code" not in fragment_params:
        raise RuntimeError("Não veio nenhum 'code' no redirect de login.")
    auth_code = fragment_params["code"][0]

    r = session.post(
        TOKEN_ENDPOINT,
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        },
        timeout=TIMEOUT_CONNECT_READ,
    )
    r.raise_for_status()
    return r.json()


def refresh_tokens(refresh_token: str) -> dict:
    r = requests.post(
        TOKEN_ENDPOINT,
        data={"grant_type": "refresh_token", "refresh_token": refresh_token,
              "client_id": CLIENT_ID},
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT_CONNECT_READ,
    )
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# API CP
# ---------------------------------------------------------------------------

class CPClient:
    def __init__(self, access_token: str, session: requests.Session | None = None):
        self.access_token = access_token
        self.session = session or make_session()

    def _headers(self, api_key: str, with_client_id: bool = False, with_token: bool = True) -> dict:
        h = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "X-Api-Key": api_key,
            "x-cp-connect-id": X_CP_CONNECT_ID,
            "x-cp-connect-secret": X_CP_CONNECT_SECRET,
        }
        if with_token:
            h["x-access-token"] = self.access_token
        if with_client_id:
            h["x-cp-client-id"] = CP_EMAIL
        return h

    def request(self, method: str, path: str, *, api_key: str, body: Any = None,
                with_client_id: bool = False, with_token: bool = True,
                timeout: tuple[float, float] = TIMEOUT_CONNECT_READ) -> CPResponse:
        """Um único pedido, sem retries. Levanta CPError só para falhas de rede."""
        url = path if path.startswith("http") else f"{API_BASE}{path}"
        headers = self._headers(api_key, with_client_id, with_token)
        pool = self._pool(url)
        conns_before = getattr(pool, "num_connections", None)
        t0 = time.perf_counter()
        sent_at = time.time()
        try:
            r = self.session.request(method, url, json=body, headers=headers, timeout=timeout)
        except requests.RequestException as e:
            kind = "not_sent" if _is_not_sent(e) else "ambiguous"
            raise CPError(kind, f"{type(e).__name__} em {method} {path}") from e
        received_at = time.time()
        conns_after = getattr(pool, "num_connections", None)
        new_conn = (conns_after > conns_before) if isinstance(conns_before, int) and isinstance(conns_after, int) else None
        try:
            retry_after = float(r.headers.get("Retry-After", ""))
        except ValueError:
            retry_after = None
        try:
            data = r.json() if r.content else None
        except ValueError:
            data = None
        return CPResponse(
            status=r.status_code, body=data, text=r.text, date_header=r.headers.get("Date"),
            sent_at=sent_at, received_at=received_at,
            elapsed_ms=(time.perf_counter() - t0) * 1000, messages=extract_messages(data),
            new_conn=new_conn, retry_after_s=retry_after,
        )

    def _pool(self, url: str):
        """O pool de ligações que vai servir este URL (para saber se o pedido abriu uma ligação nova)."""
        try:
            return self.session.get_adapter(url).poolmanager.connection_from_url(url)
        except Exception:  # noqa: BLE001 — só diagnóstico; nunca pode estragar um pedido
            return None

    def _checked(self, method: str, path: str, **kw: Any) -> CPResponse:
        """Pedido cujo sucesso exige 2xx e nenhuma mensagem de erro."""
        resp = self.request(method, path, **kw)
        if not resp.ok:
            raise CPError("http", f"HTTP {resp.status} em {method} {path}: "
                                  f"{' / '.join(resp.messages) or resp.text[:200]}", resp)
        if has_error_message(resp.messages):
            raise CPError("http", f"mensagens de erro em {method} {path}: "
                                  f"{' / '.join(resp.messages)}", resp)
        return resp

    # -- ligação --

    def warm(self, train: int | None = None, day: str | None = None) -> CPResponse | None:
        """Estabelece/mantém a ligação TCP/TLS à CP para o pedido crítico.

        NÃO usar `HEAD /`: a CP responde 404 com `Connection: close` e fecha a ligação (medido em 24/09/2026: cada
        «aquecimento» destruía a ligação e o POST /sale de T pagava DNS+TCP+TLS ≈ 250 ms, no Pi 3). O horário de um
        comboio é um pedido leve, sem login, que devolve `Connection: Keep-Alive` (200 ou 404): o pedido seguinte
        reutiliza a ligação (26–90 ms em vez de ~300 ms). A ligação aguenta parada pelo menos 120 s."""
        path = f"/travel-api/trains/{train or 731}/timetable/{day or date.today().isoformat()}"
        try:
            return self.request("GET", path, api_key=X_API_KEY_TRAVEL, with_token=False, timeout=(4.0, 6.0))
        except CPError:
            return None

    def get_seat_map(self, sale_id: int, train: int) -> Any:
        """Mapa de lugares do comboio para esta venda (`GET /train-seats/{venda}/trains/{n}`, ~40 KB, ~280 ms)."""
        return self._checked("GET", f"/ticketing-api/train-seats/{sale_id}/trains/{train}",
                             api_key=X_API_KEY_TICKETING, with_client_id=True).body

    def change_seat(self, sale_id: int, train: int, from_carriage: int, from_seat: int,
                    to_carriage: int, to_seat: int) -> CPResponse:
        """Muda o lugar de uma venda PENDENTE (`PUT /train-seats/{venda}`; descoberto em 24/09/2026 pelas mensagens de erro:
        `originalSeats` + `requestedSeats`). Lugar ocupado → 500 `WS:RES:120 «lugar ocupado»` (CPError)."""
        body = {"originalSeats": [{"trainNumber": train, "carriageNumber": from_carriage, "seatNumber": from_seat}],
                "requestedSeats": [{"trainNumber": train, "carriageNumber": to_carriage, "seatNumber": to_seat}]}
        return self._checked("PUT", f"/ticketing-api/train-seats/{sale_id}", api_key=X_API_KEY_TICKETING,
                             body=body, with_client_id=True)

    def cancel_sale(self, sale_id: int) -> CPResponse | None:
        """Cancela uma venda pendente e liberta o lugar (`DELETE /sale/{id}` → 200 «CANCELLED»; testado 24/09/2026).
        Melhor esforço: nunca levanta."""
        try:
            return self.request("DELETE", f"/ticketing-api/sale/{sale_id}", api_key=X_API_KEY_TICKETING,
                                with_client_id=True, timeout=(4.0, 10.0))
        except CPError:
            return None

    # -- pesquisa --

    def search_journeys(self, origin_code: str, dest_code: str, travel_date: str) -> dict:
        body = {
            "arrivalStationCode": dest_code,
            "classes": [TRAVEL_CLASS],
            "configID": 200,
            "departureStationCode": origin_code,
            "lang": "PT",
            "quantities": [{"quantity": 1, "type": 1}],
            "returnDate": None,
            "returnTimeLimit": {"endTime": "23:59", "limitType": 0, "startTime": "00:00"},
            "saleableOnly": False,
            "searchType": 3,
            "services": [],
            "timeLimit": {"endTime": "23:59", "limitType": 0, "startTime": "00:00"},
            "travelDate": travel_date,
            "username": "sivNetticket",
        }
        return self._checked("POST", "/travel-api/journeys", api_key=X_API_KEY_TRAVEL,
                             body=body).body

    # -- venda --

    def create_sale_request(self, travel_date: str, sections: list[dict]) -> CPResponse:
        """POST /sale: UM pedido, sem retries, resposta crua (classificar depois).

        `sections` vem de `trip_sections()`: uma entrada de `outwardTrip` por secção da
        viagem (PLANO_FINAL 2.2 e 7.3) — num comboio directo é uma só.
        """
        body = {
            "quantity": 1,
            "travelClass": {"code": str(TRAVEL_CLASS)},
            "travelDate": travel_date,
            "outwardTrip": [{
                "trainNumber": s["train"],
                "departureStation": {"code": s["dep"]},
                "arrivalStation": {"code": s["arr"]},
                "serviceCode": {"code": s["code"], "designation": s["designation"]},
            } for s in sections],
            "lang": "pt",
        }
        return self.request("POST", "/ticketing-api/sale", api_key=X_API_KEY_TICKETING,
                            body=body, with_client_id=True)

    def set_passengers(self, sale_id: int) -> CPResponse:
        body = {"salePassengers": [{
            "idtype": {"code": "CC", "designation": "Cartão de Cidadão"},
            "passengerID": PASSENGER_CC,
            "passengerName": PASSENGER_NAME,
        }]}
        return self._checked("PUT", f"/ticketing-api/sale/{sale_id}/passengers",
                             api_key=X_API_KEY_TICKETING, body=body, with_client_id=True)

    def set_client(self, sale_id: int) -> CPResponse:
        body = {"clientEmail": CP_EMAIL, "clientID": CP_EMAIL,
                "clientMobile": PASSENGER_PHONE, "clientName": PASSENGER_NAME}
        return self._checked("PUT", f"/ticketing-api/sale/{sale_id}/client",
                             api_key=X_API_KEY_TICKETING, body=body, with_client_id=True)

    def set_fiscal(self, sale_id: int) -> CPResponse:
        body: dict = {"countryCode": "PT", "fiscalID": PASSENGER_NIF, "fiscalName": PASSENGER_NAME}
        addr = fiscal_address()
        if addr is not None:
            body["fiscalAddress"] = addr
        return self._checked("PUT", f"/ticketing-api/sale/{sale_id}/fiscal",
                             api_key=X_API_KEY_TICKETING, body=body, with_client_id=True)

    def apply_green_pass(self, sale_id: int) -> CPResponse:
        """Aplica o desconto do Passe Ferroviário Verde (equivalente à dropdown)."""
        body = {"requestedItems": [{
            "itemCode": "302", "relatedTrain": None, "ticketIndex": 0,
            "type": "DISCOUNT", "inputData": GREEN_PASS_NUMBER,
        }]}
        return self._checked("PUT", f"/ticketing-api/sale/{sale_id}/items",
                             api_key=X_API_KEY_TICKETING, body=body, with_client_id=True)

    def get_sale(self, sale_id: int) -> CPResponse:
        """Estado de uma venda em qualquer estado (PLANO_FINAL 2.2): última fonte do lugar atribuído."""
        return self._checked("GET", f"/ticketing-api/sales/{sale_id}",
                             api_key=X_API_KEY_TICKETING, with_client_id=True)

    def confirm(self, sale_id: int) -> CPResponse:
        return self._checked("PUT", f"/ticketing-api/sale/{sale_id}/confirm",
                             api_key=X_API_KEY_TICKETING, with_client_id=True)


# ---------------------------------------------------------------------------
# Escolha do comboio
# ---------------------------------------------------------------------------

def pick_trip(journeys: dict, target_time: str | None = None,
              train_number: int | None = None, require_saleable: bool = True) -> dict:
    """Escolhe a viagem por nº de comboio exato (prioridade), por hora aproximada,
    ou a primeira se nada for indicado.

    `require_saleable=False` serve a véspera/pre-flight: antes de abrir a janela
    de venda o comboio ainda não é vendável online, mas já existe e tem serviceCode.
    """
    trips = journeys.get("outwardTrip", []) or []
    if require_saleable:
        trips = [t for t in trips if t.get("saleableOnline")]
    if not trips:
        raise RuntimeError("Nenhuma viagem encontrada para esta data"
                           + (" (vendável online)." if require_saleable else "."))

    if train_number is not None:
        for t in trips:
            if any(s["trainNumber"] == train_number for s in t["travelSections"]):
                return t
        disponiveis = sorted({s["trainNumber"] for t in trips for s in t["travelSections"]})
        raise RuntimeError(f"Comboio nº {train_number} não encontrado nesta data. "
                           f"Comboios disponíveis: {disponiveis}")

    if not target_time:
        return trips[0]

    def to_min(hhmm: str) -> int:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)

    target = to_min(target_time)
    return min(trips, key=lambda t: abs(to_min(t["departureTime"]) - target))


def find_section(trip: dict, train_number: int) -> dict:
    for s in trip["travelSections"]:
        if s["trainNumber"] == train_number:
            return s
    return trip["travelSections"][0]


def trip_sections(trip: dict, default_dep: str | None = None, default_arr: str | None = None) -> list[dict]:
    """Secções da viagem no formato do POST /sale: uma por comboio (com transbordo, várias).

    Cada secção traz as suas estações e o seu serviceCode. Num comboio directo cujo
    horário não traga códigos de estação, usa `default_dep`/`default_arr`; num transbordo
    não se adivinha: falta de dados é erro claro, nunca uma compra com estações trocadas.
    """
    out = []
    raw = trip["travelSections"]
    for s in raw:
        dep = (s.get("departureStation") or {}).get("code") or (default_dep if len(raw) == 1 else None)
        arr = (s.get("arrivalStation") or {}).get("code") or (default_arr if len(raw) == 1 else None)
        if not dep or not arr:
            raise RuntimeError(f"secção do comboio {s.get('trainNumber')} sem estações no horário")
        out.append({"train": s["trainNumber"], "dep": dep, "arr": arr,
                    "code": s["serviceCode"]["code"], "designation": s["serviceCode"]["designation"]})
    return out


def fiscal_address() -> Any:
    """`fiscalAddress` opcional (PLANO_FINAL 2.4): JSON em CP_FISCAL_ADDRESS, copiado do HAR.
    Só se usa se a CP recusar o passo fiscal sem morada; vazio = não se envia."""
    raw = os.environ.get("CP_FISCAL_ADDRESS", "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError as e:
        raise RuntimeError("CP_FISCAL_ADDRESS não é JSON válido") from e


# ---------------------------------------------------------------------------
# Uso manual (compra imediata, sem agendamento) — mantido do script inicial
# ---------------------------------------------------------------------------

def buy_one_leg(client: CPClient, origin_code: str, dest_code: str,
                travel_date: str, target_time: str | None = None,
                train_number: int | None = None) -> dict:
    journeys = client.search_journeys(origin_code, dest_code, travel_date)
    trip = pick_trip(journeys, target_time=target_time, train_number=train_number)
    resp = client.create_sale_request(travel_date, trip_sections(trip, origin_code, dest_code))
    kind, detail = classify_sale_response(resp)
    if kind != "ok":
        raise RuntimeError(f"Venda não criada ({kind}): {detail}")
    sale_id = resp.body["saleID"]

    client.set_passengers(sale_id)
    client.set_client(sale_id)
    client.set_fiscal(sale_id)
    client.apply_green_pass(sale_id)
    result = client.confirm(sale_id).body
    if result["status"]["code"] != "CONFIRMED":
        raise RuntimeError(f"Venda não confirmada: {result['status']}")
    return result


def main():
    import argparse
    import datetime as dt

    parser = argparse.ArgumentParser(description="Compra imediata de bilhetes CP (uso manual)")
    parser.add_argument("--login-only", action="store_true",
                        help="só faz login, guarda token.json (chmod 600) e sai; para testes")
    parser.add_argument("--origem", help="chave em STATION_CODES, ex: aveiro")
    parser.add_argument("--destino", help="chave em STATION_CODES, ex: lisboa_oriente")
    parser.add_argument("--data", default=dt.date.today().isoformat(), help="YYYY-MM-DD (default: hoje)")
    parser.add_argument("--hora-ida", default=None, help="HH:MM aproximada da ida (ignorado se --comboio-ida)")
    parser.add_argument("--hora-volta", default=None, help="HH:MM aproximada da volta (ignorado se --comboio-volta)")
    parser.add_argument("--comboio-ida", type=int, default=None, help="Nº exato do comboio de ida")
    parser.add_argument("--comboio-volta", type=int, default=None, help="Nº exato do comboio de volta")
    parser.add_argument("--so-ida", action="store_true", help="Comprar só o bilhete de ida")
    args = parser.parse_args()

    print("A autenticar...")
    tokens = login()
    common.save_tokens(tokens)
    if args.login_only:
        print(f"Login OK (access_token {tokens.get('expires_in')} s, sessão {tokens.get('refresh_expires_in')} s). "
              f"Tokens guardados em {common.TOKEN_FILE.name} (chmod 600).")
        return
    if not args.origem or not args.destino:
        parser.error("--origem e --destino são obrigatórios (exceto com --login-only)")
    origem = STATION_CODES[args.origem]
    destino = STATION_CODES[args.destino]
    client = CPClient(access_token=tokens["access_token"])

    ida_label = f"comboio nº{args.comboio_ida}" if args.comboio_ida else f"~{args.hora_ida}"
    print(f"A comprar ida: {args.origem} -> {args.destino}, {args.data}, {ida_label}")
    ida = buy_one_leg(client, origem, destino, args.data,
                      target_time=args.hora_ida, train_number=args.comboio_ida)
    print(f"  Ida confirmada: referência {ida['reference']}")

    if not args.so_ida:
        volta_label = f"comboio nº{args.comboio_volta}" if args.comboio_volta else f"~{args.hora_volta}"
        print(f"A comprar volta: {args.destino} -> {args.origem}, {args.data}, {volta_label}")
        volta = buy_one_leg(client, destino, origem, args.data,
                            target_time=args.hora_volta, train_number=args.comboio_volta)
        print(f"  Volta confirmada: referência {volta['reference']}")
    print("Concluído.")


if __name__ == "__main__":
    try:
        main()
    except (CPError, RuntimeError, requests.RequestException) as e:
        print(f"Erro: {common.sanitize(e)}", file=sys.stderr)
        sys.exit(1)
