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
import logging
import re
import time
import urllib.error
import urllib.request
from datetime import datetime

from pulse import actions
from pulse.accounts import ContaErro
from pulse.services import bilhetes_favoritos, compras, dashboard, modulos

LOG = logging.getLogger("pulse.ia")
URL = "https://api.anthropic.com/v1/messages"
MODELO_OMISSAO = "claude-haiku-4-5-20251001"
MAX_VOLTAS = 6                      # idas e voltas ao modelo por comando
MAX_MENSAGENS = 20                  # mensagens de conversa aceites do cliente
MAX_TEXTO = 600
LIMITE_POR_MINUTO = 12
# Ações de administração, manutenção e «desfazer» técnico: o agente não as vê (menos ferramentas = menos tokens a cada volta, e menos risco).
NAO_PARA_IA = {"tarefas.admin", "tarefas.gerar", "tarefas.pessoa_adicionar", "tarefas.pessoa_editar", "tarefas.pessoa_remover", "tarefas.reatribuir",
               "tarefas.avisos_horario", "tarefas.preferencias", "tarefas.piscina_repor", "compras.restaurar", "compras.categoria_ocultar", "compras.ocultar",
               "compras.sugestao_ignorar", "rto.nota_restaurar", "rto.gerar_validacoes", "peso.configurar", "bilhetes.pedido_forcar", "bilhetes.pedido_repetir",
               "bilhetes.semana", "bilhetes.cp_cancelar"}
IDS_SEM_NOME = {"conta", "tarefa", "lancamento", "evento", "registo", "pedido", "venda", "lembrete", "categoria_id", "instancia"}
LEITURAS = {
    "consultar_hoje": "Consulta o que a conta tem hoje e a seguir: tarefas, próximo bilhete, RTO, peso, contas a pagar, compras por comprar, próximos eventos do "
                      "calendário e emails importantes. `modulos` limita a consulta (por omissão, todos).",
    "bilhetes_favoritos": "Lista os comboios favoritos da conta (id, apelido, comboio, hora, origem, destino). Usa antes de marcar uma viagem por favorito "
                          "(`bilhetes.marcar_favorito`): escolhe pelo apelido, hora ou percurso que o utilizador disser.",
    "compras_procurar": "Procura produtos no catálogo de Compras (sem distinguir acentos nem maiúsculas) e diz se já estão na lista; devolve também as listas "
                        "(ids). Usa SEMPRE antes de adicionar um produto, para reutilizar o do catálogo em vez de criar um duplicado.",
}


class IaErro(ContaErro):
    pass


def nome_ferramenta(acao: str) -> str:
    return acao.replace(".", "__")


def _acao(ferramenta: str) -> str:
    return ferramenta.replace("__", ".")


def _compacto(esquema):
    """Tira do esquema o que só gasta tokens (títulos e valores por omissão): o modelo não precisa deles."""
    if isinstance(esquema, dict):
        return {k: _compacto(v) for k, v in esquema.items() if k not in ("title", "default")}
    if isinstance(esquema, list):
        return [_compacto(x) for x in esquema]
    return esquema


def ferramentas(conn, uid: int) -> list[dict]:
    """As ferramentas do modelo: as leituras e as ações dos módulos a que a conta tem acesso (o esquema vem dos modelos das ações)."""
    bloqueados = modulos.indisponiveis_para(conn, uid)
    out = [
        {"name": "consultar_hoje", "description": LEITURAS["consultar_hoje"],
         "input_schema": {"type": "object", "properties": {"modulos": {"type": "array", "items": {"type": "string", "enum": ["tarefas", "bilhetes", "rto", "peso", "financas", "compras", "calendario", "email"]}}}}},
        {"name": "compras_procurar", "description": LEITURAS["compras_procurar"],
         "input_schema": {"type": "object", "properties": {"texto": {"type": "string", "maxLength": 80}}, "required": ["texto"]}},
        {"name": "bilhetes_favoritos", "description": LEITURAS["bilhetes_favoritos"], "input_schema": {"type": "object", "properties": {}}},
    ]
    if "bilhetes" in bloqueados:
        out = [t for t in out if t["name"] != "bilhetes_favoritos"]
    for a in actions.ACOES.values():
        if a.modulo in bloqueados or a.nome in NAO_PARA_IA:
            continue
        esquema = _compacto(a.params.model_json_schema())
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


