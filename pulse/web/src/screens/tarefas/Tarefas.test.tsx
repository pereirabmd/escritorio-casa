import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App } from '../../App'
import type { InstanciaTarefa } from '../../api/types'
import { guardarFiltro, passaFiltro, quando, urlGoogleCalendar } from '../../lib/tarefas'
import { servidorFalso, UTILIZADOR, type Rotas } from '../../test/api-mock'

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '')
const OK: [number, unknown] = [200, { resultado: {} }]

const inst = (id: string, nome: string, extra: Partial<InstanciaTarefa> = {}): InstanciaTarefa => ({ id, tarefaId: 'T1', nome, categoria: 'Limpeza', prioridade: 'Media', hora: '09:00', pessoa: 'Bruno', estado: 'Pendente', data: '2026-09-30', dataConclusao: '', ...extra })
const T = (id: string, nome: string, extra = {}) => ({ id, nome, categoria: 'Limpeza', recorrencia: 'Semanal', diasSemana: 'Seg,Qua', diaMes: null, horaNotificacao: '09:00', pessoaPadrao: 'Bruno', ativa: true,
  prioridade: 'Media', rotacaoPessoas: '', dependeDe: '', resumo: 'Seg,Qua', hora: '09:00', ...extra })

const TAREFAS = {
  data: '2026-09-30', pessoa: 'Bruno', pessoas: ['Bruno', 'Camila'], categorias: ['Casa', 'Limpeza'], horaPadrao: '08:00',
  hoje: [inst('I1', 'Limpar WC'), inst('I2', 'Regar plantas', { pessoa: 'Camila', hora: '' }), inst('I3', 'Passar a ferro', { estado: 'Saltada' })],
  feitas: [inst('I4', 'Fazer camas', { estado: 'Feita', dataConclusao: '2026-09-30 07:15' })],
  atrasadas: [inst('I5', 'Lavar carro', { estado: 'Atrasada', data: '2026-09-28' })],
  amanha: [inst('I6', 'Levar o lixo', { data: '2026-10-01' })],
  tarefas: [T('T1', 'Limpar WC'), T('T2', 'Regar plantas', { recorrencia: 'Diaria', diasSemana: '', resumo: 'Todos os dias', pessoaPadrao: 'Camila', prioridade: 'Alta' }),
    T('T3', 'Pagar condomínio', { recorrencia: 'Mensal', diaMes: 5, diasSemana: '', resumo: 'Dia 5 de cada mês' })],
}

function abrir(extra: Rotas = {}, dados: unknown = TAREFAS, caminho = '/tarefas') {
  window.history.pushState({}, '', `${BASE}${caminho}`)
  const s = servidorFalso({ 'GET /auth/me': () => [200, { utilizador: UTILIZADOR }], 'GET /tasks': () => [200, dados], ...extra })
  render(<App />)
  return s
}
const corpo = (p: { caminho: string; corpo: unknown }[], c: string) => p.find((x) => x.caminho === c)!.corpo

beforeEach(() => localStorage.clear())
afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })

describe('lib', () => {
  test('quando: hoje, ontem e outras datas', () => {
    expect(quando('2026-09-30 08:00', '2026-09-30')).toBe('hoje às 08:00')
    expect(quando('2026-09-29 21:10', '2026-09-30')).toBe('ontem às 21:10')
    expect(quando('2026-09-01 07:00', '2026-09-30')).toBe('01/09 às 07:00')
    expect(quando('lixo', '2026-09-30')).toBe('lixo')
  })
  test('filtro por pessoa', () => {
    const i = inst('I1', 'x')
    expect([passaFiltro(i, 'todas', null), passaFiltro(i, 'minhas', 'Bruno'), passaFiltro(i, 'minhas', 'Camila'), passaFiltro(i, 'Bruno', null), passaFiltro(i, 'Camila', null)]).toEqual([true, true, false, true, false])
  })
  test('ligação ao Google Calendar com hora da tarefa ou a padrão', () => {
    const u = urlGoogleCalendar(inst('I1', 'Limpar WC & co'), '08:00')
    expect(u).toContain('text=Limpar%20WC%20%26%20co')
    expect(u).toContain('dates=20260930T090000/20260930T093000')
    expect(urlGoogleCalendar(inst('I1', 'x', { hora: '' }), '08:00')).toContain('20260930T080000/20260930T083000')
  })
})

