# Paridade Android ↔ Web

O Pulse tem duas interfaces sobre o mesmo servidor (as regras vivem no servidor, ADR-050). A partir de 29/09/2026 **cada funcionalidade nova é entregue nas duas** e discutida antes de implementar. Estado a 29/09/2026 (Android `0.2.2`, ADR-051/052/053).
Legenda: **Feito** · **Pendente** · **Só Android** / **Só Web** (decidido).

| Funcionalidade | Web | Android | Notas |
|---|---|---|---|
| Início de sessão, mudança obrigatória e mudança da palavra-passe | Feito | Feito | Web: cookie; Android: token `Bearer` cifrado |
| PIN e biometria | — | Feito | só Android (CLAUDE.md) |
| Tema Sistema/Claro/Escuro | Feito | Feito | |
| Hoje (cartões e ações: concluir/adiar, RTO, peso, pagar, comprar) | Feito | Feito | |
| Tarefas (Hoje, Calendário, Tarefas, Horário, Piscina, Config, administração, CSV) | Feito | Feito | Google Calendar de uma tarefa: calendário do telemóvel |
| Peso (Resumo, Gráfico, Registos, Configuração) | Feito | Feito | |
| RTO (Calendário, Ano, Notas, modo administrador, validações) | Feito | Feito | |
| Finanças (Resumo, Lançamentos, Relatórios, Categorias, Lembretes) | Feito | Feito | |
| Bilhetes CP (Semana e editor, Bilhetes, Pedidos, Registo) | Feito | Feito | |
| Compras (listas, catálogo, favoritos, sugestões, gestão) | Feito | Feito | |
| Calendário e Email (Google) | Feito | Feito | |
| Ligar e remover contas Google | Feito | Feito | Custom Tab + `pulse://google` (ADR-051) |
| Sessões e dispositivos | Feito | Feito | |
| Administração (módulos) | Feito | Feito | |
| Atualização da app | link para o APK | Feito (interna) | `version.json` (ADR-050) |
| Notificações (FCM) | — | **Pendente** | servidor pronto (ADR-045); falta a service account do Firebase |
| Fila offline / cache | — | **Pendente** | fase 5 (Room, WorkManager) |
| Puxar para atualizar | Pendente | Botão «Atualizar» | |
