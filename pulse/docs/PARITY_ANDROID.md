# Paridade Android ↔ Web

O Pulse tem duas interfaces sobre o mesmo servidor (as regras vivem no servidor, ADR-050). A partir de 29/09/2026 **cada funcionalidade nova é entregue nas duas** e discutida antes de implementar. Estado a 29/09/2026 (Android `0.3.5`, ADR-051/052/053/054/074).
Legenda: **Feito** · **Pendente** · **Só Android** / **Só Web** (decidido).

| Funcionalidade | Web | Android | Notas |
|---|---|---|---|
| Início de sessão, mudança obrigatória e mudança da palavra-passe | Feito | Feito | Web: cookie; Android: token `Bearer` cifrado |
| PIN e biometria | — | Feito | só Android (CLAUDE.md) |
| Tema Sistema/Claro/Escuro | Feito | Feito | |
| Hoje (cartões e ações: concluir/adiar, RTO, peso, pagar, comprar) | Feito | Feito | atualização parcial por módulo e alteração imediata em concluir/peso (ADR-055) |
| Definições › O meu Hoje: ordenar (arrastar) e esconder cartões, por pessoa | Feito | Feito | ADR-054/063 |
| Administração › Pessoas (contas, módulos por pessoa, ativar, palavra-passe provisória) | Feito | Feito | só administradores; ADR-063 |
| Tarefas (Hoje, Calendário, Tarefas, Horário, Piscina, Config, administração, CSV) | Feito | Feito | Google Calendar de uma tarefa: calendário do telemóvel |
| Peso (Resumo, Gráfico, Registos, Configuração) | Feito | Feito | |
| RTO (Calendário, Ano, Notas, modo administrador, validações) | Feito | Feito | |
| Finanças (Resumo, Lançamentos, Relatórios, Categorias, Lembretes) | Feito | Feito | |
| Bilhetes CP (Semana e editor, Bilhetes, Pedidos, Registo) | Feito | Feito | |
| Compras (listas, catálogo, favoritos, sugestões, gestão) | Feito | Feito | |
| Calendário e Email (Google) | Feito | Feito | Hoje: próximos 5 eventos com data; emails abrem no Gmail (ADR-074) |
| Ligar e remover contas Google | Feito | Feito | Custom Tab + `pulse://google` (ADR-051); **integração por configurar no Pi** (`GOOGLE_SETUP.md`) |
| Sessões e dispositivos | Feito | Feito | |
| Administração (módulos) | Feito | Feito | |
| Atualização da app | link para o APK | Feito (interna) | `version.json` (ADR-050) |
| Notificações (FCM) | — | **Feito** | FCM ligado; Bilhetes CP, Finanças e Tarefas avisam também pelo Pulse, em paralelo com o ntfy (ADR-057 a 060); botões «Marcar feita» e «Daqui a 1 h» e toque para o sítio certo (ADR-061; os botões precisam de `PULSE_FCM_SO_DADOS=1` depois de instalar a 0.2.7) |
| Fila offline / cache | — | **Pendente** | fase 5 (Room, WorkManager) |
| Puxar para atualizar | Pendente | Botão «Atualizar» | |
