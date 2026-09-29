import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App } from '../../App'
import { corCategoria, csvHistorico, dataDeIso, intervaloMes, intervaloSemana, somarDias, tituloMes, tituloSemana } from '../../lib/tarefas'
import { servidorFalso, UTILIZADOR, type Rotas } from '../../test/api-mock'

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '')
const OK: [number, unknown] = [200, { resultado: {} }]
const inst = (id: string, nome: string, data: string, extra = {}) => ({ id, tarefaId: 'T1', nome, categoria: 'Limpeza', prioridade: 'Media', hora: '09:00', pessoa: 'Bruno', estado: 'Pendente', data, dataConclusao: '', ...extra })

const PRINCIPAL = { data: '2026-09-30', pessoa: 'Bruno', pessoas: ['Bruno', 'Camila'], categorias: ['Casa', 'Limpeza'], horaPadrao: '08:00', hoje: [], feitas: [], atrasadas: [], amanha: [], tarefas: [] }

function abrir(aba: string, extra: Rotas = {}) {
  window.history.pushState({}, '', `${BASE}/tarefas?aba=${aba}`)
  const s = servidorFalso({ 'GET /auth/me': () => [200, { utilizador: UTILIZADOR }], 'GET /tasks': () => [200, PRINCIPAL], ...extra })
  render(<App />)
  return s
}
const corpo = (p: { caminho: string; corpo: unknown }[], c: string) => p.find((x) => x.caminho === c)!.corpo

beforeEach(() => localStorage.clear())
afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })

describe('lib do calendário', () => {
  test('grelha do mês: semanas de domingo a sábado', () => {
    expect(intervaloMes('2026-09-30')).toEqual(['2026-08-30', '2026-10-03'])      // 1 set 2026 é uma terça
    expect(intervaloMes('2026-02-10')).toEqual(['2026-02-01', '2026-02-28'])      // fevereiro a caber em 4 semanas certas
    expect(intervaloSemana('2026-09-30')).toEqual(['2026-09-27', '2026-10-03'])
    expect(somarDias('2026-12-31', 1)).toBe('2027-01-01')
    expect(dataDeIso('2026-03-29').getDate()).toBe(29)                              // dia da mudança de hora
  })
  test('títulos e cores estáveis', () => {
    expect(tituloMes('2026-09-30')).toBe('Setembro de 2026')
    expect(tituloSemana('2026-09-27', '2026-10-03')).toMatch(/^27 set\.? – 3 out\.?$/)
    expect(tituloSemana('2026-10-04', '2026-10-10')).toBe('4–10 de outubro')
    expect(corCategoria('Limpeza')).toBe(corCategoria('Limpeza'))
    expect(corCategoria('Limpeza')).not.toBe(corCategoria('Cozinha'))
  })
  test('CSV com BOM e aspas escapadas', () => {
    const csv = csvHistorico([{ tarefa: 'Lavar "carro"', categoria: 'Casa', data: '2026-09-29', pessoa: 'Bruno', estado: 'Feita', dataConclusao: '2026-09-29 10:00' }])
    expect(csv.startsWith('﻿"Tarefa","Categoria"')).toBe(true)
    expect(csv).toContain('"Lavar ""carro"""')
  })
})

