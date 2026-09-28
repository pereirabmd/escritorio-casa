# Pulse — backend (`server/`)

FastAPI + SQLite (`pulse.db`), Python 3.13 no Raspberry Pi. Base do Marco A, fase 2 (ver `../docs/EXECUTION_PLAN.md`).

- `pulse/config.py` — configuração por ambiente; fora de produção a base tem de ser `teste-*.db` (e em produção não pode).
- `pulse/db.py` + `migrations/NNN_*.sql` — SQLite em WAL, migrações numeradas (nunca editar uma já aplicada).
- `pulse/clients/dados.py` — cliente do `dados-api` com a chave de serviço (ADR-031); 4xx do módulo preservados, falhas = modo degradado.
- `pulse/api/v1/` — `health`/`version` e `auth` (login por e-mail+password, sessões, mudar password; ADR-037); contas criadas com `python -m pulse.cli criar` (password pelo stdin); `dashboard` (`GET /api/v1/dashboard/today`, o agregado do «Hoje», `pulse/services/dashboard.py`).

## Desenvolver e testar

```bash
python3 -m venv --without-pip .venv        # esta máquina não tem o pacote python3-venv/ensurepip
python3 -m pip --python .venv/bin/python install -r requirements-dev.txt
.venv/bin/python -m pytest -q              # usa só bases temporárias `teste-*.db` e um dados-api falso
PULSE_ENV=development PULSE_DB_PATH=/tmp/teste-pulse.db .venv/bin/uvicorn pulse.asgi:app --port 8897
```

Variáveis (ver `../.env.example`): `PULSE_ENV`, `PULSE_DB_PATH`, `PULSE_WEB_BASE_PATH`, `PULSE_DADOS_URL`,
`PULSE_SERVICE_KEY` (a mesma do `.env` do `dados-api`), `PULSE_LOG_DIR`.

## Ainda por fazer nesta fase

Instalar no Pi (`/var/lib/pulse`, serviço systemd, `location` no nginx), **cobrir o `pulse.db` no backup diário
e testá-lo** (obrigatório antes de haver dados reais, `../docs/OPERATIONS_AND_BACKUP.md`), e depois a autenticação (fase 3).
