/**
 * NotificationSender.gs
 * Job periódico: gera instâncias, marca atrasadas, envia notificações
 * FCM para as instâncias de hoje cuja HoraNotificacao já passou, e verifica
 * a manutenção da piscina (ver Piscina.gs).
 *
 * Corre a cada hora (ver Triggers.gs) — a notificação chega dentro da
 * janela da hora configurada, não ao minuto exato. Um Raspberry Pi pode
 * chamar, a cada 5 minutos, a parte leve (jobNotificacoes, via doPost
 * tipo 'job') para apertar essa janela; o trigger horário continua a
 * existir como reserva caso o Pi esteja em baixo.
 */

function jobPeriodico() {
  const props = PropertiesService.getScriptProperties();
  try {
    gerarInstancias();
    marcarAtrasadas();
    enviarNotificacoesComLock();
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

// Parte leve do job: só envia notificações (tarefas do dia + piscina), sem
// gerar instâncias nem marcar atrasadas. É o que o Raspberry Pi chama a cada
// 5 minutos. Não mexe em ultimaExecucao/falhasConsecutivas (essas medem o
// trigger horário completo e alimentam o alerta de "sistema falhou").
function jobNotificacoes() {
  const correu = enviarNotificacoesComLock();
  PropertiesService.getScriptProperties().setProperty('ultimaExecucaoRapida', new Date().toISOString());
  return { executado: correu };
}

// Serializa os envios: o trigger horário, o Pi (a cada 5 min) e execuções
// manuais podem coincidir, e duas execuções em simultâneo leriam
// NotificacaoEnviada=FALSE antes de qualquer uma a gravar TRUE, duplicando
// a notificação. Se não conseguir o lock em 30 s, salta — o próximo ciclo
// apanha o que ficou por enviar. Não aninhar: o lock não é reentrante.
function enviarNotificacoesComLock() {
  const lock = LockService.getUserLock();
  if (!lock.tryLock(30000)) {
    console.warn('enviarNotificacoesComLock: outra execução em curso, a saltar este ciclo.');
    return false;
  }
  try {
    enviarNotificacoesDoDia();
    verificarPiscina();
    return true;
  } finally {
    lock.releaseLock();
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
      '',
      sub.Pessoa
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
  const fusoFolha = SpreadsheetApp.openById(
    PropertiesService.getScriptProperties().getProperty('SHEET_ID')
  ).getSpreadsheetTimeZone();
  const horaPadrao = normalizarHora(config['HoraPadrao'], fusoFolha) || '08:00';
  const naoIncomodarInicio = normalizarHora(config['NaoIncomodarInicio'], fusoFolha);
  const naoIncomodarFim = normalizarHora(config['NaoIncomodarFim'], fusoFolha);

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
    if (inst.Estado === 'Feita' || inst.Estado === 'Saltada') return; // já resolvida, nada a lembrar
    if (CacheService.getScriptCache().get('snooze_' + inst.ID)) return; // ainda dentro da 1h de snooze

    const tarefa = tarefasMap[inst.TarefaID];
    if (!tarefa) return;

    const horaTarefa = normalizarHora(tarefa.HoraNotificacao, fusoFolha) || horaPadrao;
    if (horaTarefa > agora) return; // ainda não chegou a hora desta tarefa

    // F06 — Dependência: só notifica depois da tarefa-dependência estar Feita hoje
    if (tarefa.DependeDe) {
      const dependencia = instanciasHojePorTarefa[tarefa.DependeDe];
      if (!dependencia || dependencia.Estado !== 'Feita') return;
    }

    // Só marca como enviada se pelo menos um dispositivo aceitou a mensagem.
    // Sem subscrição ativa (ex: token renovado pelo Android e ainda não
    // re-registado pela app) ou com todos os envios falhados, a instância
    // fica FALSE e a próxima execução horária volta a tentar — assim, quando
    // a app re-registar o token, o aviso de hoje ainda chega em vez de se
    // perder em silêncio.
    const destinatarios = subsPorPessoa[inst.Pessoa] || [];
    if (!destinatarios.length) {
      // Sem isto o motivo mais silencioso de "não recebi nada" não deixava rasto.
      // No máx. 1 linha a cada ~6h por instância (a execução é horária).
      const cache = CacheService.getScriptCache();
      if (!cache.get('semsub_' + inst.ID)) {
        registarLogEnvio('sem_subscricao', inst.Pessoa, tarefa.Nome, inst.ID, '', '', 'Nenhuma subscrição ativa para esta pessoa');
        cache.put('semsub_' + inst.ID, '1', 21600);
      }
    }
    let algumSucesso = false;
    destinatarios.forEach(sub => {
      const resultado = enviarFCMDetalhado(sub.Endpoint, tarefa.Nome, 'Hoje: ' + tarefa.Nome, inst.ID, inst.Pessoa);
      registarResultadoEnvio(sub, resultado.ok, resultado.tokenInvalido);
      if (resultado.ok) {
        algumSucesso = true;
        if (auditoriaSheet) {
          auditoriaSheet.appendRow([new Date().toISOString(), 'notificacao_enviada', tarefa.Nome, inst.Pessoa, inst.ID]);
        }
      }
    });

    if (algumSucesso) {
      instanciasSheet.getRange(inst._rowIndex, 7).setValue('TRUE'); // NotificacaoEnviada
    }
  });
}

// A app grava as horas com valueInputOption=USER_ENTERED, por isso o Sheets
// converte "20:10" num valor de hora e o getValues() devolve-o como Date
// (dia 1899-12-30), não como texto. Comparar esse Date com o 'HH:mm' de
// "agora" (horaTarefa > agora) dá sempre false, e a notificação saía logo no
// primeiro ciclo do dia (~00:00) em vez de à hora marcada. Aqui devolvemos
// sempre 'HH:mm' (ou '' se vazio) para a comparação de strings funcionar.
function normalizarHora(valor, fuso) {
  if (valor === '' || valor === null || valor === undefined) return '';
  if (Object.prototype.toString.call(valor) === '[object Date]') {
    return Utilities.formatDate(valor, fuso, 'HH:mm');
  }
  const m = String(valor).trim().match(/^(\d{1,2}):(\d{2})/);
  return m ? ('0' + m[1]).slice(-2) + ':' + m[2] : String(valor).trim();
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

// F21 — Tolerância a falhas isoladas de envio: só desativa uma subscrição
// ao fim de duas falhas SEGUIDAS, não logo na primeira. Uma falha isolada
// (ex: o token ficou momentaneamente desatualizado porque a app ainda não
// teve oportunidade de o renovar sozinha) já não corta as notificações
// seguintes de imediato — dá tempo à app cliente para se corrigir sozinha
// da próxima vez que abrir. A notificação da própria falha continua
// perdida (não há como reenviar algo que já devia ter sido entregue);
// isto só evita que uma falha pontual arraste todas as seguintes.
// Usa PropertiesService (não CacheService) porque as falhas da mesma
// subscrição podem estar espaçadas por mais de 6 horas (o limite máximo
// de expiração da Cache) — aqui contam-se falhas consecutivas reais,
// sem limite de tempo entre elas.
var FALHAS_ANTES_DE_DESATIVAR_SUBSCRICAO = 2;

// `tokenInvalido === false` significa falha transitória (429, 5xx, rede):
// não conta, porque o token continua válido e desativá-lo cortaria as
// notificações até a app o voltar a registar. Sem o 3.º argumento
// (chamadas antigas), qualquer falha conta, como antes.
function registarResultadoEnvio(sub, sucesso, tokenInvalido) {
  const props = PropertiesService.getScriptProperties();
  const chave = 'falhasNotif_' + sub.Endpoint;
  if (sucesso) {
    props.deleteProperty(chave);
    return;
  }
  if (tokenInvalido === false) return;
  const falhas = Number(props.getProperty(chave) || '0') + 1;
  if (falhas >= FALHAS_ANTES_DE_DESATIVAR_SUBSCRICAO) {
    desativarSubscricao(sub);
    props.deleteProperty(chave);
  } else {
    props.setProperty(chave, String(falhas));
  }
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

// Devolve { ok, tokenInvalido }: tokenInvalido=true só quando o FCM diz que o
// token deixou de existir (404 / UNREGISTERED / "registration token" inválido).
// Qualquer outra falha (429, 5xx, erro de rede) é transitória.
function enviarFCMDetalhado(fcmToken, titulo, corpo, instanciaId, pessoa) {
  const projectId = PropertiesService.getScriptProperties().getProperty('FCM_PROJECT_ID');
  const accessToken = getAccessToken();
  const msgId = (instanciaId || 'msg') + '-' + Date.now();

  // Payload "data-only" (sem "notification" de topo): evita que o browser
  // mostre a notificação automaticamente por si só, em paralelo com o
  // nosso próprio onBackgroundMessage/onMessage — dono único da exibição.
  const payload = {
    message: {
      token: fcmToken,
      // pessoa/tokenFim voltam no "recebido" que o service worker envia ao
      // receber a mensagem (ver registarRecebido em WebApp.gs): é assim que
      // sabemos que a notificação chegou mesmo ao dispositivo, e a qual.
      data: Object.assign(
        { titulo: titulo, corpo: corpo, msgId: msgId, pessoa: pessoa || '', tokenFim: String(fcmToken).slice(-8) },
        instanciaId ? { instanciaId: String(instanciaId) } : {}
      ),
      webpush: {
        headers: { Urgency: 'high' },
        fcm_options: { link: 'https://pereirabmd.github.io/escritorio-casa/tarefas/' }
      }
    }
  };

  let response;
  try {
    response = UrlFetchApp.fetch(
      'https://fcm.googleapis.com/v1/projects/' + projectId + '/messages:send',
      {
        method: 'post',
        contentType: 'application/json',
        headers: { Authorization: 'Bearer ' + accessToken },
        payload: JSON.stringify(payload),
        muteHttpExceptions: true
      }
    );
  } catch (erro) {
    console.error('Falha de rede a enviar FCM: ' + erro.message);
    registarLogEnvio('erro_rede', pessoa, titulo, instanciaId, fcmToken, '', erro.message);
    return { ok: false, tokenInvalido: false };
  }

  const codigo = response.getResponseCode();
  if (codigo === 200) {
    let idMensagemFcm = '';
    try { idMensagemFcm = JSON.parse(response.getContentText()).name || ''; } catch (e) {}
    registarLogEnvio('enviado', pessoa, titulo, instanciaId, fcmToken, codigo, msgId + ' ' + idMensagemFcm);
    try {
      PropertiesService.getScriptProperties().setProperty('ultimoEnvio_' + String(fcmToken).slice(-8), new Date().toISOString());
    } catch (e) {}
    return { ok: true, tokenInvalido: false };
  }

  const corpoErro = response.getContentText();
  console.error('Falha a enviar FCM (HTTP ' + codigo + '): ' + corpoErro);
  const tokenInvalido =
    codigo === 404 ||
    corpoErro.indexOf('UNREGISTERED') !== -1 ||
    (codigo === 400 && /registration token/i.test(corpoErro));
  registarLogEnvio(tokenInvalido ? 'token_invalido' : 'falha_transitoria', pessoa, titulo, instanciaId, fcmToken, codigo, corpoErro);
  return { ok: false, tokenInvalido: tokenInvalido };
}

function enviarFCM(fcmToken, titulo, corpo, instanciaId, pessoa) {
  return enviarFCMDetalhado(fcmToken, titulo, corpo, instanciaId, pessoa).ok;
}

// ---- Log de envios (aba "LogEnvios") ----
// Uma linha por tentativa de envio, para ver depois o que realmente aconteceu:
// 'enviado' = o FCM aceitou a mensagem (HTTP 200, a coluna Detalhe traz o
// msgId e o id do FCM). 'recebido' = o service worker do telemóvel confirmou
// que a recebeu (mesmo msgId). Um 'enviado' sem 'recebido' correspondente
// significa que o problema é do lado do dispositivo (service worker, bateria,
// permissões), não do script.
// A aba é criada sozinha à primeira escrita e nunca deve impedir um envio:
// qualquer erro aqui é engolido. Mantém só as últimas ~2000 linhas.
const ABA_LOG_ENVIOS = 'LogEnvios';
const LOG_ENVIOS_MAX_LINHAS = 2000;
const LOG_ENVIOS_APAGAR_QUANDO_CHEIO = 500;
const LOG_ENVIOS_CABECALHO = ['Quando', 'Resultado', 'Pessoa', 'Titulo', 'InstanciaID', 'TokenFim', 'HTTP', 'Detalhe'];

function registarLogEnvio(resultado, pessoa, titulo, instanciaId, token, codigoHttp, detalhe) {
  try {
    const ss = SpreadsheetApp.openById(PropertiesService.getScriptProperties().getProperty('SHEET_ID'));
    let sheet = ss.getSheetByName(ABA_LOG_ENVIOS);
    if (!sheet) {
      sheet = ss.insertSheet(ABA_LOG_ENVIOS);
      // Texto simples: evita o Sheets converter a data para o fuso da folha
      // (que aqui difere do do script) ou ler o fim do token como número.
      sheet.getRange(1, 1, sheet.getMaxRows(), LOG_ENVIOS_CABECALHO.length).setNumberFormat('@');
      sheet.getRange(1, 1, 1, LOG_ENVIOS_CABECALHO.length).setValues([LOG_ENVIOS_CABECALHO]).setFontWeight('bold');
      sheet.setFrozenRows(1);
    }
    sheet.appendRow([
      Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm:ss'),
      resultado,
      pessoa || '',
      titulo || '',
      instanciaId || '',
      token ? String(token).slice(-8) : '',
      codigoHttp,
      String(detalhe || '').replace(/\s+/g, ' ').slice(0, 300)
    ]);
    if (sheet.getLastRow() > LOG_ENVIOS_MAX_LINHAS) {
      sheet.deleteRows(2, LOG_ENVIOS_APAGAR_QUANDO_CHEIO);
    }
  } catch (e) {
    console.warn('registarLogEnvio falhou: ' + e.message);
  }
}
