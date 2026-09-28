# Integrações

## Google

### Login
Google é o provedor de identidade para criar/iniciar sessão numa conta Pulse.

### Contas adicionais
O utilizador pode adicionar/remover contas Google dentro das Definições.

### Serviços
Por conta:
- Gmail;
- Calendar;
- Tasks quando aplicável.

O backend gere os tokens Google.

## Gmail

- multi-conta;
- emails importantes no dashboard;
- módulo completo em Mais;
- ações oficiais via Gmail API.

## Calendar

- eventos do dia no dashboard;
- agenda completa em Mais;
- ações oficiais via Google Calendar API.

## Tarefas

- tarefas de hoje no dashboard;
- concluir;
- adiar;
- módulo completo em Mais;
- coexistência com app dedicada;
- partilhar infraestrutura/API sempre que possível.

## Bilhetes CP

- próximo bilhete no dashboard;
- módulo completo em Mais;
- usar API existente;
- primeira vaga de migração;
- app dedicada descontinuada apenas quando autorizado.

## Peso

- registo de hoje no dashboard;
- campo pré-preenchido com o peso atual;
- módulo completo em Mais;
- usar API existente;
- primeira vaga de migração.

## RTO

- apenas semana atual no dashboard;
- edição rápida da semana;
- módulo completo em Mais;
- usar API existente;
- primeira vaga de migração.

## Finanças

Dashboard:
- próximas contas a pagar.

Mais:
- funcionalidades completas.

Usar API existente e preservar paridade funcional.

## Compras

Exclusiva do Pulse.

Catálogo pré-carregado:
- mercearia;
- higiene;
- limpeza.

Produtos:
- nome;
- categoria;
- ícone SVG;
- builtin/custom;
- favorito.

Interação:
- toque adiciona/remove;
- long press para detalhes/quantidade/nota;
- criar produto;
- pesquisa;
- favoritos;
- marcar comprado;
- limpar comprados.

## Notificações

FCM é o canal principal.

## Web

Aplicação autenticada:
`https://bmdpereira.duckdns.org/pulse/`

Página pública/referência:
`https://pereirabmd.github.io/escritorio-casa/index.html`