def _nome_de(conn, sql: str, valor) -> str | None:
    r = conn.execute(sql, (valor,)).fetchone()
    return r[0] if r else None


def _dia_curto(d: str) -> str:
    try:
        x = datetime.fromisoformat(d)
        return f"{['seg', 'ter', 'qua', 'qui', 'sex', 'sáb', 'dom'][x.weekday()]} {x:%d/%m}"
    except ValueError:
        return d


def resumo(conn, acao: "actions.Acao", params: dict) -> str:
    """O que a proposta faz, em português e **sem ids** (o utilizador nunca vê «lista 1» nem «produto 37»): os ids resolvem-se para nomes."""
    lista = _nome_de(conn, "SELECT nome FROM shop_lists WHERE id = ?", params["lista"]) if isinstance(params.get("lista"), int) else None
    if acao.nome == "compras.adicionar":
        nome = params.get("nome") or (_nome_de(conn, "SELECT nome FROM shop_products WHERE id = ?", params["produto"]) if isinstance(params.get("produto"), int) else None)
        return f"Adicionar «{nome or 'um produto'}» à lista «{lista or 'Casa'}»"
    if acao.nome == "bilhetes.marcar_favorito":
        f = conn.execute("SELECT comboio, hora, origem, destino FROM bilhetes_favoritos WHERE id = ?", (params.get("favorito"),)).fetchone()
        dias = ", ".join(_dia_curto(str(d)) for d in params.get("datas", []))
        return f"Marcar o comboio {f['comboio']} ({f['origem']} → {f['destino']}, {f['hora']}) em {dias}" if f else f"Marcar um favorito em {dias}"
    partes = []
    for k, v in params.items():
        if v is None or v == "" or k in ("cid", "utilizador"):
            continue
        if k == "lista":
            partes.append(f"lista «{lista}»" if lista else "")
        elif k == "destino" and isinstance(v, int):
            n = _nome_de(conn, "SELECT nome FROM shop_lists WHERE id = ?", v)
            partes.append(f"para a lista «{n}»" if n else "")
        elif k == "produto":
            n = _nome_de(conn, "SELECT nome FROM shop_products WHERE id = ?", v) if isinstance(v, int) else None
            partes.append(f"«{n}»" if n else "")
        elif k == "item":
            n = _nome_de(conn, "SELECT p.nome FROM shop_items i JOIN shop_products p ON p.id = i.product_id WHERE i.id = ?", v) if isinstance(v, int) else None
            partes.append(f"«{n}»" if n else "")
        elif k == "favorito":
            f = conn.execute("SELECT comboio, hora FROM bilhetes_favoritos WHERE id = ?", (v,)).fetchone() if isinstance(v, int) else None
            partes.append(f"comboio {f['comboio']} às {f['hora']}" if f else "")
        elif (isinstance(v, int) and not isinstance(v, bool) and k in IDS_SEM_NOME) or (isinstance(v, str) and re.fullmatch(r"I\d{1,20}", v)):
            continue                                                  # ids que não se conseguem traduzir: melhor não mostrar
        elif isinstance(v, list):
            partes.append(f"{k}: {', '.join(_dia_curto(str(x)) for x in v)}")
        else:
            partes.append(f"{k}: {_dia_curto(v) if isinstance(v, str) and len(v) == 10 and v[4] == '-' else v}")
    partes = [p for p in partes if p]
    base = acao.descricao.rstrip(".")
    return f"{base} — {'; '.join(partes)}" if partes else base


