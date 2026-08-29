/**
 * NotificationSender.gs
 * Job periódico: gera instâncias, marca atrasadas, envia notificações
 * FCM para as instâncias de hoje cuja HoraNotificacao já passou.
 *
 * Corre a cada hora (ver Triggers.gs) — a notificação chega dentro da
 * janela da hora configurada, não ao minuto exato.
 */

function jobPeriodico() {
  const props = PropertiesService.getScriptProperties();
  try {
    gerarInstancias();
    marcarAtrasadas();
    enviarNotificacoesDoDia();
    props.setProperty('ultimaExecucao', new Date().toISOString());
    props.setProperty('falhasConsecutivas', '0');
  } catch (erro) {
    const falhas = Number(props.getProperty('falhasConsecutivas') || '0') + 1;
    props.setProperty('falhasConsecutivas', String(falhas));
    console.error('jobPeriodico falhou (' + falhas + 'x consecutivas): ' + erro.message);

    if (falhas >= 2) {
      alertarFalhaSistema(erro.message, falhas);
    }
    throw erro; // mantém o erro visível no histórico de Execuções
  }
}

// F02 — Avisa todas as pessoas com notificações ativas se o job falhar
// 2 vezes seguidas (evita alarme numa falha isolada/transitória).
function alertarFalhaSistema(mensagemErro, falhas) {
  const subs = sheetToObjects(getSheet('Subscriptions')).filter(
    s => String(s.Ativa).toUpperCase() === 'TRUE'
  );
  subs.forEach(sub => {
    enviarFCM(
      sub.Endpoint,
      '⚠️ Tarefas de Casa',
      `O sistema falhou ${falhas}x seguidas. Pode haver tarefas por notificar.`,
      ''
    );
  });
}

function marcarAtrasadas() {
  const sheet = getSheet('Instancias');
  const data = sheet.getDataRange().getValues();
  const hoje = formatDate(new Date());

  for (let i = 1; i < data.length; i++) {
    const dataStr = data[i][2]; // coluna Data
    const estado = data[i][4]; // coluna Estado
    if (estado === 'Pendente' && formatDate(new Date(dataStr)) < hoje) {
      sheet.getRange(i + 1, 5).setValue('Atrasada');
    }
  }
}

function enviarNotificacoesDoDia() {
  const config = getConfigMap();
  const horaPadrao = config['HoraPadrao'] || '08:00';
  const naoIncomodarInicio = config['NaoIncomodarInicio'] || '';
  const naoIncomodarFim = config['NaoIncomodarFim'] || '';

  const tarefasMap = {};
  sheetToObjects(getSheet('Tarefas')).forEach(t => (tarefasMap[t.ID] = t));

  const subs = sheetToObjects(getSheet('Subscriptions')).filter(
    s => String(s.Ativa).toUpperCase() === 'TRUE'
  );
  const subsPorPessoa = {};
  subs.forEach(s => {
    if (!subsPorPessoa[s.Pessoa]) subsPorPessoa[s.Pessoa] = [];
    subsPorPessoa[s.Pessoa].push(s);
  });

  const instanciasSheet = getSheet('Instancias');
  const instancias = sheetToObjects(instanciasSheet);
  const hoje = formatDate(new Date());
  const agora = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'HH:mm');

  // F03 — Não incomodar: se a hora atual cair dentro da janela definida,
  // não envia nada nesta execução (a instância continua Pendente/FALSE,
  // será apanhada na próxima execução fora da janela).
  if (naoIncomodarInicio && naoIncomodarFim && dentroDaJanela(agora, naoIncomodarInicio, naoIncomodarFim)) {
    return;
  }

  // F17 — Registo simples de auditoria (append-only, opcional)
  const auditoriaSheet = getSheetOpcional('Auditoria');

  // Instâncias de hoje, indexadas por TarefaID, para checagem de dependências (F06)
  const instanciasHojePorTarefa = {};
  instancias.forEach(i => {
    if (formatDate(new Date(i.Data)) === hoje) instanciasHojePorTarefa[i.TarefaID] = i;
  });

  instancias.forEach(inst => {
    if (formatDate(new Date(inst.Data)) !== hoje) return;
    if (String(inst.NotificacaoEnviada).toUpperCase() === 'TRUE') return;
    if (CacheService.getScriptCache().get('snooze_' + inst.ID)) return; // ainda dentro da 1h de snooze

    const tarefa = tarefasMap[inst.TarefaID];
    if (!tarefa) return;

    const horaTarefa = tarefa.HoraNotificacao || horaPadrao;
    if (horaTarefa > agora) return; // ainda não chegou a hora desta tarefa

    // F06 — Dependência: só notifica depois da tarefa-dependência estar Feita hoje
    if (tarefa.DependeDe) {
      const dependencia = instanciasHojePorTarefa[tarefa.DependeDe];
      if (!dependencia || dependencia.Estado !== 'Feita') return;
    }

    const destinatarios = subsPorPessoa[inst.Pessoa] || [];
    destinatarios.forEach(sub => {
      const ok = enviarFCM(sub.Endpoint, tarefa.Nome, 'Hoje: ' + tarefa.Nome, inst.ID);
      if (!ok) desativarSubscricao(sub);
      if (ok && auditoriaSheet) {
        auditoriaSheet.appendRow([new Date().toISOString(), 'notificacao_enviada', tarefa.Nome, inst.Pessoa, inst.ID]);
      }
    });

    instanciasSheet.getRange(inst._rowIndex, 7).setValue('TRUE'); // NotificacaoEnviada
  });
}

