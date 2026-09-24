"""Camada de dados em SQLite — a alternativa local ao Google Sheets (`common.SheetsClient`).

Tem a MESMA interface (read_objects, append_rows, update_cells, delete_rows, tab_exists, rename_tab, find_config,
set_config) e devolve os dados no mesmo formato (dicts por NOME de cabeçalho, com `_rowIndex`), por isso
`instancias.py`, `recalcular.py`, `manutencao.py` e `servidor.py` não mudam. Escolhe-se com
`TAREFAS_BACKEND=sqlite` (ver `common.get_store`).

Traduções (para o resto do código continuar a ler "à Sheet"):
- booleanos guardam-se como 0/1 e lêem-se como 'TRUE'/'FALSE' (o código compara `str(x).upper() == "TRUE"`);
- `_rowIndex` é o `rowid` da linha (estável enquanto a linha existir), que `update_cells`/`delete_rows` usam;
- datas e horas já vêm em ISO / 'HH:MM' (a armadilha do USER_ENTERED da Sheet acabou);
- NULL lê-se como '' (a Sheet devolvia células vazias).

Nunca cria a base de dados nem o esquema (é do `dados/migrations/004_tarefas.sql`, aplicado pela API): se o
ficheiro não existir, falha alto. Uma ligação por chamada, com espera de até 10 s por um lock de escrita.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from common import BASE_DIR, env

# aba -> (tabela, [(cabeçalho da Sheet, coluna, tipo)])   tipos: txt | int | bool | data (NULL <-> '')
TABELAS: dict[str, tuple[str, list[tuple[str, str, str]]]] = {
    "Tarefas": ("tarefas_tarefas", [
        ("ID", "id", "txt"), ("Nome", "nome", "txt"), ("Categoria", "categoria", "txt"), ("Icone", "icone", "txt"),
        ("Recorrencia", "recorrencia", "txt"), ("DiasSemana", "dias_semana", "txt"), ("DiaMes", "dia_mes", "int"),
        ("HoraNotificacao", "hora_notificacao", "txt"), ("PessoaPadrao", "pessoa_padrao", "txt"), ("Ativa", "ativa", "bool"),
        ("Prioridade", "prioridade", "txt"), ("RotacaoPessoas", "rotacao_pessoas", "txt"), ("DependeDe", "depende_de", "txt")]),
    "Instancias": ("tarefas_instancias", [
        ("ID", "id", "txt"), ("TarefaID", "tarefa_id", "txt"), ("Data", "data", "txt"), ("Pessoa", "pessoa", "txt"),
        ("Estado", "estado", "txt"), ("DataConclusao", "data_conclusao", "txt"), ("NotificacaoEnviada", "notificacao_enviada", "bool")]),
    "Config": ("tarefas_config", [("Chave", "chave", "txt"), ("Valor", "valor", "txt"), ("Notas", "notas", "txt")]),
    "Piscina": ("tarefas_piscina", [
        ("ID", "id", "txt"), ("Nome", "nome", "txt"), ("AvisoLongo", "aviso_longo", "bool"), ("UltimaData", "ultima_data", "data"),
        ("ProximaData", "proxima_data", "data"), ("NotificacaoEnviada", "notificacao_enviada", "bool"),
        ("UsarIntervaloLongo", "usar_intervalo_longo", "bool")]),
}


def default_db_path() -> Path:
    # ~/tarefas/pi e ~/dados são "primos" (no repositório e no Pi): BASE_DIR.parents[1] é a pasta que contém ambos
    return Path(env("DADOS_DB") or (BASE_DIR.parents[1] / "dados" / "data" / "dados.db"))


def _para_sql(valor: Any, tipo: str) -> Any:
    if tipo == "bool":
        return 1 if (valor is True or str(valor).strip().upper() == "TRUE") else 0
    if valor is None or valor == "":
        return None if tipo in ("int", "data") else ""
    if tipo == "int":
        return int(float(valor))
    return str(valor)


def _da_sql(valor: Any, tipo: str) -> Any:
    if tipo == "bool":
        return "TRUE" if valor else "FALSE"
    return "" if valor is None else valor


class SqliteStore:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else default_db_path()

    def _connect(self) -> sqlite3.Connection:
        if not self.path.is_file():
            raise FileNotFoundError(f"base de dados inexistente: {self.path}")
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=10000")
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _tabela(tab: str) -> tuple[str, list[tuple[str, str, str]]]:
        if tab not in TABELAS:
            raise ValueError(f"aba {tab!r} não existe")
        return TABELAS[tab]

    # ---- interface da SheetsClient --------------------------------------------

    def read_objects(self, tab: str, last_col: str = "Z") -> list[dict[str, Any]]:
        tabela, cols = self._tabela(tab)
        with closing(self._connect()) as c:
            rows = c.execute(f"SELECT rowid AS _r, {', '.join(col for _, col, _ in cols)} FROM {tabela} ORDER BY rowid").fetchall()
        out = []
        for r in rows:
            obj = {cab: _da_sql(r[col], tipo) for cab, col, tipo in cols}
            obj["_rowIndex"] = r["_r"]
            out.append(obj)
        return out

    def append_rows(self, tab: str, rows: list[list[Any]]) -> None:
        """Acrescenta linhas (valores POR ORDEM dos cabeçalhos). Um id ou uma (tarefa, data) que entretanto
        já exista (p. ex. criada pela PWA ao mesmo tempo) não falha — o gerador recria o que faltar no ciclo seguinte."""
        if not rows:
            return
        tabela, cols = self._tabela(tab)
        marcas = ", ".join("?" * len(cols))
        nomes = ", ".join(col for _, col, _ in cols)
        with closing(self._connect()) as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                for valores in rows:
                    vs = list(valores) + [""] * (len(cols) - len(valores))
                    # ON CONFLICT DO NOTHING só ignora colisões de PK/UNIQUE — uma linha inválida (CHECK/NOT NULL) continua a
                    # falhar alto; um `INSERT OR IGNORE` engoliria também essas, em silêncio
                    c.execute(f"INSERT INTO {tabela} ({nomes}) VALUES ({marcas}) ON CONFLICT DO NOTHING",
                              [_para_sql(v, tipo) for v, (_, _, tipo) in zip(vs, cols)])
                c.execute("COMMIT")
            except Exception:
                c.execute("ROLLBACK")
                raise

    def update_cells(self, tab: str, row_index: int, **col_valor: Any) -> None:
        if not col_valor:
            return
        tabela, cols = self._tabela(tab)
        por_cab = {cab: (col, tipo) for cab, col, tipo in cols}
        sets, args = [], []
        for nome, valor in col_valor.items():
            if nome not in por_cab:
                raise ValueError(f"coluna {nome!r} não existe em {tab!r}")
            col, tipo = por_cab[nome]
            sets.append(f"{col} = ?")
            args.append(_para_sql(valor, tipo))
        with closing(self._connect()) as c:
            cur = c.execute(f"UPDATE {tabela} SET {', '.join(sets)} WHERE rowid = ?", (*args, int(row_index)))
            if cur.rowcount == 0:
                raise ValueError(f"linha {row_index} não existe em {tab!r}")

    def delete_rows(self, tab: str, row_indices: list[int]) -> None:
        if not row_indices:
            return
        tabela, _ = self._tabela(tab)
        with closing(self._connect()) as c:
            c.execute(f"DELETE FROM {tabela} WHERE rowid IN ({', '.join('?' * len(row_indices))})", [int(i) for i in row_indices])

    def tab_exists(self, tab: str) -> bool:
        return tab in TABELAS       # 'Subscriptions' (FCM) já não existe: a limpeza correspondente não faz nada

    def rename_tab(self, old: str, new: str) -> bool:
        return False                # só servia para marcar a aba 'Subscriptions' como descontinuada

    def find_config(self, chave: str) -> dict[str, Any] | None:
        return next((r for r in self.read_objects("Config") if str(r.get("Chave", "")).strip() == chave), None)

    def set_config(self, chave: str, valor: Any, notas: str = "") -> None:
        existente = self.find_config(chave)
        if existente:
            self.update_cells("Config", existente["_rowIndex"], Valor=valor)
        else:
            self.append_rows("Config", [[chave, valor, notas]])
