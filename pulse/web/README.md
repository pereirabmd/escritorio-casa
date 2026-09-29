# Pulse — Web (`web/`)

React + Vite + TypeScript. Publicada em `https://bmdpereira.duckdns.org/pulse/`, com a API na mesma origem (`/pulse/api/v1`),
por isso a sessão é um cookie httpOnly (nunca um token em JavaScript).

- **Ecrãs (fase 4 do plano)**: início de sessão; mudança obrigatória de palavra-passe no primeiro acesso (`mudarPassword`);
  **Hoje** (consome `GET /dashboard/today`, com loading de marca, vazio, erro e degradado por cartão); **Mais**;
  **Definições** (conta, mudar palavra-passe, sessões/dispositivos, tema Claro/Escuro/Sistema).
- Design System: `src/styles/tokens.css` (Light/Dark com paridade), Inter (variável, incluída no build), ícones SVG lineares em
  `components/Icon.tsx`, formatos pt-PT em `lib/format.ts`. Sem emojis, sem estilos inline (a CSP do nginx não os permite).
- **Peso completo** (`/peso`, a partir de Mais ou do cartão do Hoje; `?aba=resumo|grafico|registos|config`): resumo com estatísticas, gráfico SVG com períodos e média móvel, registos (registar, editar, eliminar com desfazer) e configuração. Paridade em `../docs/PARITY_PESO.md`.
- **RTO completo** (`/rto`; `?aba=calendario|ano|notas`): calendário mensal com T/C/férias/astreinte/feriados, painel do dia, hoje e próxima mudança, totais e saldo com «como se calcula», comparação com o mês anterior, visão do ano e notas (criar, editar, eliminar com desfazer, gerador de validações). Paridade em `../docs/PARITY_RTO.md`.
- **Tarefas** (`/tarefas`; `?aba=hoje|calendario|tarefas|horario|piscina|config`): Hoje (filtro por pessoa, atrasadas, amanhã, concluir/reabrir/saltar/adiar, tarefa rápida, Google Calendar), Calendário (mês/semana com feriados), catálogo (criar, editar, duplicar, apagar), Horário escolar, Piscina, e Config (pessoas, reatribuir, não incomodar, resumo, estado do Pi, exportar CSV, administração). Paridade em `../docs/PARITY_TAREFAS.md`.
- **Finanças** (`/financas`; `?aba=resumo|lancamentos|relatorios|categorias|lembretes`): resumo «ativo − passivo» (mês ou 30 dias) com aviso persistente de vencidas, lançamentos do mês (criar, editar, pagar/anular, apagar com desfazer; o mês é preparado ao abrir), relatórios por mês e categoria, categorias e lembretes. Paridade em `../docs/PARITY_FINANCAS.md`.
- **Bilhetes CP** (`/bilhetes`; `?aba=semana|bilhetes|pedidos|registo`): próximo comboio (mantém «Em viagem» até à chegada estimada), Passe Verde, viagens da semana e editor (vários comboios por dia, «Ativo» por dia, desfazer), bilhetes, pedidos avulsos (tentar agora, repetição) e registo. Paridade em `../docs/PARITY_BILHETES.md`.
- **Compras** (`/compras`; `?aba=lista|catalogo`): listas «Casa» (partilhada), pessoais e partilhadas extra; lista por corredor com detalhes (quantidade opcional, nota, passar para outra lista, remover), comprados com «Limpar» e desfazer; catálogo de 338 produtos com pesquisa sem acentos, favoritos, «Gerir» e criar produto próprio; esconder categorias inteiras («Gerir») e sugestões calmas (a acabar / costumas comprar, com «Não sugerir»); atualiza a cada 30 s. ADR-047/048, `../docs/COMPRAS_CATALOGO.md`.
- **Módulos** (ADR-046): Definições → Administração (só administradores) liga/desliga módulos para todos; os desativados saem de Mais e do Hoje (`lib/modulos.tsx`).
- **Instalável no Android**: `public/manifest.webmanifest` + `<link rel="manifest">`.
- **Ações rápidas nos cartões (fase 7, ADR-039)**, todas por `POST /actions/{nome}`: concluir e adiar tarefa (amanhã ou uma data),
  registar peso (campo pré-preenchido com o último valor), marcar o dia de RTO (um toque no dia: vazio → T → C → vazio, sem seletor) e pagar uma conta, com
  «Desfazer» onde faz sentido. Erros em pt-PT no próprio ecrã; abrir o Hoje nunca escreve nada.

## Desenvolver

```bash
npm ci
npm run dev        # http://localhost:5173/pulse/ — /pulse/api é reencaminhado para o backend em 127.0.0.1:8897
npm run lint && npm test && npm run build
```

Testes (218, Vitest + Testing Library, com um servidor falso no lugar do `fetch`): formatos, regras de palavra-passe, cliente da API,
fluxos de acesso, mudança de palavra-passe, os estados do Hoje, sessões e tema.

## Publicar

`../scripts/deploy/deploy_pi.sh` corre lint, testes e build, e envia `dist/` para a release (`/opt/pulse/releases/<tag>/web`,
servido pelo nginx a partir de `/opt/pulse/current/web`; ver `../infra/nginx/pulse-web.conf`).
`public/pulse-loading.webp` é cópia do asset oficial em `../assets/branding/`.
