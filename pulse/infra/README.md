# Pulse — instalação no Raspberry Pi

Estado (28/09/2026): backend instalado e a responder em `https://bmdpereira.duckdns.org/pulse/api/v1/health`.

| O quê | Onde |
|---|---|
| Código (releases `beta_YYYYMMDD_X`, `current` → release ativa; guarda as 5 últimas) | `/opt/pulse/releases/`, `/opt/pulse/current` |
| Ambiente virtual partilhado (não faz parte da release) | `/opt/pulse/venv` |
| Base de produção (`pulse.db`, dono `bpereira`, 600, pasta 700) | `/var/lib/pulse/` |
| Logs (`api.log` rotativo; o resto no journald) | `/var/log/pulse/` |
| Segredos e configuração (root, 600) | `/etc/pulse-app/pulse.env` — **não** `/etc/pulse/`, que é do PulseAudio |
| Serviço (loopback `127.0.0.1:8897`, sandbox como o `dados-api`, `MemoryMax=200M`) | `pulse-api.service` (`infra/systemd/`) |
| nginx (API) | `location /pulse/api/` no vhost `bmdpereira.duckdns.org` + zona `pulse_api` em `conf.d/pulse-api.conf` (`infra/nginx/pulse-api.conf`) |
| nginx (Web) | `location /pulse/` e `/pulse/assets/` a servir `/opt/pulse/current/web` (estáticos da release; SPA com `try_files`, CSP restrita) — `infra/nginx/pulse-web.conf` |

## Publicar uma versão nova
`pulse/scripts/deploy/deploy_pi.sh` — verifica e compila a Web (lint, testes, build), cria a release (`server/` + `web/`), instala dependências, troca o `current`, reinicia e verifica `/health`
(até 90 s: o primeiro arranque de uma release no Pi 3 demora cerca de 1 min a compilar bytecode); se falhar, volta à
release anterior. Nunca toca nos dados.

## Instalação de raiz (já feita; para repetir noutro Pi)
```bash
sudo mkdir -p /opt/pulse/releases /var/lib/pulse /var/log/pulse /etc/pulse-app
sudo chown -R bpereira:bpereira /opt/pulse /var/lib/pulse /var/log/pulse && sudo chmod 700 /var/lib/pulse /etc/pulse-app
# /etc/pulse-app/pulse.env (root, 600): PULSE_ENV=production, PULSE_DB_PATH=/var/lib/pulse/pulse.db,
#   PULSE_WEB_BASE_PATH=/pulse/, PULSE_DADOS_URL=http://127.0.0.1:8898, PULSE_LOG_DIR=/var/log/pulse,
#   PULSE_SERVICE_KEY=<a mesma do ~/dados/.env>
sudo install -m 644 infra/systemd/pulse-api.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable pulse-api
# nginx: ver infra/nginx/pulse-api.conf (guardar cópia do vhost; `nginx -t` antes do reload)
scripts/deploy/deploy_pi.sh
```

## Backup (obrigatório, validado a 28/09/2026)
O `pulse.db` entra no backup diário do `dados/` (03:30, cifrado com `age`, repositório privado `pereirabmd/backup_database`,
ficheiro `pulse.sql.age`) através de `BACKUP_BASES_EXTRA=pulse=/var/lib/pulse/pulse.db` no `~/dados/.env`; o
`dados-backup.service` tem `/var/lib/pulse` em `ReadWritePaths`. **Testado ponta a ponta**: backup real → ficheiro
descarregado do GitHub → `backup.py restore … --identity ~/.age/dados-backup.key` → `pulse_settings` e `pulse_activity`
restauradas, `user_version` 1 e `integrity_check` ok. `teste-pulse.db` nunca entra no backup.

### Restaurar o `pulse.db`
```bash
cd ~/dados && python3 backup.py restore pulse.sql.age --identity <chave.txt> --out /var/lib/pulse/pulse-restaurado.db
sudo systemctl stop pulse-api && mv /var/lib/pulse/pulse.db /var/lib/pulse/pulse.db.antigo \
  && mv /var/lib/pulse/pulse-restaurado.db /var/lib/pulse/pulse.db && sudo systemctl start pulse-api
```
(a chave privada `age` não está no Pi: trazer o `pulse.sql.age` para a máquina de desenvolvimento, restaurar lá e enviar o `.db`).

## Contas (ADR-037)
Não há auto-registo: o administrador cria as contas no servidor (a password vai pelo stdin, nunca na linha de comandos):
```bash
ADM='sudo sh -c "set -a; . /etc/pulse-app/pulse.env; set +a; cd /opt/pulse/current/server && exec sudo -u bpereira -E /opt/pulse/venv/bin/python -m pulse.cli'
printf '%s\n' '<password provisória>' | ssh casamento-pi "$ADM criar --email a@b.pt --nome Nome [--admin]\""
printf '%s\n' '<nova provisória>'    | ssh casamento-pi "$ADM repor --email a@b.pt\""       # esqueci-me da password
ssh casamento-pi "$ADM listar\""    # também: desativar / ativar --email …
```
(Executar sempre como `bpereira`, dono do `pulse.db`; como root os ficheiros WAL ficavam com o dono errado.)
O primeiro acesso obriga a mudar a password (`POST /api/v1/auth/password`); até lá só `/auth/me`, `/auth/password` e `/auth/logout`.
