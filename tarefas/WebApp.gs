/**
 * WebApp.gs
 * Endpoint doPost — chamado pela PWA depois de o utilizador aceitar
 * a permissão de notificações e obter um token FCM.
 *
 * POST body esperado: { "pessoa": "Bruno", "fcmToken": "..." }
 */

function doGet(e) {
  return jsonResponse(estadoSaude());
}

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);

    if (body.tipo === 'teste') {
      return testarNotificacao(body.pessoa);
    }
    if (body.tipo === 'gerar') {
      const n = gerarInstancias();
      return jsonResponse({ ok: true, criadas: n });
    }
    if (body.tipo === 'marcarFeita') {
      return marcarInstanciaFeita(body.instanciaId);
    }
    if (body.tipo === 'snooze') {
      return adiarNotificacao(body.instanciaId);
    }
    if (body.tipo === 'saude') {
      return jsonResponse(estadoSaude());
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

function marcarInstanciaFeita(instanciaId) {
  if (!instanciaId) return jsonResponse({ ok: false, erro: 'instanciaId é obrigatório' });

  const sheet = getSheet('Instancias');
  const rows = sheetToObjects(sheet);
  const inst = rows.find(r => r.ID === instanciaId);
  if (!inst) return jsonResponse({ ok: false, erro: 'Instância não encontrada' });

  const agora = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm');
  sheet.getRange(inst._rowIndex, 5).setValue('Feita'); // Estado
  sheet.getRange(inst._rowIndex, 6).setValue(agora); // DataConclusao

  return jsonResponse({ ok: true });
}

// F01 — Snooze: guarda em cache (não no Sheet) até quando esta instância
// deve voltar a poder notificar. Sem precisar de coluna nova.
function adiarNotificacao(instanciaId) {
  if (!instanciaId) return jsonResponse({ ok: false, erro: 'instanciaId é obrigatório' });

  const sheet = getSheet('Instancias');
  const rows = sheetToObjects(sheet);
  const inst = rows.find(r => r.ID === instanciaId);
  if (!inst) return jsonResponse({ ok: false, erro: 'Instância não encontrada' });

  // Reabre a possibilidade de notificar (o jobPeriodico ignora
  // NotificacaoEnviada=FALSE + snooze_{id} em cache durante 1h)
  sheet.getRange(inst._rowIndex, 7).setValue('FALSE'); // NotificacaoEnviada
  CacheService.getScriptCache().put('snooze_' + instanciaId, '1', 3600); // 1h

  return jsonResponse({ ok: true });
}

function estadoSaude() {
  const props = PropertiesService.getScriptProperties();
  const ultima = props.getProperty('ultimaExecucao');
  const falhas = Number(props.getProperty('falhasConsecutivas') || '0');
  if (!ultima) {
    return { ok: true, ultimaExecucao: null, minutosDesde: null, saudavel: false, falhasConsecutivas: falhas };
  }
  const minutos = Math.round((Date.now() - new Date(ultima).getTime()) / 60000);
  return {
    ok: true,
    ultimaExecucao: ultima,
    minutosDesde: minutos,
    saudavel: minutos < 90 && falhas < 2, // trigger corre a cada hora; > 90min sem correr ou 2+ falhas é sinal de alerta
    falhasConsecutivas: falhas
  };
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

  if (sucesso === 0) {
    return jsonResponse({
      ok: false,
      erro: `Encontradas ${subs.length} subscrição(ões) mas todas falharam ao enviar (tokens provavelmente expirados — foram desativadas). Toca em "Ativar notificações" para gerar um token novo.`
    });
  }

  return jsonResponse({ ok: true, enviados: sucesso, total: subs.length });
}

function jsonResponse(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(
    ContentService.MimeType.JSON
  );
}
