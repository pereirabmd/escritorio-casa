# Estratégia de testes

## Princípio

Nenhuma funcionalidade é considerada terminada apenas porque compila.

## Bases

Testes usam:
- `teste-pulse.db`;
- clones `teste-*` das duas BDs existentes.

Nunca escrever em produção.

## Backend

- pytest;
- testes unitários;
- integração;
- contratos;
- migrations;
- autenticação;
- autorização;
- sync;
- idempotência;
- modo degradado.

## Android

- ViewModel;
- repositories;
- Room;
- fila offline;
- Compose UI;
- navegação;
- deep links;
- widgets;
- biometria/PIN;
- atualizações.

## Web

- componentes;
- fluxos;
- autenticação;
- responsividade;
- integração API;
- estados de erro.

## Paridade

Para cada app migrada:
- lista completa de funcionalidades;
- comparação app dedicada vs Pulse;
- testes equivalentes quando possível.

## UI Quality Gate

Antes de concluir uma tarefa visual, rever:
1. consistência Design System;
2. aparência de template/IA;
3. espaçamento;
4. alinhamento;
5. tipografia;
6. ícones;
7. dark/light;
8. loading/empty/error;
9. acessibilidade;
10. animação.

## Release

Antes de uma beta:
- build Android;
- build Web;
- testes backend;
- contract tests;
- migration tests;
- smoke test no Raspberry;
- validar backups quando houver alteração de dados.
