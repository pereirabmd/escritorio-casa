"""Agente de IA (ADR-077): o utilizador diz (ou escreve) o que quer e o modelo escolhe ações do catálogo oficial (`actions.py`).

Regras que não se discutem:
- o modelo **nunca escreve**: as ações de escrita (`safe_action` e `sensitive_action`) ficam como *propostas* que o utilizador confirma
  (um toque ou «confirma» por voz) e só então correm por `actions.executar(..., origem="ia", confirmado=True)`, com as mesmas validações,
  permissões e auditoria de qualquer outra via; as de leitura correm logo, em nome da conta (nunca dados de outra);
- o modelo só vê as ações dos módulos a que a conta tem acesso;
- sem estado no servidor: o cliente guarda a conversa (só texto) e devolve as propostas para confirmar.
O canal é a API de mensagens da Anthropic com ferramentas (HTTPS, chave só no Pi). `transporte` existe para os testes.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime

from pulse import actions
from pulse.accounts import ContaErro
from pulse.services import compras, dashboard, modulos

URL = "https://api.anthropic.com/v1/messages"
MODELO_OMISSAO = "claude-haiku-4-5-20251001"
MAX_VOLTAS = 6                      # idas e voltas ao modelo por comando
MAX_MENSAGENS = 20                  # mensagens de conversa aceites do cliente
MAX_TEXTO = 600
LIMITE_POR_MINUTO = 12
LEITURAS = {
    "consultar_hoje": "Consulta o que a conta tem hoje e a seguir: tarefas, próximo bilhete, RTO, peso, contas a pagar, compras por comprar, próximos eventos do "
                      "calendário e emails importantes. `modulos` limita a consulta (por omissão, todos).",
    "compras_procurar": "Procura produtos no catálogo de Compras (sem distinguir acentos nem maiúsculas) e diz se já estão na lista; devolve também as listas "
                        "(ids). Usa SEMPRE antes de adicionar um produto, para reutilizar o do catálogo em vez de criar um duplicado.",
}


class IaErro(ContaErro):
    pass


def nome_ferramenta(acao: str) -> str:
    return acao.replace(".", "__")


def _acao(ferramenta: str) -> str:
    return ferramenta.replace("__", ".")


def ferramentas(conn, uid: int) -> list[dict]:
    """As ferramentas do modelo: as leituras e as ações dos módulos a que a conta tem acesso (o esquema vem dos modelos das ações)."""
    bloqueados = modulos.indisponiveis_para(conn, uid)
    out = [
        {"name": "consultar_hoje", "description": LEITURAS["consultar_hoje"],
         "input_schema": {"type": "object", "properties": {"modulos": {"type": "array", "items": {"type": "string", "enum": ["tarefas", "bilhetes", "rto", "peso", "financas", "compras", "calendario", "email"]}}}}},
        {"name": "compras_procurar", "description": LEITURAS["compras_procurar"],
         "input_schema": {"type": "object", "properties": {"texto": {"type": "string", "maxLength": 80}}, "required": ["texto"]}},
    ]
    for a in actions.ACOES.values():
        if a.modulo in bloqueados:
            continue
        esquema = a.params.model_json_schema()
        out.append({"name": nome_ferramenta(a.nome), "input_schema": esquema,
                    "description": f"{a.descricao} [{'pede confirmação do utilizador' if a.nivel == 'sensitive_action' else 'o utilizador confirma antes de correr'}]"})
    return out


def _sem_acentos(t: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def _procurar(conn, uid: int, texto: str) -> dict:
    v = compras.visao(conn, uid)
    alvo = _sem_acentos(texto.strip())
    achados = [{"produto": p["id"], "nome": p["nome"], "categoria": p["categoria"], "naLista": p["estado"]} for p in v["produtos"]
               if alvo and (alvo in _sem_acentos(p["nome"]) or _sem_acentos(p["nome"]) in alvo)]
    return {"listas": [{"id": l["id"], "nome": l["nome"], "tipo": l["tipo"]} for l in v["listas"]], "produtos": achados[:15],
            "dica": "se não houver o produto, `compras.adicionar` aceita `nome` e `categoria` e cria-o"}


def _sistema(nome: str, agora: datetime) -> str:
    dias = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
    return (f"És o assistente do Pulse, a aplicação doméstica de {nome or 'um utilizador'}. Agora: {dias[agora.weekday()]}, {agora:%d/%m/%Y %H:%M} (Europe/Lisbon).\n"
            "Responde sempre em português de Portugal, curto e direto. Usa as ferramentas para consultar e para propor ações; nunca inventes ids nem dados.\n"
            "Escrever não é contigo: as ações ficam como proposta e o utilizador confirma. Propõe tudo o que foi pedido de uma vez e resume em uma frase "
            "o que vais fazer («Vou adicionar pão e cebolas à lista Casa. Confirmas?»).\n"
            "Se faltar informação que não consegues deduzir, pergunta. Compras: a lista por omissão é a «Casa» (partilhada); procura o produto antes de o adicionar. "
            "Datas relativas («amanhã», «sexta») resolvem-se a partir de agora. Nunca apagues nada que não tenha sido pedido expressamente.")


def _http(url: str, cabecalhos: dict, corpo: bytes) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=corpo, method="POST", headers=cabecalhos)
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        raise IaErro(503, "ia_sem_rede", "não consegui falar com o assistente; tenta outra vez") from None


class Agente:
    def __init__(self, chave: str, modelo: str = "", transporte=None):
        self.chave, self.modelo, self.transporte = chave, modelo or MODELO_OMISSAO, transporte or _http
        self._pedidos: dict[int, list[float]] = {}

    @property
    def ativo(self) -> bool:
        return bool(self.chave)

    def _limite(self, uid: int) -> None:
        agora = time.monotonic()
        recentes = [t for t in self._pedidos.get(uid, []) if agora - t < 60]
        if len(recentes) >= LIMITE_POR_MINUTO:
            raise IaErro(429, "ia_demasiados_pedidos", "demasiados pedidos seguidos; espera um minuto")
        self._pedidos[uid] = recentes + [agora]

    def _modelo(self, sistema: str, mensagens: list, tools: list) -> dict:
        corpo = json.dumps({"model": self.modelo, "max_tokens": 1024, "system": sistema, "tools": tools, "messages": mensagens}).encode()
        status, raw = self.transporte(URL, {"x-api-key": self.chave, "anthropic-version": "2023-06-01", "content-type": "application/json"}, corpo)
        if status != 200:
            raise IaErro(502, "ia_erro", f"o assistente respondeu com erro (HTTP {status})")
        return json.loads(raw.decode())

    def conversar(self, conn, app, user: dict, mensagens: list[dict], agora: datetime) -> dict:
        """Uma volta da conversa. `mensagens`: [{papel: 'utilizador'|'assistente', texto}] (o cliente guarda-as). Devolve o texto e as propostas."""
        if not self.ativo:
            raise IaErro(503, "ia_desligada", "o assistente não está ligado neste servidor")
        if not mensagens or mensagens[-1]["papel"] != "utilizador":
            raise IaErro(400, "conversa_invalida", "a última mensagem tem de ser do utilizador")
        self._limite(user["id"])
        hist = [{"role": "user" if m["papel"] == "utilizador" else "assistant", "content": m["texto"][:MAX_TEXTO]} for m in mensagens[-MAX_MENSAGENS:]]
        while hist and hist[0]["role"] != "user":
            hist.pop(0)
        tools = ferramentas(conn, user["id"])
        permitidas = {t["name"] for t in tools}
        propostas: list[dict] = []
        texto = ""
        for _ in range(MAX_VOLTAS):
            r = self._modelo(_sistema(user["nome"] or "", agora), hist, tools)
            blocos = r.get("content", [])
            texto = " ".join(b["text"] for b in blocos if b.get("type") == "text").strip() or texto
            usos = [b for b in blocos if b.get("type") == "tool_use"]
            if not usos:
                break
            hist.append({"role": "assistant", "content": blocos})
            resultados = []
            for u in usos:
                resultados.append({"type": "tool_result", "tool_use_id": u["id"], **self._ferramenta(conn, app, user, u, permitidas, propostas)})
            hist.append({"role": "user", "content": resultados})
        return {"texto": texto or "Não percebi o que queres; podes dizer de outra forma?", "propostas": propostas}

    def _ferramenta(self, conn, app, user: dict, uso: dict, permitidas: set, propostas: list) -> dict:
        nome, entrada = uso["name"], uso.get("input") or {}
        if nome not in permitidas:
            return {"content": "ferramenta indisponível para esta conta", "is_error": True}
        try:
            if nome == "compras_procurar":
                return {"content": json.dumps(_procurar(conn, user["id"], str(entrada.get("texto", ""))), ensure_ascii=False)}
            if nome == "consultar_hoje":
                from pulse.api.v1.dashboard import construir_locais
                so = {m for m in entrada.get("modulos", []) if isinstance(m, str)} or None
                r = dashboard.hoje(app.dados, user["email"], app.agora(), modulos.indisponiveis_para(conn, user["id"]), construir_locais(app, user["id"]), so)
                return {"content": json.dumps(r["modulos"], ensure_ascii=False, default=str)[:12000]}
            acao = actions.ACOES[_acao(nome)]
            acao.params.model_validate(entrada)                            # recusar já parâmetros inválidos: o modelo corrige
        except ContaErro as e:
            return {"content": e.mensagem if hasattr(e, "mensagem") else str(e), "is_error": True}
        except Exception as e:                                             # parâmetros inválidos e falhas de módulos: o modelo vê e reage
            return {"content": f"erro: {str(e)[:300]}", "is_error": True}
        propostas.append({"acao": acao.nome, "nivel": acao.nivel, "descricao": acao.descricao, "params": entrada})
        return {"content": "Proposta registada; o utilizador vai confirmar. Não voltes a propor a mesma ação."}


def confirmar(conn, app, user: dict, propostas: list[dict], agora: datetime) -> list[dict]:
    """Corre as propostas confirmadas, pela camada oficial de ações (origem `ia`). Uma que falha não impede as outras."""
    ctx = actions.Contexto(app.dados, user["email"], agora, app.avisos, lambda: app.avisos.recalcular_em_fundo(user["email"]), app.google, app.canais)
    out = []
    for p in propostas:
        try:
            r = actions.executar(conn, ctx, p["acao"], p["params"], origem="ia", confirmado=True)
            out.append({"acao": p["acao"], "ok": True, "resultado": r})
        except ContaErro as e:
            out.append({"acao": p["acao"], "ok": False, "erro": getattr(e, "mensagem", str(e))})
        except Exception as e:
            out.append({"acao": p["acao"], "ok": False, "erro": str(getattr(e, "mensagem", e))[:200]})
    return out
