/**
 * Utils.gs
 * Funções auxiliares partilhadas por todo o projeto.
 */

function getSheet(nome) {
  const ss = SpreadsheetApp.openById(
    PropertiesService.getScriptProperties().getProperty('SHEET_ID')
  );
  const sheet = ss.getSheetByName(nome);
  if (!sheet) throw new Error('Sheet não encontrado: ' + nome);
  return sheet;
}

// Converte uma sheet em array de objetos {header: valor}, incluindo _rowIndex
// (linha real na folha, 1-indexed, para permitir editar de volta).
function sheetToObjects(sheet) {
  const data = sheet.getDataRange().getValues();
  const headers = data[0];
  return data
    .slice(1)
    .map((row, i) => {
      const obj = {};
      headers.forEach((h, idx) => (obj[h] = row[idx]));
      obj._rowIndex = i + 2; // +1 porque slice(1), +1 porque a folha é 1-indexed
      return obj;
    })
    .filter(obj => Object.keys(obj).some(k => k !== '_rowIndex' && obj[k] !== ''));
}

function getConfigMap() {
  const rows = sheetToObjects(getSheet('Config'));
  const map = {};
  rows.forEach(r => (map[r.Chave] = r.Valor));
  return map;
}

function formatDate(date) {
  return Utilities.formatDate(date, Session.getScriptTimeZone(), 'yyyy-MM-dd');
}
