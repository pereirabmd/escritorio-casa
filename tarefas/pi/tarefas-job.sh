#!/usr/bin/env bash
# tarefas-job.sh — corre no Raspberry Pi, chamado pelo cron a cada 5 minutos.
# Pede ao Apps Script para enviar as notificações que já estão na hora
# (equivale a jobNotificacoes(), a parte leve do jobPeriodico). O trigger
# horário do Apps Script continua ativo como reserva se o Pi estiver em baixo.
#
# Instalação (uma vez, no Pi):
#   1. Segredo partilhado, igual ao da propriedade JOB_SEGREDO do Apps Script
#      (Configurações do projeto > Propriedades do script):
#        openssl rand -hex 16 > ~/.tarefas-job-segredo && chmod 600 ~/.tarefas-job-segredo
#   2. cp tarefas-job.sh ~/tarefas-job.sh && chmod +x ~/tarefas-job.sh
#   3. crontab -e  e acrescentar:
#        */5 * * * * flock -n /tmp/tarefas-job.lock "$HOME/tarefas-job.sh"
#
# Nota: sem `-X POST` de propósito — o Apps Script responde ao POST com um
# redirect (302) e o curl só volta a GET no destino se não forçarmos o método.

set -uo pipefail

URL="${TAREFAS_JOB_URL:-https://script.google.com/macros/s/AKfycbwWfRcQ5QK0dI2YAhqHGfLbKLJoDwSCEwTb345fU352LdWk6ezdLqG1WzQLsJGO3zSj/exec}"
SEGREDO_FICHEIRO="${TAREFAS_JOB_SEGREDO_FICHEIRO:-$HOME/.tarefas-job-segredo}"
LOG="${TAREFAS_JOB_LOG:-$HOME/tarefas-job.log}"
LINHAS_MAX=2000

if [ ! -r "$SEGREDO_FICHEIRO" ]; then
  echo "$(date '+%F %T') ERRO: segredo em falta ($SEGREDO_FICHEIRO)" >> "$LOG"
  exit 1
fi
SEGREDO="$(tr -d '[:space:]' < "$SEGREDO_FICHEIRO")"

RESPOSTA="$(curl -sS -L --max-time 90 --data "{\"tipo\":\"job\",\"segredo\":\"$SEGREDO\"}" "$URL" 2>&1)"
echo "$(date '+%F %T') ${RESPOSTA:-<sem resposta>}" >> "$LOG"

# Mantém o log pequeno (SD card): só as últimas LINHAS_MAX linhas.
if [ "$(wc -l < "$LOG")" -gt $((LINHAS_MAX + 200)) ]; then
  tail -n "$LINHAS_MAX" "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi
