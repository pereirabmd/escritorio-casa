"""horario.py — aviso 30 min antes de acabar a última aula de cada dia (horário escolar).

Usa o mesmo mecanismo das tarefas (`recalcular.reconciliar_chave`): a mensagem fica AGENDADA no ntfy
(`X-Delay`) para os próximos dias e é reagendada/cancelada se o horário mudar. Chave de estado
`horario:<aluno>:<data>` em `ntfy_agendados.json`.

Regras:
- a "última aula" do dia é a que acaba mais tarde; se houver duas ao mesmo tempo (turma dividida) contam as duas
  e o aviso menciona-as;
- só há aviso de segunda a sexta dentro do ano letivo (1 set do 1.º ano a 31 jul do 2.º) e se houver aulas nesse dia;
- nunca se avisa "tarde": se a hora do aviso já passou e não estava agendado, esse dia fica sem aviso;
- vai para quem o painel de administração escolher (`Notif_horario`; por omissão a pessoa com o nome do aluno), no tópico
  de cada uma (`tarefas_<utilizador>`);
- Config `HorarioAvisos` = FALSE pausa os avisos (férias, greves); `HorarioAvisoMinutos` muda os 30 min.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any, Callable

import common
from common import TZ, get_logger, normalizar_hora

log = get_logger("horario")

ANTECEDENCIA_MIN = 30
PREFIXO = "horario:"


def dentro_do_ano_letivo(ano_letivo: str, dia: date) -> bool:
    try:
        a, b = (int(x) for x in ano_letivo.split("/"))
    except ValueError:
        return False
    return date(a, 9, 1) <= dia <= date(b, 7, 31)


def ultima_aula(aulas: list[dict], aluno: str, dia: date) -> tuple[str, list[dict]] | None:
    """(hora de fim, aulas que acabam a essa hora) do aluno nesse dia, ou None se não há aulas."""
    do_dia = [a for a in aulas
              if a.get("Aluno") == aluno and int(a.get("DiaSemana") or 0) == dia.isoweekday()
              and dentro_do_ano_letivo(str(a.get("AnoLetivo", "")), dia)]
    if not do_dia:
        return None
    fim = max(normalizar_hora(a["HoraFim"]) for a in do_dia)
    return fim, [a for a in do_dia if normalizar_hora(a["HoraFim"]) == fim]


def alvo_aviso(fim: str, dia: date, minutos: int) -> datetime:
    h, m = (int(x) for x in fim.split(":"))
    return datetime.combine(dia, time(h, m), tzinfo=TZ) - timedelta(minutes=minutos)


def mensagem(aluno: str, fim: str, ultimas: list[dict], minutos: int) -> tuple[str, str]:
    aulas = " + ".join(f"{a['Disciplina']}" + (f" ({a['Sala']})" if a.get("Sala") else "") for a in ultimas)
    return (f"🎒 {aluno}: a última aula acaba às {fim}",
            f"Faltam {minutos} minutos. Última aula: {aulas}.")


def reconciliar(store, config: dict[str, Any], estado: dict[str, dict], agora: datetime, plan_only: bool,
                reconciliar_chave: Callable[..., str], url_app: str, dias: int = 3) -> list[str]:
    aulas = store.read_objects("Horario")
    ativo = str(config.get("HorarioAvisos", "TRUE")).strip().upper() != "FALSE"
    try:
        minutos = int(float(str(config.get("HorarioAvisoMinutos") or ANTECEDENCIA_MIN)))
    except ValueError:
        minutos = ANTECEDENCIA_MIN
    alunos = sorted({a.get("Aluno") for a in aulas if a.get("Aluno")})
    resultados: list[str] = []
    chaves_vivas: set[str] = set()
    for delta in range(0, dias + 1):
        dia = agora.date() + timedelta(days=delta)
        for aluno in alunos:
            chave = f"{PREFIXO}{aluno}:{dia.isoformat()}"
            info = ultima_aula(aulas, aluno, dia) if ativo else None
            alvo, titulo, corpo = None, "", ""
            if info:
                fim, ultimas = info
                alvo = alvo_aviso(fim, dia, minutos)
                titulo, corpo = mensagem(aluno, fim, ultimas, minutos)
                agendado = any(v.get("alvo") == alvo.isoformat() for k, v in estado.items() if k == chave or k.startswith(chave + ":"))
                if alvo <= agora and not agendado:
                    alvo = None      # a hora já passou e nada estava agendado: não se avisa tarde
            topicos = common.topicos_de(config, common.destinatarios_geral(config, "horario", [aluno])) if ativo else []
            for topico in (topicos or [None]):
                chave_t = chave + (f":{topico}" if topico else "")
                if (alvo is not None and topicos) or chave_t in estado:
                    chaves_vivas.add(chave_t)
                    resultados.append(reconciliar_chave(chave_t, alvo if topicos else None, titulo, corpo, None, estado, agora,
                                                        plan_only, click=f"{url_app}/{dia.isoweekday()}", topico=topico))
    # avisos de dias/alunos que deixaram de existir (horário apagado ou alterado): cancelam-se
    for chave in [k for k in estado if k.startswith(PREFIXO) and k not in chaves_vivas]:
        resultados.append(reconciliar_chave(chave, None, "", "", None, estado, agora, plan_only))
    return resultados
