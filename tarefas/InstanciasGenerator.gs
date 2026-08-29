/**
 * InstanciasGenerator.gs
 * Gera linhas em "Instancias" a partir do catálogo em "Tarefas",
 * cobrindo a janela de DiasAntecedenciaGeracao (tab Config).
 * Idempotente: nunca duplica uma ocorrência TarefaID+Data já existente.
 */

function gerarInstancias() {
  // F19 — Lock: gerarInstancias() pode ser chamada tanto pelo trigger horário
  // (jobPeriodico) como manualmente por qualquer pessoa ("Atualizar tarefas
  // do dia agora"). Sem serializar, duas execuções em simultâneo podiam ler
  // o mesmo estado de "Instancias" antes de qualquer uma escrever e ambas
  // decidir criar a mesma ocorrência (TarefaID+Data) — duplicando-a. O lock
  // garante que só uma execução gera de cada vez; a segunda espera a vez.
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(15000);
  } catch (e) {
    console.warn('gerarInstancias: não obteve o lock a tempo, outra execução está em curso.');
    return 0;
  }
  try {
    return gerarInstanciasSemLock();
  } finally {
    lock.releaseLock();
  }
}

function gerarInstanciasSemLock() {
  const config = getConfigMap();
  const horizonteDias = Number(config['DiasAntecedenciaGeracao'] || 30);

  const tarefas = sheetToObjects(getSheet('Tarefas')).filter(
    t => String(t.Ativa).toUpperCase() === 'TRUE'
  );

  const instanciasSheet = getSheet('Instancias');
  const instanciasExistentes = sheetToObjects(instanciasSheet);
  const chavesExistentes = new Set(
    instanciasExistentes.map(i => i.TarefaID + '|' + formatDate(new Date(i.Data)))
  );

  // Contagem de ocorrências já existentes por tarefa, para a rotação
  // de responsável continuar de forma consistente entre execuções.
  const contagemPorTarefa = {};
  instanciasExistentes.forEach(i => {
    contagemPorTarefa[i.TarefaID] = (contagemPorTarefa[i.TarefaID] || 0) + 1;
  });

  let proximoId = instanciasExistentes.length
    ? Math.max(...instanciasExistentes.map(i => Number(String(i.ID).replace(/\D/g, '')) || 0)) + 1
    : 1;

  const hoje = new Date();
  hoje.setHours(0, 0, 0, 0);

  const novasLinhas = [];
  const nomesDiaSemana = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab'];

  for (let d = 0; d <= horizonteDias; d++) {
    const data = new Date(hoje);
    data.setDate(data.getDate() + d);
    const diaSemana = nomesDiaSemana[data.getDay()];
    const diaMes = data.getDate();

    tarefas.forEach(t => {
      if (!ocorreNestaData(t, data, diaSemana, diaMes)) return;

      const chave = t.ID + '|' + formatDate(data);
      if (chavesExistentes.has(chave)) return;

      const responsavel = calcularResponsavel(t, contagemPorTarefa);

      novasLinhas.push([
        'I' + String(proximoId).padStart(4, '0'),
        t.ID,
        formatDate(data),
        responsavel,
        'Pendente',
        '',
        'FALSE'
      ]);
      chavesExistentes.add(chave);
      proximoId++;
    });
  }

  if (novasLinhas.length) {
    instanciasSheet
      .getRange(instanciasSheet.getLastRow() + 1, 1, novasLinhas.length, novasLinhas[0].length)
      .setValues(novasLinhas);
  }

  return novasLinhas.length;
}

// F12 — Rotação automática: se a tarefa tiver RotacaoPessoas preenchido
// (nomes separados por vírgula), alterna entre eles a cada ocorrência nova.
function calcularResponsavel(tarefa, contagemPorTarefa) {
  const rotacao = String(tarefa.RotacaoPessoas || '')
    .split(',')
    .map(s => s.trim())
    .filter(Boolean);

  if (rotacao.length < 2) return tarefa.PessoaPadrao;

  const indiceAtual = contagemPorTarefa[tarefa.ID] || 0;
  contagemPorTarefa[tarefa.ID] = indiceAtual + 1;
  return rotacao[indiceAtual % rotacao.length];
}

function ocorreNestaData(tarefa, data, diaSemana, diaMes) {
  switch (tarefa.Recorrencia) {
    case 'Diaria':
      return true;
    case 'Semanal':
    case 'Dias especificos': {
      const dias = String(tarefa.DiasSemana || '')
        .split(',')
        .map(s => s.trim());
      return dias.includes(diaSemana);
    }
    case 'Mensal':
      return diaMes === Number(tarefa.DiaMes);
    case 'Pontual':
      // Ocorrências pontuais são criadas diretamente pela PWA, não geradas aqui.
      return false;
    default:
      return false;
  }
}
