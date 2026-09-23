# Deploy do `tarefas/pi` no Raspberry Pi

Passo a passo para pôr o novo backend a correr a par do Apps Script (nunca
substituindo-o de imediato — ver "Migração faseada" no fim). Convenção de
caminhos igual ao `bilhetes_cp`: o repo fica em
`/home/bpereira/escritorio-casa/tarefas` (dev/git), mas corre a partir de
`/home/bpereira/tarefas/pi` no Pi.

## 1. Copiar o código para o Pi

```bash
rsync -av --exclude='.venv' --exclude='state' --exclude='logs' --exclude='locks' \
  ~/escritorio-casa/tarefas/pi/ casamento-pi:~/tarefas/pi/
```

## 2. Ambiente Python

```bash
ssh casamento-pi
cd ~/tarefas/pi
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install google-api-python-client google-auth requests cryptography
```

## 3. Credenciais Google

Não é preciso criar uma service account nova — a mesma que já serve o
`bilhetes_cp` tem acesso à pasta partilhada onde está a Sheet `tarefas`
(confirmado, sem partilha extra). Copiar o ficheiro:

```bash
mkdir -p ~/tarefas/pi/config
cp ~/bilhetes_cp/config/service-account.json ~/tarefas/pi/config/
```

## 4. `.env`

```bash
cp .env.example .env
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # -> FERNET_KEY
python3 -c "import secrets; print(secrets.token_hex(32))"                                     # -> ACAO_SEGREDO
```

Preencher `FERNET_KEY`, `ACAO_SEGREDO` e `NTFY_WRITE_PASSWORD` no `.env`
(nunca fazer commit deste ficheiro).

## 5. ntfy: conta de escrita do Pi + conta de leitura por pessoa

```bash
# Conta de escrita — só o Pi a usa, nunca fica na Sheet nem na PWA
sudo -u _ntfy ntfy user add tarefas-pi
sudo -u _ntfy ntfy access tarefas-pi tarefas rw

# Uma conta de LEITURA por pessoa (repetir por cada pessoa da casa) — a
# própria pessoa depois guarda este user/password pela app (Configurações
# > Notificações), nunca é preciso tocar na Sheet à mão.
sudo -u _ntfy ntfy user add <utilizador-da-pessoa>
sudo -u _ntfy ntfy access <utilizador-da-pessoa> tarefas read
```

## 6. nginx — novo `location` no MESMO vhost do ntfy

Editar `/etc/nginx/sites-available/bmdpereira.duckdns.org` e colar o
conteúdo de `nginx-tarefas-api.conf` dentro do `server { listen 443 ... }`
já existente (ao lado do `location /` do ntfy, não a substituir):

```bash
sudo nano /etc/nginx/sites-available/bmdpereira.duckdns.org
sudo nginx -t
sudo systemctl reload nginx
```

## 7. fail2ban — jail próprio (reaproveita a infraestrutura do `ntfy-auth`)

```bash
sudo cp fail2ban-tarefas-api-filter.conf /etc/fail2ban/filter.d/tarefas-api-auth.conf
sudo cp fail2ban-tarefas-api-jail.conf   /etc/fail2ban/jail.d/tarefas-api.conf
sudo systemctl restart fail2ban
```

## 8. systemd — serviço HTTP + timers

```bash
sudo cp tarefas-api.service tarefas-recalcular.service tarefas-recalcular.timer \
        tarefas-instancias.service tarefas-instancias.timer \
        tarefas-manutencao.service tarefas-manutencao.timer \
        /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tarefas-api.service
sudo systemctl enable --now tarefas-recalcular.timer
sudo systemctl enable --now tarefas-instancias.timer
sudo systemctl enable --now tarefas-manutencao.timer
```

## 9. Verificar antes de confiar

```bash
cd ~/tarefas/pi
.venv/bin/python -m unittest discover -s tests -t .      # hermético, sem rede
.venv/bin/python recalcular.py --plan-only                # dry-run com a Sheet real
curl -s https://bmdpereira.duckdns.org/tarefas-api/saude
```

Checklist manual ponta-a-ponta (ver PLANO):
1. Guardar as credenciais de leitura de uma pessoa pela app (Configurações
   > Notificações > Guardar) e confirmar na Sheet (`Config`) que
   `Pessoa{N}_NtfyPasswordEnc` ficou CIFRADO, não em claro.
2. "Testar" na app e confirmar receção na app ntfy dessa pessoa.
3. Publicar manualmente uma mensagem no tópico `tarefas` com uma ação
   `http` a apontar para `/tarefas-api/marcarFeita?id=<ID real>&s=<assinatura>`
   e confirmar que a linha em `Instancias` muda para `Feita`.
4. Mudar a `HoraNotificacao` de uma tarefa com instância já agendada e
   confirmar no log do ntfy que a mensagem antiga foi cancelada e há uma
   nova agendada para a hora certa.

## Migração faseada — não desligar o Apps Script já

Deixar o `pi/tarefas-job.sh`/trigger horário do Apps Script a correr em
paralelo por uns dias. Só depois de confirmar que o `recalcular.py` está a
notificar corretamente:
1. Desativar o trigger horário no editor do Apps Script
   (`instalarTriggerLimpeza`/o trigger de `jobNotificacoes` — não apagar o
   código, só o trigger).
2. Renomear a aba `Subscriptions` para `Subscriptions (deprecated)` na
   Sheet (não apagar — histórico para uma limpeza futura).
