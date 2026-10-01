#!/usr/bin/env python3
"""Servidor de demonstração para a revisão visual da app (ADR-081): o Pulse **real** sobre uma base de teste + um `dados-api` falso com dados sintéticos.

Não toca em produção: usa uma pasta temporária e a porta 18897 (o `dados-api` falso na 18898). As capturas de ecrãs do Android
(`android/app/src/test/.../captura`, `PULSE_CAPTURAS=1`) falam com este servidor. Conta de demonstração: pereirabmd@gmail.com / DemoPulse1234.

    server/.venv/bin/python scripts/capturas/servidor_demo.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "server"))

import uvicorn  # noqa: E402

from pulse import accounts, config  # noqa: E402
from pulse.main import create_app  # noqa: E402
from pulse.services import compras, ia  # noqa: E402

CHAVE = "k" * 40
EMAIL, CAMILA, SENHA = "pereirabmd@gmail.com", "camilameau@gmail.com", "DemoPulse1234"
TZ = ZoneInfo("Europe/Lisbon")
HOJE = datetime.now(TZ).date()


def iso(d: date) -> str:
    return d.isoformat()


def segunda(d: date) -> date:
    return d - timedelta(days=d.weekday())


# --- dados sintéticos ------------------------------------------------------------------------------------------------------------

def rto_dias() -> dict:
    dias = {}
    d = date(HOJE.year, 1, 1)
    while d < HOJE + timedelta(days=20):
        if d.weekday() < 5:
            dias[iso(d)] = "T" if d.weekday() in (1, 2, 3) else "C"
        d += timedelta(days=1)
    return dias


def rto_notas() -> list:
    s = segunda(HOJE) + timedelta(days=14)
    return [{"id": 1, "dataInicio": iso(s), "dataFim": iso(s + timedelta(days=4)), "categoria": "Férias", "descricao": ""},
            {"id": 2, "dataInicio": iso(HOJE + timedelta(days=3)), "dataFim": iso(HOJE + timedelta(days=3)), "categoria": "Validação", "descricao": "Normal"}]


def peso_registos() -> list:
    out, p = [], 108.4
    for i in range(60, -1, -2):
        p -= 0.15 + (0.1 if i % 6 == 0 else -0.05)
        out.append({"id": 100 - i, "quando": f"{iso(HOJE - timedelta(days=i))} 08:0{i % 6}:00", "peso": round(p, 1), "nota": "jejum" if i % 10 == 0 else ""})
    return out


CATS = [{"id": 1, "nome": "Casa", "cor": "#2F9E72"}, {"id": 2, "nome": "Rendimentos", "cor": "#3F7FC0"}, {"id": 3, "nome": "Alimentação", "cor": "#D9A441"},
        {"id": 4, "nome": "Transportes", "cor": "#C24848"}, {"id": 5, "nome": "Saúde", "cor": "#6A5ACD"}]


def lanc(i, tipo, desc, valor, venc, pago=None, cat=1):
    c = next(x for x in CATS if x["id"] == cat)
    return {"id": i, "tipo": tipo, "descricao": desc, "valor": valor, "categoria_id": cat, "categoria": c["nome"], "data_vencimento": venc, "data_pagamento": pago,
            "recorrente": i % 3 == 0, "mes_referencia": venc[:7]}


def lancamentos(mes: str) -> list:
    a, m = int(mes[:4]), int(mes[5:])
    d = lambda n: f"{a:04d}-{m:02d}-{n:02d}"  # noqa: E731
    atual = mes == HOJE.strftime("%Y-%m")
    return [lanc(1, "rendimento", "Salário", 2150.0, d(1), d(1), 2), lanc(2, "despesa", "Renda", 780.0, d(5), d(5), 1), lanc(3, "despesa", "Eletricidade", 64.3, d(8), d(8) if not atual or HOJE.day > 8 else None, 1),
            lanc(4, "despesa", "Internet e TV", 42.9, d(10), d(10) if not atual or HOJE.day > 10 else None, 1), lanc(5, "despesa", "Supermercado", 312.45, d(12), None if atual else d(12), 3),
            lanc(6, "despesa", "Passe CP", 40.0, d(2), d(2), 4), lanc(7, "despesa", "Farmácia", 23.8, d(20), None, 5), lanc(8, "despesa", "Seguro automóvel", 118.0, d(25), None, 4)]


def bilhetes() -> dict:
    s = segunda(HOJE)
    v = lambda i, dia, hora, comb, o, dst, ativo="SIM": {"id": i, "data": iso(s + timedelta(days=dia)), "hora": hora, "origem": o, "destino": dst, "comboio": comb, "ativo": ativo}  # noqa: E731
    seguinte = [v(111, 7, "06:45", 520, "Aveiro", "Lisboa Oriente"), v(112, 7, "17:30", 731, "Lisboa Oriente", "Aveiro"), v(113, 8, "06:45", 520, "Aveiro", "Lisboa Oriente"),
                v(114, 10, "17:30", 731, "Lisboa Oriente", "Aveiro")]
    esta = [v(101, i, "06:45", 520, "Aveiro", "Lisboa Oriente") for i in (1, 2, 3)] + [v(105, i, "17:30", 731, "Lisboa Oriente", "Aveiro") for i in (1, 2, 3)]
    compras_ = [{"id": 1, "data": iso(s + timedelta(days=7)), "hora": "06:45", "comboio": 520, "origem": "Aveiro", "destino": "Lisboa Oriente", "carruagem": "21", "lugar": "53", "referencia": "R1"},
                {"id": 2, "data": iso(s + timedelta(days=1)), "hora": "06:45", "comboio": 520, "origem": "Aveiro", "destino": "Lisboa Oriente", "carruagem": "22", "lugar": "77", "referencia": "R2"}]
    return {"passe": {"dataUltimaCompra": iso(HOJE - timedelta(days=21)), "validadeDias": 29, "dataExpira": iso(HOJE + timedelta(days=8)), "diasRestantes": 8},
            "viagens": esta + seguinte, "compras": compras_,
            "pedidos": [{"id": 104, "data": iso(s + timedelta(days=8)), "hora": "17:30", "origem": "Lisboa Oriente", "destino": "Aveiro", "comboio": 731, "ativo": "SIM", "retry": "SIM",
                         "intervaloMinutos": 15, "forcar": "NAO", "estado": "PENDENTE", "ultimaTentativa": None, "referencia": None, "mensagem": "", "trocaVenda": 126351561,
                         "trocaReferencia": "CP-G3DWZ445104M", "trocaAntecedenciaMin": 30},
                        {"id": 1, "data": iso(s + timedelta(days=8)), "hora": "06:45", "origem": "Aveiro", "destino": "Lisboa Oriente", "comboio": 520, "ativo": "SIM", "retry": "SIM",
                         "intervaloMinutos": 15, "forcar": "NAO", "estado": "ESGOTADO", "ultimaTentativa": None, "referencia": None, "mensagem": "sem lugares"}],
            "logs": [{"ts": f"{iso(HOJE)} 06:00:00", "tipo": "COMPRA", "resultado": "CONFIRMED"}, {"ts": f"{iso(HOJE - timedelta(days=1))} 06:00:00", "tipo": "VERIFICACAO", "resultado": "OK"}],
            "utilizador": {"id": 1, "nome": "Bruno", "eu": True}, "pessoas": [{"id": 1, "nome": "Bruno", "eu": True}, {"id": 2, "nome": "Camila", "eu": False}]}


def tarefas() -> dict:
    T = lambda i, nome, cat, rec, pessoa, prio="Media", dias="": {"id": i, "nome": nome, "categoria": cat, "recorrencia": rec, "diasSemana": dias, "diaMes": None, "horaNotificacao": "",  # noqa: E731
                                                                  "pessoaPadrao": pessoa, "ativa": True, "prioridade": prio, "icone": "", "rotacaoPessoas": "", "dependeDe": ""}
    ts = [T("T1", "Limpar casas de banho", "Limpeza", "Semanal", "Bruno", "Alta", "Seg"), T("T2", "Aspirar a sala", "Limpeza", "Diaria", "Camila"), T("T3", "Lavar a loiça", "Cozinha", "Diaria", "Bruno"),
          T("T4", "Regar as plantas", "Casa", "Semanal", "Camila", "Baixa", "Qua"), T("T5", "Mudar areia do gato", "Animais", "Diaria", "Bruno", "Alta"), T("T6", "Tirar o lixo", "Casa", "Diaria", "Camila"),
          T("T7", "Mudar roupas de cama", "Casa", "Semanal", "Camila", "Media", "Qui"), T("T8", "Limpar o frigorífico", "Cozinha", "Mensal", "Bruno", "Baixa")]
    I = lambda i, t, dia, pessoa, estado="Pendente": {"id": i, "tarefaId": t, "data": iso(HOJE + timedelta(days=dia)), "pessoa": pessoa, "estado": estado, "dataConclusao": "", "notificacaoEnviada": False}  # noqa: E731
    ins = [I("I1", "T1", 0, "Bruno"), I("I2", "T2", 0, "Camila", "Concluida"), I("I3", "T3", 0, "Bruno"), I("I4", "T5", 0, "Bruno", "Concluida"), I("I5", "T6", 0, "Camila"),
           I("I6", "T7", 0, "Camila"), I("I7", "T2", -1, "Camila"), I("I8", "T4", 1, "Camila"), I("I9", "T3", 1, "Bruno"), I("I10", "T8", 1, "Bruno")]
    cfg = [{"chave": "Pessoa1_Nome", "valor": "Bruno"}, {"chave": "Pessoa1_Email", "valor": EMAIL}, {"chave": "Pessoa2_Nome", "valor": "Camila"}, {"chave": "Pessoa2_Email", "valor": CAMILA}] + \
          [{"chave": f"Categoria{n}", "valor": c} for n, c in enumerate(["Limpeza", "Cozinha", "Casa", "Animais", "Jardim"], 1)]
    return {"tarefas": ts, "instancias": ins, "config": cfg, "piscina": []}


ROTAS = {
    "/rto/dias": lambda q: {"dias": rto_dias()}, "/rto/notas": lambda q: {"notas": rto_notas()},
    "/peso/registos": lambda q: {"registos": peso_registos()}, "/peso/config": lambda q: {"altura": 178.0, "pesoAlvo": 98.0, "nascimento": "1984-05-12", "sexo": "M", "atividade": "leve"},
    "/financas/categorias": lambda q: {"categorias": CATS}, "/financas/lembretes": lambda q: {"lembretes": [{"id": 1, "titulo": "IRS", "data": iso(HOJE + timedelta(days=30)), "recorrencia": "unico"}]},
    "/financas/lancamentos": lambda q: {"lancamentos": [x for m in {q.get("mes", [HOJE.strftime("%Y-%m")])[0], (HOJE - timedelta(days=28)).strftime("%Y-%m"), HOJE.strftime("%Y-%m")} for x in lancamentos(m)
                                                      if ("mes" not in q or x["mes_referencia"] == q["mes"][0]) and ("pendentes" not in q or x["data_pagamento"] is None)]},
    "/financas/agregado": lambda q: {"linhas": [{"mes": (HOJE.replace(day=1) - timedelta(days=30 * k)).strftime("%Y-%m"), "tipo": t, "categoria_id": c, "categoria": n, "descricao": n, "total": v, "n": 1}
                                                 for k in range(4) for (t, c, n, v) in (("despesa", 1, "Casa", 890.0 - k * 20), ("despesa", 3, "Alimentação", 410.0 + k * 15), ("rendimento", 2, "Rendimentos", 2150.0))]},
    "/bilhetes/dados": lambda q: bilhetes(), "/tarefas/dados": lambda q: tarefas(),
    "/bilhetes/cp/futuros": lambda q: {"bilhetes": [{"venda": 126351561, "referencia": "CP-G3DWZ445104M", "estado": "CONFIRMED", "origem": "Lisboa Oriente", "destino": "Aveiro", "data": iso(HOJE + timedelta(days=1)),
                                                    "hora": "19:39", "chegada": "22:02", "comboio": 723, "servico": "Intercidades", "carruagem": 22, "lugar": 77, "valor": 0, "podeCancelar": True}]},
    "/bilhetes/cp/passe": lambda q: {"passes": [{"cartao": "Cartão CP", "designacao": "Passe Ferroviário Verde Digital 30", "origem": "Aveiro", "destino": "Lisboa Oriente", "inicio": iso(HOJE - timedelta(days=21)),
                                                "validade": iso(HOJE + timedelta(days=8)), "renovavel": False}]},
}


class FalsoDados(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _resp(self, status, corpo):
        raw = json.dumps(corpo).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/saude":
            return self._resp(200, {"ok": True})
        f = ROTAS.get(u.path)
        self._resp(*((200, f(parse_qs(u.query))) if f else (200, {"ok": True})))

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0)); self._resp(200, {"ok": True})
    do_PUT = do_DELETE = do_POST


def semear(app) -> None:
    c = app.state.db()
    try:
        u1 = accounts.criar_utilizador(c, EMAIL, SENHA, must_change=False, admin=True, nome="Bruno")
        accounts.criar_utilizador(c, CAMILA, SENHA, must_change=False, nome="Camila")
        casa = c.execute("SELECT id FROM shop_lists WHERE padrao = 1").fetchone()["id"]
        agora = int(datetime.now(TZ).timestamp())
        for n, nome in enumerate(["Leite meio-gordo", "Ovos", "Maçã", "Pão de forma", "Arroz agulha", "Papel higiénico", "Detergente da loiça", "Iogurte natural", "Cebola", "Frango", "Café", "Água"]):
            p = c.execute("SELECT id FROM shop_products WHERE nome = ? COLLATE NOCASE", (nome,)).fetchone()
            if p:
                compras.adicionar(c, u1, casa, produto=p["id"], agora=agora)
        for it in c.execute("SELECT id FROM shop_items WHERE list_id = ? ORDER BY id LIMIT 3", (casa,)).fetchall():
            compras.comprado(c, u1, it["id"], True, agora)
        compras.lista_criar(c, u1, "Churrasco", "pessoal", agora)
    finally:
        c.close()


def modelo_simulado(url, cabecalhos, corpo):
    """O «modelo» da demonstração: propõe adicionar pão e cebolas (só para ver o ecrã de confirmação do assistente)."""
    r = {"content": [{"type": "text", "text": "Vou adicionar pão e cebolas à lista Casa. Confirmas?"},
                     {"type": "tool_use", "id": "t1", "name": "compras__adicionar", "input": {"lista": 1, "nome": "Pão", "categoria": "padaria"}},
                     {"type": "tool_use", "id": "t2", "name": "compras__adicionar", "input": {"lista": 1, "nome": "Cebola", "categoria": "frutas-legumes"}}], "usage": {}}
    return 200, json.dumps(r).encode()


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="pulse-demo-"))
    srv = ThreadingHTTPServer(("127.0.0.1", 18898), FalsoDados)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    s = config.load({"PULSE_ENV": "test", "PULSE_DB_PATH": str(tmp / "teste-demo.db"), "PULSE_DADOS_URL": "http://127.0.0.1:18898", "PULSE_TAREFAS_URL": "",
                     "PULSE_SERVICE_KEY": CHAVE, "PULSE_WEB_BASE_PATH": "/", "PULSE_SCHEDULER_S": "0"})
    app = create_app(s, ia_agente=ia.Agente("demo", transporte=modelo_simulado))
    import contextlib
    with contextlib.ExitStack():
        servidor = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=18897, log_level="warning"))
        t = threading.Thread(target=servidor.run, daemon=True); t.start()
        while not servidor.started:
            pass
        semear(app)
        print(f"servidor de demonstração pronto em http://127.0.0.1:18897 ({EMAIL} / {SENHA})", flush=True)
        t.join()


if __name__ == "__main__":
    main()
