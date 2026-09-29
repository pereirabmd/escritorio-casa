"""Gmail no Pulse (ADR-049): caixa de entrada de várias contas num só formato.

Só se lê e organiza: marcar lida/por ler, arquivar, estrela. **Nunca se envia, responde ou apaga** (o scope `gmail.modify` não o exige e
enviar seria uma ação sensível à parte). O conteúdo dos emails é não confiável: a interface mostra-o sempre como texto simples.
"""

from __future__ import annotations

import base64
import html
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from email.header import decode_header, make_header
from email.utils import parseaddr
from urllib.parse import quote
from zoneinfo import ZoneInfo

from pulse import google_api as g
from pulse.accounts import ContaErro

FILTROS = {
    "importantes": "in:inbox is:important",
    "entrada": "in:inbox",
    "por_ler": "in:inbox is:unread",
}
POR_CONTA = 15
MAX_CORPO = 20000
CABECALHOS = ["From", "Subject", "Date"]


def _cab(headers: list[dict], nome: str) -> str:
    v = next((h["value"] for h in headers if h.get("name", "").lower() == nome.lower()), "")
    try:
        return str(make_header(decode_header(v))).strip()
    except (ValueError, LookupError):
        return v.strip()


def mensagem_json(m: dict, conta: dict, tz: ZoneInfo) -> dict:
    headers = m.get("payload", {}).get("headers", [])
    nome, endereco = parseaddr(_cab(headers, "From"))
    etiquetas = set(m.get("labelIds", []))
    ms = int(m.get("internalDate", 0) or 0)
    data = datetime.fromtimestamp(ms / 1000, tz).isoformat(timespec="minutes") if ms else ""
    return {"id": m["id"], "conta": conta["id"], "contaEmail": conta["email"], "thread": m.get("threadId", ""),
            "de": nome or endereco, "deEmail": endereco, "assunto": _cab(headers, "Subject") or "(sem assunto)", "resumo": html.unescape(m.get("snippet", ""))[:200],
            "data": data, "lida": "UNREAD" not in etiquetas, "estrela": "STARRED" in etiquetas, "importante": "IMPORTANT" in etiquetas,
            "entrada": "INBOX" in etiquetas}


def _mensagens_de_uma_conta(api: g.GoogleApi, conta: dict, filtro: str, tz: ZoneInfo, n: int) -> tuple[list[dict], int]:
    """(mensagens, estimativa do total). Uma chamada para a lista e uma por mensagem (metadados), em paralelo."""
    _, lista = api.pedir(conta["id"], conta["refresh"], "GET", f"{g.GMAIL}/messages", {"q": FILTROS[filtro], "maxResults": n})
    ids = [x["id"] for x in (lista or {}).get("messages", [])]

    def uma(mid: str) -> dict | None:
        try:
            _, m = api.pedir(conta["id"], conta["refresh"], "GET", f"{g.GMAIL}/messages/{quote(mid, safe='')}",
                             {"format": "metadata", "metadataHeaders": CABECALHOS})
            return mensagem_json(m, conta, tz) if m else None
        except g.GoogleErro:
            return None                     # uma mensagem que desapareceu entretanto não estraga a lista
    with ThreadPoolExecutor(max_workers=max(min(len(ids), 8), 1)) as pool:
        msgs = [m for m in pool.map(uma, ids) if m]
    return msgs, int((lista or {}).get("resultSizeEstimate", len(msgs)))


def caixa(api: g.GoogleApi, contas: list[dict], filtro: str, tz: ZoneInfo, n: int = POR_CONTA) -> dict:
    """As mensagens de todas as contas (mais recentes primeiro). Uma conta que falha vem em `contas` com o motivo; as outras aparecem."""
    if filtro not in FILTROS:
        raise ContaErro(400, "filtro_invalido", "filtro desconhecido")
    ativas = [c for c in contas if c["estado"] == "ok"]

    def uma(c):
        try:
            return c, *_mensagens_de_uma_conta(api, c, filtro, tz, n), None
        except g.GoogleErro as e:
            return c, [], 0, e
    with ThreadPoolExecutor(max_workers=max(len(ativas), 1)) as pool:
        resultados = list(pool.map(uma, ativas))
    estados = [{"id": c["id"], "email": c["email"], "estado": "reautorizar", "erro": "Volta a ligar esta conta."} for c in contas if c["estado"] != "ok"]
    msgs: list[dict] = []
    for c, ms, total, erro in resultados:
        if erro is None:
            msgs.extend(ms); estados.append({"id": c["id"], "email": c["email"], "estado": "ok", "total": total})
        else:
            estados.append({"id": c["id"], "email": c["email"], "estado": "reautorizar" if erro.reautorizar else "erro", "erro": str(erro)})
    msgs.sort(key=lambda m: m["data"], reverse=True)
    ordem = {c["id"]: i for i, c in enumerate(contas)}
    estados.sort(key=lambda x: ordem.get(x["id"], 99))
    return {"filtro": filtro, "contas": estados, "mensagens": msgs}