describe('Hoje', () => {
  test('três secções, progresso e estados das linhas', async () => {
    abrir()
    expect(await screen.findByText('1 de 4 concluídas')).toBeInTheDocument()
    const hoje = within(screen.getByRole('region', { name: 'Hoje' }))
    expect(hoje.getByText(/Concluída por Bruno · hoje às 07:15/)).toBeInTheDocument()
    expect(hoje.getByText(/Saltada/)).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Atrasadas' })).getByText('Lavar carro')).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Atrasadas' })).getByText('Atrasada')).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Amanhã' })).getByText('Levar o lixo')).toBeInTheDocument()
  })

  test('filtro «Minhas» e por pessoa, e fica guardado', async () => {
    abrir()
    await userEvent.click(await screen.findByRole('button', { name: 'Camila' }))
    expect(screen.queryByText('Limpar WC')).not.toBeInTheDocument()
    expect(screen.getByText('Regar plantas')).toBeInTheDocument()
    expect(localStorage.getItem('pulse.tarefas.filtro')).toBe('Camila')
    await userEvent.click(screen.getByRole('button', { name: 'Minhas' }))
    expect(screen.getByText('Limpar WC')).toBeInTheDocument()
    expect(screen.queryByText('Regar plantas')).not.toBeInTheDocument()
  })

  test('o filtro guardado é reposto ao abrir (e um filtro inválido volta a «Todas»)', async () => {
    guardarFiltro('Camila')
    abrir()
    expect(await screen.findByRole('button', { name: 'Camila' })).toHaveAttribute('aria-pressed', 'true')
  })

  test('um filtro guardado que já não existe volta a «Todas»', async () => {
    guardarFiltro('Fantasma')
    abrir()
    expect(await screen.findByRole('button', { name: 'Todas' })).toHaveAttribute('aria-pressed', 'true')
  })

  test('concluir mostra quantas atrasadas fechou e o desfazer reabre todas', async () => {
    const { pedidos } = abrir({ 'POST /actions/tarefas.concluir': () => [200, { resultado: { tambem: ['I8', 'I9'] } }], 'POST /actions/tarefas.reabrir': () => OK })
    await userEvent.click(await screen.findByRole('button', { name: 'Marcar como concluída: Lavar carro' }))
    expect(await screen.findByText('Tarefa concluída · +2 atrasadas anteriores.')).toBeInTheDocument()
    expect(corpo(pedidos, '/actions/tarefas.concluir')).toEqual({ params: { instancia: 'I5' } })
    await userEvent.click(screen.getByRole('button', { name: 'Desfazer' }))
    await waitFor(() => expect(pedidos.some((p) => p.caminho === '/actions/tarefas.reabrir')).toBe(true))
    expect(corpo(pedidos, '/actions/tarefas.reabrir')).toEqual({ params: { instancia: 'I5', tambem: ['I8', 'I9'] } })
  })

  test('clicar numa tarefa feita reabre-a', async () => {
    const { pedidos } = abrir({ 'POST /actions/tarefas.reabrir': () => OK })
    await userEvent.click(await screen.findByRole('button', { name: 'Marcar como não concluída: Fazer camas' }))
    expect(await screen.findByText('Tarefa reaberta.')).toBeInTheDocument()
    expect(corpo(pedidos, '/actions/tarefas.reabrir')).toEqual({ params: { instancia: 'I4' } })
  })

  test('saltar, com desfazer', async () => {
    const { pedidos } = abrir({ 'POST /actions/tarefas.saltar': () => OK, 'POST /actions/tarefas.reabrir': () => OK })
    await userEvent.click(await screen.findByRole('button', { name: 'Saltar Limpar WC' }))
    expect(await screen.findByText('Tarefa saltada.')).toBeInTheDocument()
    expect(corpo(pedidos, '/actions/tarefas.saltar')).toEqual({ params: { instancia: 'I1' } })
    await userEvent.click(screen.getByRole('button', { name: 'Desfazer' }))
    await waitFor(() => expect(pedidos.some((p) => p.caminho === '/actions/tarefas.reabrir')).toBe(true))
  })

  test('adiar para amanhã ou para uma data; passado não aceite; conflito explicado', async () => {
    let conflito = false
    const { pedidos } = abrir({ 'POST /actions/tarefas.adiar': () => (conflito ? [409, { erro: { codigo: 'conflito', mensagem: 'x' } }] : OK) })
    await userEvent.click(await screen.findByRole('button', { name: 'Adiar Limpar WC' }))
    const g = within(screen.getByRole('group', { name: 'Adiar Limpar WC' }))
    const enviar = g.getByRole('button', { name: 'Adiar para essa data' })
    await userEvent.type(g.getByLabelText('Escolher data'), '2026-09-01')
    expect(enviar).toBeDisabled()
    await userEvent.clear(g.getByLabelText('Escolher data')); await userEvent.type(g.getByLabelText('Escolher data'), '2026-10-15')
    await userEvent.click(enviar)
    expect(await screen.findByText('Tarefa adiada para 15/10/2026.')).toBeInTheDocument()
    expect(corpo(pedidos, '/actions/tarefas.adiar')).toEqual({ params: { instancia: 'I1', data: '2026-10-15' } })
    conflito = true
    await userEvent.click(screen.getByRole('button', { name: 'Adiar Limpar WC' }))
    await userEvent.click(within(screen.getByRole('group', { name: 'Adiar Limpar WC' })).getByRole('button', { name: 'Amanhã' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Já existe esta tarefa nesse dia')
  })

  test('cada tarefa por fazer tem a ligação ao Google Calendar', async () => {
    abrir()
    const a = await screen.findByRole('link', { name: 'Adicionar Limpar WC ao Google Calendar' })
    expect(a).toHaveAttribute('href', expect.stringContaining('calendar.google.com'))
    expect(a).toHaveAttribute('rel', 'noopener noreferrer')
    expect(screen.queryByRole('link', { name: 'Adicionar Fazer camas ao Google Calendar' })).not.toBeInTheDocument()
  })

  test('estados vazios', async () => {
    abrir({}, { ...TAREFAS, hoje: [], feitas: [], atrasadas: [], amanha: [] })
    expect(await screen.findByText('Sem tarefas para hoje.')).toBeInTheDocument()
    expect(screen.getByText('Nenhuma tarefa atrasada.')).toBeInTheDocument()
    expect(screen.getByText('Nada agendado para amanhã.')).toBeInTheDocument()
  })
})

describe('Tarefas (catálogo)', () => {
  const abrirCat = (extra: Rotas = {}, dados: unknown = TAREFAS) => abrir(extra, dados, '/tarefas?aba=tarefas')

  test('lista com resumo da repetição e pesquisa', async () => {
    abrirCat()
    const lista = within(await screen.findByRole('region', { name: 'Lista de tarefas' }))
    expect(lista.getByText(/Limpeza · Seg,Qua · 09:00 · Bruno/)).toBeInTheDocument()
    expect(lista.getByText(/Todos os dias/)).toBeInTheDocument()
    expect(lista.getByText('Prioridade alta')).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Pesquisar tarefas'), 'condom')
    expect(lista.getAllByRole('listitem').length).toBe(1)
    await userEvent.clear(screen.getByLabelText('Pesquisar tarefas')); await userEvent.type(screen.getByLabelText('Pesquisar tarefas'), 'zzz')
    expect(await screen.findByText('Nenhuma tarefa corresponde à pesquisa.')).toBeInTheDocument()
  })

  test('nova tarefa semanal com dias, cid, e mais opções', async () => {
    const { pedidos } = abrirCat({ 'POST /actions/tarefas.criar': () => OK })
    await userEvent.click(await screen.findByRole('button', { name: 'Nova tarefa' }))
    await userEvent.type(screen.getByLabelText('Nome'), 'Limpar filtros')
    await userEvent.selectOptions(screen.getByLabelText('Repetição'), 'Semanal')
    const dias = screen.getByRole('group', { name: 'Dias da semana' })
    await userEvent.click(within(dias).getByRole('button', { name: 'Segunda' })); await userEvent.click(within(dias).getByRole('button', { name: 'Quinta' }))
    await userEvent.click(screen.getByRole('button', { name: '+ Mais opções' }))
    await userEvent.click(within(screen.getByRole('group', { name: 'Prioridade' })).getByRole('button', { name: 'Alta' }))
    await userEvent.click(within(screen.getByRole('group', { name: 'Rotação entre pessoas' })).getByRole('button', { name: 'Camila' }))
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByText('Tarefa criada.')).toBeInTheDocument()
    const p = (corpo(pedidos, '/actions/tarefas.criar') as { params: Record<string, unknown> }).params
    expect(p).toMatchObject({ nome: 'Limpar filtros', categoria: 'Casa', recorrencia: 'Semanal', dias: ['Seg', 'Qui'], hora: '08:00', pessoa: 'Bruno', prioridade: 'Alta', rotacao: ['Camila'], dependeDe: '' })
    expect(p.cid).toMatch(/^[A-Za-z0-9-]{8,64}$/)
    expect(p).not.toHaveProperty('data'); expect(p).not.toHaveProperty('diaMes')
  })

  test('validações no cliente antes de enviar', async () => {
    const { pedidos } = abrirCat()
    await userEvent.click(await screen.findByRole('button', { name: 'Nova tarefa' }))
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Preenche o nome e a categoria.')
    await userEvent.type(screen.getByLabelText('Nome'), 'X')
    await userEvent.selectOptions(screen.getByLabelText('Repetição'), 'Dias especificos')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Escolhe pelo menos um dia da semana.')
    await userEvent.selectOptions(screen.getByLabelText('Repetição'), 'Pontual')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Escolhe a data.')
    await userEvent.selectOptions(screen.getByLabelText('Repetição'), 'Trimestral')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Escolhe a data de início.')
    await userEvent.selectOptions(screen.getByLabelText('Repetição'), 'Mensal')
    await userEvent.clear(screen.getByLabelText('Dia do mês')); await userEvent.type(screen.getByLabelText('Dia do mês'), '40')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Dia do mês inválido.')
    expect(pedidos.filter((p) => p.metodo !== 'GET')).toEqual([])
  })

  test('tarefa pontual e mensal enviam a data / o dia certos', async () => {
    const { pedidos } = abrirCat({ 'POST /actions/tarefas.criar': () => OK })
    await userEvent.click(await screen.findByRole('button', { name: 'Nova tarefa' }))
    await userEvent.type(screen.getByLabelText('Nome'), 'Dentista')
    await userEvent.selectOptions(screen.getByLabelText('Repetição'), 'Pontual')
    await userEvent.type(screen.getByLabelText('Data'), '2026-11-05')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    await waitFor(() => expect(pedidos.some((p) => p.caminho === '/actions/tarefas.criar')).toBe(true))
    expect((corpo(pedidos, '/actions/tarefas.criar') as { params: Record<string, unknown> }).params).toMatchObject({ recorrencia: 'Pontual', data: '2026-11-05' })
  })

  test('editar traz os valores e guarda com o id; duplicar cria uma cópia', async () => {
    const { pedidos } = abrirCat({ 'POST /actions/tarefas.editar': () => OK, 'POST /actions/tarefas.criar': () => OK })
    await userEvent.click(await screen.findByRole('button', { name: 'Editar Limpar WC' }))
    expect(screen.getByLabelText('Nome')).toHaveValue('Limpar WC')
    expect(screen.getByLabelText('Repetição')).toHaveValue('Semanal')
    expect(within(screen.getByRole('group', { name: 'Dias da semana' })).getByRole('button', { name: 'Segunda' })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.clear(screen.getByLabelText('Nome')); await userEvent.type(screen.getByLabelText('Nome'), 'Limpar casa de banho')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByText('Tarefa atualizada.')).toBeInTheDocument()
    expect((corpo(pedidos, '/actions/tarefas.editar') as { params: Record<string, unknown> }).params).toMatchObject({ tarefa: 'T1', nome: 'Limpar casa de banho', dias: ['Seg', 'Qua'] })
    await userEvent.click(screen.getByRole('button', { name: 'Duplicar Regar plantas' }))
    expect(screen.getByRole('heading', { name: 'Duplicar tarefa' })).toBeInTheDocument()
    expect(screen.getByLabelText('Nome')).toHaveValue('Regar plantas (cópia)')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    await waitFor(() => expect(pedidos.some((p) => p.caminho === '/actions/tarefas.criar')).toBe(true))
    expect((corpo(pedidos, '/actions/tarefas.criar') as { params: Record<string, unknown> }).params).toMatchObject({ nome: 'Regar plantas (cópia)', recorrencia: 'Diaria', prioridade: 'Alta' })
  })

  test('apagar pergunta antes, e confirma com o servidor', async () => {
    const { pedidos } = abrirCat({ 'POST /actions/tarefas.apagar': () => OK })
    await userEvent.click(await screen.findByRole('button', { name: 'Apagar Pagar condomínio' }))
    expect(pedidos.some((p) => p.caminho === '/actions/tarefas.apagar')).toBe(false)
    expect(screen.getByText(/O histórico mantém-se; as pendentes desaparecem/)).toBeInTheDocument()
    await userEvent.click(within(screen.getByRole('group', { name: 'Apagar Pagar condomínio' })).getByRole('button', { name: 'Apagar' }))
    expect(await screen.findByText('Tarefa apagada.')).toBeInTheDocument()
    expect(corpo(pedidos, '/actions/tarefas.apagar')).toEqual({ params: { tarefa: 'T3' }, confirmado: true })
  })

  test('cancelar não escreve nada', async () => {
    const { pedidos } = abrirCat()
    await userEvent.click(await screen.findByRole('button', { name: 'Apagar Pagar condomínio' }))
    await userEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(pedidos.filter((p) => p.metodo !== 'GET')).toEqual([])
  })

  test('catálogo vazio', async () => {
    abrirCat({}, { ...TAREFAS, tarefas: [] })
    expect(await screen.findByText(/Ainda não há tarefas/)).toBeInTheDocument()
  })
})

