# Resumo — widget do ecrã inicial do Android

Widget nativo (não é PWA) com um resumo de 4 linhas — tarefas, próxima viagem, RTO, finanças —, usando as
mesmas APIs que as PWAs já usam (`https://bmdpereira.duckdns.org/dados-api`). Não faz parte do conjunto de
PWAs estáticas do resto deste repositório: é um projeto Android (Gradle/Java) à parte, compilado localmente
e instalado por fora da Play Store (sideload).

**Fase 1 — só o Bruno.** Não há login por utilizador nem seleção de pessoa: mostra sempre os dados da conta
Google autorizada no telefone onde o widget está instalado.

## O que o widget mostra

| Linha | Fonte | O que significa |
|---|---|---|
| Tarefas | `GET /tarefas/dados` | `N atrasada(s)` (estado `Atrasada`) e/ou `N hoje` (estado `Pendente` com data de hoje); "Tudo em dia" se nenhuma |
| Bilhetes | `GET /bilhetes/dados` | O próximo bilhete já **comprado** com data ≥ hoje; se não houver nenhum, a próxima viagem **configurada** (ativa), marcada "(por comprar)" |
| RTO | `GET /rto/dias?desde=hoje&ate=amanhã` | O que está marcado para hoje e amanhã (`T`=Escritório, `C`=Casa) |
| Finanças | `GET /financas/lancamentos?mes=<atual>&pendentes=1` | Soma das despesas por pagar no mês corrente, com o nº de vencidas se houver |

Tocar numa linha abre a PWA correspondente no browser por omissão. Tocar no ícone de topo atualiza na hora.
A atualização automática corre de 30 em 30 minutos (o próprio Android não permite widgets mais frequentes).

## Autenticação (sem backend novo)

O widget não reutiliza o login das PWAs no browser (são processos separados). Usa a **Authorization API**
dos serviços de identidade da Google para Android (`com.google.android.gms.auth.api.identity`, incluída em
`play-services-auth`), pedindo só o scope `email`. O token resultante é um **access token** igual, na forma,
ao que as PWAs já enviam — a API do Pi não muda nada (`dados/auth.py` já aceita uma lista de client ids).

**Estado (27/09/2026): passos 1 e 2 já feitos.**

1. ~~Registar um cliente OAuth do tipo "Android"~~ — feito: `pt.pereirabmd.resumo`, SHA-1
   `12:EA:91:47:84:C2:97:82:B9:C3:E9:99:E1:9A:10:F9:5F:99:71:9B`, client ID
   `108256538530-qpkatnr3t8pjk7gs76g92kibrd4kv6q4.apps.googleusercontent.com`.
2. ~~Acrescentar esse client ID ao `.env` do Pi~~ — feito (`GOOGLE_CLIENT_IDS` tem agora os dois client ids,
   separados por vírgula; cópia de segurança do `.env` anterior em `~/dados/.env.bak-antes-resumo-widget`
   no Pi); `dados-api` reiniciada e confirmada ativa.

**Falta, feito por ti** (só no telefone):

3. **Descarregar o `.apk`**: `https://bmdpereira.duckdns.org/resumo-apk/resumo.apk` — já publicado no Pi
   (servido por nginx a partir de `/var/www/resumo-apk/`, fora da Play Store) e ligado a partir da página
   inicial do repositório (`https://pereirabmd.github.io/escritorio-casa/`, secção "Widget (Android)"). Ao
   voltar a compilar (`assembleDebug`), o `.apk` publicado não se atualiza sozinho — repetir o `scp`/`cp`
   manualmente (ver "Publicar uma versão nova" abaixo).
   - Ativar "Instalar apps desconhecidas" para a app que usares para abrir o ficheiro (Chrome, Ficheiros, etc.)
   - Abrir o ficheiro descarregado para instalar
4. **Abrir a app "Resumo"** uma vez, tocar em "Autorizar com a Google", escolher a conta e aceitar.
5. **Adicionar o widget**: manter o dedo no ecrã inicial → Widgets → "Resumo" → arrastar para o ecrã.

## Publicar uma versão nova do `.apk`

Depois de recompilar (`assembleDebug`), o ficheiro publicado no Pi é uma cópia estática — não se atualiza
sozinho:

```bash
scp app/build/outputs/apk/debug/app-debug.apk casamento-pi:/tmp/resumo.apk
ssh casamento-pi 'sudo cp /tmp/resumo.apk /var/www/resumo-apk/resumo.apk && \
  sudo chown root:root /var/www/resumo-apk/resumo.apk && sudo chmod 644 /var/www/resumo-apk/resumo.apk && \
  rm /tmp/resumo.apk'
```

