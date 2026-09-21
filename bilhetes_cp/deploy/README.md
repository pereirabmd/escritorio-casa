# deploy/ — configurações aplicadas no Raspberry Pi

Cópia versionada, **sem segredos**, do que está instalado no RPi (`casamento-pi`
no `~/.ssh/config`), para poder ser reproduzido ou reposto. A fonte de verdade
é o que corre no RPi; se alterares lá, atualiza aqui (e vice-versa).

Tudo foi aplicado de forma **aditiva** (ver regra em `PLANO_FINAL.md`): ficheiros
novos ou alterações pontuais, nunca substituição de configuração existente.

| Ficheiro aqui | Destino no RPi | Notas |
|---|---|---|
| `ntfy/server.yml` | `/etc/ntfy/server.yml` (`root:_ntfy`, 640) | o original do pacote ficou em `server.yml.pkg-orig` |
| `nginx/bmdpereira.duckdns.org` | `/etc/nginx/sites-available/` + symlink em `sites-enabled/` | `server{}` novo; não toca em `default` nem `camilaebruno` |
| `fail2ban/filter.d/ntfy-auth.conf` | `/etc/fail2ban/filter.d/` | conta respostas 401/403 do ntfy |
| `fail2ban/jail.d/ntfy.conf` | `/etc/fail2ban/jail.d/` | 5 falhas / 10 min → ban de 1 h; LAN ignorada |
| `systemd/cp-scheduler.service` | `/etc/systemd/system/` | daemon do Scheduler (`Restart=always`, watchdog); lança o processo de compra como subprocesso separado |
| `cron/bilhetes-cp` | `/etc/cron.d/bilhetes-cp` (root, 644) | lembrete de sábado, validade do passe e heartbeat; não toca no crontab do utilizador |
| `logrotate/bilhetes-cp` | `/etc/logrotate.d/bilhetes-cp` (root, 644) | roda `logs/cron.log`; precisa da diretiva `su` porque a pasta é gravável pelo grupo |
| `duckdns/update.sh` | `~/.duckdns/update.sh` | só mudou `domains=` para incluir `bmdpereira`; o token está em `~/.duckdns/token` (fora do git) |

## Como foi instalado (21/09/2026)

O ntfy não estava instalado (nem Docker), por isso usou-se o pacote nativo
Debian em vez de Docker.

```bash
sudo apt-get install -y ntfy                      # cria o utilizador de sistema _ntfy; serviço fica desativado
sudo install -d -o _ntfy -g _ntfy -m 750 /var/lib/ntfy /var/cache/ntfy
# copiar deploy/ntfy/server.yml para /etc/ntfy/server.yml e:
sudo chown root:_ntfy /etc/ntfy/server.yml && sudo chmod 640 /etc/ntfy/server.yml
sudo systemctl enable --now ntfy                  # demora ~3 s a abrir a porta 8080

# utilizador e ACL (a password vem do .env; passar por variável de ambiente, não na linha de comandos)
sudo -E -u _ntfy ntfy user add --role=user "$NTFY_USERNAME"     # lê NTFY_PASSWORD do ambiente
sudo -u _ntfy ntfy access "$NTFY_USERNAME" "$NTFY_TOPIC" read-write

# nginx: 1) só a porta 80 (desafio ACME), 2) certificado, 3) HTTPS completo
sudo certbot certonly --webroot -w /var/www/html -d bmdpereira.duckdns.org \
     --deploy-hook "systemctl reload nginx"
sudo nginx -t && sudo systemctl reload nginx      # sempre testar antes de recarregar

# fail2ban
sudo fail2ban-client reload
```

Nota sobre o certificado: o ficheiro `nginx/bmdpereira.duckdns.org` já referencia
`/etc/letsencrypt/live/bmdpereira.duckdns.org/`, que só existe depois do
`certbot`. Num RPi novo, aplicar primeiro só o bloco da porta 80.

## Onde ver os logs

- ntfy: `sudo journalctl -u ntfy -f` (nível INFO: arranque e estatísticas por minuto)
- pedidos HTTP: `/var/log/nginx/ntfy.access.log` (rodam diariamente, 14 dias)
- erros nginx do vhost: `/var/log/nginx/ntfy.error.log`
- bans: `sudo fail2ban-client status ntfy-auth` e `/var/log/fail2ban.log`
- desbanir: `sudo fail2ban-client set ntfy-auth unbanip <IP>`

## Testar

```bash
set -a; source .env; set +a          # o .env tem de ter os valores com espaços entre aspas
curl -u "$NTFY_USERNAME:$NTFY_PASSWORD" -H "Priority: high" -d "teste" "$NTFY_SERVER_URL/$NTFY_TOPIC"
```

Para testar só pela LAN (sem router nem hairpin NAT, e sem risco de ban, porque a
LAN está no `ignoreip`), acrescentar `--resolve bmdpereira.duckdns.org:443:<IP-privado-do-RPi>`.
Pelo hostname público a partir de casa, o fail2ban vê o IP público da casa e
5 falhas seguidas banem-no durante 1 h.
