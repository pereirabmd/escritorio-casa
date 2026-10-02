# Paridade Android ↔ Web

O Pulse tem duas interfaces sobre o mesmo servidor (as regras vivem no servidor, ADR-050). A partir de 29/09/2026 **cada funcionalidade nova é entregue nas duas** e discutida antes de implementar. Estado a 30/09/2026 (Android `0.4.2`; ADR-051/052/053/054/074/075/076/077/078).
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
| Bilhetes CP › Na CP (passe e bilhetes futuros, cancelar) | Feito | Feito | ADR-075 |
| Calendário e Email (Google) | Feito | Feito | Hoje: próximos 5 eventos com data; emails abrem no Gmail (ADR-074) |
| Ligar e remover contas Google | Feito | Feito | Custom Tab + `pulse://google` (ADR-051); **integração por configurar no Pi** (`GOOGLE_SETUP.md`) |
| Sessões e dispositivos | Feito | Feito | |
| Administração (módulos) | Feito | Feito | |
| Atualização da app | link para o APK | Feito (interna) | `version.json` (ADR-050) |
| Notificações (FCM) | — | **Feito** | FCM ligado; Bilhetes CP, Finanças e Tarefas avisam também pelo Pulse, em paralelo com o ntfy (ADR-057 a 060); botões «Marcar feita» e «Daqui a 1 h» e toque para o sítio certo (ADR-061; os botões precisam de `PULSE_FCM_SO_DADOS=1` depois de instalar a 0.2.7) |
| Compras › Última chamada (aviso a todos antes de ir às compras; uma por ida) | Feito | Feito | ADR-076 |
| Bilhetes CP › Histórico (todos os pedidos à CP e desfecho das compras; só administrador) | Feito | Feito | ADR-085; Android 0.4.4 (publicado a 01/10/2026) |
| Bilhetes CP › Troca: hora do comboio novo da CP e início agendado | Feito | Feito | ADR-086; Android 0.4.5 (publicado a 01/10/2026) |
| Bilhetes CP › Troca pelo mesmo comboio (bilhete sem desconto → com desconto) e Simular devolução | Feito | Feito | ADR-087/088/089; Android 0.4.8 (publicado a 02/10/2026) |
| Hoje › cartões abrem o módulo; email abre no Pulse; minigráfico do peso | Feito | Feito | ADR-090; Android 0.4.9 (por publicar) |
| Bilhetes CP › Favoritos (seletor, guardar, remover; marcar por voz) | Feito | Feito | ADR-078; Android 0.4.1 |
| Assistente de voz (toque no logotipo; propostas com confirmação; leitura das respostas por voz) | — | **Só Android** | ADR-077/079/080; exceção à paridade, decidida com o utilizador |
| Fila offline / cache | — | **Pendente** | fase 5 (Room, WorkManager) |
| Puxar para atualizar | Pendente | Botão «Atualizar» | |
