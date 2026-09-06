/**
 * Piscina.gs
 * Notificações para a manutenção da piscina — lê a aba "Piscina" (criada
 * pela PWA na primeira utilização, ver criarTabPiscina() no index.html) e
 * avisa quando uma tarefa está prevista, sem impor prazos: um único aviso
 * por ciclo, nunca escalado.
 *
 * O catálogo de tarefas (nomes, periodicidade, alternância de intervalos)
 * é estático e só existe no `index.html` — a PWA é quem calcula UltimaData
 * e ProximaData ao marcar uma tarefa como feita. Este ficheiro não conhece
 * essa lógica: só lê ProximaData/AvisoLongo/NotificacaoEnviada já gravados
 * na aba e decide se e como notificar.
 */

// Tarefas com AvisoLongo=TRUE (ex: troca da areia do filtro, a cada 3-4
// anos) avisam com esta antecedência — são fáceis de esquecer por completo
// ao longo de anos, ao contrário de uma tarefa semanal que volta a aparecer
// sozinha em poucos dias.
const PISCINA_ANTECEDENCIA_AVISO_LONGO_DIAS = 30;

function verificarPiscina() {
  const sheet = getSheetOpcional('Piscina');
  if (!sheet) return; // aba ainda não criada — funcionalidade opcional, ignora

  const linhas = sheetToObjects(sheet);
  const hoje = new Date();
  hoje.setHours(0, 0, 0, 0);

  const subs = sheetToObjects(getSheet('Subscriptions')).filter(
    s => String(s.Ativa).toUpperCase() === 'TRUE'
  );
  if (!subs.length) return;

  const auditoriaSheet = getSheetOpcional('Auditoria');

  linhas.forEach(linha => {
    if (!linha.ProximaData) return; // tarefa 'log' (sem periodicidade) ou nunca registada
    if (String(linha.NotificacaoEnviada).toUpperCase() === 'TRUE') return;

    const avisoLongo = String(linha.AvisoLongo).toUpperCase() === 'TRUE';
    const antecedencia = avisoLongo ? PISCINA_ANTECEDENCIA_AVISO_LONGO_DIAS : 0;

    const limiteAviso = new Date(linha.ProximaData);
    limiteAviso.setDate(limiteAviso.getDate() - antecedencia);
    if (hoje < limiteAviso) return;

    const titulo = avisoLongo ? '🏊 Piscina — manutenção anual' : '🏊 Piscina';
    const corpo = avisoLongo
      ? `Está a aproximar-se: ${linha.Nome} (previsto para ${linha.ProximaData}).`
      : `Sugestão de hoje: ${linha.Nome}.`;

    let algumSucesso = false;
    subs.forEach(sub => {
      const ok = enviarFCM(sub.Endpoint, titulo, corpo, '');
      registarResultadoEnvio(sub, ok);
      if (ok) algumSucesso = true;
    });

    if (algumSucesso) {
      sheet.getRange(linha._rowIndex, 6).setValue('TRUE'); // NotificacaoEnviada
      if (auditoriaSheet) {
        auditoriaSheet.appendRow([new Date().toISOString(), 'piscina_notificacao_enviada', linha.Nome, '', '']);
      }
    }
  });
}