describe('Calendário', () => {
  const dias = (de: string, n: number) => Array.from({ length: n }, (_, k) => { const data = somarDias(de, k); return { data, feriado: data === '2026-10-05' ? 'Implantação da República' : null, itens: data === '2026-09-30' ? [inst('I1', 'Limpar WC', data)] : [] } })
  const cal = (de: string, ate: string) => ({ de, ate, hoje: '2026-09-30', horaPadrao: '08:00', dias: dias(de, Math.round((dataDeIso(ate).getTime() - dataDeIso(de).getTime()) / 86400000) + 1) })

  test('mostra o mês, o dia de hoje e as tarefas desse dia com as ações', async () => {
    const { pedidos } = abrir('calendario', { 'GET /tasks/calendar?de=2026-08-30&ate=2026-10-03': () => [200, cal('2026-08-30', '2026-10-03')], 'POST /actions/tarefas.saltar': () => OK })
    expect(await screen.findByRole('heading', { name: 'Setembro de 2026' })).toBeInTheDocument()
    const dia = within(await screen.findByRole('region', { name: 'Tarefas do dia' }))
    expect(await dia.findByText('Limpar WC')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^30 de setembro, 1 tarefa$/ })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(dia.getByRole('button', { name: 'Saltar Limpar WC' }))
    await waitFor(() => expect(pedidos.some((p) => p.caminho === '/actions/tarefas.saltar')).toBe(true))
    expect(corpo(pedidos, '/actions/tarefas.saltar')).toEqual({ params: { instancia: 'I1' } })
  })

  test('navegar para outro mês pede esse intervalo e o feriado aparece na nota e no dia', async () => {
    const { pedidos } = abrir('calendario', {
      'GET /tasks/calendar?de=2026-08-30&ate=2026-10-03': () => [200, cal('2026-08-30', '2026-10-03')],
      'GET /tasks/calendar?de=2026-09-27&ate=2026-10-31': () => [200, cal('2026-09-27', '2026-11-07')],
    })
    await screen.findByRole('heading', { name: 'Setembro de 2026' })
    await userEvent.click(screen.getByRole('button', { name: 'Mês seguinte' }))
    expect(await screen.findByRole('heading', { name: 'Outubro de 2026' })).toBeInTheDocument()
    await waitFor(() => expect(pedidos.some((p) => p.caminho === '/tasks/calendar?de=2026-09-27&ate=2026-10-31')).toBe(true))
    expect(await screen.findByText(/5 — Implantação da República/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /^5 de outubro, Implantação da República$/ }))
    expect(within(screen.getByRole('region', { name: 'Tarefas do dia' })).getByText(/Implantação da República/)).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Tarefas do dia' })).getByText('Sem tarefas neste dia.')).toBeInTheDocument()
  })

  test('vista de semana pede sete dias', async () => {
    const { pedidos } = abrir('calendario', {
      'GET /tasks/calendar?de=2026-08-30&ate=2026-10-03': () => [200, cal('2026-08-30', '2026-10-03')],
      'GET /tasks/calendar?de=2026-09-27&ate=2026-10-03': () => [200, cal('2026-09-27', '2026-10-03')],
    })
    await screen.findByRole('heading', { name: 'Setembro de 2026' })
    await userEvent.click(screen.getByRole('button', { name: 'Semana' }))
    expect(await screen.findByRole('heading', { name: /27 set\.? – 3 out\.?/ })).toBeInTheDocument()
    expect(pedidos.some((p) => p.caminho === '/tasks/calendar?de=2026-09-27&ate=2026-10-03')).toBe(true)
    expect(screen.getAllByRole('button', { name: /^\d+ de / })).toHaveLength(7)
  })

  test('erro a carregar e nova tentativa', async () => {
    let falha = true
    abrir('calendario', { 'GET /tasks/calendar?de=2026-08-30&ate=2026-10-03': () => (falha ? [503, { erro: { codigo: 'modulo_indisponivel', mensagem: 'x' } }] : [200, cal('2026-08-30', '2026-10-03')]) })
    expect(await screen.findByRole('alert')).toHaveTextContent('não está disponível de momento')
    falha = false
    await userEvent.click(screen.getAllByRole('button', { name: 'Tentar de novo' })[0])
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
  })
})

