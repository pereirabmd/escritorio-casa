"""
Automação de compra de bilhetes CP (Comboios de Portugal) com Passe Ferroviário Verde.

Fluxo: login (Keycloak/OAuth2 PKCE) -> pesquisa -> criar venda -> preencher
passageiro/cliente/dados fiscais -> aplicar desconto/passe -> confirmar.

IMPORTANTE:
- Isto usa a API interna do site cp.pt, obtida a partir de um HAR capturado
  manualmente. A CP pode alterar esta API a qualquer momento sem aviso —
  o script pode parar de funcionar.
- Todos os dados pessoais vêm de variáveis de ambiente (ficheiro .env),
  nunca hardcoded aqui.
- Usa isto apenas para a tua própria conta/passe. Uso abusivo ou em nome
  de terceiros pode violar os Termos e Condições da Bilheteira Online da CP.
"""

import base64
import hashlib
import os
import re
import secrets
import sys
import urllib.parse as up
from dataclasses import dataclass

import requests

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

# Estações (códigos internos CP). Ajusta conforme a tua rota.
STATION_CODES = {
    "aveiro": "94-38000",
    "lisboa_oriente": "94-31039",
    # adiciona aqui outras estações que precises, com o mesmo formato "94-XXXXX"
}

TRAVEL_CLASS = 2  # 2 = 2ª classe / turística

# --- Endpoints ---
LOGIN_BASE = "https://login.cp.pt/realms/cpclients"
AUTH_ENDPOINT = f"{LOGIN_BASE}/protocol/openid-connect/auth"
TOKEN_ENDPOINT = f"{LOGIN_BASE}/protocol/openid-connect/token"
API_BASE = "https://api-gateway.cp.pt/cp/services"

CLIENT_ID = "websitecp"
REDIRECT_URI = "https://cp.pt/pt/login-check"

# Chaves/headers estáticos observados no tráfego do site (embutidos no
# JS do frontend, não são segredos pessoais). Se deixarem de funcionar,
# terás de os recapturar num novo HAR.
X_CP_CONNECT_ID = os.environ.get("CP_CONNECT_ID", "")
X_CP_CONNECT_SECRET = os.environ.get("CP_CONNECT_SECRET", "")
X_API_KEY_TRAVEL = os.environ.get("CP_API_KEY_TRAVEL", "")
X_API_KEY_TICKETING = os.environ.get("CP_API_KEY_TICKETING", "")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
)


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
    """Faz login via Keycloak com PKCE e devolve os tokens (access/refresh)."""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    verifier, challenge = make_pkce_pair()
    state = secrets.token_hex(16)
    nonce = secrets.token_hex(16)

    # 1) Pedir o ecrã de login (traz session_code + execution no HTML)
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
    r = session.get(AUTH_ENDPOINT, params=params)
    r.raise_for_status()

    match = re.search(r'action="([^"]+)"', r.text)
    if not match:
        raise RuntimeError(
            "Não encontrei o formulário de login na página (a CP pode ter "
            "mudado o HTML, ou pode haver CAPTCHA/MFA ativo)."
        )
    form_action = match.group(1).replace("&amp;", "&")

    # 2) Submeter utilizador/password
    r = session.post(
        form_action,
        data={"username": CP_EMAIL, "password": CP_PASSWORD, "credentialId": ""},
        allow_redirects=False,
    )
    if r.status_code != 302 or "location" not in r.headers:
        raise RuntimeError(
            f"Login falhou (status {r.status_code}). Verifica as credenciais "
            "ou se apareceu algum passo extra (CAPTCHA/MFA) que o script não sabe tratar."
        )

    location = r.headers["location"]
    fragment = up.urlsplit(location).fragment
    fragment_params = up.parse_qs(fragment)
    if "code" not in fragment_params:
        raise RuntimeError(f"Não veio nenhum 'code' no redirect de login: {location}")
    auth_code = fragment_params["code"][0]

    # 3) Trocar o code por tokens
    r = session.post(
        TOKEN_ENDPOINT,
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        },
    )
    r.raise_for_status()
    tokens = r.json()
    return tokens


