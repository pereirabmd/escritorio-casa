# Pulse — backend (`server/`)

FastAPI + SQLite (`pulse.db`), Python 3.13 no Raspberry Pi. Base do Marco A, fase 2 (ver `../docs/EXECUTION_PLAN.md`).

- `pulse/config.py` — configuração por ambiente; fora de produção a base tem de ser `teste-*.db` (e em produção não pode).
- `pulse/db.py` + `migrations/NNN_*.sql` — SQLite em WAL, migrações numeradas (nunca editar uma já aplicada).
- `pulse/clients/dados.py` — cliente do `dados-api` com a chave de serviço (ADR-031); 4xx do módulo preservados, falhas = modo degradado.
- `pulse/api/v1/` — `health`/`version` e `auth` (login por e-mail+password, sessões, mudar password; ADR-037); contas criadas com `python -m pulse.cli criar` (password pelo stdin); `tasks` (`GET /api/v1/tasks` e `/tasks/{calendar,schedule,pool,settings,history}`; regras em `services/tarefas.py`, `horario.py` e `piscina.py`); `rto` (`GET /api/v1/rto`, regras em `services/rto.py`); `weight` (`GET /api/v1/weight`, módulo Peso com estatísticas calculadas em `services/peso.py`); `actions` (`POST /api/v1/actions/{nome}`, a camada de ações: concluir/adiar tarefa, registar peso, marcar RTO, pagar conta; `pulse/actions.py`); `dashboard` (`GET /api/v1/dashboard/today`, o agregado do «Hoje», `pulse/services/dashboard.py`); `finance` (`GET /api/v1/finance`, `/finance/reports`, `/finance/reminders`; `services/financas.py`); `tickets` (`GET /api/v1/tickets`, Bilhetes CP; `services/bilhetes.py`); `modules` (`GET /api/v1/modules`, `PUT /api/v1/admin/modules`: módulos ativáveis pelo administrador, `services/modulos.py`); `shopping` (`GET /api/v1/shopping`, Compras; `services/compras.py`, catálogo em `compras_catalogo.py`, ações `compras.*`); `notifications` (`/devices`, `/notifications`, `/internal/events`; `pulse/notifications.py`, canais e agendador, ADR-045).
- Notificações: a caixa de eventos e o agendador de fundo (`PULSE_SCHEDULER_S`) funcionam sempre; o canal FCM só liga com `PULSE_FCM_CREDENTIALS` (e precisa de `cryptography` no venv do Pi; nunca foi testado contra o Firebase real).

## Desenvolver e testar

```bash
python3 -m venv --without-pip .venv        # esta máquina não tem o pacote python3-venv/ensurepip
python3 -m pip --python .venv/bin/python install -r requirements-dev.txt
.venv/bin/python -m pytest -q              # usa só bases temporárias `teste-*.db` e um dados-api falso
PULSE_ENV=development PULSE_DB_PATH=/tmp/teste-pulse.db .venv/bin/uvicorn pulse.asgi:app --port 8897
```

Variáveis (ver `../.env.example`): `PULSE_ENV`, `PULSE_DB_PATH`, `PULSE_WEB_BASE_PATH`, `PULSE_DADOS_URL`, `PULSE_TAREFAS_URL` (o `tarefas-api`, por omissão `http://127.0.0.1:8899`; vazio desliga o recálculo imediato dos avisos),
`PULSE_SERVICE_KEY` (a mesma do `.env` do `dados-api` **e do `tarefas-api`**), `PULSE_LOG_DIR`, `PULSE_FCM_CREDENTIALS`, `PULSE_FCM_PROJECT`, `PULSE_SCHEDULER_S`, `PULSE_AI_KEY` (chave da API da Anthropic; vazio = assistente desligado) e `PULSE_AI_MODEL` (opcional).

## Ainda por fazer nesta fase

Instalar no Pi (`/var/lib/pulse`, serviço systemd, `location` no nginx), **cobrir o `pulse.db` no backup diário
e testá-lo** (obrigatório antes de haver dados reais, `../docs/OPERATIONS_AND_BACKUP.md`), e depois a autenticação (fase 3).