describe('Horário', () => {
  const aula = (disciplina: string, sala = '') => ({ disciplina, sala })
  const HOR = {
    disponivel: true, anoLetivo: '2026/2027', diaHoje: 3, avisos: { ativos: true, minutos: 30 },
    alunos: [{ nome: 'Ana', dias: [
      { dia: 1, nome: 'Seg', entra: '09:00', sai: '10:00', aviso: '09:30', totalAulas: 1, slots: [{ ini: '09:00', fim: '10:00', aulas: [aula('Português', 'A1')], dividida: false, ultima: true }] },
      { dia: 3, nome: 'Qua', entra: '08:15', sai: '11:30', aviso: '11:00', totalAulas: 3, slots: [
        { ini: '08:15', fim: '09:45', aulas: [aula('Matemática', 'B1')], dividida: false, ultima: false },
        { ini: '10:00', fim: '11:30', aulas: [aula('Física', 'L1'), aula('Química', 'L2')], dividida: true, ultima: true }] }] },
    { nome: 'Rui', dias: [{ dia: 2, nome: 'Ter', entra: '10:00', sai: '12:00', aviso: '11:30', totalAulas: 1, slots: [{ ini: '10:00', fim: '12:00', aulas: [aula('História')], dividida: false, ultima: true }] }] }],
  }

  test('abre no dia de hoje com resumo, turma dividida e saída/aviso', async () => {
    abrir('horario', { 'GET /tasks/schedule': () => [200, HOR] })
    expect(await screen.findByText(/ano letivo 2026\/2027/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Quarta' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText(/Entra às/)).toHaveTextContent('Entra às 08:15 · sai às 11:30 · 3 aulas')
    expect(screen.getByText('turma dividida')).toBeInTheDocument()
    expect(screen.getByText('Saída às 11:30 · aviso às 11:00')).toBeInTheDocument()
    expect(screen.getByText('Química')).toBeInTheDocument()
  })

  test('escolher o dia, o aluno e a vista da semana', async () => {
    abrir('horario', { 'GET /tasks/schedule': () => [200, HOR] })
    await userEvent.click(await screen.findByRole('button', { name: 'Segunda' }))
    expect(screen.getByText('Português')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Semana' }))
    const tabela = within(screen.getByRole('table'))
    expect(tabela.getByText('Matemática')).toBeInTheDocument()
    expect(tabela.getByText('Português')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Rui' }))
    expect(within(screen.getByRole('table')).getByText('História')).toBeInTheDocument()
    expect(within(screen.getByRole('table')).queryByText('Matemática')).not.toBeInTheDocument()
  })

  test('pausar os avisos e voltar a ativá-los', async () => {
    const { pedidos } = abrir('horario', { 'GET /tasks/schedule': () => [200, HOR], 'POST /actions/tarefas.avisos_horario': () => OK })
    await userEvent.click(await screen.findByRole('button', { name: 'Pausar avisos' }))
    expect(await screen.findByText(/Avisos do horário pausados \(os já agendados/)).toBeInTheDocument()
    expect(corpo(pedidos, '/actions/tarefas.avisos_horario')).toEqual({ params: { ativos: false } })
  })

  test('indisponível e sem horário importado', async () => {
    abrir('horario', { 'GET /tasks/schedule': () => [200, { disponivel: false, anoLetivo: null, diaHoje: 3, avisos: null, alunos: [] }] })
    expect(await screen.findByText(/O horário não está disponível de momento/)).toBeInTheDocument()
  })
  test('sem horário importado', async () => {
    abrir('horario', { 'GET /tasks/schedule': () => [200, { ...HOR, alunos: [] }] })
    expect(await screen.findByText('Ainda não há horário importado.')).toBeInTheDocument()
  })
})

describe('Piscina', () => {
  const C = (id: string, nome: string, extra = {}) => ({ id, nome, nota: '', notaLonga: '', tipo: 'periodica', ultima: '', proxima: '', estado: 'nunca', diasDesde: null, ...extra })
  const POOL = { estacao: 'quente', periodicas: [
    C('P04', 'Robô aspirador', { ultima: '2026-09-01', proxima: '2026-09-04', estado: 'atrasada', diasDesde: 29, destacar: true }),
    C('P05', 'Escovar paredes', { ultima: '2026-09-27', proxima: '2026-09-30', estado: 'hoje', diasDesde: 3, destacar: true, sugeridoHoje: true }),
    C('P06', 'Limpar cesto', { ultima: '2026-09-29', proxima: '2026-10-06', estado: 'ok', diasDesde: 1 }),
    C('P07', 'Testar TAC', { nota: 'ideal 80-120 ppm' }),
    C('P11', 'Pressão do filtro', { notaLonga: 'Contralavagem quando o manómetro atingir ~16 psi.' })],
    outras: [C('P13', 'Choque de cloro', { tipo: 'log', estado: 'registo', ultima: '2026-08-01' })] }

  test('estação, estados de cada tarefa e notas', async () => {
    abrir('piscina', { 'GET /tasks/pool': () => [200, POOL] })
    expect(await screen.findByText('meses quentes')).toBeInTheDocument()
    expect(screen.getByText('por fazer há 29 dias')).toBeInTheDocument()
    expect(screen.getByText('Última vez: 27/09/2026 (há 3 dias)')).toBeInTheDocument()
    expect(screen.getAllByText('sugerido para hoje').length).toBeGreaterThan(0)
    expect(screen.getByText(/Última vez: 29\/09\/2026 \(há 1 dia\) · sugerido: 06\/10\/2026/)).toBeInTheDocument()
    expect(screen.getAllByText('Ainda não registada')).toHaveLength(2)
    expect(screen.getByText('(ideal 80-120 ppm)')).toBeInTheDocument()
    expect(screen.getByText(/Contralavagem quando o manómetro/)).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Outras ações' })).getByText('Última vez: 01/08/2026')).toBeInTheDocument()
  })

  test('marcar feita hoje e desfazer repõe o estado anterior', async () => {
    const anterior = { ultimaData: '2026-09-01', proximaData: '2026-09-04', usarIntervaloLongo: false, notificacaoEnviada: true }
    const { pedidos } = abrir('piscina', { 'GET /tasks/pool': () => [200, POOL], 'POST /actions/tarefas.piscina_registar': () => [200, { resultado: { anterior } }], 'POST /actions/tarefas.piscina_repor': () => OK })
    await userEvent.click(await screen.findByRole('button', { name: 'Marcar feita hoje: Robô aspirador' }))
    expect(await screen.findByText('Robô aspirador registada.')).toBeInTheDocument()
    expect(corpo(pedidos, '/actions/tarefas.piscina_registar')).toEqual({ params: { item: 'P04' } })
    await userEvent.click(screen.getByRole('button', { name: 'Desfazer' }))
    await waitFor(() => expect(pedidos.some((p) => p.caminho === '/actions/tarefas.piscina_repor')).toBe(true))
    expect(corpo(pedidos, '/actions/tarefas.piscina_repor')).toEqual({ params: { item: 'P04', ...anterior } })
  })

  test('registar uma ação condicional', async () => {
    const { pedidos } = abrir('piscina', { 'GET /tasks/pool': () => [200, POOL], 'POST /actions/tarefas.piscina_registar': () => OK })
    await userEvent.click(await screen.findByRole('button', { name: 'Registar agora: Choque de cloro' }))
    expect(await screen.findByText('Choque de cloro registada.')).toBeInTheDocument()
    expect(corpo(pedidos, '/actions/tarefas.piscina_registar')).toEqual({ params: { item: 'P13' } })
  })
})

describe('Config', () => {
  const DEF = {
    pessoas: [{ nome: 'Bruno', email: 'b@x.pt' }, { nome: 'Camila', email: '' }], pessoaAtual: 'Bruno', categorias: ['Casa'],
    preferencias: { horaPadrao: '08:00', naoIncomodarInicio: '22:00', naoIncomodarFim: '07:00', horarioAvisos: true, horarioAvisoMinutos: 30 },
    resumo: { pessoas: [{ nome: 'Bruno', feitas: 6 }, { nome: 'Camila', feitas: 1 }], desequilibrio: 'Bruno' },
    auditoria: [{ ts: '2026-09-29T10:00:00.000Z', acao: 'piscina_feita', tarefa: 'Cloro rápido', pessoa: 'Bruno' }],
    souAdmin: false, admin: null,
    saude: { ok: true, saudavel: true, ultimaExecucao: '2026-09-30T09:55:00', minutosDesde: 4, contagens: { agendado: 2, sem_alteracao: 7 } },
  }
  const ADMIN = { raiz: ['b@x.pt'], admins: ['b@x.pt'], pessoas: [{ num: 1, nome: 'Bruno', email: 'b@x.pt', admin: true, fixo: true }, { num: 2, nome: 'Camila', email: 'c@x.pt', admin: false, fixo: false }],
    notificacoes: [{ id: 'piscina', nome: 'Piscina', descricao: 'Sugestão de manutenção.', destinatarios: ['Bruno'], padrao: false }] }
  const abrirConfig = (extra: Rotas = {}, def: unknown = DEF) => abrir('config', { 'GET /tasks/settings': () => [200, def], ...extra })

  test('resumo, aviso de desequilíbrio, saúde do Pi e últimas ações', async () => {
    abrirConfig()
    expect(await screen.findByText(/A tua conta corresponde a/)).toHaveTextContent('Bruno')
    expect(screen.getByRole('progressbar', { name: 'Bruno: 6 tarefas' })).toBeInTheDocument()
    expect(screen.getByText(/Bruno tem feito bastante mais/)).toBeInTheDocument()
    expect(screen.getByText('Em dia')).toBeInTheDocument()
    expect(screen.getByText(/há 4 min/)).toBeInTheDocument()
    expect(screen.getByText(/2 novas/)).toBeInTheDocument()
    expect(screen.getByText(/Cloro rápido · Bruno/)).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Administração' })).not.toBeInTheDocument()
  })

  test('Pi sem resposta e reconciliação que nunca correu', async () => {
    abrirConfig({}, { ...DEF, saude: null, auditoria: [] })
    expect(await screen.findByText(/Não foi possível verificar o estado do Pi/)).toBeInTheDocument()
    expect(screen.getByText('Ainda não há registos.')).toBeInTheDocument()
  })

  test('adicionar pessoa valida e envia', async () => {
    const { pedidos } = abrirConfig({ 'POST /actions/tarefas.pessoa_adicionar': () => OK })
    await userEvent.click(await screen.findByRole('button', { name: 'Adicionar' }))
    expect(screen.getByText('Escreve um nome.')).toBeInTheDocument()
    await userEvent.type(screen.getByRole('textbox', { name: 'Adicionar pessoa' }), 'A,B')
    await userEvent.click(screen.getByRole('button', { name: 'Adicionar' }))
    expect(screen.getByText('O nome não pode ter vírgulas.')).toBeInTheDocument()
    await userEvent.clear(screen.getByRole('textbox', { name: 'Adicionar pessoa' }))
    await userEvent.type(screen.getByRole('textbox', { name: 'Adicionar pessoa' }), 'Diana')
    await userEvent.type(screen.getByLabelText(/E-mail Google \(opcional/), 'd@x.pt')
    await userEvent.click(screen.getByRole('button', { name: 'Adicionar' }))
    expect(await screen.findByText('Pessoa adicionada.')).toBeInTheDocument()
    expect(corpo(pedidos, '/actions/tarefas.pessoa_adicionar')).toEqual({ params: { nome: 'Diana', email: 'd@x.pt' } })
  })

  test('editar (renomear e mudar o e-mail)', async () => {
    const { pedidos } = abrirConfig({ 'POST /actions/tarefas.pessoa_editar': () => OK })
    await userEvent.click(await screen.findByRole('button', { name: 'Editar Camila' }))
    const g = within(screen.getByRole('group', { name: 'Editar Camila' }))
    await userEvent.clear(g.getByLabelText('Nome')); await userEvent.type(g.getByLabelText('Nome'), 'Camila M.')
    await userEvent.type(g.getByLabelText('E-mail Google'), 'c@x.pt')
    await userEvent.click(g.getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByText('Pessoa atualizada.')).toBeInTheDocument()
    expect(corpo(pedidos, '/actions/tarefas.pessoa_editar')).toEqual({ params: { nome: 'Camila', novoNome: 'Camila M.', email: 'c@x.pt' } })
  })

  test('remover pede o substituto e envia com confirmação', async () => {
    const { pedidos } = abrirConfig({ 'POST /actions/tarefas.pessoa_remover': () => [200, { resultado: { reatribuidas: 3 } }] })
    await userEvent.click(await screen.findByRole('button', { name: 'Remover Camila' }))
    const g = within(screen.getByRole('group', { name: 'Remover Camila' }))
    expect(g.getByRole('button', { name: 'Bruno' })).toHaveAttribute('aria-pressed', 'true')       // o único candidato vem escolhido
    await userEvent.click(g.getByRole('button', { name: 'Remover' }))
    expect(await screen.findByText('Pessoa removida · 3 tarefa(s) passada(s) para Bruno.')).toBeInTheDocument()
    expect(pedidos.find((p) => p.caminho === '/actions/tarefas.pessoa_remover')!.corpo).toEqual({ params: { nome: 'Camila', substituto: 'Bruno' }, confirmado: true })
  })

  test('cancelar a remoção não envia nada; a última pessoa não se remove', async () => {
    const { pedidos } = abrirConfig()
    await userEvent.click(await screen.findByRole('button', { name: 'Remover Camila' }))
    await userEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(pedidos.filter((p) => p.metodo !== 'GET')).toEqual([])
  })
  test('com uma só pessoa o botão remover está desativado', async () => {
    abrirConfig({}, { ...DEF, pessoas: [{ nome: 'Bruno', email: '' }] })
    expect(await screen.findByRole('button', { name: 'Remover Bruno' })).toBeDisabled()
  })

  test('reatribuir em massa exige pessoas diferentes e confirma', async () => {
    const { pedidos } = abrirConfig({ 'POST /actions/tarefas.reatribuir': () => OK })
    await userEvent.click(await screen.findByRole('button', { name: 'Reatribuir tarefas em massa' }))
    const g = within(screen.getByRole('group', { name: 'Reatribuir tarefas em massa' }))
    await userEvent.selectOptions(g.getByLabelText('Para'), 'Bruno')
    await userEvent.click(g.getByRole('button', { name: 'Reatribuir' }))
    expect(screen.getByText('Escolhe pessoas diferentes.')).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Para'), 'Camila')
    await userEvent.click(screen.getByRole('button', { name: 'Reatribuir' }))
    expect(await screen.findByText(/Tarefas por fazer passadas de Bruno para Camila/)).toBeInTheDocument()
    expect(pedidos.find((p) => p.caminho === '/actions/tarefas.reatribuir')!.corpo).toEqual({ params: { de: 'Bruno', para: 'Camila' }, confirmado: true })
  })

  test('não incomodar: a janela tem de ter início e fim', async () => {
    const { pedidos } = abrirConfig({ 'POST /actions/tarefas.preferencias': () => OK })
    await screen.findByLabelText('Início')
    await userEvent.clear(screen.getByLabelText('Fim'))
    await userEvent.click(screen.getAllByRole('button', { name: 'Guardar' })[0])
    expect(screen.getByText(/Indica o início e o fim/)).toBeInTheDocument()
    await userEvent.clear(screen.getByLabelText('Início'))
    await userEvent.click(screen.getAllByRole('button', { name: 'Guardar' })[0])
    expect(await screen.findByText('Preferências guardadas.')).toBeInTheDocument()
    expect(corpo(pedidos, '/actions/tarefas.preferencias')).toEqual({ params: { naoIncomodarInicio: '', naoIncomodarFim: '' } })
  })

  test('atualizar tarefas agora usa o servidor das tarefas; se falhar, explica', async () => {
    let falha = false
    abrirConfig({ 'POST /actions/tarefas.gerar': () => (falha ? [503, { erro: { codigo: 'modulo_indisponivel', mensagem: 'x' } }] : [200, { resultado: { criadas: 4 } }]) })
    await userEvent.click(await screen.findByRole('button', { name: 'Atualizar tarefas agora' }))
    expect(await screen.findByText('Tarefas atualizadas (4 novas).')).toBeInTheDocument()
    falha = true
    await userEvent.click(screen.getByRole('button', { name: 'Atualizar tarefas agora' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('não está disponível de momento')
  })

  test('exportar histórico gera o ficheiro CSV', async () => {
    const criar = vi.fn(() => 'blob:x'); const revogar = vi.fn()
    Object.assign(URL, { createObjectURL: criar, revokeObjectURL: revogar })
    const clique = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    abrirConfig({ 'GET /tasks/history': () => [200, { linhas: [{ tarefa: 'Lavar carro', categoria: 'Casa', data: '2026-09-29', pessoa: 'Bruno', estado: 'Feita', dataConclusao: '2026-09-29 10:00' }] }] })
    await userEvent.click(await screen.findByRole('button', { name: 'Exportar histórico (CSV)' }))
    expect(await screen.findByText('Histórico exportado.')).toBeInTheDocument()
    expect(criar).toHaveBeenCalledOnce(); expect(clique).toHaveBeenCalledOnce(); expect(revogar).toHaveBeenCalledWith('blob:x')
    clique.mockRestore()
  })

  test('histórico vazio não exporta', async () => {
    const criar = vi.fn(); Object.assign(URL, { createObjectURL: criar, revokeObjectURL: vi.fn() })
    abrirConfig({ 'GET /tasks/history': () => [200, { linhas: [] }] })
    await userEvent.click(await screen.findByRole('button', { name: 'Exportar histórico (CSV)' }))
    expect(await screen.findByText('Sem histórico para exportar.')).toBeInTheDocument()
    expect(criar).not.toHaveBeenCalled()
  })

  test('painel de administração só para administradores, com confirmação', async () => {
    const { pedidos } = abrirConfig({ 'POST /actions/tarefas.admin': () => OK }, { ...DEF, souAdmin: true, admin: ADMIN })
    const adm = within(await screen.findByRole('region', { name: 'Administração' }))
    const admins = within(adm.getByRole('group', { name: 'Administradores' }))
    expect(admins.getByRole('checkbox', { name: /Bruno/ })).toBeDisabled()                          // administrador fixo
    expect(admins.getByRole('checkbox', { name: /Bruno/ })).toBeChecked()
    await userEvent.click(admins.getByRole('checkbox', { name: /Camila/ }))
    await userEvent.click(adm.getByRole('button', { name: 'Guardar administração' }))
    expect(pedidos.filter((p) => p.metodo === 'POST')).toEqual([])                                 // ainda só pediu confirmação
    await userEvent.click(adm.getByRole('button', { name: 'Confirmar' }))
    expect(await screen.findByText(/Guardado\. Os avisos agendados/)).toBeInTheDocument()
    expect(pedidos.find((p) => p.caminho === '/actions/tarefas.admin')!.corpo).toEqual({ params: { admins: ['c@x.pt'], notificacoes: { piscina: ['Bruno'] } }, confirmado: true })
  })
})

describe('Hoje: tarefa rápida e dia completo', () => {
  test('cria uma tarefa pontual para hoje', async () => {
    const { pedidos } = abrir('hoje', { 'POST /actions/tarefas.criar': () => OK })
    await userEvent.click(await screen.findByRole('button', { name: 'Adicionar tarefa a hoje' }))
    await userEvent.type(screen.getByLabelText('Nome'), 'Marcar dentista')
    await userEvent.selectOptions(screen.getByLabelText('Pessoa'), 'Camila')
    await userEvent.click(screen.getByRole('button', { name: 'Adicionar' }))
    expect(await screen.findByText('Tarefa adicionada a hoje.')).toBeInTheDocument()
    const c = (corpo(pedidos, '/actions/tarefas.criar') as { params: Record<string, unknown> }).params
    expect(c).toMatchObject({ nome: 'Marcar dentista', categoria: 'Casa', recorrencia: 'Pontual', data: '2026-09-30', pessoa: 'Camila' })
    expect(String(c.cid).length).toBeGreaterThanOrEqual(8)
  })

  test('dia completo mostra a confirmação discreta', async () => {
    abrir('hoje', { 'GET /tasks': () => [200, { ...PRINCIPAL, feitas: [inst('I4', 'Fazer camas', '2026-09-30', { estado: 'Feita', dataConclusao: '2026-09-30 07:15' })] }] })
    expect(await screen.findByText('Tudo feito por hoje')).toBeInTheDocument()
  })
})