A `location = /resumo-apk/resumo.apk` foi acrescentada ao vhost `bmdpereira.duckdns.org` (fora de
`/home/bpereira`, que é `700` e o `www-data` do nginx não consegue atravessar — por isso o ficheiro vive em
`/var/www/resumo-apk/`, não em `~/`). Cópia de segurança do vhost anterior em
`/root/bmdpereira.duckdns.org.bak-antes-resumo-apk-*` no Pi.

## Risco conhecido: não testado num telemóvel real

Este projeto foi escrito e compilado nesta máquina (sem SDK/Android instalados antes), mas **sem um
telemóvel ou emulador Android disponível para testar**. O que está confirmado por inspeção direta dos
`.aar` da Google (não só por memória): a classe `AuthorizationClient`/`AuthorizationRequest`/
`AuthorizationResult` existe mesmo na versão de `play-services-auth` usada, com os métodos usados aqui
(`builder()`, `setRequestedScopes()`, `authorize()`, `hasResolution()`, `getAccessToken()`,
`getAuthorizationResultFromIntent()`). O que **não** foi possível confirmar sem o dispositivo:
- Se o `aud` do token devolvido corresponde mesmo ao cliente OAuth "Android" registado no passo 1 (é o
  comportamento documentado da Google, mas não testado de ponta a ponta aqui).
- O comportamento exato do pedido silencioso em segundo plano (`AuthHelper.tokenSilencioso`) depois da
  primeira autorização — se a Google alguma vez pedir novo consentimento sem aviso, a linha mostra
  "Não foi possível atualizar" até reabrires a app.
- O aspeto real do widget no ecrã (cores, tamanho, texto cortado) — só visto pela composição do layout,
  nunca renderizado num launcher a sério.

Se algo destes falhar, o sítio mais provável é `AuthHelper.java` (o fluxo de autorização) — `adb logcat -s
ResumoAuth ResumoWorker` no telemóvel ligado por USB mostra o que se passou.

## Reproduzir a chave de assinatura

A chave usada para assinar o `.apk` (debug, mas estável — não é a `debug.keystore` genérica que o Android
Studio recria a cada máquina) vive em `~/.local/keystores/resumo-debug.jks` **nesta máquina**, fora do
repositório (nunca comitar chaves). Password e alias: `resumo123` / `resumo`. Para a recriar noutra máquina
(o SHA-1 muda, e o cliente OAuth teria de ser atualizado):

```bash
keytool -genkeypair -v -keystore resumo-debug.jks -storepass resumo123 -keypass resumo123 \
  -alias resumo -keyalg RSA -keysize 2048 -validity 10000 \
  -dname "CN=Bruno Pereira, OU=escritorio-casa, O=pereirabmd, L=Lisboa, S=Lisboa, C=PT"
keytool -list -v -keystore resumo-debug.jks -storepass resumo123 -alias resumo | grep SHA1
```

## Compilar

Ferramentas instaladas nesta máquina (fora do repositório, em `~/.local` e `~/Android/Sdk`, sem `sudo`):
JDK 17 (Temurin), SDK de linha de comandos do Android (`platform-tools`, `platforms;android-34`,
`build-tools;34.0.0`) e Gradle 8.7.

```bash
export JAVA_HOME=~/.local/opt/jdk17
export PATH="$JAVA_HOME/bin:$PATH"
export ANDROID_HOME=~/Android/Sdk
cd resumo_widget
~/.local/opt/gradle-8.7/bin/gradle --no-daemon assembleDebug
# .apk em app/build/outputs/apk/debug/app-debug.apk
```

`gradle.properties` já limita a memória do Gradle (`-Xmx1280m`, sem daemon, sem paralelismo) para esta
máquina ter pouca RAM livre.

## O que fica por fazer

- **Play Store**: fora de âmbito por agora (conta de programador, política de privacidade, revisão) —
  ver a conversa que levou a esta decisão. Uma atualização futura exige reinstalar o `.apk` à mão.
- **Vários utilizadores**: só o Bruno. Alargar à Camila/Bruninho/Davi seria replicar a mesma app com o
  próprio login de cada um (cada instalação no respetivo telefone).
- **Teste num telemóvel real**: ver a secção acima.
- **Ícone da app**: `icon-source.png` (dado pelo utilizador, 27/09/2026) — as camadas do ícone adaptativo e o
  achatado são gerados a partir dele (ver PROJECT-CONTEXT.md, secção deste projeto).
