/**
 * WebApp.gs
 * Endpoint doPost — chamado pela PWA depois de o utilizador aceitar
 * a permissão de notificações e obter um token FCM.
 *
 * POST body esperado: { "pessoa": "Bruno", "fcmToken": "..." }
 */

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);

    if (body.tipo === 'teste') {
      return testarNotificacao(body.pessoa);
    }

    if (!body.pessoa || !body.fcmToken) {
      return jsonResponse({ ok: false, erro: 'pessoa e fcmToken são obrigatórios' });
    }

    const sheet = getSheet('Subscriptions');
    const rows = sheetToObjects(sheet);
    const existente = rows.find(
      r => r.Pessoa === body.pessoa && r.Endpoint === body.fcmToken
    );

    if (existente) {
      sheet.getRange(existente._rowIndex, 6).setValue('TRUE'); // Ativa
    } else {
      sheet.appendRow([
        body.pessoa,
        body.fcmToken, // Endpoint guarda o token FCM
        '', // Keys_p256dh — não usado com FCM
        '', // Keys_auth — não usado com FCM
        Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm'),
        'TRUE'
      ]);
    }

    return jsonResponse({ ok: true });
  } catch (err) {
    return jsonResponse({ ok: false, erro: err.message });
  }
}

function testarNotificacao(pessoa) {
  if (!pessoa) return jsonResponse({ ok: false, erro: 'pessoa é obrigatória' });

  const subs = sheetToObjects(getSheet('Subscriptions')).filter(
    s => s.Pessoa === pessoa && String(s.Ativa).toUpperCase() === 'TRUE'
  );
  if (!subs.length) {
    return jsonResponse({ ok: false, erro: 'Sem subscrição ativa para ' + pessoa + '. Ativa as notificações primeiro.' });
  }

  let sucesso = 0;
  subs.forEach(sub => {
    const ok = enviarFCM(sub.Endpoint, 'Teste', 'Notificação de teste — Tarefas de Casa 👋');
    if (ok) sucesso++;
    else desativarSubscricao(sub);
  });

  return jsonResponse({ ok: sucesso > 0, enviados: sucesso, total: subs.length });
}

function jsonResponse(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(
    ContentService.MimeType.JSON
  );
}
