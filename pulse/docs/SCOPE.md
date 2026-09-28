# Scope

## Objetivo

Pulse é o ponto central para informação pessoal, tarefas, deslocações, presença no escritório, peso, finanças, compras, email e calendário.

Deve existir como:

- APK Android nativo;
- aplicação Web responsiva para desktop/mobile;
- backend central no Raspberry Pi.

## Módulos

1. Gmail multi-conta.
2. Google Calendar.
3. Tarefas.
4. Bilhetes CP.
5. Peso.
6. RTO.
7. Finanças.
8. Lista de Compras.

## Dashboard Hoje

O dashboard mostra apenas a funcionalidade principal e imediata de cada domínio:

- resumo/insight do Pulse;
- eventos do calendário do dia;
- tarefas de hoje com ações rápidas de concluir e adiar;
- emails importantes;
- próximo bilhete CP;
- RTO da semana atual, editável;
- registo do peso de hoje pré-preenchido com o peso atual;
- próximas contas a pagar.

As funcionalidades completas e históricas das apps ficam em **Mais**.

## Área Mais

A área Mais dá acesso às aplicações completas:

- Email;
- Calendário;
- Tarefas;
- Bilhetes CP;
- Peso;
- RTO;
- Finanças;
- Compras.

Também inclui:

- Pesquisa global;
- Favoritos e fixados;
- Centro de atividade;
- Assistente IA;
- Definições/Administração.

A organização deve ser configurável.

## Funcionalidades transversais

- pesquisa global;
- favoritos/fixados;
- drag-and-drop para ordenação;
- centro de atividade;
- retenção de atividade por 30 dias;
- notificações FCM;
- deep links;
- widgets Android;
- atalhos Android por clique prolongado no ícone;
- modo de privacidade rápida;
- modo degradado com alerta;
- onboarding inteligente;
- sincronização offline;
- fila de ações pendentes;
- atualização interna do APK;
- light/dark mode;
- estados de loading profissionais.

## Migração

As funcionalidades das aplicações dedicadas devem ser preservadas integralmente no Pulse, adaptando apenas a apresentação ao Design System Pulse.

Primeira vaga de migração:
- RTO;
- Peso;
- Tarefas;
- Bilhetes CP.

Finanças é migrada numa vaga posterior.

O utilizador decide quando cada migração está concluída.

## Apps dedicadas

Após validação:
- RTO: descontinuar.
- Peso: descontinuar.
- Bilhetes CP: descontinuar.
- Finanças: descontinuar.
- Tarefas: pode continuar em paralelo.
- Compras: existe apenas no Pulse.

## Fora de escopo imediato

Detalhes finais de prompts e comportamento fino do agente IA serão afinados numa fase posterior. A infraestrutura necessária para ações de IA entra desde o início.
