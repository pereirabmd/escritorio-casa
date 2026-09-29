#!/usr/bin/env bash
# Publica o Pulse (backend + Web) no Raspberry Pi: nova release em /opt/pulse/releases/beta_YYYYMMDD_X (X = contador global,
# nunca reinicia), instala as dependências no venv partilhado, troca o symlink `current`, reinicia e verifica /health.
# Se a verificação falhar, volta à release anterior (rollback de código; os dados nunca se tocam).
#
# Uso: pulse/scripts/deploy/deploy_pi.sh            (a partir de qualquer pasta)
# Requisitos (feitos uma vez, ver infra/README.md): /opt/pulse, /var/lib/pulse, /var/log/pulse, /etc/pulse-app/pulse.env,
# pulse-api.service instalado.
set -euo pipefail
PI="${PULSE_PI:-casamento-pi}"
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

ULTIMO="$(ssh "$PI" 'ls /opt/pulse/releases 2>/dev/null | sed -n "s/^beta_[0-9]*_\([0-9]*\)$/\1/p" | sort -n | tail -1')"
TAG="beta_$(date +%Y%m%d)_$(( ${ULTIMO:-0} + 1 ))"
DESTINO="/opt/pulse/releases/$TAG"
echo "Release $TAG"

# Web: instalar, verificar (lint, testes, tsc) e compilar antes de mexer no Pi
if [ -f "$RAIZ/web/package.json" ]; then
  ( cd "$RAIZ/web" && npm ci --no-audit --no-fund --silent && npm run lint --silent && npm test --silent && npm run build --silent )
fi

ssh "$PI" "mkdir -p '$DESTINO'"
rsync -a --delete --exclude='.venv' --exclude='__pycache__' --exclude='.pytest_cache' --exclude='tests' \
  "$RAIZ/server/" "$PI:$DESTINO/server/"
if [ -d "$RAIZ/web/dist" ]; then
  rsync -a --delete "$RAIZ/web/dist/" "$PI:$DESTINO/web/"
fi
ssh "$PI" "[ -x /opt/pulse/venv/bin/python ] || python3 -m venv /opt/pulse/venv
/opt/pulse/venv/bin/pip install -q -r '$DESTINO/server/requirements.txt'
# opcional (Google/FCM): se não houver roda pré-compilada no Pi, o Pulse arranca na mesma e essas integrações ficam desligadas
/opt/pulse/venv/bin/pip install -q -r '$DESTINO/server/requirements-google.txt' || echo 'AVISO: cryptography nao instalou; Google e FCM ficam desligados'
cd '$DESTINO/server' && /opt/pulse/venv/bin/python -c 'import pulse.main'"

ANTERIOR="$(ssh "$PI" 'readlink -f /opt/pulse/current 2>/dev/null || true')"
ssh "$PI" "ln -sfn '$DESTINO' /opt/pulse/current && sudo systemctl restart pulse-api"

# no Pi 3 o primeiro arranque de uma release (compilar bytecode) pode demorar ~1 min
for _ in $(seq 1 90); do
  if ssh "$PI" "curl -fsS http://127.0.0.1:8897/api/v1/health" >/tmp/pulse-health.json 2>/dev/null; then
    echo "OK: $(cat /tmp/pulse-health.json)"
    ssh "$PI" "ls -1d /opt/pulse/releases/beta_* | sort -t_ -k3 -n | head -n -5 | xargs -r rm -rf"   # guarda as 5 últimas
    exit 0
  fi
  sleep 1
done
echo "FALHOU a verificação de /health." >&2
if [ -n "$ANTERIOR" ] && [ -d "$ANTERIOR" ]; then
  echo "A voltar a $ANTERIOR" >&2
  ssh "$PI" "ln -sfn '$ANTERIOR' /opt/pulse/current && sudo systemctl restart pulse-api"
fi
exit 1
