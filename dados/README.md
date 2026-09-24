# `dados/` — base de dados SQLite do Raspberry Pi + backup para o GitHub

Base comum às apps que migrarem do Google Sheets (ver `PROJECT-CONTEXT.md`).
Só usa a biblioteca padrão do Python (Debian: 3.11, SQLite ≥ 3.40) — sem venv, sem `pip`.

- `db.py` — liga com WAL + chaves estrangeiras e aplica `migrations/NNN_*.sql` por ordem
  (versão em `PRAGMA user_version`, cada migração numa transação). `python db.py init|status`.
- `migrations_bilhetes/` — esquema da base `bilhetes.db` (separada de propósito; o Pi também a acede em SQL direto, ver `bilhetes_cp/scripts/store.py`).
- `migrations/001_peso.sql` — esquema do piloto (peso). Cada app nova = uma migração nova,
  com tabelas prefixadas (`peso_…`, `rto_…`); nunca editar uma migração já aplicada.
- `backup.py` — export SQL determinístico → só publica se mudou → cifra com `age` → push.
- `api.py` + `auth.py` + `apps/<app>.py` — API HTTP (ver secção API). Cada app nova = um módulo em `apps/` + uma migração.
- `admin_db.py` + `admin_web/` — página web para **consultar e editar** as duas bases (ver secção abaixo). `deploy/dados-admin.service`.
- `deploy/` — `dados-backup.service` + `.timer` (diário, 03:30).

**Convenções**: datas em texto ISO (`YYYY-MM-DD HH:MM:SS`, hora local), nunca serial do Sheets;
logs de debug ficam em ficheiros (`logs/`), nunca na BD; o backup exclui `BACKUP_EXCLUIR`, `logs/` e `state/`.

## Deploy no Pi (uma vez)

```bash
rsync -av --exclude='data' --exclude='state' --exclude='logs' --exclude='.env' \
  ~/escritorio-casa/dados/ casamento-pi:~/dados/
ssh casamento-pi
sudo apt install age git
cd ~/dados && cp .env.example .env && chmod 600 .env
python3 db.py init
```

### Estado atual do backup (24/09/2026)

Instalado: repositório privado `pereirabmd/backup_database`, timer diário, alerta no tópico ntfy `backup`, restauro testado. A chave privada `age` está **só** em `~/.age/dados-backup.key` na máquina do utilizador (não no Pi). Para restaurar: descarregar `dados.sql.age` do repositório e `python3 backup.py restore dados.sql.age --identity ~/.age/dados-backup.key --out novo.db`. Os passos abaixo são o procedimento genérico para repetir a instalação.

### Repositório de backup

1. Criar no GitHub um repositório **privado** novo (nunca o `escritorio-casa`, que é público).
2. No Pi: `ssh-keygen -t ed25519 -f ~/.ssh/dados_backup -N ""` e adicionar `dados_backup.pub` ao
   repo em *Settings → Deploy keys* com **Allow write access**.
3. `git clone git@github.com:<user>/<repo-privado>.git ~/dados-backup` (o repo precisa de pelo
   menos um commit; a chave usada é a do `.env`, por isso o primeiro clone pode precisar de
   `GIT_SSH_COMMAND='ssh -i ~/.ssh/dados_backup -o IdentitiesOnly=yes'`).
4. Gerar o par age **fora do Pi** (`age-keygen -o chave-backup.txt`), pôr só a linha `age1...`
   em `AGE_RECIPIENT`, e guardar `chave-backup.txt` num gestor de passwords. **Sem ela o backup
   é irrecuperável**; o Pi não consegue decifrar o que envia.
5. ntfy: dar à conta de escrita acesso ao tópico: `sudo -u _ntfy ntfy access <NTFY_WRITE_USER> backup rw`
   e à tua conta de leitura: `... <tu> backup read`.
6. Testar e ativar:

```bash
python3 backup.py --force          # deve dizer "backup publicado"
sudo cp deploy/dados-backup.* /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now dados-backup.timer
systemctl list-timers dados-backup.timer
```

## Restaurar (testar uma vez no dia 1, num diretório à parte)

```bash
git clone git@github.com:<user>/<repo-privado>.git /tmp/restauro
python3 backup.py restore /tmp/restauro/dados.sql.age --identity chave-backup.txt --out /tmp/novo.db
python3 -c "import db; c=db.connect('/tmp/novo.db'); print(db.versao(c))"
```

