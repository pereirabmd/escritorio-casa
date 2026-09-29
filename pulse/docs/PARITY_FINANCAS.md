# Paridade — Finanças

Tabela exigida por `MIGRATION_AND_PARITY.md`. App original: `financas/` (v1.2.0). **A app dedicada não se descontinua** até o utilizador o declarar (ADR-044); o Pulse partilha a mesma API/BD (`/financas/*` do `dados-api`). Estado a 29/09/2026: **Web feita** (Resumo, Lançamentos, Relatórios, Categorias, Lembretes); pendentes na tabela.

Legenda: **Feito** · **Pendente** · **Substituído** · **Descartado**.

| Funcionalidade | App original | Pulse | Estado | Notas |
|---|---|---|---|---|
| Lançamentos do mês (por pagar/receber e pagos/recebidos), totais do mês, navegar entre meses | Lista | Finanças → Lançamentos | Feito | `GET /finance?mes=` |
| Estados pago/vencido/hoje/pendente derivados das datas | Lista | Lançamentos e Resumo | Feito | nunca guardados |
| Criar (despesa/rendimento, categoria, vencimento, recorrente) | Lista | Lançamentos | Feito | `cid` idempotente |
| Editar e apagar | Lista | Lançamentos | Feito | apagar pede confirmação e oferece «Desfazer» (volta a criar) |
| Marcar como paga/recebida e anular | Lista | Lançamentos e Resumo | Feito | «Desfazer» na mensagem |
| Preparar o mês (copiar recorrentes) ao abrir | Lista | Web ao abrir o mês | Feito | ação idempotente; só até ao mês seguinte |
| Resumo «ativo − passivo» (mês civil ou 30 dias), défice, saldo com as vencidas antes do período | Resumo | Resumo | Feito | calculado no servidor |
| Aviso persistente de despesas vencidas por pagar | Lista/Resumo | Resumo e Lançamentos | Feito | não é toast |
| Despesas por categoria | Resumo | Resumo | Feito | barras (a app dedicada usa Chart.js) |
| Relatório mensal/anual por categoria | Relatórios | Relatórios | Feito | 3, 6 ou 12 meses até ao mês à vista |
| Relatório homólogo (mesmo mês em 3 anos) e histórico de uma conta (24 meses) | Relatórios | — | **Pendente** | o `GET /finance/reports` já serve os dados; falta o ecrã |
| Categorias: criar, renomear, cor, apagar (só sem lançamentos) | Categorias | Categorias | Feito | |
| Lembretes agendados (único/mensal), pausar, apagar | Lembretes | Lembretes | Feito | os avisos continuam a sair do `financas_notificar.py` (ntfy) |
| Avisos ntfy no dia do vencimento | Pi | — | **Mantido no Pi** | quando houver Android+FCM (ADR-045) passa-se para eventos do Pulse |
| Fila offline e cache de 8 meses | Global | — | **Pendente** | é do Android (fase 5) |
| Puxar para atualizar | Global | — | **Pendente** | |
| Importar CSV inicial | Script | — | Descartado | `dados/importar_financas.py` continua a existir |
| Tema claro/escuro | Cabeçalho | Definições (global) | Feito | |
