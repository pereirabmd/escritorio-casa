# Paridade — RTO

Tabela exigida por `MIGRATION_AND_PARITY.md`. App original: `RTO/` (PWA v8.0.0). Estado a 29/09/2026. A app dedicada só é descontinuada quando o utilizador declarar a migração concluída.

Legenda: **Feito** · **Pendente** · **Substituído** (feito de outra forma, decidido) · **Descartado**.

| Funcionalidade | App original | Pulse | Estado | Notas |
|---|---|---|---|---|
| Calendário mensal com T (escritório) e C (casa), navegação por mês e «Hoje» | Calendário | Calendário | Feito | semanas de segunda a domingo |
| Feriados portugueses (fixos, Sexta-feira Santa, Corpo de Deus) | Calendário | Calendário | Feito | calculados no servidor (`services/rto.py`, com a Páscoa); vêm 3 anos de cada vez |
| Letras F (férias), A (astreinte) e feriado na célula; A+f quando coincidem | Calendário | Calendário | Feito | férias não aparecem ao fim de semana; astreinte sim |
| Informação de um dia (feriado, notas que o cobrem) | Toque longo | Painel do dia | Substituído | toque no dia abre o painel; o toque longo deixa de ser a única via |
| Marcar o dia (ciclo vazio → T → C → vazio) | Toque no dia | Toque no dia (Calendário e cartão do Hoje) | Feito | sem seletor; o painel do dia é só de leitura (notas e feriado). Fins de semana e dias passados só no modo administrador |
| Fins de semana e dias passados bloqueados no modo normal | Calendário | Calendário | Feito | só dias úteis de hoje em diante; regra validada também no servidor (`dia_bloqueado`), por isso vale para o Android e para a IA |
| Modo Férias (tocar num dia marca/desmarca férias, junta/divide notas) | Modo | Seletor «Férias»: ligado, o toque marca/tira F | Feito | (sujeito ao mesmo bloqueio de fins de semana e passado) | mesma lógica de juntar (dias úteis vizinhos), encolher, dividir e apagar; limpa a marca T/C do dia |
| Modo Administrador (sem restrições: fins de semana, dias e notas passados) | Modo (com confirmação) | Calendário → Administrador (com confirmação) | Feito | aviso visível em todos os separadores enquanto ativo; o ciclo é T→C→vazio por toque e as férias têm o seletor próprio |
| Totais T e C do ano, % da quota anual | Cabeçalho | Totais | Feito | férias nunca contam |
| Quota pro-rata, saldo e saldo condicional (astreinte -1, suspensão) | Cabeçalho | Totais | Feito | arredondamento igual ao JavaScript (meio para cima); cores por escalão (<0, ≤10, >10) |
| «Como se calcula o saldo» | Diálogo | Totais (secção que abre) | Feito | |
| «Hoje: onde trabalho?» e próxima mudança (feriado/início de férias em 60 dias) | Faixa | Calendário | Feito | nunca inventa T/C futuros |
| Comparação com o mês anterior | Calendário | Calendário | Feito | só aparece se houver dados no mês anterior |
| Visão do ano (mapa de calor de 12 meses) | Ano | Ano | Feito | tocar num mês abre-o no calendário |
| Notas: criar, editar, eliminar (com «Desfazer»), por ano ou todas | Notas | Notas | Feito | eliminar pergunta antes (ação sensível); desfazer repõe com o mesmo id |
| Notas em datas passadas bloqueadas sem modo administrador | Notas | Notas | Feito | validado no servidor (`data_passada`) |
| Gerador de validações (14 em 14 dias, alternando Normal/Batica, sem repetir) | Notas | Notas | Feito | em lotes de 100 (atómicos no dados-api); máximo de 400 por pedido |
| Exportar para Excel (XLSX) | Botão | — | **Pendente** | decidir formato e onde vive (servidor ou cliente) |
| Puxar para atualizar | Global | — | **Pendente** | «Tentar de novo» existe em erro |
| Atalhos do ícone (Escritório/Casa de hoje) | Manifest | — | **Pendente** | são atalhos do Android (fase 11: atalhos por clique prolongado) |
| Funcionar sem ligação (fila de marcas) | Global | — | **Pendente** | Web só online; a fila offline é da fase 5 (Android) |
| Tema claro/escuro | Cabeçalho | Definições (global) | Feito | |
| Ligação direta a um separador | — | `/rto?aba=…` | Feito | novo (deep links) |
| Histórico de versões | Rodapé | — | Descartado | o Pulse terá o seu, em Definições → Atualizações |

**Evoluções durante a migração:** qualquer mudança à app `RTO/` enquanto existir tem de vir para aqui, ou ficar registada como pendente nesta tabela.