def _sistema(nome: str, agora: datetime) -> str:
    dias = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
    return (f"És o assistente do Pulse, a aplicação doméstica de {nome or 'um utilizador'}. Hoje é {dias[agora.weekday()]}, {agora:%d/%m/%Y} (Europe/Lisbon).\n"
            "Responde sempre em português de Portugal, curto e direto. Usa as ferramentas para consultar e para propor ações; nunca inventes ids nem dados.\n"
            "Escrever não é contigo: as ações ficam como proposta e o utilizador confirma. Propõe tudo o que foi pedido de uma vez e resume em uma frase "
            "o que vais fazer («Vou adicionar pão e cebolas à lista Casa. Confirmas?»).\n"
            "Se faltar informação que não consegues deduzir, pergunta. Compras: a lista por omissão é a «Casa» (partilhada); procura o produto antes de o adicionar. "
            "Datas relativas («amanhã», «sexta») resolvem-se a partir de agora. Nunca apagues nada que não tenha sido pedido expressamente.\n"
            "NUNCA escrevas ids nem números internos (de listas, produtos, itens, favoritos…) na resposta: usa só nomes («lista Casa», «Pão»). "
            "Bilhetes: para marcar um comboio favorito usa `bilhetes_favoritos` e depois `bilhetes.marcar_favorito` (podes marcar vários dias numa só ação).")


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
        # cache do prompt (ferramentas + sistema, ~15 mil tokens): as voltas seguintes e os pedidos nos 5 minutos seguintes leem-no a 10 % do preço
        tools = [*tools[:-1], {**tools[-1], "cache_control": {"type": "ephemeral"}}]
        corpo = json.dumps({"model": self.modelo, "max_tokens": 1024, "tools": tools, "messages": mensagens,
                            "system": [{"type": "text", "text": sistema, "cache_control": {"type": "ephemeral"}}]}).encode()
        status, raw = self.transporte(URL, {"x-api-key": self.chave, "anthropic-version": "2023-06-01", "content-type": "application/json"}, corpo)
        if status != 200:
            raise IaErro(502, "ia_erro", f"o assistente respondeu com erro (HTTP {status})")
        r = json.loads(raw.decode())
        u = r.get("usage") or {}
        LOG.info("ia: entrada=%s cache_lida=%s cache_escrita=%s saida=%s", u.get("input_tokens"), u.get("cache_read_input_tokens"), u.get("cache_creation_input_tokens"), u.get("output_tokens"))
        return r

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
        permitidas_escrita = permitidas - set(LEITURAS)
        propostas: list[dict] = []
        texto = ""
        if hist and hist[-1]["role"] == "user":                       # a hora vai aqui (e não no sistema) para não invalidar a cache
            hist[-1] = {**hist[-1], "content": f"{hist[-1]['content']}\n(agora são {agora:%H:%M})"}
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
            if all(u["name"] in permitidas_escrita for u in usos) and texto:
                break                                                     # só propostas e o modelo já explicou: poupa a volta final
        return {"texto": texto or "Não percebi o que queres; podes dizer de outra forma?", "propostas": propostas}

    def _ferramenta(self, conn, app, user: dict, uso: dict, permitidas: set, propostas: list) -> dict:
        nome, entrada = uso["name"], uso.get("input") or {}
        if nome not in permitidas:
            return {"content": "ferramenta indisponível para esta conta", "is_error": True}
        try:
            if nome == "compras_procurar":
                return {"content": json.dumps(_procurar(conn, user["id"], str(entrada.get("texto", ""))), ensure_ascii=False)}
            if nome == "bilhetes_favoritos":
                return {"content": json.dumps({"favoritos": bilhetes_favoritos.listar(conn, user["id"])}, ensure_ascii=False)}
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
        propostas.append({"acao": acao.nome, "nivel": acao.nivel, "descricao": acao.descricao, "resumo": resumo(conn, acao, entrada), "params": entrada})
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
