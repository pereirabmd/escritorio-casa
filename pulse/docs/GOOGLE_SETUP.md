# Google no Pulse: Calendário e Email (passo a passo)

Estado a 30/09/2026 às 19:29: **ligada no Pi** (cliente OAuth «Pulse servidor» do projeto `bmdpereira-5a8f4`, variáveis `PULSE_GOOGLE_*` no `pulse.env`, cópia `pulse.env.bak-antes-google`; o log diz «Google ligado (Gmail/Calendar)»). Verificado que o Google aceita o pedido de consentimento (302 para o início de sessão, sem `redirect_uri_mismatch` nem `invalid_client`). Falta só cada pessoa ligar a sua conta na app. Sem as variáveis, ligar uma conta responde `google_desligado` (503) e os cartões dizem «não ligado». O login do Pulse continua a ser e-mail + palavra-passe (decisão de 30/09/2026: **não** há login com Google, só ligação de contas para o Calendário e o Gmail).

## 1. Consola do Google Cloud (só o dono da conta Google pode fazer)
1. https://console.cloud.google.com, no projeto `bmdpereira-5a8f4` (o do Firebase) ou num novo.
2. **APIs e serviços › Biblioteca:** ativar **Gmail API** e **Google Calendar API**.
3. **Ecrã de consentimento OAuth:** tipo «Externo»; nome «Pulse»; e-mail de apoio e de contacto o do dono. Âmbitos: `https://www.googleapis.com/auth/gmail.modify`, `…/calendar.events`, `…/calendar.readonly` (mais `openid`, `email`, `profile`).
   - **Estado de publicação:** em «Teste» o Google faz **expirar as autorizações ao fim de ~7 dias** (a conta passa a `reautorizar`) e só deixa entrar os «utilizadores de teste» listados. Para uso pessoal/família convém **«Em produção»**: aparece o aviso «app não verificada» (Avançadas › Continuar) e, por o `gmail.modify` ser um âmbito restrito, o Google limita a app a ~100 utilizadores sem verificação, o que chega.
4. **Credenciais › Criar credenciais › ID de cliente OAuth,** tipo **«Aplicação Web»**. **URI de redirecionamento autorizado, exatamente:**
   `https://bmdpereira.duckdns.org/pulse/api/v1/google/callback`
5. **Transferir JSON** (traz `client_id` e `client_secret`). Não vai para o Git (está no `.gitignore` da pasta `pulse/`).

### Marca («Branding») para publicar em produção
Para passar de «Teste» a «Em produção» (externo) o Google exige nome, e-mail de apoio, **página inicial** e **política de privacidade**. O Pulse serve-as (30/09/2026):
- **Nome da app:** `Pulse` · **E-mail de apoio:** o do dono da conta.
- **Página inicial:** `https://bmdpereira.duckdns.org/pulse/`
- **Política de privacidade:** `https://bmdpereira.duckdns.org/pulse/privacidade.html` (fonte: `pulse/web/public/privacidade.html`; diz que o Gmail nunca envia nem apaga, que nada é copiado para bases de dados e que só o token cifrado fica no servidor pessoal).
- **Domínios autorizados:** `bmdpereira.duckdns.org` (se a consola recusar o domínio por ser um subdomínio de `duckdns.org`, diz-se e vê-se a alternativa).
- **E-mail de contacto do programador:** o do dono.

### Marca («Branding») para publicar em produção
Para passar de «Teste» a «Em produção» (externo) o Google exige nome, e-mail de apoio, **página inicial**, **política de privacidade** e o domínio em «Domínios autorizados». O Pulse serve as páginas (30/09/2026):
- **Nome da app:** `Pulse` · **E-mail de apoio e de contacto:** o do dono da conta.
- **Página inicial:** `https://bmdpereira.duckdns.org/pulse/`
- **Política de privacidade:** `https://bmdpereira.duckdns.org/pulse/privacidade.html` (fonte: `pulse/web/public/privacidade.html`; diz que o Gmail nunca envia nem apaga, que nada é copiado para bases de dados e que só o token cifrado fica no servidor pessoal).
- **Domínios autorizados:** `bmdpereira.duckdns.org` (o domínio completo, sem `https://` nem caminho).

## 2. No Pi (feito por quem publica; o segredo nunca se mostra nem se comita)
Acrescentar ao `/etc/pulse-app/pulse.env` (root, 600) e reiniciar `pulse-api`:

```
PULSE_GOOGLE_CLIENT_ID=<client_id do JSON>
PULSE_GOOGLE_CLIENT_SECRET=<client_secret do JSON>
PULSE_GOOGLE_REDIRECT_URI=https://bmdpereira.duckdns.org/pulse/api/v1/google/callback
PULSE_GOOGLE_KEY=<chave Fernet gerada uma vez: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
```

- A `PULSE_GOOGLE_KEY` cifra os refresh tokens em `google_accounts`. **Perdê-la obriga a voltar a ligar todas as contas**; guardar num gestor de palavras-passe, tal como a chave `age` do backup.
- `cryptography` já está no venv do Pi (instalada com o FCM, ADR-057).
- O ficheiro de credenciais do Google tem de ficar legível só pelo dono (o serviço corre com o utilizador `bpereira`; o `pulse.env` é lido pelo systemd).

## 3. Na app (cada pessoa, com a sua conta)
Definições › **Contas Google** › ligar conta: escolher Gmail, Calendário ou os dois → consentimento do Google no browser → regressa à app (`pulse://google`). Cada pessoa liga as **suas** contas (várias são possíveis); a conta da Camila liga-se na app dela, não na tua. É preciso que a pessoa tenha os módulos **Calendário** e/ou **Email** em Definições › Pessoas (ADR-063).

## 4. O que o Pulse faz e não faz
- Gmail: só `gmail.modify` (ler, marcar como lida, arquivar, estrela). **Nunca envia nem apaga.** Ler uma mensagem não a marca como lida; o corpo vem em texto simples, sem HTML nem anexos.
- Calendário: criar, editar e apagar eventos (apagar é ação sensível, com confirmação).
- Se o Google recusar a autorização (expirou, revogada), a conta passa a `reautorizar` e a app mostra um aviso persistente com o botão para voltar a ligar; as outras contas não são afetadas.

## 5. Verificar
Depois de ligar: Hoje mostra os cartões de Calendário e Email; `journalctl -u pulse-api` não deve ter erros `google_*`. No Hoje os dois cartões têm cache de 60 s (ADR-055).
