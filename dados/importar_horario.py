"""Importa o horário escolar (CSV com ';') para `tarefas_horario`.

    python importar_horario.py horario.txt            # só valida e mostra o relatório
    python importar_horario.py horario.txt --gravar   # grava (idempotente: repetir não duplica)
    python importar_horario.py horario.txt --gravar --substituir   # apaga antes o horário desses alunos/anos e grava o do ficheiro

Formato: nome_aluno;ano_letivo;dia_semana;hora_inicio;hora_fim;disciplina;sala
Dois registos com o mesmo dia e hora são aceites (turma dividida em dois turnos); só se recusam
linhas ilegíveis e duplicados exatos.
"""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from pathlib import Path

import db

CABECALHO = ["nome_aluno", "ano_letivo", "dia_semana", "hora_inicio", "hora_fim", "disciplina", "sala"]
DIAS = {"2ª feira": 1, "3ª feira": 2, "4ª feira": 3, "5ª feira": 4, "6ª feira": 5, "sábado": 6, "domingo": 7}
_HORA = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")
_ANO = re.compile(r"^\d{4}/\d{4}$")


def _hora(v: str) -> str:
    v = v.strip()
    if not _HORA.match(v):
        raise ValueError(f"hora inválida: {v!r}")
    return v.rjust(5, "0")


def ler(caminho: Path) -> tuple[list[dict], list[str]]:
    """(aulas, problemas). Nada é gravado aqui."""
    aulas, problemas, vistos = [], [], set()
    with open(caminho, encoding="utf-8-sig", newline="") as f:
        leitor = csv.reader(f, delimiter=";")
        cab = [c.strip() for c in next(leitor, [])]
        if cab != CABECALHO:
            raise SystemExit(f"cabeçalho inesperado: {cab}")
        for n, linha in enumerate(leitor, start=2):
            if not any(c.strip() for c in linha):
                continue
            try:
                if len(linha) != 7:
                    raise ValueError(f"{len(linha)} colunas em vez de 7")
                aluno, ano, dia, ini, fim, disc, sala = (c.strip() for c in linha)
                if not aluno or not disc:
                    raise ValueError("aluno e disciplina são obrigatórios")
                if not _ANO.match(ano):
                    raise ValueError(f"ano letivo inválido: {ano!r}")
                if dia.lower() not in DIAS:
                    raise ValueError(f"dia da semana desconhecido: {dia!r}")
                ini, fim = _hora(ini), _hora(fim)
                if fim <= ini:
                    raise ValueError(f"a aula acaba antes de começar ({ini}-{fim})")
                a = {"aluno": aluno, "ano_letivo": ano, "dia_semana": DIAS[dia.lower()], "hora_inicio": ini,
                     "hora_fim": fim, "disciplina": disc, "sala": "" if sala.lower() == "sem sala" else sala}
                chave = tuple(a.values())
                if chave in vistos:
                    raise ValueError("linha repetida")
                vistos.add(chave)
                aulas.append(a)
            except ValueError as e:
                problemas.append(f"linha {n}: {e}")
    return aulas, problemas


def gravar(conn, aulas: list[dict], substituir: bool = False) -> int:
    novas = 0
    conn.execute("BEGIN IMMEDIATE")
    try:
        if substituir:
            for aluno, ano in sorted({(a["aluno"], a["ano_letivo"]) for a in aulas}):
                conn.execute("DELETE FROM tarefas_horario WHERE aluno = ? AND ano_letivo = ?", (aluno, ano))
        for a in aulas:
            cur = conn.execute(
                "INSERT INTO tarefas_horario (aluno, ano_letivo, dia_semana, hora_inicio, hora_fim, disciplina, sala) "
                "VALUES (:aluno, :ano_letivo, :dia_semana, :hora_inicio, :hora_fim, :disciplina, :sala) "
                "ON CONFLICT DO NOTHING", a)
            novas += cur.rowcount
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return novas


def relatorio(aulas: list[dict], problemas: list[str]) -> str:
    out = [f"{len(aulas)} aulas válidas, {len(problemas)} problemas"]
    out += [f"  ! {p}" for p in problemas]
    por_dia = Counter(a["dia_semana"] for a in aulas)
    fim_dia: dict[int, str] = {}
    for a in aulas:
        fim_dia[a["dia_semana"]] = max(fim_dia.get(a["dia_semana"], ""), a["hora_fim"])
    nomes = {v: k for k, v in DIAS.items()}
    for d in sorted(por_dia):
        out.append(f"  {nomes[d]}: {por_dia[d]} aulas, última acaba às {fim_dia[d]}")
    dup = Counter((a["dia_semana"], a["hora_inicio"]) for a in aulas)
    turnos = sorted(k for k, n in dup.items() if n > 1)
    out.append(f"  tempos com duas aulas (turma dividida, não é erro): {len(turnos)}")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    aulas, problemas = ler(Path(argv[1]))
    print(relatorio(aulas, problemas))
    if problemas:
        print("Há linhas com problemas: nada foi gravado.")
        return 1
    if "--gravar" not in argv:
        print("(simulação: use --gravar para gravar)")
        return 0
    db.migrate_all()
    conn = db.connect_named("dados")
    try:
        novas = gravar(conn, aulas, "--substituir" in argv)
        total = conn.execute("SELECT COUNT(*) FROM tarefas_horario").fetchone()[0]
    finally:
        conn.close()
    print(f"gravadas {novas} novas ({len(aulas) - novas} já existiam); a tabela tem {total} aulas")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