Para repor em produção: parar as apps que usam a BD, mover `data/dados.db*` para o lado e
copiar o `novo.db` para `data/dados.db`.

## Testes

```bash
python3 -m unittest discover -s tests -t .
```

## API (`api.py`)

Serviço em `127.0.0.1:8898`, exposto só pelo nginx em `https://bmdpereira.duckdns.org/dados-api/`.
As PWAs chamam-no com `Authorization: Bearer <access token Google>` — **têm de pedir os scopes
`openid email` além dos que já pedem** (o e-mail é o que identifica quem chama; sem ele o token é recusado).

| Método e caminho | Função |
|---|---|
| `GET /saude` | `{"ok":true}` (público, sem informação) |
| `GET /peso/registos?desde=&ate=` | lista |
| `POST /peso/registos` | cria; `cid` (id do cliente) torna o pedido idempotente (200 se já existia) |
| `PUT /peso/registos/{id}` · `DELETE /peso/registos/{id}` | edita · apaga (devolve o registo, para "desfazer") |
| `POST /peso/importar` | importação em lote (≤100, idempotente por `cid`; itens inválidos vêm em `rejeitados`) |
| `GET/PUT /peso/config` | lê · grava (tudo ou nada; `null` apaga a chave) |
| `GET/PUT /rto/dias` · `PUT /rto/dias/{AAAA-MM-DD}` | dias marcados `{data: "T" ou "C"}`; PUT em lote atómico (≤400), `""` limpa o dia |
| `GET/POST /rto/notas` · `POST /rto/notas/lote` | notas (datas ISO); o lote (≤100) devolve os ids pela ordem |
| `PUT/DELETE /rto/notas/{id}` | PUT é upsert (recria com o mesmo id, para o Desfazer); DELETE devolve a nota apagada |
| `GET /convidados/dados` | convidados + listas de fases e estados numa só chamada |
| `POST /convidados/lista` · `PUT/DELETE /convidados/lista/{id}` | criar · atualizar **só os campos enviados** · eliminar. Só "Confirmado" pode ter mesa (o servidor larga-a se o estado mudar) |
| `POST /convidados/lista/{id}/convite` | regista a data do convite (hora do servidor) |
| `PUT /convidados/opcoes` | substitui as listas `fases`/`estados` (atómico; os estados têm de incluir "Confirmado" e "Convidado") |
| `GET /bilhetes/dados` | passe, viagens (Config), bilhetes, pedidos e registos (base `bilhetes.db`) |
| `PUT /bilhetes/semana` | substitui as viagens de [inicio, inicio+6] **preservando os ids** das que continuam (data+comboio+hora) |
| `PUT /bilhetes/passe` | data do último carregamento do passe (a expiração calcula-se) |
| `PUT /bilhetes/pedidos/{id}` · `POST /bilhetes/pedidos/{id}/forcar` | repetição automática (`retry`, `intervaloMinutos`) · "tentar agora" |
| `GET /tarefas/dados` | tarefas, ocorrências, config (password ntfy mascarada) e piscina |
| `POST /tarefas/tarefas` · `PUT/DELETE /tarefas/tarefas/{id}` | criar (as Pontuais criam a ocorrência) · atualizar · desativar + saltar pendentes |
| `POST /tarefas/instancias` · `PUT /tarefas/instancias[/{id}]` | criar · atualizar (lote atómico; 409 se a tarefa já tem ocorrência nesse dia) |
| `POST /tarefas/pessoas/reatribuir` · `PUT /tarefas/config` | renomear/remover/reatribuir pessoa (atómico) · gravar/apagar chaves |
| `PUT /tarefas/piscina/{id}` · `POST /tarefas/piscina/catalogo` · `GET/POST /tarefas/auditoria` | piscina e registo de quem fez o quê |

Erros: `{"erro":{"codigo":"...","mensagem":"..."}}` com 400/401/403/404/405/409/413/415/429/503.

### Segurança (o que está implementado)

