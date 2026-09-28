# Plano de execução

## Marco A — Fundação

### Fase 1 — Projeto e documentação
- criar estrutura do repositório;
- configurar GitHub;
- instalar stack;
- aplicar CLAUDE.md;
- preparar contratos;
- preparar Design System;
- versionamento `beta_YYYYMMDD_X`.

### Fase 2 — Backend base
- FastAPI;
- `/api/v1/`;
- configuração;
- logging;
- health checks;
- `pulse.db`;
- migrations;
- `teste-pulse.db`;
- validar backups.

### Fase 3 — Autenticação e segurança
- Sign-in/sign-up Google;
- criação da conta Pulse;
- sessões próprias;
- Android PIN;
- Android biometria;
- Web Google-only;
- gestão segura de tokens Google.

### Fase 4 — Shell Android + Web
- splash/loading;
- temas Light/Dark;
- Hoje;
- Mais;
- navegação;
- estados loading/empty/error/degraded;
- português de Portugal.

### Fase 5 — Sync/offline
- Room;
- cache;
- offline queue;
- idempotência;
- WorkManager;
- retries;
- estado de sincronização.

### Fase 6 — Dashboard Hoje
- Calendário hoje;
- tarefas hoje;
- emails importantes;
- próximo bilhete;
- RTO da semana;
- peso hoje;
- próximas contas a pagar.

## Marco B — Migração funcional

### Fase 7 — Primeira vaga
- RTO;
- Peso;
- Tarefas;
- Bilhetes CP.

Preservar todas as funcionalidades existentes. UI adaptada ao Pulse.

### Fase 8 — Compras
- módulo exclusivo Pulse;
- catálogo pré-carregado;
- SVG;
- criação de produtos;
- toque adicionar/remover;
- favoritos;
- quantidades/notas;
- offline.

### Fase 9 — Finanças
- migração completa;
- privacidade configurável;
- dashboard apenas com próximas contas;
- app dedicada só é descontinuada quando o utilizador decidir.

### Fase 10 — Google completo
- Gmail multi-conta;
- Calendar;
- Tasks;
- adicionar/remover contas;
- refresh tokens;
- scopes por serviço.

## Marco C — Produto avançado

### Fase 11 — Funcionalidades transversais
- pesquisa global;
- favoritos/fixados;
- drag-and-drop;
- centro de atividade;
- deep links;
- widgets;
- FCM;
- atalhos por clique prolongado;
- onboarding;
- privacidade rápida.

### Fase 12 — IA
- tool/action layer;
- consulta;
- execução;
- permissões;
- confirmações;
- audit log;
- contexto consolidado.

### Fase 13 — Paridade e descontinuação
- checklist por app;
- validação;
- testes;
- utilizador declara migração concluída;
- descontinuar quando autorizado.

Tarefas é exceção e pode coexistir indefinidamente.

### Fase 14 — Polish / hardening
- UX review;
- performance;
- acessibilidade;
- estabilidade;
- dark/light;
- offline real;
- falhas parciais;
- segurança;
- backups/restauro.

### Fase 15 — Beta operacional
- APK fora da Play Store;
- Web em `/pulse/`;
- sistema de atualização;
- changelog;
- releases versionadas;
- página pública.
