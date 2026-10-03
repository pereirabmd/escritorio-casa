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
    "consultar_tempo": "A previsão do tempo (Open-Meteo) para onde o utilizador está (ou Aveiro, se não deu a localização): agora, hoje e os próximos dias. "
                       "Usa para «vai chover?», «que tempo faz amanhã?», «preciso de casaco?».",
    "bilhetes_na_cp": "Os bilhetes futuros desta conta na CP, ao vivo (demora alguns segundos): venda, data, hora, percurso, comboio, carruagem, lugar, valor e se se pode "
                      "cancelar. A `venda` é interna: serve para `simular_devolucao` e `bilhetes.troca_armar`; NUNCA a digas ao utilizador.",
    "simular_devolucao": "Simula a devolução de um bilhete futuro (só leitura, nunca cancela): a CP deixa devolver e quanto se recebe? Usa antes de propor uma troca. "
                         "Precisa da `venda` de `bilhetes_na_cp`.",
    "bilhetes_historico": "Os pedidos feitos à CP nas compras (hora, fase, resposta, pessoa) dos últimos dias, mais recentes primeiro, e a contagem por resposta. "
                          "Só o administrador. Usa para «o que aconteceu com a compra de ontem?».",
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
        {"name": "consultar_tempo", "description": LEITURAS["consultar_tempo"], "input_schema": {"type": "object", "properties": {}}},
        {"name": "bilhetes_na_cp", "description": LEITURAS["bilhetes_na_cp"], "input_schema": {"type": "object", "properties": {}}},
        {"name": "simular_devolucao", "description": LEITURAS["simular_devolucao"],
         "input_schema": {"type": "object", "properties": {"venda": {"type": "integer", "minimum": 1}}, "required": ["venda"]}},
        {"name": "bilhetes_historico", "description": LEITURAS["bilhetes_historico"],
         "input_schema": {"type": "object", "properties": {"dias": {"type": "integer", "minimum": 1, "maximum": 30}}}},
    ]
    if "bilhetes" in bloqueados:
        out = [t for t in out if t["name"] not in ("bilhetes_favoritos", "bilhetes_na_cp", "simular_devolucao", "bilhetes_historico")]
    for a in actions.ACOES.values():
        if a.modulo in bloqueados or a.nome in NAO_PARA_IA:
            continue
        esquema = _compacto(a.params.model_json_schema())
        out.append({"name": nome_ferramenta(a.nome), "input_schema": esquema,
                    "description": f"{a.descricao} [{'pede confirmação do utilizador' if a.nivel == 'sensitive_action' else 'o utilizador confirma antes de correr'}]"})
    return out


def _tempo_para_ia(p: dict) -> dict:
    """A previsão em poucas linhas (o modelo não precisa das 24 horas): agora, hoje e os próximos dias."""
    h = p.get("hoje") or {}
    return {"local": "onde o utilizador está" if p.get("localizacao") == "dispositivo" else "Aveiro (o aparelho não deu a localização)",
            "agora": {k: p["agora"].get(k) for k in ("temp", "descricao", "vento")},
            "hoje": {k: h.get(k) for k in ("max", "min", "chuva", "descricao", "nascer", "poer")},
            "proximas_horas_com_chuva": [f"{x['hora']} ({x['chuva']}%)" for x in p.get("horas", [])[:12] if (x.get("chuva") or 0) >= 50][:6],
            "dias": [{"dia": d["diaSemana"], "data": d["data"], "max": d["max"], "min": d["min"], "chuva": d["chuva"], "descricao": d["descricao"]} for d in p.get("dias", [])[1:6]]}


