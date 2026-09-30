"""pulse_eventos.py — cópia dos avisos das Tarefas para o Pulse (FCM), em paralelo com o ntfy (ADR-060 do Pulse).

O motor de `recalcular.py` decide *quando* e *a quem* avisar; aqui, para cada aviso, o Pulse guarda um evento **agendado** para a mesma hora
(`POST /internal/events` com `entregarEm`) e um agendador do Pulse entrega-o por FCM. Quando o motor cancela ou reagenda (tarefa feita,
adiada, hora mudada) cancela-se o evento (`DELETE /internal/events/<chave>`). Estado à parte em `pulse_agendados.json`: o do ntfy não se toca.

Melhor esforço: desligado sem PULSE_EVENTS_URL e PULSE_SERVICE_KEY; o Pulse em baixo nunca impede o ntfy (o que falha repete-se no ciclo seguinte,
e a chave é estável, por isso repetir não duplica).
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from typing import Any, Callable

import common

log = common.get_logger("pulse_eventos")
HORIZONTE_DIAS = 3          # o mesmo do ntfy: não se agenda mais longe do que o motor reconcilia
TIMEOUT_S = 5

Http = Callable[[str, str, dict | None], int]     # (método, «url|email», corpo JSON) -> código HTTP (0 se não chegou); só para os testes


def ligado() -> bool:
    return bool(common.env("PULSE_EVENTS_URL") and len(common.env("PULSE_SERVICE_KEY")) >= 32)


# --- quem recebe -------------------------------------------------------------------------------------------------------------------

def _pessoas(config: dict[str, Any]) -> dict[str, dict[str, str]]:
    """{ 'Bruno': {'email': …, 'ntfy': …} } a partir das chaves Pessoa<N>_Nome/_Email/_NtfyUser da Config."""
    out: dict[str, dict[str, str]] = {}
    for k, v in config.items():
        m = re.fullmatch(r"Pessoa(\d+)_Nome", str(k).strip())
        if m and str(v or "").strip():
            n = m.group(1)
            ntfy = str(config.get(f"Pessoa{n}_NtfyUser") or "").strip().lower()
            out[str(v).strip()] = {"email": str(config.get(f"Pessoa{n}_Email") or "").strip().lower(), "ntfy": ntfy}
    return out


def emails_da_pessoa(config: dict[str, Any], nome: str) -> list[str]:
    """O e-mail do Pulse dessa pessoa; sem responsável (nome vazio) ou desconhecido, todas as pessoas com e-mail."""
    pessoas = _pessoas(config)
    p = pessoas.get(str(nome or "").strip())
    if p and p["email"]:
        return [p["email"]]
    return sorted({x["email"] for x in pessoas.values() if x["email"]})


def emails_do_topico(config: dict[str, Any], topico: str | None) -> list[str]:
    """O tópico ntfy `tarefas_<utilizador>` é de uma pessoa; o tópico legado (None) é de toda a gente."""
    if topico:
        for p in _pessoas(config).values():
            if p["ntfy"] and (p["ntfy"] if p["ntfy"].startswith("tarefas_") else f"tarefas_{p['ntfy']}") == topico and p["email"]:
                return [p["email"]]
    return sorted({x["email"] for x in _pessoas(config).values() if x["email"]})


def dados_do_aviso(chave: str) -> dict[str, str]:
    """O que a app Android precisa para o toque abrir o sítio certo e para os botões da notificação: `pulse://tarefas/<aba>` e, nas tarefas, a instância."""
    tipo, _, resto = chave.partition(":")
    if tipo == "inst":
        return {"link": "pulse://tarefas/hoje", "instancia": resto.split(":")[0]}
    return {"link": f"pulse://tarefas/{'piscina' if tipo == 'piscina' else 'horario' if tipo == 'horario' else 'hoje'}"}


# --- reconciliação -----------------------------------------------------------------------------------------------------------------

def _chave_evento(chave: str, alvo_iso: str, email: str) -> str:
    return "tar-" + hashlib.sha1(f"{chave}|{alvo_iso}|{email}".encode()).hexdigest()[:24]


def reconciliar(chave: str, alvo: datetime | None, titulo: str, corpo: str, emails: list[str], estado: dict[str, dict], agora: datetime,
                plan_only: bool, *, tipo: str = "tarefas.aviso", dados: dict[str, str] | None = None, http: Http | None = None) -> str:
    """Mantém no Pulse o evento certo para esta chave do motor. Devolve: desligado / agendado / cancelado / sem_alteracao / fora_do_horizonte / falhou."""
    if not ligado() and http is None:
        return "desligado"
    url = common.env("PULSE_EVENTS_URL").rstrip("/")
    anterior = estado.get(chave)

    def chamar(metodo: str, caminho: str, email: str, corpo_json: dict | None) -> int:
        if http is not None:
            return http(metodo, f"{caminho}|{email}", corpo_json)
        return _http_com_utilizador(metodo, caminho, email, corpo_json)

    def cancelar_anterior() -> None:
        for email, ev in (anterior or {}).get("chaves", {}).items():
            chamar("DELETE", f"{url}/{ev}", email, None)

    if alvo is None:
        if anterior:
            if not plan_only:
                cancelar_anterior()
                estado.pop(chave, None)
            return "cancelado"
        return "sem_alteracao"

    iso = alvo.isoformat()
    if anterior and anterior.get("alvo") == iso and set(anterior.get("chaves", {})) == set(emails):
        return "sem_alteracao"
    if alvo - agora > timedelta(days=HORIZONTE_DIAS, hours=-6):
        if anterior and not plan_only:
            cancelar_anterior(); estado.pop(chave, None)
        return "fora_do_horizonte"
    if plan_only:
        return "agendado"
    if anterior:
        cancelar_anterior()
    chaves: dict[str, str] = {}
    falhou = False
    for email in emails:
        ev = _chave_evento(chave, iso, email)
        corpo_json = {"modulo": "tarefas", "tipo": tipo, "titulo": titulo[:200] or "Tarefas", "corpo": corpo[:1000], "dados": dados or dados_do_aviso(chave), "chave": ev}
        if alvo > agora:
            corpo_json["entregarEm"] = int(alvo.timestamp())      # no passado ou agora: sai já
        codigo = chamar("POST", url, email, corpo_json)
        if 200 <= codigo < 300:
            chaves[email] = ev
        else:
            falhou = True
            log.warning("Pulse não aceitou o aviso %s para %s (HTTP %s)", chave, email, codigo)
    if chaves:
        estado[chave] = {"alvo": iso, "chaves": chaves}
    else:
        estado.pop(chave, None)
    return "falhou" if falhou else "agendado"


def _http_com_utilizador(metodo: str, url: str, email: str, corpo: dict | None) -> int:
    req = urllib.request.Request(url, data=json.dumps(corpo).encode() if corpo is not None else None, method=metodo,
                                 headers={"Content-Type": "application/json", "X-Pulse-Key": common.env("PULSE_SERVICE_KEY"), "X-Pulse-User": email})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, OSError):
        return 0
