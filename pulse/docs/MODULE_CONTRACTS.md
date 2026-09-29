# Contratos dos módulos

## Contrato base

Cada módulo deve declarar:

- fonte de dados;
- API oficial;
- leitura;
- criação;
- edição;
- eliminação;
- histórico;
- estatísticas;
- offline;
- notificações;
- pesquisa;
- IA read;
- IA actions;
- requisitos de privacidade;
- estado de migração.

## Email
Dashboard: importantes.
Mais: experiência completa prevista.
Escritas: Gmail API.

## Calendário
Dashboard: hoje.
Mais: calendário completo.
Escritas: Google Calendar API.

## Tarefas
Dashboard: apenas hoje.
Ações rápidas: concluir e adiar.
Mais: funcionalidades completas.
App dedicada permanece possível.

## Bilhetes CP
Dashboard: próximo bilhete.
Mais: funcionalidades completas.
Primeira vaga de migração.

## Peso
Dashboard: registo de hoje pré-preenchido.
Mais: histórico, evolução e funcionalidades completas.
Primeira vaga.

## RTO
Dashboard: semana atual editável.
Mais: funcionalidades completas.
Primeira vaga.

## Finanças
Dashboard: próximas contas a pagar.
Mais: funcionalidades completas.
Sem exposição obrigatória de outras métricas no Hoje.

## Compras
Exclusivo Pulse (**implementado, ADR-047**).
Catálogo pré-carregado (338 produtos), produtos custom, SVG, favoritos, quantidade opcional (nunca direta), estado comprado, toque rápido, listas partilhada («Casa») e pessoais, categorias escondíveis e sugestões (ADR-048).

## UI

Todos os módulos usam o Design System Pulse. A integração não deve importar visual antigo se isso quebrar a consistência.
