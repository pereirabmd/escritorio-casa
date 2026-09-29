# Paridade Android ↔ Web

O Pulse tem duas interfaces sobre o mesmo servidor (as regras vivem no servidor, ADR-050). A partir de 29/09/2026 **cada funcionalidade nova é entregue nas duas** e discutida antes de implementar. Estado a 29/09/2026 (Android `0.1.0`).
Legenda: **Feito** · **Na Web** (o Android abre a Web) · **Pendente** · **Só Android** / **Só Web** (decidido).

| Funcionalidade | Web | Android | Notas |
|---|---|---|---|
| Início de sessão (e-mail + palavra-passe) | Feito | Feito | Web: cookie; Android: token `Bearer` cifrado |
| Mudança obrigatória da palavra-passe | Feito | Feito | mesmas regras |
| Mudar palavra-passe (Definições) | Feito | Feito | |
| PIN e biometria | — | Feito | só Android (CLAUDE.md) |
| Tema Sistema/Claro/Escuro | Feito | Feito | |
| Hoje (cartões, estados degradado/erro/loading) | Feito | Feito (leitura) | ações no Hoje (concluir, adiar, registar peso, pagar, RTO, compras): **Na Web** |
| Mais (lista de módulos, respeita ativação) | Feito | Feito | módulos abrem a Web |
| Tarefas, Peso, RTO, Finanças, Bilhetes CP, Compras, Calendário, Email (ecrãs completos) | Feito | **Na Web** | ecrãs nativos por fases |
| Ligar contas Google | Feito | **Na Web** | OAuth de servidor (ADR-049) |
| Sessões e dispositivos (terminar sessões) | Feito | **Pendente** | |
| Administração (módulos) | Feito | **Pendente** | |
| Atualização da app | link para o APK | Feito (interna) | `version.json` (ADR-050) |
| Notificações (FCM) | — | **Pendente** | fase seguinte; servidor pronto (ADR-045) |
| Fila offline / cache | — | **Pendente** | fase 5 (Room, WorkManager) |
| Puxar para atualizar | Pendente | Botão «Atualizar» | |
