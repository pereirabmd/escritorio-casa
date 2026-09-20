/**
 * Manutencao.gs
 * Limpeza periódica: remove instâncias já concluídas (Feita ou Saltada)
 * com mais de X dias, para a tab Instancias não crescer para sempre, e
 * subscrições FCM inativas há mais de 30 dias.
 * Instala-se uma vez com instalarTriggerLimpeza(); corre uma vez por mês.
 */

const DIAS_RETER_HISTORICO = 90;

function limparHistoricoAntigo() {
  const sheet = getSheet('Instancias');
  const data = sheet.getDataRange().getValues();
  const limite = new Date();
  limite.setDate(limite.getDate() - DIAS_RETER_HISTORICO);

  const linhasParaApagar = [];
  for (let i = 1; i < data.length; i++) {
    const dataStr = data[i][2]; // Data
    const estado = data[i][4]; // Estado
    if ((estado === 'Feita' || estado === 'Saltada') && new Date(dataStr) < limite) {
      linhasParaApagar.push(i + 1); // linha real na folha (1-indexed)
    }
  }

  // Apagar de baixo para cima para não desalinhar os índices entretanto
  linhasParaApagar.sort((a, b) => b - a).forEach(rowIndex => {
    sheet.deleteRow(rowIndex);
  });

  limparSubscricoesInativas();

  return linhasParaApagar.length;
}

// Tokens FCM antigos que já falharam (Ativa=FALSE) não voltam a servir —
// a app gera um token novo. Apaga os que estão inativos há mais de 30 dias.
// Ignora linhas sem data válida (ex: a linha de nota no topo da folha).
const DIAS_RETER_SUBSCRICOES_INATIVAS = 30;

function limparSubscricoesInativas() {
  const sheet = getSheet('Subscriptions');
  const data = sheet.getDataRange().getValues();
  const limite = new Date();
  limite.setDate(limite.getDate() - DIAS_RETER_SUBSCRICOES_INATIVAS);

  const linhasParaApagar = [];
  for (let i = 1; i < data.length; i++) {
    const criada = new Date(data[i][4]); // Criada
    const inativa = String(data[i][5]).toUpperCase() === 'FALSE'; // Ativa
    if (inativa && !isNaN(criada.getTime()) && criada < limite) linhasParaApagar.push(i + 1);
  }
  linhasParaApagar.sort((a, b) => b - a).forEach(rowIndex => sheet.deleteRow(rowIndex));
  return linhasParaApagar.length;
}

function instalarTriggerLimpeza() {
  ScriptApp.getProjectTriggers().forEach(t => {
    if (t.getHandlerFunction() === 'limparHistoricoAntigo') {
      ScriptApp.deleteTrigger(t);
    }
  });

  ScriptApp.newTrigger('limparHistoricoAntigo')
    .timeBased()
    .onMonthDay(1)
    .atHour(4)
    .create();
}