function dentroDaJanela(agora, inicio, fim) {
  // Suporta janelas que atravessam a meia-noite (ex: 22:00–07:00)
  if (inicio <= fim) return agora >= inicio && agora < fim;
  return agora >= inicio || agora < fim;
}

function getSheetOpcional(nome) {
  try {
    return getSheet(nome);
  } catch (e) {
    return null; // tab Auditoria não existe — funcionalidade opcional, ignora
  }
}

function desativarSubscricao(sub) {
  getSheet('Subscriptions').getRange(sub._rowIndex, 6).setValue('FALSE'); // Ativa
}

// ---- Transporte FCM (HTTP v1 API, autenticado via service account) ----

function getAccessToken() {
  const props = PropertiesService.getScriptProperties();
  const cache = CacheService.getScriptCache();
  const cached = cache.get('fcm_access_token');
  if (cached) return cached;

  const clientEmail = props.getProperty('FCM_CLIENT_EMAIL');
  const privateKey = props.getProperty('FCM_PRIVATE_KEY').replace(/\\n/g, '\n');

  const header = { alg: 'RS256', typ: 'JWT' };
  const now = Math.floor(Date.now() / 1000);
  const claimSet = {
    iss: clientEmail,
    scope: 'https://www.googleapis.com/auth/firebase.messaging',
    aud: 'https://oauth2.googleapis.com/token',
    exp: now + 3600,
    iat: now
  };

  const encode = obj =>
    Utilities.base64EncodeWebSafe(JSON.stringify(obj)).replace(/=+$/, '');
  const toSign = encode(header) + '.' + encode(claimSet);
  const signatureBytes = Utilities.computeRsaSha256Signature(toSign, privateKey);
  const signature = Utilities.base64EncodeWebSafe(signatureBytes).replace(/=+$/, '');
  const jwt = toSign + '.' + signature;

  const response = UrlFetchApp.fetch('https://oauth2.googleapis.com/token', {
    method: 'post',
    contentType: 'application/x-www-form-urlencoded',
    payload: {
      grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer',
      assertion: jwt
    },
    muteHttpExceptions: true
  });

  const result = JSON.parse(response.getContentText());
  if (!result.access_token) {
    throw new Error('Falha a obter access token: ' + response.getContentText());
  }

  cache.put('fcm_access_token', result.access_token, 3300); // ~55 min
  return result.access_token;
}

function enviarFCM(fcmToken, titulo, corpo, instanciaId) {
  const projectId = PropertiesService.getScriptProperties().getProperty('FCM_PROJECT_ID');
  const accessToken = getAccessToken();
  const msgId = (instanciaId || 'msg') + '-' + Date.now();

  // Payload "data-only" (sem "notification" de topo): evita que o browser
  // mostre a notificação automaticamente por si só, em paralelo com o
  // nosso próprio onBackgroundMessage/onMessage — dono único da exibição.
  const payload = {
    message: {
      token: fcmToken,
      data: Object.assign(
        { titulo: titulo, corpo: corpo, msgId: msgId },
        instanciaId ? { instanciaId: String(instanciaId) } : {}
      ),
      webpush: {
        headers: { Urgency: 'high' },
        fcm_options: { link: 'https://pereirabmd.github.io/escritorio-casa/tarefas/' }
      }
    }
  };

  const response = UrlFetchApp.fetch(
    'https://fcm.googleapis.com/v1/projects/' + projectId + '/messages:send',
    {
      method: 'post',
      contentType: 'application/json',
      headers: { Authorization: 'Bearer ' + accessToken },
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    }
  );

  if (response.getResponseCode() === 200) return true;

  console.error('Falha a enviar FCM: ' + response.getContentText());
  return false; // token provavelmente inválido/expirado -> desativar
}
