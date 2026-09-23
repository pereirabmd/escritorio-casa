"""FakeSheetsClient — dublê em memória do common.SheetsClient para os
testes correrem sem rede nem bibliotecas Google (mesmo espírito dos
dublês do bilhetes_cp/tests)."""

from __future__ import annotations

from typing import Any

COLUNAS: dict[str, list[str]] = {
    "Config": ["Chave", "Valor", "Notas"],
    "Instancias": ["ID", "TarefaID", "Data", "Pessoa", "Estado", "DataConclusao", "NotificacaoEnviada"],
}


class FakeSheetsClient:
    def __init__(self, dados: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self.tabs: dict[str, list[dict[str, Any]]] = {
            tab: [dict(linha) for linha in linhas] for tab, linhas in (dados or {}).items()
        }
        for linhas in self.tabs.values():
            for i, linha in enumerate(linhas):
                linha.setdefault("_rowIndex", i + 2)

    # ---- mesma interface pública do SheetsClient real, o que os testes usam ----

    def read_objects(self, tab: str, last_col: str = "Z") -> list[dict[str, Any]]:
        return [dict(r) for r in self.tabs.get(tab, [])]

    def append_rows(self, tab: str, rows: list[list[Any]]) -> None:
        linhas = self.tabs.setdefault(tab, [])
        colunas = COLUNAS.get(tab, [])
        proximo_index = (max((r["_rowIndex"] for r in linhas), default=1)) + 1
        for valores in rows:
            obj: dict[str, Any] = {colunas[i]: v for i, v in enumerate(valores) if i < len(colunas)}
            obj["_rowIndex"] = proximo_index
            linhas.append(obj)
            proximo_index += 1

    def update_cells(self, tab: str, row_index: int, **col_valor: Any) -> None:
        for r in self.tabs.get(tab, []):
            if r["_rowIndex"] == row_index:
                r.update(col_valor)
                return
        raise ValueError(f"linha {row_index} não existe em {tab!r}")

    def delete_rows(self, tab: str, row_indices: list[int]) -> None:
        alvo = set(row_indices)
        self.tabs[tab] = [r for r in self.tabs.get(tab, []) if r["_rowIndex"] not in alvo]

    def tab_exists(self, tab: str) -> bool:
        return tab in self.tabs

    def rename_tab(self, old: str, new: str) -> bool:
        if old not in self.tabs:
            return False
        self.tabs[new] = self.tabs.pop(old)
        return True

    def find_config(self, chave: str) -> dict[str, Any] | None:
        return next((r for r in self.tabs.get("Config", []) if str(r.get("Chave", "")).strip() == chave), None)

    def set_config(self, chave: str, valor: Any, notas: str = "") -> None:
        existente = self.find_config(chave)
        if existente:
            existente["Valor"] = valor
        else:
            self.append_rows("Config", [[chave, valor, notas]])