def importantes_hoje(api: g.GoogleApi, contas: list[dict], tz: ZoneInfo, limite: int = 3) -> dict:
    """O cartão do Hoje: emails importantes por ler."""
    c = caixa(api, contas, "importantes", tz, 10)
    por_ler = [m for m in c["mensagens"] if not m["lida"]]
    return {"porLer": len(por_ler), "mensagens": por_ler[:limite], "contas": len(contas), "comProblemas": [x for x in c["contas"] if x["estado"] != "ok"]}


# --- detalhe -----------------------------------------------------------------------------------------------------------------

def _texto_html(h: str) -> str:
    h = re.sub(r"(?is)<(script|style|head).*?</\1>", " ", h)
    h = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d)>", "\n", h)
    h = re.sub(r"(?s)<[^>]+>", "", h)
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t\r\f\v]+", " ", html.unescape(h))).strip()


def _b64(d: str) -> str:
    return base64.urlsafe_b64decode(d + "=" * (-len(d) % 4)).decode("utf-8", errors="replace")


def _partes(p: dict):
    yield p
    for x in p.get("parts", []) or []:
        yield from _partes(x)


def corpo_texto(payload: dict) -> tuple[str, bool]:
    """(texto simples, tem anexos). Prefere `text/plain`; senão converte o `text/html`. Limita o tamanho."""
    planos, htmls, anexos = [], [], False
    for p in _partes(payload):
        if p.get("filename"):
            anexos = True
            continue
        dados = p.get("body", {}).get("data")
        if not dados:
            continue
        if p.get("mimeType") == "text/plain":
            planos.append(_b64(dados))
        elif p.get("mimeType") == "text/html":
            htmls.append(_b64(dados))
    texto = "\n\n".join(planos) if planos else "\n\n".join(_texto_html(h) for h in htmls)
    return texto.strip()[:MAX_CORPO], anexos


def detalhe(api: g.GoogleApi, conta: dict, mensagem: str, tz: ZoneInfo) -> dict:
    _, m = api.pedir(conta["id"], conta["refresh"], "GET", f"{g.GMAIL}/messages/{quote(mensagem, safe='')}", {"format": "full"})
    if not m:
        raise ContaErro(404, "nao_encontrado", "mensagem inexistente")
    corpo, anexos = corpo_texto(m.get("payload", {}))
    headers = m.get("payload", {}).get("headers", [])
    return {**mensagem_json(m, conta, tz), "para": _cab(headers, "To")[:300], "corpo": corpo, "temAnexos": anexos}


# --- organizar ---------------------------------------------------------------------------------------------------------------

def _alterar(api: g.GoogleApi, conta: dict, mensagem: str, adicionar: list[str], remover: list[str], tz: ZoneInfo) -> dict:
    _, m = api.pedir(conta["id"], conta["refresh"], "POST", f"{g.GMAIL}/messages/{quote(mensagem, safe='')}/modify", None,
                     {"addLabelIds": adicionar, "removeLabelIds": remover})
    return mensagem_json(m or {"id": mensagem}, conta, tz)


def marcar_lida(api, conta, mensagem, lida: bool, tz):
    return _alterar(api, conta, mensagem, [] if lida else ["UNREAD"], ["UNREAD"] if lida else [], tz)


def arquivar(api, conta, mensagem, arquivado: bool, tz):
    return _alterar(api, conta, mensagem, [] if arquivado else ["INBOX"], ["INBOX"] if arquivado else [], tz)


def estrela(api, conta, mensagem, com_estrela: bool, tz):
    return _alterar(api, conta, mensagem, ["STARRED"] if com_estrela else [], [] if com_estrela else ["STARRED"], tz)
