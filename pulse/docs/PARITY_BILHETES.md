# Paridade — Bilhetes CP

App original: `bilhetes_cp/` (PWA v2.1.0 + scripts no Pi). **A app dedicada não se descontinua** até o utilizador o declarar (ADR-046); o Pulse partilha a mesma API/BD (`/bilhetes/*` do `dados-api`) e o Pi continua a comprar e a avisar por ntfy (cópia para o Pulse em `PLANO_FINAL.md` §9.12). Estado a 29/09/2026: **Web feita** (Semana, Bilhetes, Pedidos, Registo); pendentes na tabela.

Legenda: **Feito** · **Pendente** · **Substituído** · **Descartado**.

| Funcionalidade | App original | Pulse | Estado | Notas |
|---|---|---|---|---|
| Próximo comboio com o bilhete (carruagem, lugar, ref.) | Semana | Semana e Hoje | Feito | mantém-se «Em viagem» até à chegada **estimada** (partida + 180 min) |
| Aviso «falta configurar a semana» | Semana | Semana | Feito | |
| Passe Verde: dias restantes, barra, estado, atualizar a data do carregamento | Semana/Definições | Semana | Feito | `bilhetes.passe` |
| Viagens da semana com o estado (comprado, por comprar, inativa, em viagem) | Semana | Semana | Feito | navegar entre semanas |
| Editor da semana: várias viagens por dia, «Ativo» por dia, validações | Editor | Semana → Configurar semana | Feito | `bilhetes.semana`; preserva os ids; «Desfazer» |
| «Comboios que já usei» | Editor | Editor | Feito | |
| Verificação do horário na CP (comboio, data, percurso e hora) | Editor | Semana → Configurar semana | Feito | pelo servidor (as chaves da CP ficam no Pi, não no telemóvel); consultiva, aviso bem visível e «Usar HH:MM»; preenche a hora em falta (ADR-068) |
| Bilhetes comprados (próximos e anteriores) | Bilhetes | Bilhetes | Feito | |
| Pedidos avulsos: tentar agora, repetição automática de X em X min | Pedidos | Pedidos | Feito | estado incerto pede confirmação na App CP |
| Registo (compras, erros, verificações) com filtros | Registo | Registo | Feito | |
| Página de administração de utilizadores (LAN) | Admin | — | **Mantido no Pi** | só abre na rede de casa |
| Marcar para outras pessoas (compra com as credenciais de quem viaja) | — | Bilhetes (seletor, administrador) | **Feito no código, por publicar** | ADR-069; depois da compra de 01/10 |
| Notificações ntfy | Pi | — | **Mantido no Pi** | desde 30/09/2026 cada aviso chega também ao Pulse por FCM (ADR-058); o ntfy continua em paralelo |
| Fila offline / puxar para atualizar | Global | — | **Pendente** | Android (fase 5) |
