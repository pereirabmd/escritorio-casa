# CLAUDE.md — Regras do projeto Pulse

## Regra principal

O Pulse deve parecer e comportar-se como uma aplicação comercial profissional, completa, moderna e desenhada intencionalmente. Não deve parecer um protótipo, um dashboard genérico nem uma interface gerada por IA.

## Stack fixa

### Android
- Kotlin.
- Jetpack Compose.
- Material 3.
- Room/SQLite para cache e fila offline.
- WorkManager para sincronização diferida.
- PIN e biometria apenas no Android.

### Web
- React.
- Vite.
- TypeScript.
- Login Google.
- Sem PIN/biometria na Web.

### Backend
- Python.
- FastAPI.
- SQLite.
- API versionada em `/api/v1/`.

Não introduzir React Native, Flutter ou wrappers Web para substituir o APK Android nativo sem decisão explícita.

## Linguagem

Toda a interface destinada ao utilizador deve ser escrita em português de Portugal (`pt-PT`).

Preferir:
- aplicação;
- ecrã;
- ficheiro;
- iniciar sessão;
- palavra-passe;
- definições;
- telemóvel.

Código, classes, funções e nomes técnicos podem permanecer em inglês.

## UI

- Sem emojis como ícones de produto.
- Ícones minimalistas, estilizados, coerentes e preferencialmente SVG.
- Evitar gradientes excessivos, neon, glassmorphism exagerado e cartões dentro de cartões.
- Evitar raios gigantes e ornamentação sem função.
- Reutilizar componentes Pulse antes de criar novos.
- Animações discretas, rápidas e funcionais.
- Light e Dark mode devem ter paridade.
- Implementar sempre estados loading, empty, error e degraded.
- Usar o asset oficial `assets/branding/pulse-loading.webp` quando apropriado.

## Dados

- Nunca modificar diretamente uma base de dados de uma aplicação de origem para executar uma operação funcional.
- Escritas, edições e eliminações passam pelas APIs/serviços oficiais.
- O Pulse pode ler/consolidar dados quando previsto pela arquitetura.
- `pulse.db` guarda apenas dados próprios do Pulse.
- `teste-pulse.db` e clones `teste-*` são usados para desenvolvimento/testes.
- Nunca testar escrita em bases de produção.

## Apps dedicadas

RTO, Peso, Bilhetes CP e Finanças serão descontinuadas apenas quando o utilizador declarar explicitamente que a migração terminou após testes.

Tarefas é uma exceção: a app dedicada pode continuar permanentemente para outros utilizadores. O Pulse e a app Tarefas devem partilhar infraestrutura/API sempre que possível.

Compras existe exclusivamente dentro do Pulse.

## IA

A IA deve poder executar ações.

Toda a ação de IA:
1. usa a camada oficial de Actions/Tools;
2. passa pelas APIs/serviços oficiais;
3. respeita permissões;
4. usa idempotência quando aplicável;
5. é auditada;
6. nunca escreve diretamente na base de dados.

Níveis:
- `read`;
- `safe_action`;
- `sensitive_action`.

Ações sensíveis/destrutivas exigem confirmação.

## Testes

Após alterações significativas:
- build;
- lint;
- unit tests;
- integration tests relevantes;
- contract tests quando uma API for alterada.

Nunca remover ou enfraquecer testes apenas para fazer uma build passar.

## Estrutura

Consultar `docs/FOLDER_STRUCTURE.md` antes de criar novos diretórios. Não criar estruturas paralelas sem necessidade arquitetural clara.

## Releases

Formato:
`beta_YYYYMMDD_X`

`X` é um contador global crescente e nunca reinicia diariamente.

Exemplo:
- `beta_20260928_17`
- `beta_20260929_18`

## Backups

Ao criar ou mover `pulse.db`, validar explicitamente que a base está incluída no sistema de backups existente no Raspberry Pi. Não assumir que a localização é automaticamente protegida.