def refresh_tokens(refresh_token: str) -> dict:
    r = requests.post(
        TOKEN_ENDPOINT,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": CLIENT_ID,
        },
        headers={"User-Agent": USER_AGENT},
    )
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# API CP
# ---------------------------------------------------------------------------

@dataclass
class CPClient:
    access_token: str

    def _headers(self, api_key: str, with_client_id: bool = False) -> dict:
        h = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "x-access-token": self.access_token,
            "X-Api-Key": api_key,
            "x-cp-connect-id": X_CP_CONNECT_ID,
            "x-cp-connect-secret": X_CP_CONNECT_SECRET,
        }
        if with_client_id:
            h["x-cp-client-id"] = CP_EMAIL
        return h

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
        r = requests.post(
            f"{API_BASE}/travel-api/journeys",
            json=body,
            headers=self._headers(X_API_KEY_TRAVEL),
        )
        r.raise_for_status()
        return r.json()

    def create_sale(self, travel_date: str, train_number: int, origin_code: str,
                     dest_code: str, service_code: str, service_designation: str) -> dict:
        body = {
            "quantity": 1,
            "travelClass": {"code": str(TRAVEL_CLASS)},
            "travelDate": travel_date,
            "outwardTrip": [
                {
                    "trainNumber": train_number,
                    "departureStation": {"code": origin_code},
                    "arrivalStation": {"code": dest_code},
                    "serviceCode": {"code": service_code, "designation": service_designation},
                }
            ],
            "lang": "pt",
        }
        r = requests.post(
            f"{API_BASE}/ticketing-api/sale",
            json=body,
            headers=self._headers(X_API_KEY_TICKETING, with_client_id=True),
        )
        r.raise_for_status()
        return r.json()

    def set_passengers(self, sale_id: int) -> dict:
        body = {
            "salePassengers": [
                {
                    "idtype": {"code": "CC", "designation": "Cartão de Cidadão"},
                    "passengerID": PASSENGER_CC,
                    "passengerName": PASSENGER_NAME,
                }
            ]
        }
        r = requests.put(
            f"{API_BASE}/ticketing-api/sale/{sale_id}/passengers",
            json=body,
            headers=self._headers(X_API_KEY_TICKETING, with_client_id=True),
        )
        r.raise_for_status()
        return r.json()

    def set_client(self, sale_id: int) -> dict:
        body = {
            "clientEmail": CP_EMAIL,
            "clientID": CP_EMAIL,
            "clientMobile": PASSENGER_PHONE,
            "clientName": PASSENGER_NAME,
        }
        r = requests.put(
            f"{API_BASE}/ticketing-api/sale/{sale_id}/client",
            json=body,
            headers=self._headers(X_API_KEY_TICKETING, with_client_id=True),
        )
        r.raise_for_status()
        return r.json()

    def set_fiscal(self, sale_id: int) -> dict:
        body = {"countryCode": "PT", "fiscalID": PASSENGER_NIF, "fiscalName": PASSENGER_NAME}
        r = requests.put(
            f"{API_BASE}/ticketing-api/sale/{sale_id}/fiscal",
            json=body,
            headers=self._headers(X_API_KEY_TICKETING, with_client_id=True),
        )
        r.raise_for_status()
        return r.json()

    def apply_green_pass(self, sale_id: int) -> dict:
        """Aplica o desconto do Passe Ferroviário Verde (equivalente à dropdown)."""
        body = {
            "requestedItems": [
                {
                    "itemCode": "302",
                    "relatedTrain": None,
                    "ticketIndex": 0,
                    "type": "DISCOUNT",
                    "inputData": GREEN_PASS_NUMBER,
                }
            ]
        }
        r = requests.put(
            f"{API_BASE}/ticketing-api/sale/{sale_id}/items",
            json=body,
            headers=self._headers(X_API_KEY_TICKETING, with_client_id=True),
        )
        r.raise_for_status()
        return r.json()

    def confirm(self, sale_id: int) -> dict:
        r = requests.put(
            f"{API_BASE}/ticketing-api/sale/{sale_id}/confirm",
            headers=self._headers(X_API_KEY_TICKETING, with_client_id=True),
        )
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# Lógica de escolha do comboio
# ---------------------------------------------------------------------------

