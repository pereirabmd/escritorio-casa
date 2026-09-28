# Pulse — Web (`web/`)

React + Vite + TypeScript. Publicada em `https://bmdpereira.duckdns.org/pulse/`, com a API na mesma origem (`/pulse/api/v1`),
por isso a sessão é um cookie httpOnly (nunca um token em JavaScript).

- **Ecrãs (fase 4 do plano)**: início de sessão; mudança obrigatória de palavra-passe no primeiro acesso (`mudarPassword`);
  **Hoje** (consome `GET /dashboard/today`, com loading de marca, vazio, erro e degradado por cartão); **Mais**;
  **Definições** (conta, mudar palavra-passe, sessões/dispositivos, tema Claro/Escuro/Sistema).
- Design System: `src/styles/tokens.css` (Light/Dark com paridade), Inter (variável, incluída no build), ícones SVG lineares em
  `components/Icon.tsx`, formatos pt-PT em `lib/format.ts`. Sem emojis, sem estilos inline (a CSP do nginx não os permite).
- Ainda **só leitura**: as ações dos cartões (concluir/adiar tarefa, editar RTO, registar peso, pagar conta) chegam na fase 7.

## Desenvolver

```bash
npm ci
npm run dev        # http://localhost:5173/pulse/ — /pulse/api é reencaminhado para o backend em 127.0.0.1:8897
npm run lint && npm test && npm run build
```

Testes (Vitest + Testing Library, com um servidor falso no lugar do `fetch`): formatos, regras de palavra-passe, cliente da API,
fluxos de acesso, mudança de palavra-passe, os estados do Hoje, sessões e tema.

## Publicar

`../scripts/deploy/deploy_pi.sh` corre lint, testes e build, e envia `dist/` para a release (`/opt/pulse/releases/<tag>/web`,
servido pelo nginx a partir de `/opt/pulse/current/web`; ver `../infra/nginx/pulse-web.conf`).
`public/pulse-loading.webp` é cópia do asset oficial em `../assets/branding/`.