- Só escuta em loopback; TLS, HSTS e `limit_req` no nginx; sem SQL exposto, só endpoints com validação estrita e SQL parametrizado.
- Autenticação em todos os caminhos (menos `/saude` e o preflight): token validado na Google (`aud` = os nossos CLIENT_ID, e-mail verificado, não expirado), com cache por hash; o token vai no corpo do pedido à Google, nunca em URLs nem em logs.
- Autorização por app (`ACL_<APP>`); sem lista = ninguém entra. Utilizador fora da lista → 403.
- CORS só para `CORS_ORIGINS`; sem cookies, logo sem CSRF.
- Corpo ≤ 16 KB, só `application/json`, sem `Transfer-Encoding`, timeout de socket (slowloris), sem `NaN`/`Infinity`, campos desconhecidos recusados.
- Rate limit por IP, por utilizador e de falhas de autenticação; `fail2ban` sobre 401/403/429 (não sobre 503).
- Erros genéricos (nunca stack traces); cabeçalhos `nosniff`, `no-store`, CSP `default-src 'none'`.
- systemd: `NoNewPrivileges`, `ProtectSystem=strict`, escrita só em `data/ state/ logs/`, sem capabilities, `MemoryMax=150M`.

### Deploy da API

```bash
cd ~/dados && nano .env     # preencher ACL_PESO com os e-mails autorizados
sudo mkdir -p /etc/nginx/conf.d && echo 'limit_req_zone $binary_remote_addr zone=dados_api:10m rate=5r/s;' \
  | sudo tee /etc/nginx/conf.d/dados-api.conf
# colar deploy/nginx-dados-api.conf dentro do server{} 443 do vhost e:
sudo nginx -t && sudo systemctl reload nginx
sudo cp deploy/fail2ban-dados-api-filter.conf /etc/fail2ban/filter.d/dados-api-auth.conf
sudo cp deploy/fail2ban-dados-api-jail.conf   /etc/fail2ban/jail.d/dados-api.conf
sudo systemctl restart fail2ban
mkdir -p data state logs
sudo cp deploy/dados-api.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now dados-api
curl -s https://bmdpereira.duckdns.org/dados-api/saude            # {"ok":true}
curl -si https://bmdpereira.duckdns.org/dados-api/peso/registos   # 401
```


## Página de consulta/edição das bases (`admin_db.py`)

`http://192.168.68.103:8890/` (só na rede local; serviço `dados-admin`). Escolhe a base (`dados` ou `bilhetes`), navega as tabelas
(pesquisa, ordenação, paginação, esquema), edita/cria/apaga linhas, corre consultas SELECT, vê as alterações e faz **backup agora** para o
repositório privado `pereirabmd/backup_database`.

- **Segurança (por camadas):** só aceita endereços privados (`ADMIN_DB_REDES`) e a firewall só abre a porta à LAN (`ufw allow from
  192.168.68.0/24 to any port 8890`); nunca passa pelo nginx; login com password (PBKDF2, `ADMIN_DB_PASSWORD_HASH` no `.env`; trocar com
  `python3 admin_db.py --set-password`), cookie HttpOnly/SameSite=Strict, CSRF nas escritas, 5 falhas bloqueiam o IP 10 min, CSP estrita
  (sem JS inline). É HTTP simples: a password viaja em claro na LAN (para TLS, pôr atrás do nginx com certificado interno).
- **Escrita segura:** nomes de tabelas/colunas só do esquema, valores por parâmetros; as restrições CHECK/UNIQUE/FK da base recusam o inválido;
  formatos de data/hora conhecidos (`quando`, `data`, `hora_*`…) são validados (a base não os verifica; só a API das apps o fazia);
  segredos (`*password*`, `*token*`, `*secret*`, `Pessoa*_NtfyPasswordEnc`) saem mascarados e não se editam.
- **Rede de segurança:** antes de escrever guarda um instantâneo da base em `data/undo/` (no máximo 1/min, 20 mais recentes); cada alteração fica em
  `logs/admin_edits.jsonl` (antes/depois) e **«Reverter»** desfaz uma alteração de uma linha (só se a linha ainda estiver como a deixámos).
- **Consola SQL:** só SELECT/WITH, base aberta em modo `ro` + autorizador; 500 linhas e 3 s no máximo.
- Edita-se a base **por baixo das apps**: regras que só as apps garantem (ids sequenciais, estados, dependências entre tabelas) não são verificadas.
