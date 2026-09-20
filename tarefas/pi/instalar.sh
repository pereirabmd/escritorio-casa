#!/usr/bin/env bash
# instalar.sh — instala no Raspberry Pi o cron que chama o Apps Script a cada
# 5 minutos (ver tarefas-job.sh). Idempotente: pode correr-se de novo para
# trocar o segredo ou reparar a instalação.
#
# Uso, no Pi (o segredo é pedido sem eco, para não ficar no histórico):
#   bash <(curl -fsSL https://pereirabmd.github.io/escritorio-casa/tarefas/pi/instalar.sh)
# ou, com os ficheiros já copiados para o Pi:
#   ./instalar.sh
#
# O segredo tem de ser IGUAL ao valor da propriedade JOB_SEGREDO nas
# Propriedades do script do Apps Script.

set -euo pipefail

BASE_URL="https://pereirabmd.github.io/escritorio-casa/tarefas/pi"
DESTINO="$HOME/tarefas-job.sh"
SEGREDO_FICHEIRO="$HOME/.tarefas-job-segredo"
LINHA_CRON='*/5 * * * * flock -n /tmp/tarefas-job.lock "$HOME/tarefas-job.sh"'

for cmd in curl flock crontab; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "Erro: '$cmd' não está instalado." >&2; exit 1; }
done

read -rsp "Segredo (valor de JOB_SEGREDO no Apps Script): " SEGREDO; echo
SEGREDO="$(printf '%s' "$SEGREDO" | tr -d '[:space:]')"
[ -n "$SEGREDO" ] || { echo "Erro: segredo vazio." >&2; exit 1; }
( umask 077; printf '%s\n' "$SEGREDO" > "$SEGREDO_FICHEIRO" )
chmod 600 "$SEGREDO_FICHEIRO"

# Usa o tarefas-job.sh ao lado deste ficheiro; se não existir, descarrega-o.
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || true)"
if [ -n "$AQUI" ] && [ -f "$AQUI/tarefas-job.sh" ]; then
  cp "$AQUI/tarefas-job.sh" "$DESTINO"
else
  curl -fsSL "$BASE_URL/tarefas-job.sh" -o "$DESTINO"
fi
chmod +x "$DESTINO"

# Acrescenta a linha ao crontab só se ainda não lá estiver.
ATUAL="$(crontab -l 2>/dev/null || true)"
if printf '%s\n' "$ATUAL" | grep -qF 'tarefas-job.sh'; then
  echo "Cron já existia — mantido."
else
  { [ -n "$ATUAL" ] && printf '%s\n' "$ATUAL"; printf '%s\n' "$LINHA_CRON"; } | crontab -
  echo "Cron instalado: a cada 5 minutos."
fi

echo "A testar uma chamada agora..."
"$DESTINO" || true
echo "Resposta: $(tail -n 1 "$HOME/tarefas-job.log" 2>/dev/null || echo '<sem log>')"
echo "Esperado: {\"ok\":true,...,\"executado\":true}. Se disser \"não autorizado\", o segredo não coincide com JOB_SEGREDO."