describe('estados', () => {
  test('erro a carregar com «Tentar de novo»', async () => {
    let falha = true
    abrir({ 'GET /tasks': () => (falha ? [503, { erro: { codigo: 'modulo_indisponivel', mensagem: 'x' } }] : [200, TAREFAS]) })
    expect(await screen.findByRole('alert')).toHaveTextContent('não está disponível de momento')
    falha = false
    await userEvent.click(screen.getByRole('button', { name: 'Tentar de novo' }))
    expect(await screen.findByText('Limpar WC')).toBeInTheDocument()
  })

  test('Mais leva às Tarefas e as seis secções estão à vista', async () => {
    window.history.pushState({}, '', `${BASE}/mais`)
    servidorFalso({ 'GET /auth/me': () => [200, { utilizador: UTILIZADOR }], 'GET /tasks': () => [200, TAREFAS] })
    render(<App />)
    await userEvent.click(await screen.findByRole('link', { name: /Tarefas/ }))
    expect(await screen.findByRole('heading', { name: 'Tarefas' })).toBeInTheDocument()
    const abas = within(await screen.findByRole('tablist', { name: 'Secções das Tarefas' }))
    expect(abas.getAllByRole('tab').map((t) => t.textContent)).toEqual(['Hoje', 'Calendário', 'Tarefas', 'Horário', 'Piscina', 'Config'])
  })
})
