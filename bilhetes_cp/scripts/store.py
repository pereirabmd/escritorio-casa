"""Camada de dados em SQLite (bilhetes.db) — a alternativa local ao Google Sheets.

Tem EXATAMENTE a interface de `common.SheetsClient` (read_config, read_tickets, read_requests,
append_log, append_ticket, append_request, update_request) e devolve os dados no mesmo formato
(listas de células, na mesma ordem de colunas), por isso o resto do sistema — scheduler, hot_buy,
pedidos, live_delay, os validadores — não muda. Escolhe-se com `BILHETES_BACKEND=sqlite` (ver
`common.get_store`).

Diferenças deliberadas face à Sheet:
- Cada linha de `read_config()['weekly']` traz o `id` da viagem numa 7.ª coluna e cada linha de
  `read_requests()` numa 14.ª: é o número de `vN` / `pedidoN` (estável, nunca reutilizado), em vez da
  posição da linha na folha. Ver `common._row_id`.
- Datas em ISO, horas em 'HH:MM'. A validade do passe e os dias que faltam calculam-se aqui (na
  Sheet eram fórmulas).
- Nunca cria a base de dados: o esquema é do `dados/migrations_bilhetes/` e quem o aplica é a API.
  Se o ficheiro não existir, falha alto (nada de uma BD vazia criada por engano a "esconder" a config).
- Uma ligação por chamada (o daemon vive semanas), com espera de até 10 s por um lock de escrita.
  Os chamadores já tratam qualquer falha como não-fatal (`Buyer.sheet()`), como com a Sheet.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import common
from common import BASE_DIR, TZ, env, sanitize

_REQUEST_FIELDS = {"data", "origem", "destino", "comboio", "hora", "ativo", "retry", "intervalo_minutos",
                   "forcar", "estado", "ultima_tentativa", "referencia", "mensagem"}


def default_db_path() -> Path:
    # ~/bilhetes_cp e ~/dados são irmãos (no repositório e no Pi); a BD vive em dados/data/
    return Path(env("BILHETES_DB") or (BASE_DIR.parent / "dados" / "data" / "bilhetes.db"))


def _txt(v: Any) -> str:
    return sanitize(v) if isinstance(v, str) else ("" if v is None else str(v))


class SqliteStore:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else default_db_path()

    def _connect(self) -> sqlite3.Connection:
        if not self.path.is_file():
            raise FileNotFoundError(f"base de dados dos bilhetes inexistente: {self.path}")
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    # ---- leitura ------------------------------------------------------------

    def read_config(self) -> dict:
        with closing(self._connect()) as c:
            p = c.execute("SELECT data_ultima_compra, validade_dias FROM bilhetes_passe WHERE id=1").fetchone()
            rows = c.execute("SELECT data, origem, destino, comboio, hora, ativo, id FROM bilhetes_viagens "
                             "ORDER BY data, hora, id").fetchall()
        ultima = p["data_ultima_compra"] if p else None
        validade = p["validade_dias"] if p else 29
        if ultima:
            expira = date.fromisoformat(ultima) + timedelta(days=validade)   # 30 dias contando o dia do carregamento
            passe = [ultima, validade, expira.isoformat(), (expira - common.now_local().date()).days]
        else:
            passe = ["", validade, "", ""]
        return {"fetched_at": datetime.now(UTC).isoformat(), "passe": passe,
                "weekly": [list(r) for r in rows], "first_row": 0}

    def read_tickets(self) -> list[list[Any]]:
        with closing(self._connect()) as c:
            rows = c.execute("SELECT data, comboio, origem, destino, hora_partida, carruagem, lugar, referencia "
                             "FROM bilhetes_compras ORDER BY data, hora_partida, id").fetchall()
        return [list(r) for r in rows]

    def read_requests(self) -> list[list[Any]]:
        with closing(self._connect()) as c:
            rows = c.execute("SELECT data, origem, destino, comboio, hora, ativo, retry, intervalo_minutos, forcar, "
                             "estado, ultima_tentativa, referencia, mensagem, id FROM bilhetes_pedidos ORDER BY id").fetchall()
        out = []
        for r in rows:
            cells = list(r)
            if cells[7] is None:
                cells[7] = ""
            out.append(cells)
        return out

    # ---- escrita ------------------------------------------------------------

    def append_log(self, tipo: str, data_viagem: str = "", perna: str = "", comboio: Any = "",
                   status_http: Any = "", resultado: str = "", referencia: str = "",
                   mensagem_erro: str = "") -> None:
        with closing(self._connect()) as c:
            c.execute("INSERT INTO bilhetes_logs (ts, tipo, data_viagem, perna, comboio, status_http, resultado, "
                      "referencia, mensagem_erro) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      (datetime.now(TZ).isoformat(timespec="milliseconds"), _txt(tipo), _txt(data_viagem), _txt(perna),
                       _txt(comboio), _txt(status_http), _txt(resultado), _txt(referencia), _txt(mensagem_erro)))

    def append_attempts(self, rows: list[dict[str, Any]]) -> int:
        """Grava, numa só transação, os pedidos à CP de uma compra (ver `bilhetes_tentativas`) e poda os de há mais de 90 dias.
        Chamado no fim da compra, fora do caminho crítico."""
        if not rows:
            return 0
        campos = ("ts", "data_viagem", "perna", "comboio", "fase", "http", "resultado", "rel_t_ms", "rtt_ms", "ligacao_nova",
                  "ts_cp", "codigo", "detalhe")
        with closing(self._connect()) as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                c.executemany(f"INSERT INTO bilhetes_tentativas ({', '.join(campos)}) VALUES ({', '.join('?' * len(campos))})",
                              [tuple(r.get(k) if k in ("http", "rel_t_ms", "rtt_ms", "ligacao_nova", "comboio") else _txt(r.get(k, ""))
                                     for k in campos) for r in rows])
                c.execute("DELETE FROM bilhetes_tentativas WHERE gravado < datetime('now', '-90 days')")
                c.execute("COMMIT")
            except sqlite3.Error:
                c.execute("ROLLBACK")
                raise
        return len(rows)

    def append_ticket(self, data: str, comboio: Any, origem: str, destino: str,
                      hora: str, carruagem: Any, lugar: Any, referencia: str) -> None:
        try:
            train = int(float(comboio))
        except (TypeError, ValueError):
            train = None
        with closing(self._connect()) as c:
            # OR IGNORE: repetir a escrita da mesma compra (mesma referência) nunca duplica nem falha
            c.execute("INSERT OR IGNORE INTO bilhetes_compras (data, comboio, origem, destino, hora_partida, "
                      "carruagem, lugar, referencia) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                      (_txt(data), train, _txt(origem), _txt(destino), _txt(hora), _txt(carruagem), _txt(lugar), _txt(referencia)))

    def append_request(self, data: str, origem: str, destino: str, comboio: Any, hora: str,
                       ativo: str = "SIM", retry: str = "NAO", intervalo: Any = "",
                       estado: str = "PENDENTE") -> None:
        try:
            train = int(float(comboio))
        except (TypeError, ValueError):
            train = None
        try:
            minutos = int(float(intervalo)) if intervalo not in ("", None) else None
        except (TypeError, ValueError):
            minutos = None
        with closing(self._connect()) as c:
            c.execute("INSERT INTO bilhetes_pedidos (data, origem, destino, comboio, hora, ativo, retry, "
                      "intervalo_minutos, forcar, estado) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'NAO', ?)",
                      (_txt(data), _txt(origem), _txt(destino), train, _txt(hora), _txt(ativo).upper() or "SIM",
                       _txt(retry).upper() or "NAO", minutos, _txt(estado) or "PENDENTE"))

    def update_request(self, row: int, **fields: Any) -> None:
        """Escreve só os campos dados, no pedido `row` (o `N` de `pedidoN`, isto é, o id)."""
        sets, args = [], []
        for name, value in fields.items():
            if name not in _REQUEST_FIELDS:
                raise ValueError(f"coluna de Pedidos desconhecida: {name!r}")
            if name == "intervalo_minutos":
                value = int(float(value)) if value not in ("", None) else None
            elif name == "comboio":
                value = int(float(value)) if value not in ("", None) else None
            else:
                value = _txt(value)
            sets.append(f"{name} = ?")
            args.append(value)
        if not sets:
            return
        with closing(self._connect()) as c:
            cur = c.execute(f"UPDATE bilhetes_pedidos SET {', '.join(sets)} WHERE id = ?", (*args, int(row)))
            if cur.rowcount == 0:
                raise LookupError(f"pedido {row} inexistente")
