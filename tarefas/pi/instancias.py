"""instancias.py — porta de InstanciasGenerator.gs.

Gera linhas em "Instancias" a partir do catálogo em "Tarefas", cobrindo a
janela de DiasAntecedenciaGeracao (aba Config). Idempotente: nunca duplica
uma ocorrência TarefaID+Data já existente.

    python instancias.py               # gera e mostra quantas criou
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from typing import Any

import common
from common import FileLock, SheetsClient, get_logger, parse_sheet_date

log = get_logger("instancias")

DIAS_SEMANA = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sab"]


def ocorre_nesta_data(tarefa: dict, data: date, dia_semana: str, dia_mes: int) -> bool:
    recorrencia = str(tarefa.get("Recorrencia", ""))
    if recorrencia == "Diaria":
        return True
    if recorrencia in ("Semanal", "Dias especificos"):
        dias = [d.strip() for d in str(tarefa.get("DiasSemana", "")).split(",")]
        return dia_semana in dias
    if recorrencia == "Mensal":
        try:
            return dia_mes == int(tarefa.get("DiaMes") or 0)
        except (TypeError, ValueError):
            return False
    if recorrencia in ("Trimestral", "Semestral"):
        # Reaproveita DiasSemana para guardar a data de início (YYYY-MM-DD),
        # o mesmo truque que 'Pontual' já usa — mesmo comportamento do GAS.
        inicio = parse_sheet_date(tarefa.get("DiasSemana"))
        if inicio is None or data < inicio or dia_mes != inicio.day:
            return False
        intervalo_meses = 3 if recorrencia == "Trimestral" else 6
        diff_meses = (data.year - inicio.year) * 12 + (data.month - inicio.month)
        return diff_meses % intervalo_meses == 0
    if recorrencia == "Pontual":
        return False  # ocorrências pontuais são criadas diretamente pela PWA
    return False


def calcular_responsavel(tarefa: dict, contagem_por_tarefa: dict[str, int]) -> str:
    """F12 — rotação automática: se RotacaoPessoas tiver 2+ nomes (separados
    por vírgula), alterna entre eles a cada ocorrência nova."""
    rotacao = [p.strip() for p in str(tarefa.get("RotacaoPessoas", "")).split(",") if p.strip()]
    if len(rotacao) < 2:
        return str(tarefa.get("PessoaPadrao", ""))
    tarefa_id = tarefa.get("ID")
    indice = contagem_por_tarefa.get(tarefa_id, 0)
    contagem_por_tarefa[tarefa_id] = indice + 1
    return rotacao[indice % len(rotacao)]


def gerar_instancias(sheets: SheetsClient | None = None) -> int:
    """F19 — lock: gerarInstancias() pode ser chamada tanto pelo cron periódico
    como manualmente ("Atualizar tarefas do dia agora"). Sem serializar, duas
    execuções em simultâneo podiam decidir criar a mesma ocorrência (mesmo
    TarefaID+Data) e duplicá-la."""
    lock = FileLock("gerar-instancias")
    if not lock.acquire(timeout_s=15):
        log.warning("gerarInstancias: não obteve o lock a tempo, outra execução em curso.")
        return 0
    try:
        return _gerar_sem_lock(sheets or SheetsClient())
    finally:
        lock.release()


def _gerar_sem_lock(sheets: SheetsClient) -> int:
    config = {str(r.get("Chave", "")).strip(): r.get("Valor") for r in sheets.read_objects("Config")}
    horizonte_dias = int(config.get("DiasAntecedenciaGeracao") or 30)

    tarefas = [t for t in sheets.read_objects("Tarefas") if str(t.get("Ativa", "")).strip().upper() == "TRUE"]

    instancias_existentes = sheets.read_objects("Instancias")
    chaves_existentes: set[str] = set()
    contagem_por_tarefa: dict[str, int] = {}
    max_id = 0
    for inst in instancias_existentes:
        d = parse_sheet_date(inst.get("Data"))
        if d is not None:
            chaves_existentes.add(f"{inst.get('TarefaID')}|{d.isoformat()}")
        tid = inst.get("TarefaID")
        contagem_por_tarefa[tid] = contagem_por_tarefa.get(tid, 0) + 1
        digitos = "".join(c for c in str(inst.get("ID", "")) if c.isdigit())
        if digitos:
            max_id = max(max_id, int(digitos))
    proximo_id = max_id + 1

    hoje = common.now_local().date()
    novas_linhas: list[list[Any]] = []

    for offset in range(horizonte_dias + 1):
        data = hoje + timedelta(days=offset)
        dia_semana = DIAS_SEMANA[(data.weekday() + 1) % 7]  # Python: Seg=0; queremos Dom=0
        dia_mes = data.day

        for tarefa in tarefas:
            if not ocorre_nesta_data(tarefa, data, dia_semana, dia_mes):
                continue
            chave = f"{tarefa.get('ID')}|{data.isoformat()}"
            if chave in chaves_existentes:
                continue
            responsavel = calcular_responsavel(tarefa, contagem_por_tarefa)
            novas_linhas.append([
                f"I{proximo_id:04d}", tarefa.get("ID"), data.isoformat(), responsavel,
                "Pendente", "", "FALSE",
            ])
            chaves_existentes.add(chave)
            proximo_id += 1

    if novas_linhas:
        sheets.append_rows("Instancias", novas_linhas)
    return len(novas_linhas)


def main() -> int:
    n = gerar_instancias()
    log.info("Geradas %d instância(s) nova(s).", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