def _historico_para_ia(d: dict) -> dict:
    """Os pedidos à CP em resumo: contagem por resposta e os 20 mais recentes (hora, pessoa, comboio, fase, resposta, HTTP)."""
    pedidos = d.get("pedidos", [])
    contagem: dict[str, int] = {}
    for x in pedidos:
        contagem[x.get("resultado") or "?"] = contagem.get(x.get("resultado") or "?", 0) + 1
    return {"dias": d.get("dias"), "total": len(pedidos), "por_resposta": contagem,
            "recentes": [{"hora": x["ts"][:19].replace("T", " "), "pessoa": x.get("pessoa"), "comboio": x.get("comboio"), "fase": x.get("fase"), "resposta": x.get("resultado"),
                          "http": x.get("http"), "detalhe": (x.get("detalhe") or "")[:80]} for x in pedidos[:20]],
            "desfechos": [{"hora": x["ts"][:19].replace("T", " "), "tipo": x.get("tipo"), "resultado": x.get("resultado"), "comboio": x.get("comboio")} for x in d.get("desfechos", [])[:8]]}


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
    if acao.nome == "bilhetes.troca_armar":
        inicio = f", a partir de {_dia_curto(params['inicio'][:10])} às {params['inicio'][11:16]}" if params.get("inicio") else ""
        return (f"Trocar o bilhete atual pelo comboio {params.get('comboio')} das {params.get('hora')}{inicio}. Se for outro comboio: reservo o lugar, devolvo o atual e confirmo o novo "
                "(de 15 em 15 min, até 30 min antes da partida). Se for o mesmo comboio (para ficar com o desconto): devolvo já o atual e compro logo a seguir o lugar libertado, com o risco de outra pessoa o apanhar")
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
            "Bilhetes: para marcar um comboio favorito usa `bilhetes_favoritos` e depois `bilhetes.marcar_favorito` (podes marcar vários dias numa só ação). "
            "Trocas: usa `bilhetes_na_cp` para ver os bilhetes e `simular_devolucao` para ver o reembolso antes de propor `bilhetes.troca_armar`; a hora é a da 1.ª estação do comboio. "
            "Se o comboio novo for o mesmo do bilhete, avisa o utilizador do risco (devolve-se o atual e compra-se logo a seguir: outra pessoa pode apanhar o lugar) e que só compensa se o bilhete atual foi comprado sem desconto. "
            "Tempo: usa `consultar_tempo` para o clima. Para o RTO de hoje usa `rto.marcar_dia` (T = escritório, C = casa).")


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

    def conversar(self, conn, app, user: dict, mensagens: list[dict], agora: datetime, posicao: dict | None = None) -> dict:
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
                resultados.append({"type": "tool_result", "tool_use_id": u["id"], **self._ferramenta(conn, app, user, u, permitidas, propostas, posicao)})
            hist.append({"role": "user", "content": resultados})
            if all(u["name"] in permitidas_escrita for u in usos) and texto:
                break                                                     # só propostas e o modelo já explicou: poupa a volta final
        return {"texto": texto or "Não percebi o que queres; podes dizer de outra forma?", "propostas": propostas}

    def _ferramenta(self, conn, app, user: dict, uso: dict, permitidas: set, propostas: list, posicao: dict | None = None) -> dict:
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
            if nome == "consultar_tempo":
                return {"content": json.dumps(_tempo_para_ia(app.tempo.previsao((posicao or {}).get("lat"), (posicao or {}).get("lon"), app.agora())), ensure_ascii=False)}
            if nome == "bilhetes_na_cp":
                _, d = app.dados.pedir("GET", "/bilhetes/cp/futuros", user["email"], None, timeout=100)
                return {"content": json.dumps({"bilhetes": [{k: b.get(k) for k in ("venda", "data", "hora", "origem", "destino", "comboio", "carruagem", "lugar", "valor", "podeCancelar")}
                                                            for b in (d or {}).get("bilhetes", [])][:20]}, ensure_ascii=False, default=str)}
            if nome == "simular_devolucao":
                venda = entrada.get("venda")
                if isinstance(venda, bool) or not isinstance(venda, int) or venda <= 0:
                    return {"content": "venda inválida: usa a de `bilhetes_na_cp`", "is_error": True}
                _, d = app.dados.pedir("GET", "/bilhetes/trocas/simular", user["email"], {"venda": venda}, timeout=100)
                return {"content": json.dumps({k: (d or {}).get(k) for k in ("cancelavel", "motivo", "valor")}, ensure_ascii=False)}
            if nome == "bilhetes_historico":
                dias = entrada.get("dias") if isinstance(entrada.get("dias"), int) and 1 <= entrada["dias"] <= 30 else 2
                _, d = app.dados.pedir("GET", "/bilhetes/historico", user["email"], {"dias": dias}, timeout=20)
                return {"content": json.dumps(_historico_para_ia(d or {}), ensure_ascii=False)}
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
