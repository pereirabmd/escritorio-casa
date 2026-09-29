# Paridade — Tarefas

Tabela exigida por `MIGRATION_AND_PARITY.md`. App original: `tarefas/` (PWA, ~3200 linhas: Hoje, Calendário, Tarefas, Horário, Piscina, Config). **A app dedicada continua para sempre** (ADR-019: outros utilizadores, como a Camila); o Pulse partilha a mesma API/BD (`/tarefas/*` do `dados-api`). Estado a 29/09/2026: **completo** (Hoje, Calendário, Tarefas, Horário, Piscina e Config); o que ficou de fora está listado abaixo como pendente ou descartado, com o motivo.

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
| Célula/checkmark animado e celebração ao completar o dia | Hoje | Hoje | **Substituído** | sem animação: aparece «Tudo feito por hoje» quando não resta nada por fazer |
| Tarefa rápida de hoje (pontual, mínimo de campos) | Hoje (F14) | Hoje | Feito | categoria «Outros» (ou a primeira); `cid` idempotente |
| Catálogo: listar, pesquisar (nome, categoria, pessoa) | Tarefas | Tarefas → Tarefas | Feito | resumo da repetição como na app |
| Criar tarefa (Todos os dias, Semanal, Dias específicos, Mensal, Trimestral, Semestral, Pontual) | Tarefas | Tarefas | Feito | validações iguais; a pontual cria logo a ocorrência; `cid` idempotente |
| Editar e duplicar | Tarefas | Tarefas | Feito | |
| Mais opções: prioridade, rotação entre pessoas, «só depois de…» | Tarefas | Tarefas | Feito | |
| Apagar (desativa e salta as pendentes; histórico fica) | Tarefas | Tarefas | Feito | ação sensível: pergunta antes |
| Calendário mensal e semanal, com feriados e lista do dia (com as mesmas ações do «Hoje») | Calendário | Tarefas → Calendário | Feito | o servidor devolve o intervalo pedido (`/tasks/calendar`); semanas de domingo a sábado |
| Tira dos próximos 10 dias | Calendário | — | **Substituído** | a vista de semana e o «Hoje»/«Amanhã» cobrem o mesmo |
| Horário escolar (dia, semana, aula em curso, hora de saída e do aviso, turma dividida, aluno) | Horário | Tarefas → Horário | Feito | só leitura de `/tarefas/horario`; regras (ano letivo, E.M.R. não conta) no servidor |
| Pausar/ativar os avisos do horário | Horário | Horário | Feito | `tarefas.avisos_horario` |
| Piscina (catálogo, regimes por estação, próxima data e alternância, atraso, registar, ações condicionais) | Piscina | Tarefas → Piscina | Feito | catálogo e cálculos no servidor (`services/piscina.py`); repara o catálogo se faltar alguma; «Desfazer» novo |
| Gerir pessoas (adicionar, renomear, e-mail, remover com reatribuição) | Config | Tarefas → Config | Feito | renomear é atómico; remover exige substituto se houver tarefas por fazer e nunca remove a última |
| Reatribuir tarefas em massa | Config | Config | Feito | ação sensível (confirmação) |
| Escolher «quem sou» e modo convidado | Config | — | **Substituído** | o Pulse sabe quem és pelo e-mail da conta; sem modo convidado |
| Categorias da Config | Config | Lê-as | Feito | a app dedicada também não as edita |
| Notificações por pessoa (utilizador/palavra-passe ntfy, tópicos, testar) | Config | — | **Descartado** | o Pulse terá notificações próprias (FCM, ADR-032); o ntfy fica na app dedicada (ADR-043) |
| Painel de administração (administradores, destinatários das notificações gerais) | Config (admin) | Config | Feito | só para administradores; guardar pede confirmação |
| «Não incomodar» | Config | Config | Feito | início e fim juntos ou ambos vazios |
| Hora padrão e dias de antecedência | Config (só no Sheet) | Lê a hora padrão | **Descartado** | a app dedicada também não os edita |
| Resumo por pessoa (7 dias) e aviso de desequilíbrio | Config | Config | Feito | calculado no servidor |
| Auditoria («quem fez o quê») | Config | Config | Feito | últimas 10 entradas; o Pulse regista ainda as suas ações no Centro de atividade |
| Estado do Pi (última reconciliação dos avisos) e «Atualizar tarefas agora» | Config | Config | Feito | `/saude` e `/gerar` do `tarefas-api` |
| Exportar histórico (CSV) | Config | Config | Feito | `/tasks/history`; o ficheiro gera-se na interface |
| Recalcular avisos já (`/recalcularAgora`) depois de concluir/adiar | Todas as ações | Todas as ações do módulo | Feito | em segundo plano e sem nunca falhar a ação; o `tarefas-api` aceita a chave de serviço do Pulse (ADR-043); o timer de 5 min continua a ser a rede de segurança |
| Ligação profunda a partir de uma notificação (`#hoje/<id>`) | Notificações ntfy | — | Descartado | as notificações do Pulse serão FCM com deep links próprios |
| Tema claro/escuro | Cabeçalho | Definições (global) | Feito | |
| Puxar para atualizar | Global | — | **Pendente** | |
| Funcionar sem ligação | Global | — | **Pendente** | Web só online; fila offline é do Android (fase 5) |
| Ligação direta a um separador | — | `/tarefas?aba=…` | Feito | novo |

**Evoluções durante a migração:** qualquer mudança à app `tarefas/` tem de vir para aqui, ou ficar registada como pendente nesta tabela.