def pick_trip(journeys: dict, target_time: str | None = None,
              train_number: int | None = None) -> dict:
    """Escolhe a viagem por número de comboio exato, por horário aproximado,
    ou a primeira saleable se nada for indicado."""
    trips = [t for t in journeys.get("outwardTrip", []) if t.get("saleableOnline")]
    if not trips:
        raise RuntimeError("Nenhuma viagem disponível para venda online nesta data.")

    if train_number is not None:
        for t in trips:
            # o nº de comboio está em cada secção da viagem (pode haver transbordos)
            if any(s["trainNumber"] == train_number for s in t["travelSections"]):
                return t
        disponiveis = sorted(
            {s["trainNumber"] for t in trips for s in t["travelSections"]}
        )
        raise RuntimeError(
            f"Comboio nº {train_number} não encontrado ou não disponível nesta data. "
            f"Comboios disponíveis: {disponiveis}"
        )

    if not target_time:
        return trips[0]

    def time_to_minutes(hhmm: str) -> int:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)

    target = time_to_minutes(target_time)
    return min(trips, key=lambda t: abs(time_to_minutes(t["departureTime"]) - target))


def buy_one_leg(client: CPClient, origin_code: str, dest_code: str,
                 travel_date: str, target_time: str | None = None,
                 train_number: int | None = None) -> dict:
    journeys = client.search_journeys(origin_code, dest_code, travel_date)
    trip = pick_trip(journeys, target_time=target_time, train_number=train_number)
    section = trip["travelSections"][0]

    sale = client.create_sale(
        travel_date=travel_date,
        train_number=section["trainNumber"],
        origin_code=origin_code,
        dest_code=dest_code,
        service_code=section["serviceCode"]["code"],
        service_designation=section["serviceCode"]["designation"],
    )
    sale_id = sale["saleID"]

    client.set_passengers(sale_id)
    client.set_client(sale_id)
    client.set_fiscal(sale_id)
    client.apply_green_pass(sale_id)
    result = client.confirm(sale_id)

    if result["status"]["code"] != "CONFIRMED":
        raise RuntimeError(f"Venda não confirmada: {result['status']}")

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse
    import datetime as dt

    parser = argparse.ArgumentParser(description="Compra automática de bilhetes CP")
    parser.add_argument("--origem", required=True, help="chave em STATION_CODES, ex: aveiro")
    parser.add_argument("--destino", required=True, help="chave em STATION_CODES, ex: lisboa_oriente")
    parser.add_argument("--data", default=dt.date.today().isoformat(), help="YYYY-MM-DD (default: hoje)")
    parser.add_argument("--hora-ida", default=None, help="HH:MM aproximada da ida (ignorado se --comboio-ida for dado)")
    parser.add_argument("--hora-volta", default=None, help="HH:MM aproximada da volta (ignorado se --comboio-volta for dado)")
    parser.add_argument("--comboio-ida", type=int, default=None, help="Nº exato do comboio de ida")
    parser.add_argument("--comboio-volta", type=int, default=None, help="Nº exato do comboio de volta")
    parser.add_argument("--so-ida", action="store_true", help="Comprar só o bilhete de ida")
    args = parser.parse_args()

    origem = STATION_CODES[args.origem]
    destino = STATION_CODES[args.destino]

    print("A autenticar...")
    tokens = login()
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
    except requests.HTTPError as e:
        print(f"Erro HTTP: {e.response.status_code} - {e.response.text[:500]}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Erro: {e}", file=sys.stderr)
        sys.exit(1)
