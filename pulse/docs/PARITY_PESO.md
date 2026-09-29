# Paridade — Peso

Tabela exigida por `MIGRATION_AND_PARITY.md`. App original: `peso/` (PWA). Estado a 29/09/2026. A app dedicada só é descontinuada quando o utilizador declarar a migração concluída.

Legenda: **Feito** · **Pendente** (a fazer antes de declarar a paridade) · **Substituído** (feito de outra forma, decidido) · **Descartado** (deixou de fazer sentido).

| Funcionalidade | App original | Pulse | Estado | Notas |
|---|---|---|---|---|
| Peso atual e diferença para o registo anterior | Resumo | Resumo | Feito | «↓ 0,7 kg desde 20/09/2026» |
| Etiquetas: sequência de dias, novo mínimo, dentro/acima/abaixo do controlo | Resumo | Resumo | Feito | sem ✓/▲/▼ (Pulse não usa símbolos como ícones) |
| Barra de progresso até ao peso alvo | Resumo | Resumo | Feito | elemento `<progress>` acessível |
| Total perdido, ritmo semanal (e por dia), «faltam» / «atingido» | Resumo | Resumo | Feito | lógica portada para o servidor (`services/peso.py`) e testada |
| IMC e classificação | Resumo | Resumo | Feito | mesmas classes da app original |
| Gasto diário (TMB × atividade) | Resumo | Resumo | Feito | fórmula de Mifflin-St Jeor, atividade normalizada como antes |
| Mínimo / máximo | Resumo | Resumo | Feito | |
| Previsão da data do objetivo | Gráfico | Resumo | Feito | ritmo dos últimos 30 dias (ou histórico todo); movida para o Resumo |
| Gráfico com períodos 7d/30d/90d/6m/1a/tudo | Gráfico | Gráfico | Feito | SVG próprio; período contado desde o último registo |
| Média móvel de 7 dias | Gráfico | Gráfico | Feito | |
| Linha do peso alvo no gráfico | Gráfico | Gráfico | Feito | só se estiver dentro da escala; fora dela fica na legenda |
| Análise: tendência (regressão linear), evolução mensal, melhor/pior semana | Gráfico | Resumo | Feito | mínimo de 5 registos; 3 semanas para melhor/pior |
| Registar peso (com nota) | Registos / botão flutuante | Registos e cartão do Hoje | Feito | campo pré-preenchido; `cid` idempotente |
| Listar registos (mais recente primeiro) | Registos | Registos | Feito | mostra os 200 mais recentes |
| Editar registo (data/hora, peso, nota) | Registos | Registos | Feito | |
| Eliminar registo com «Desfazer» | Registos | Registos | Feito | pergunta antes (ação sensível) e o desfazer repõe a data original |
| Eliminar deslizando a linha | Registos | — | Substituído | botões, como nas Tarefas (o deslizar foi removido lá por engano frequente) |
| Configuração: altura, nascimento, sexo, atividade, dia de controlo, peso alvo/mín/máx | Config | Configuração | Feito | validações no cliente e no servidor |
| Tema claro/escuro | Cabeçalho | Definições (global) | Feito | escolha única para todo o Pulse |
| Ligação direta a um separador | — | `/peso?aba=…` | Feito | novo (deep links) |
| Exportar para Excel (XLSX) | Config | — | **Pendente** | decidir formato (XLSX ou CSV) e onde vive (servidor ou cliente) |
| Explicações «ⓘ» de cada indicador | Resumo/Gráfico | — | **Pendente** | textos de ajuda por indicador |
| Celebrações (novo mínimo, objetivo atingido) | Resumo | — | **Pendente** | decidir se se mantêm (animação discreta) |
| Puxar para atualizar | Global | — | **Pendente** | «Atualizar» existe noutros ecrãs; falta aqui |
| Funcionar sem ligação (fila de registos) | Global | — | **Pendente** | Web: só leitura online; a fila offline é da fase 5 (Android) |
| Importar do Google Sheets | Config | — | Descartado | migração já feita (24/09/2026); o Sheets antigo ficou como rede de segurança |
| Histórico de versões (changelog) | Config | — | Descartado | o Pulse terá o seu, em Definições → Atualizações |

**Evoluções durante a migração** (`MIGRATION_AND_PARITY.md`): qualquer mudança à app `peso/` enquanto existir tem de vir para aqui, ou ser registada como pendente nesta tabela.
