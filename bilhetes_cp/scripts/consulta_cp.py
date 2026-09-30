"""Consultas à conta da CP de uma pessoa, para o Pulse (ADR-075): bilhetes futuros, cancelar um bilhete e validade do Passe Verde.

Chamado pelo `dados-api` como subprocesso (`python consulta_cp.py --utilizador N futuros|passe|cancelar --venda ID`), sempre na mesma
máquina. Escreve **um só JSON** no stdout (`{"ok": true, ...}` ou `{"ok": false, "erro": "<código>", "mensagem": "..."}`), nunca dados pessoais
a mais: não sai o nº do documento, a foto nem o QR do cartão. Reaproveita a sessão da CP guardada (renova-a, e só faz login se for preciso).

Endpoints (observados no site da CP, HAR de 30/09/2026): `ticketing-api/trips/<email>`, `ticketing-api/sales/<id>`,
`ticketing-api/post-sale/refund…` e `mobility-cards-api/cards/client/<email cifrado>` (AES-ECB com a chave pública do site).
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from typing import Any

import common
import credenciais
import cp_ticket
from cp_ticket import CPClient, CPError

MAX_FUTUROS = 20
# a CP exige este cabeçalho nas listas de viagens (no site é a data de registo da conta) mas aceita qualquer data bem formada
_DATA_REGISTO = "2000-01-01T00:00:00.000Z"
# a chave é pública: vem no JavaScript do site da CP (mobility-cards-service), que cifra o e-mail do cliente com ela
_CHAVE_SITE_CARTOES = b"SMCMIVLQR382234B"


class ConsultaErro(Exception):
    def __init__(self, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.codigo, self.mensagem = codigo, mensagem


# --- sessão ------------------------------------------------------------------------------------------------------------------

def cliente(utilizador_id: int) -> CPClient:
    """Um cliente da CP com sessão válida para esta pessoa: usa o token guardado, renova-o ou, em último caso, faz login."""
    try:
        cred = credenciais.carregar(utilizador_id)
    except credenciais.CredenciaisIncompletas as e:
        raise ConsultaErro("credenciais", str(e)) from e
    tokens = common.load_tokens(utilizador_id)
    agora = time.time()
    if tokens and tokens.get("access_expires_at", 0) > agora + 30:
        return CPClient(tokens["access_token"], cred=cred)
    try:
        if tokens and tokens.get("refresh_token") and tokens.get("refresh_expires_at", 0) > agora + 10:
            novos = cp_ticket.refresh_tokens(tokens["refresh_token"])
        else:
            novos = cp_ticket.login(cred)
        common.save_tokens(novos, utilizador_id)
    except Exception as e:  # noqa: BLE001 - qualquer falha de sessão vira um erro claro, sem detalhes da CP
        raise ConsultaErro("sessao_cp", "Não consegui iniciar sessão na CP.") from e
    return CPClient(novos["access_token"], cred=cred)


def _pedir(cli: CPClient, metodo: str, caminho: str, corpo: Any = None, *, chave: str | None = None, com_cliente: bool = True) -> Any:
    try:
        r = cli.request(metodo, caminho, api_key=chave or cp_ticket.X_API_KEY_TICKETING, body=corpo, with_client_id=com_cliente, timeout=(4.0, 15.0))
    except CPError as e:
        raise ConsultaErro("rede_cp", "A CP não respondeu.") from e
    if not r.ok:
        raise ConsultaErro("erro_cp", f"A CP respondeu {r.status}: {' / '.join(r.messages)[:200]}")
    return r.body


# --- bilhetes futuros ---------------------------------------------------------------------------------------------------------

def _futuros_brutos(cli: CPClient) -> list[dict]:
    cli.data_registo = _DATA_REGISTO
    lista = _pedir(cli, "GET", f"/ticketing-api/trips/{cli.cp_email}?page=0&count={MAX_FUTUROS}&filter=FUTURE&order-by=TRAVEL_DATE&sort=ASC")
    return lista if isinstance(lista, list) else []


def _bilhete(viagem: dict, venda: dict | None) -> dict:
    """Uma viagem da lista + o detalhe da venda → o formato do Pulse (sem documentos nem dados fiscais)."""
    v = venda or {}
    troco = ((v.get("travelData") or {}).get("outwardTrip") or [{}])[0]
    lugar = (troco.get("seatData") or [{}])[0]
    return {
        "venda": int(viagem["saleID"]), "referencia": v.get("reference", ""), "estado": (v.get("status") or {}).get("code", ""),
        "origem": (viagem.get("departure") or {}).get("designation", ""), "destino": (viagem.get("arrival") or {}).get("designation", ""),
        "data": str(viagem.get("travelDate", ""))[:10], "hora": troco.get("departureTime", ""), "chegada": troco.get("arrivalTime", ""),
        "comboio": troco.get("trainNumber"), "servico": (troco.get("service") or {}).get("designation", ""),
        "carruagem": lugar.get("carriageNumber"), "lugar": lugar.get("seatNumber"), "valor": viagem.get("totalAmount", 0),
        "podeCancelar": (v.get("status") or {}).get("code") == "CONFIRMED",
    }


def futuros(cli: CPClient) -> dict:
    out = []
    for viagem in _futuros_brutos(cli):
        try:
            venda = _pedir(cli, "GET", f"/ticketing-api/sales/{int(viagem['saleID'])}")
        except ConsultaErro:
            venda = None                                # o detalhe é um extra: a viagem aparece na mesma
        out.append(_bilhete(viagem, venda))
    return {"bilhetes": out}


# --- cancelar -----------------------------------------------------------------------------------------------------------------

def cancelar(cli: CPClient, venda: int) -> dict:
    """Devolução de um bilhete futuro da própria pessoa (2 passos da CP: pedir e confirmar). Só se a CP a oferecer (`REFUND`)."""
    if venda not in {int(v["saleID"]) for v in _futuros_brutos(cli)}:
        raise ConsultaErro("nao_encontrado", "Esse bilhete não é um bilhete futuro desta conta.")
    operacoes = _pedir(cli, "GET", f"/ticketing-api/sales/{venda}/available-operations")
    if not isinstance(operacoes, list) or "REFUND" not in operacoes:
        raise ConsultaErro("nao_cancelavel", "A CP já não permite devolver este bilhete.")
    elegiveis = _pedir(cli, "GET", f"/ticketing-api/post-sale/refund/available/tickets/{venda}") or {}
    documentos = [t["itemData"]["documentNumber"] for t in elegiveis.get("ticketData", [])
                  if t.get("itemType") == "TICKET" and (t.get("itemData") or {}).get("documentNumber")]
    if not documentos:
        raise ConsultaErro("nao_cancelavel", "Não há bilhetes a devolver nesta venda.")
    pedido = _pedir(cli, "POST", "/ticketing-api/post-sale/refund", {
        "devolutionObservations": "", "devolutionReasonId": 0, "lang": "PT", "operatorData": elegiveis.get("operatorData") or {"agencyCode": "NETTICKET", "agencyName": "NETTICKET"},
        "refundProducts": True, "saleId": venda, "tickets": documentos, "type": "REFUND", "username": cli.cp_email})
    refund_id = (pedido or {}).get("refundID")
    if not refund_id:
        raise ConsultaErro("erro_cp", "A CP não devolveu o pedido de devolução.")
    final = _pedir(cli, "PUT", f"/ticketing-api/post-sale/refund/{int(refund_id)}", com_cliente=False)
    estado = ((final or {}).get("status") or {}).get("code", "")
    if estado != "CONFIRMED":
        raise ConsultaErro("erro_cp", f"A devolução ficou no estado {estado or 'desconhecido'}.")
    return {"venda": venda, "estado": estado, "reembolso": (final or {}).get("totalRefundAmount", "")}


# --- Passe Verde --------------------------------------------------------------------------------------------------------------

def _cifrar_email(email: str) -> str:
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    p = padding.PKCS7(128).padder()
    dados = p.update(email.encode()) + p.finalize()
    c = Cipher(algorithms.AES(_CHAVE_SITE_CARTOES), modes.ECB()).encryptor()     # é o que o próprio site faz
    return base64.b64encode(c.update(dados) + c.finalize()).decode()


def _data_br(s: str) -> str:
    """«20/10/2026» → «2026-10-20» (a CP usa dd/mm/aaaa nos contratos)."""
    try:
        d, m, a = s.split("/")
        return f"{a}-{int(m):02d}-{int(d):02d}"
    except ValueError:
        return ""


def passe(cli: CPClient) -> dict:
    from urllib.parse import quote
    cartoes = _pedir(cli, "GET", f"/mobility-cards-api/cards/client/{quote(_cifrar_email(cli.cp_email), safe='')}", chave=cp_ticket.X_API_KEY_TRAVEL)
    contratos = []
    for c in cartoes if isinstance(cartoes, list) else []:
        for k in c.get("contratos", c.get("contracts", [])) or []:
            contratos.append({
                "cartao": c.get("card_type_name", ""), "designacao": k.get("designation", ""),
                "origem": (k.get("init_station") or {}).get("designation", ""), "destino": (k.get("end_station") or {}).get("designation", ""),
                "inicio": _data_br(k.get("init_date", "")), "validade": _data_br(k.get("expiration_date", "")), "renovavel": bool(k.get("allow_renewal")),
            })
    return {"passes": contratos}


# --- linha de comandos ---------------------------------------------------------------------------------------------------------

def correr(utilizador: int, comando: str, venda: int | None = None) -> dict:
    try:
        cli = cliente(utilizador)
        if comando == "futuros":
            return {"ok": True, **futuros(cli)}
        if comando == "passe":
            return {"ok": True, **passe(cli)}
        if comando == "cancelar":
            if not venda:
                raise ConsultaErro("pedido_invalido", "Falta o número da venda.")
            return {"ok": True, **cancelar(cli, venda)}
        raise ConsultaErro("pedido_invalido", "Comando desconhecido.")
    except ConsultaErro as e:
        return {"ok": False, "erro": e.codigo, "mensagem": e.mensagem}
    except Exception as e:  # noqa: BLE001 - o chamador só lê JSON; nunca um traceback com dados
        return {"ok": False, "erro": "interno", "mensagem": type(e).__name__}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--utilizador", type=int, default=1)
    ap.add_argument("comando", choices=["futuros", "passe", "cancelar"])
    ap.add_argument("--venda", type=int)
    a = ap.parse_args(argv)
    r = correr(a.utilizador, a.comando, a.venda)
    print(json.dumps(r, ensure_ascii=False))
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
