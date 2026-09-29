# Paridade — Tarefas

Tabela exigida por `MIGRATION_AND_PARITY.md`. App original: `tarefas/` (PWA, ~3200 linhas: Hoje, Calendário, Tarefas, Horário, Piscina, Config). **A app dedicada continua para sempre** (ADR-019: outros utilizadores, como a Camila); o Pulse partilha a mesma API/BD (`/tarefas/*` do `dados-api`). Estado a 29/09/2026: **primeira fatia** (Hoje e catálogo de Tarefas); o resto está listado como pendente.

Legenda: **Feito** · **Pendente** · **Substituído** · **Descartado**.

| Funcionalidade | App original | Pulse | Estado | Notas |
|---|---|---|---|---|
| Lista de hoje (por fazer, feitas, saltadas), com progresso «x de y concluídas» | Hoje | Tarefas → Hoje | Feito | ordenada por hora e prioridade (`services/tarefas.py`) |
| Atrasadas: só a ocorrência mais recente de cada tarefa | Hoje | Hoje | Feito | regra portada para o servidor |
| Amanhã (sem feitas nem saltadas) | Hoje | Hoje | Feito | |
| Filtro Todas / Minhas / uma pessoa (guardado) | Hoje | Hoje | Feito | «Minhas» pelo `Pessoa<N>_Email` da Config |
| Concluir e reabrir | Hoje | Hoje | Feito | reabrir também por «Desfazer» |
| Concluir uma atrasada conclui as atrasadas anteriores da mesma tarefa (atómico) | Hoje | Hoje | Feito | o resultado diz quantas; o «Desfazer» reabre todas |
| Saltar | Hoje | Hoje | Feito | com «Desfazer» |
| Reagendar / adiar | Hoje | Hoje | Feito | amanhã ou uma data; nunca para o passado; 409 explicado (ADR-033) |
| Adicionar ao Google Calendar (ligação pré-preenchida) | Hoje | Hoje | Feito | |
| Célula/checkmark animado e celebração ao completar o dia | Hoje | — | **Pendente** | decidir se se mantém (animação discreta) |
| Catálogo: listar, pesquisar (nome, categoria, pessoa) | Tarefas | Tarefas → Tarefas | Feito | resumo da repetição como na app |
| Criar tarefa (Todos os dias, Semanal, Dias específicos, Mensal, Trimestral, Semestral, Pontual) | Tarefas | Tarefas | Feito | validações iguais; a pontual cria logo a ocorrência; `cid` idempotente |
| Editar e duplicar | Tarefas | Tarefas | Feito | |
| Mais opções: prioridade, rotação entre pessoas, «só depois de…» | Tarefas | Tarefas | Feito | |
| Apagar (desativa e salta as pendentes; histórico fica) | Tarefas | Tarefas | Feito | ação sensível: pergunta antes |
| Calendário semanal/mensal com feriados e lista do dia | Calendário | — | **Pendente** | próxima fatia |
| Horário escolar (dia, semana, aula em curso, aviso 30 min antes) | Horário | — | **Pendente** | só leitura de `/tarefas/horario`; o aviso vive no Pi |
| Piscina (catálogo, regimes por estação, registar manutenção) | Piscina | — | **Pendente** | |
| Gerir pessoas (adicionar, renomear, remover com reatribuição) | Config | — | **Pendente** | |
| Categorias da Config | Config | Lê-as | Feito (leitura) | editar categorias: **Pendente** |
| Notificações por pessoa (utilizador/palavra-passe ntfy, tópicos) | Config | — | **Pendente** | o Pulse usa FCM (ADR-032): decidir se se mantém ntfy só na app dedicada |
| Painel de administração (destinatários das notificações gerais, admins) | Config (admin) | — | **Pendente** | |
| «Não incomodar», hora padrão, dias de antecedência | Config | Lê a hora padrão | **Pendente** | |
| Resumo por pessoa e aviso de desequilíbrio | Config | — | **Pendente** | |
| Auditoria («quem fez o quê») | Config | — | **Pendente** | o Pulse já regista as ações no Centro de atividade |
| Recalcular avisos já (`/recalcularAgora`) depois de concluir/adiar | Todas as ações | — | **Pendente** | o `tarefas-recalcular.timer` corre de 5 em 5 min, por isso um aviso já agendado pode disparar até 5 min depois de a tarefa mudar no Pulse; ligar o `tarefas-api` à chave de serviço resolve |
| Ligação profunda a partir de uma notificação (`#hoje/<id>`) | Notificações ntfy | — | Descartado | as notificações do Pulse serão FCM com deep links próprios |
| Tema claro/escuro | Cabeçalho | Definições (global) | Feito | |
| Puxar para atualizar | Global | — | **Pendente** | |
| Funcionar sem ligação | Global | — | **Pendente** | Web só online; fila offline é do Android (fase 5) |
| Ligação direta a um separador | — | `/tarefas?aba=…` | Feito | novo |

**Evoluções durante a migração:** qualquer mudança à app `tarefas/` tem de vir para aqui, ou ficar registada como pendente nesta tabela.
