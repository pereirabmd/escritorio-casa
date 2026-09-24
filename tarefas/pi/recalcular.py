"""recalcular.py — motor de reconciliação das notificações.

Substitui `NotificationSender.gs`/`Piscina.gs`, mas com desenho diferente:
em vez de "a cada ciclo, o que já estiver na hora, envia já", mantém sempre
agendada no ntfy (`X-Delay`) a mensagem certa para cada instância pendente
— e cancela+reagenda sempre que algo muda (hora, Ativa, Estado, dependência,
"não incomodar"). Ver PLANO_FINAL / plano de implementação para o desenho
completo.

O ntfy só deixa agendar até 3 dias à frente — por isso só se reconcilia o
que está dentro desse horizonte; o resto fica para um ciclo mais tarde,
quando entrar na janela (o cron corre a cada poucos minutos).

    python recalcular.py               # aplica
    python recalcular.py --plan-only   # só mostra o que faria, sem publicar
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import sys
from datetime import date, datetime, time, timedelta
from typing import Any

import common
from common import FileLock, SheetsClient, TZ, get_logger, normalizar_hora, now_local, parse_sheet_date

log = get_logger("recalcular")

HORIZONTE_NTFY_DIAS = 3
MARGEM_SEGURANCA_HORAS = 6  # nunca tentar agendar mais perto do limite do ntfy que isto

# Ao tocar na notificação (fora dos botões de ação), o ntfy abre este URL em
# vez do próprio ecrã de detalhe do ntfy — assim vai direto para a app.
URL_APP = common.env("TAREFAS_APP_URL", "https://pereirabmd.github.io/escritorio-casa/tarefas/")


# ---------------------------------------------------------------------------
# Ação "Marcar feita" / "Daqui a 1h" na própria notificação — assinada por
# HMAC (chave só no .env), sem precisar de guardar um segredo por instância.
# ---------------------------------------------------------------------------

def assinar_instancia(instancia_id: str) -> str:
    chave = common.env("ACAO_SEGREDO").encode()
    return hmac.new(chave, instancia_id.encode(), hashlib.sha256).hexdigest()[:24]


def acoes_notificacao(instancia_id: str) -> list[dict[str, Any]]:
    base = common.env("TAREFAS_API_URL").rstrip("/")
    s = assinar_instancia(instancia_id)
    return [
        {"action": "http", "label": "Marcar feita", "clear": True, "method": "POST",
         "url": f"{base}/marcarFeita?id={instancia_id}&s={s}"},
        {"action": "http", "label": "Daqui a 1h", "clear": True, "method": "POST",
         "url": f"{base}/snooze?id={instancia_id}&s={s}"},
    ]


# ---------------------------------------------------------------------------
# "Não incomodar": desloca para o fim da janela em vez de "salta este ciclo"
# ---------------------------------------------------------------------------

def _dentro_da_janela(agora_hhmm: str, inicio: str, fim: str) -> bool:
    if inicio <= fim:
        return inicio <= agora_hhmm < fim
    return agora_hhmm >= inicio or agora_hhmm < fim  # atravessa a meia-noite


def ajustar_nao_incomodar(alvo: datetime, config: dict[str, Any]) -> datetime:
    inicio = normalizar_hora(config.get("NaoIncomodarInicio"))
    fim = normalizar_hora(config.get("NaoIncomodarFim"))
    if not inicio or not fim:
        return alvo
    if not _dentro_da_janela(alvo.strftime("%H:%M"), inicio, fim):
        return alvo
    fh, fm = (int(x) for x in fim.split(":"))
    ajustado = alvo.replace(hour=fh, minute=fm, second=0, microsecond=0)
    if ajustado <= alvo:  # a janela atravessa a meia-noite: o fim é amanhã
        ajustado += timedelta(days=1)
    return ajustado


# ---------------------------------------------------------------------------
# Instante certo a notificar, por instância / por linha da Piscina
# ---------------------------------------------------------------------------

def alvo_instancia(inst: dict, tarefa: dict | None, config: dict[str, Any], hoje: date,
                   instancias_hoje_por_tarefa: dict[str, dict]) -> datetime | None:
    """None significa "não deve notificar (mais)" — desativada, já resolvida
    por outra via, dependência por cumprir, ou data ilegível."""
    if tarefa is None:
        return None
    if str(tarefa.get("Ativa", "")).strip().upper() != "TRUE":
        return None  # gap corrigido ao portar: o GAS original não conferia isto
    if str(inst.get("Estado", "")) in ("Feita", "Saltada"):
        return None
    if str(inst.get("NotificacaoEnviada", "")).strip().upper() == "TRUE":
        return None  # já foi entregue neste ciclo; só volta a considerar-se com um /snooze (repõe a FALSE)
    data_inst = parse_sheet_date(inst.get("Data"))
    if data_inst is None:
        return None
    depende_de = str(tarefa.get("DependeDe", "")).strip()
    if depende_de:
        dep = instancias_hoje_por_tarefa.get(depende_de)
        if not dep or dep.get("Estado") != "Feita":
            return None
    hora = normalizar_hora(tarefa.get("HoraNotificacao")) or normalizar_hora(config.get("HoraPadrao")) or "08:00"
    h, m = (int(x) for x in hora.split(":"))
    return ajustar_nao_incomodar(datetime.combine(data_inst, time(h, m), tzinfo=TZ), config)


def alvo_piscina(linha: dict, config: dict[str, Any]) -> datetime | None:
    if str(linha.get("NotificacaoEnviada", "")).strip().upper() == "TRUE":
        return None
    proxima = parse_sheet_date(linha.get("ProximaData"))
    if proxima is None:
        return None
    antecedencia = 30 if str(linha.get("AvisoLongo", "")).strip().upper() == "TRUE" else 0
    limite = proxima - timedelta(days=antecedencia)
    hora = normalizar_hora(config.get("HoraPadrao")) or "08:00"
    h, m = (int(x) for x in hora.split(":"))
    return ajustar_nao_incomodar(datetime.combine(limite, time(h, m), tzinfo=TZ), config)


# ---------------------------------------------------------------------------
# Reconciliação: garante que o ntfy tem (ou não tem) a mensagem certa
# ---------------------------------------------------------------------------

def reconciliar_chave(chave: str, alvo: datetime | None, titulo: str, corpo: str,
                      acoes: list[dict] | None, estado: dict[str, dict], agora: datetime,
                      plan_only: bool, click: str | None = None, topico: str | None = None) -> str:
    """Devolve o que aconteceu: agendado / reagendado / cancelado / entregue /
    presumivelmente_entregue / sem_alteracao / fora_do_horizonte / falhou.

    `topico`: tópico ntfy de destino (None = o tópico legado do .env). O tópico fica no estado: se mudar (a pessoa
    passou a ter utilizador ntfy), a mensagem agendada no tópico antigo é cancelada e reagendada no novo."""
    anterior = estado.get(chave)
    destino = topico or common.env("NTFY_TOPIC", common.TOPICO_LEGADO)
    topico_anterior = (anterior or {}).get("topico") or common.env("NTFY_TOPIC", common.TOPICO_LEGADO)

    def cancelar_anterior() -> None:
        common.ntfy_cancel(anterior["message_id"], topico_anterior)

    if alvo is None:
        if anterior:
            if not plan_only:
                cancelar_anterior()
                del estado[chave]
            return "cancelado"
        return "sem_alteracao"

    alvo_iso = alvo.isoformat()
    igual = bool(anterior) and anterior.get("alvo") == alvo_iso and topico_anterior == destino

    if alvo <= agora:
        if igual:
            # estava agendado exatamente para esta hora, que já passou: o
            # ntfy já deve ter entregue por si só — só falta refletir isso.
            if not plan_only:
                estado.pop(chave, None)
            return "presumivelmente_entregue"
        # nunca chegou a agendar-se para esta hora (RPi em baixo, ou o
        # agendamento anterior já não batia com a hora certa) — publica já,
        # para garantir que chega, em vez de esperar pelo próximo ciclo.
        if anterior and not plan_only:
            cancelar_anterior()
        if plan_only:
            return "entregue"
        resp = common.ntfy_publish(title=titulo, message=corpo, actions=acoes, click=click, topic=topico)
        estado.pop(chave, None)
        return "entregue" if resp else "falhou"

    if alvo - agora > timedelta(days=HORIZONTE_NTFY_DIAS, hours=-MARGEM_SEGURANCA_HORAS):
        return "fora_do_horizonte"

    if igual:
        return "sem_alteracao"  # já está agendado para a hora e o tópico certos, nada a fazer

    reagendado = anterior is not None
    if anterior and not plan_only:
        cancelar_anterior()

    if plan_only:
        return "reagendado" if reagendado else "agendado"
    resp = common.ntfy_publish(title=titulo, message=corpo, delay_at=alvo, actions=acoes, click=click, topic=topico)
    if resp and resp.get("id"):
        estado[chave] = {"message_id": resp["id"], "alvo": alvo_iso, "topico": destino}
        return "reagendado" if reagendado else "agendado"
    estado.pop(chave, None)
    return "falhou"


# ---------------------------------------------------------------------------
# Snooze ("Daqui a 1h"): guardado num ficheiro de estado local (não na
# Sheet), tal como o F01 original (CacheService). Enquanto o snooze estiver
# ativo, sobrepõe-se à hora normalmente calculada (que estaria "atrasada" e
# republicaria de imediato) — ver PLANO.
# ---------------------------------------------------------------------------

def carregar_snoozes(agora: datetime) -> dict[str, datetime]:
    path = common._state_file("snooze.json")
    bruto = common._read_json(path, {})
    vivos: dict[str, datetime] = {}
    mudou = False
    for instancia_id, iso in bruto.items():
        try:
            quando = datetime.fromisoformat(iso)
        except ValueError:
            mudou = True
            continue
        if quando > agora:
            vivos[instancia_id] = quando
        else:
            mudou = True  # expirou, não vale a pena continuar a guardar
    if mudou:
        common._write_json_atomic(path, {k: v.isoformat() for k, v in vivos.items()})
    return vivos


def registar_snooze(instancia_id: str, minutos: int = 60) -> datetime:
    """Chamado pelo servidor.py quando a pessoa toca em "Daqui a 1h" — a
    própria PWA/ntfy-action já repôs NotificacaoEnviada=FALSE na Sheet."""
    path = common._state_file("snooze.json")
    bruto = common._read_json(path, {})
    ate = now_local() + timedelta(minutes=minutos)
    bruto[instancia_id] = ate.isoformat()
    common._write_json_atomic(path, bruto)
    return ate


def recalcular(sheets: SheetsClient | None = None, plan_only: bool = False) -> dict[str, int]:
    lock = FileLock("recalcular")
    if not lock.acquire(timeout_s=15):
        log.warning("recalcular: outra execução em curso, a saltar este ciclo.")
        return {}
    try:
        return _recalcular_sem_lock(sheets or common.get_store(), plan_only)
    finally:
        lock.release()


def _recalcular_sem_lock(sheets: SheetsClient, plan_only: bool) -> dict[str, int]:
    agora = now_local()
    hoje = agora.date()
    if not plan_only:
        import instancias
        instancias.marcar_atrasadas(sheets, hoje)   # a cada 5 min: o que ficou por fazer ontem passa a Atrasada (ver instancias.py)
    config = {str(r.get("Chave", "")).strip(): r.get("Valor") for r in sheets.read_objects("Config")}
    tarefas_map = {t.get("ID"): t for t in sheets.read_objects("Tarefas")}
    instancias = sheets.read_objects("Instancias")
    instancias_hoje_por_tarefa = {
        i.get("TarefaID"): i for i in instancias if parse_sheet_date(i.get("Data")) == hoje
    }

    estado_path = common._state_file("ntfy_agendados.json")
    estado: dict[str, dict] = common._read_json(estado_path, {})
    snoozes = carregar_snoozes(agora)
    contagens: dict[str, int] = {}

    def contar(resultado: str) -> None:
        contagens[resultado] = contagens.get(resultado, 0) + 1

    for inst in instancias:
        data_inst = parse_sheet_date(inst.get("Data"))
        if data_inst is None:
            continue
        # fora de qualquer janela relevante para agendar OU cancelar: nem vale a pena olhar
        if data_inst < hoje - timedelta(days=1) or data_inst > hoje + timedelta(days=HORIZONTE_NTFY_DIAS + 1):
            continue

        tarefa = tarefas_map.get(inst.get("TarefaID"))
        alvo = alvo_instancia(inst, tarefa, config, hoje, instancias_hoje_por_tarefa)
        instancia_id = str(inst.get("ID"))

        snoozed_until = snoozes.get(instancia_id)
        if snoozed_until and alvo is not None and alvo <= agora:
            alvo = snoozed_until  # atrasada, mas com snooze ativo: só volta a incomodar mais tarde

        chave = f"inst:{instancia_id}"
        nome_tarefa = tarefa.get("Nome") if tarefa else str(inst.get("TarefaID"))
        titulo = str(nome_tarefa)
        corpo = f"{inst.get('Pessoa')}: é a vez de \"{nome_tarefa}\" hoje."
        acoes = acoes_notificacao(instancia_id) if alvo is not None else None

        resultado = reconciliar_chave(chave, alvo, titulo, corpo, acoes, estado, agora, plan_only, click=URL_APP,
                                      topico=common.topico_da_pessoa(config, str(inst.get('Pessoa', ''))))
        contar(resultado)
        if resultado in ("entregue", "presumivelmente_entregue") and not plan_only:
            sheets.update_cells("Instancias", inst["_rowIndex"], NotificacaoEnviada="TRUE")

    # A piscina não tem responsável: vai para quem o painel de administração escolher (por omissão todas as pessoas). Uma chave de estado por tópico, para cada mensagem poder ser cancelada no sítio certo.
    topicos_piscina = common.topicos_de(config, common.destinatarios_geral(config, "piscina", common.nomes_pessoas(config)))
    chaves_piscina: set[str] = set()
    for linha in sheets.read_objects("Piscina"):
        alvo = alvo_piscina(linha, config)
        aviso_longo = str(linha.get("AvisoLongo", "")).strip().upper() == "TRUE"
        titulo = "🏊 Piscina — manutenção anual" if aviso_longo else "🏊 Piscina"
        corpo = (f"Está a aproximar-se: {linha.get('Nome')} (previsto para {linha.get('ProximaData')})."
                if aviso_longo else f"Sugestão de hoje: {linha.get('Nome')}.")
        entregue = False
        for topico in topicos_piscina:
            chave = f"piscina:{linha.get('ID')}" + (f":{topico}" if topico else "")
            chaves_piscina.add(chave)
            resultado = reconciliar_chave(chave, alvo, titulo, corpo, None, estado, agora, plan_only, click=URL_APP, topico=topico)
            contar(resultado)
            entregue = entregue or resultado in ("entregue", "presumivelmente_entregue")
        if entregue and not plan_only:
            sheets.update_cells("Piscina", linha["_rowIndex"], NotificacaoEnviada="TRUE")
    for chave in [k for k in estado if k.startswith("piscina:") and k not in chaves_piscina]:
        contar(reconciliar_chave(chave, None, "", "", None, estado, agora, plan_only))   # chave antiga (sem tópico) ou pessoa removida

    if sheets.tab_exists("Horario"):
        import horario
        try:
            for resultado in horario.reconciliar(sheets, config, estado, agora, plan_only, reconciliar_chave, URL_APP):
                contar(resultado)
        except Exception:   # o horário nunca pode impedir as notificações das tarefas (ex.: migração 005 por aplicar)
            log.exception("Horário escolar: falhou a reconciliação dos avisos")
            contar("horario_falhou")

    if not plan_only:
        common._write_json_atomic(estado_path, estado)
        common._write_json_atomic(common._state_file("saude.json"), {
            "ultima_execucao": agora.isoformat(), "contagens": contagens,
        })
    log.info("Recalcular: %s", contagens)
    return contagens


def main() -> int:
    ap = argparse.ArgumentParser(description="Reconciliação das notificações agendadas no ntfy")
    ap.add_argument("--plan-only", action="store_true", help="mostra o que faria, sem publicar/cancelar nada")
    args = ap.parse_args()
    recalcular(plan_only=args.plan_only)
    return 0


if __name__ == "__main__":
    sys.exit(main())
