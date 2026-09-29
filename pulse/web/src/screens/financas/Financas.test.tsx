import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App } from '../../App'
import { lerValor, somarMeses, tituloMesFin } from '../../lib/financas'
import { servidorFalso, UTILIZADOR, type Rotas } from '../../test/api-mock'

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '')
const OK: [number, unknown] = [200, { resultado: {} }]
const CATS = [{ id: 1, nome: 'Casa', cor: '#111111' }, { id: 2, nome: 'Rendimentos', cor: '#222222' }]
const L = (id: number, tipo: 'despesa' | 'rendimento', descricao: string, valor: number, venc: string, estado: string, pago: string | null = null) =>
  ({ id, tipo, descricao, valor, categoria_id: tipo === 'despesa' ? 1 : 2, categoria: tipo === 'despesa' ? 'Casa' : 'Rendimentos', data_vencimento: venc, data_pagamento: pago, recorrente: false, mes_referencia: venc.slice(0, 7), estado })
const VENCIDA = L(4, 'despesa', 'Água', 50, '2026-09-10', 'vencido')
const DADOS = {
  mes: '2026-09', hoje: '2026-09-15', categorias: CATS,
  totaisMes: { rendimento: 2000, despesas: 450.5, porPagar: 350 },
  lancamentos: [L(3, 'despesa', 'Internet', 100.5, '2026-09-05', 'pago', '2026-09-05'), VENCIDA, L(2, 'despesa', 'Luz', 300, '2026-09-20', 'pendente'), L(1, 'rendimento', 'Salário', 2000, '2026-09-26', 'pendente')],
  atrasadas: { total: 50, itens: [VENCIDA] },
  janela: { modo: 'mes', de: '2026-09-01', ate: '2026-09-30' },
  resumo: { rendimento: 2000, porPagar: 350, saldo: 1650, emAtraso: 0, saldoComAtraso: 1650, porCategoria: [{ categoriaId: 1, nome: 'Casa', cor: '#111111', total: 450.5 }] },
}

function abrir(aba: string, extra: Rotas = {}, dados: unknown = DADOS) {
  window.history.pushState({}, '', `${BASE}/financas?aba=${aba}`)
  const s = servidorFalso({
    'GET /auth/me': () => [200, { utilizador: UTILIZADOR }], 'GET /finance?janela=mes': () => [200, dados],
    'POST /actions/financas.preparar_mes': () => [200, { resultado: { criados: 0 } }], ...extra,
  })
  render(<App />)
  return s
}
const corpo = (p: { caminho: string; corpo: unknown }[], c: string) => p.find((x) => x.caminho === c)?.corpo

beforeEach(() => localStorage.clear())
afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })

test('lib: meses, valores e títulos', () => {
  expect(somarMeses('2026-01', -1)).toBe('2025-12')
  expect(somarMeses('2026-11', 3)).toBe('2027-02')
  expect(tituloMesFin('2026-09')).toBe('setembro de 2026')
  expect(['12,5', '12.5', '1 234,50', '0', '', 'abc', '-3'].map(lerValor)).toEqual([12.5, 12.5, 1234.5, null, null, null, null])
})

test('Mais leva às Finanças e o mês é preparado ao abrir', async () => {
  window.history.pushState({}, '', `${BASE}/mais`)
  const s = servidorFalso({ 'GET /auth/me': () => [200, { utilizador: UTILIZADOR }], 'GET /finance?janela=mes': () => [200, DADOS], 'POST /actions/financas.preparar_mes': () => [200, { resultado: { criados: 0 } }] })
  render(<App />)
  await userEvent.click(await screen.findByRole('link', { name: /Finanças/ }))
  expect(await screen.findByRole('heading', { name: 'Finanças' })).toBeInTheDocument()
  await waitFor(() => expect(corpo(s.pedidos, '/actions/financas.preparar_mes')).toEqual({ params: { mes: '2026-09' } }))
})

test('preparar um mês que criou lançamentos volta a carregar', async () => {
  let n = 0
  const s = abrir('resumo', { 'GET /finance?janela=mes': () => { n++; return [200, DADOS] }, 'POST /actions/financas.preparar_mes': () => [200, { resultado: { criados: 3 } }] })
  await screen.findByText('Ativo − passivo')
  await waitFor(() => expect(n).toBe(2))
  expect(s.pedidos.filter((p) => p.caminho === '/actions/financas.preparar_mes')).toHaveLength(1)
})

describe('Resumo', () => {
  test('saldo, aviso persistente de vencidas e categorias', async () => {
    abrir('resumo')
    expect(await screen.findByText('Ativo − passivo')).toBeInTheDocument()
    expect(screen.getAllByText(/1 despesa vencida e por pagar/).length).toBeGreaterThan(0)
    expect(screen.getByText(/Saldo do período/)).toBeInTheDocument()
    const cat = screen.getByRole('region', { name: 'Despesas por categoria' })
    expect(within(cat).getByText('Casa')).toBeInTheDocument()
  })
  test('trocar para 30 dias pede a janela ao servidor', async () => {
    const pedidos: string[] = []
    abrir('resumo', { 'GET /finance?janela=30d': () => { pedidos.push('30d'); return [200, { ...DADOS, janela: { modo: '30d', de: '2026-09-15', ate: '2026-10-14' } }] } })
    await userEvent.click(await screen.findByRole('button', { name: 'Próximos 30 dias' }))
    await waitFor(() => expect(pedidos).toEqual(['30d']))
    expect(await screen.findByText(/15\/09\/2026 – 14\/10\/2026/)).toBeInTheDocument()
  })
  test('com atraso anterior mostra o saldo com as vencidas', async () => {
    abrir('resumo', {}, { ...DADOS, resumo: { ...DADOS.resumo, emAtraso: 200, saldoComAtraso: 1450 } })
    expect(await screen.findByText(/Com as vencidas de antes do período/)).toBeInTheDocument()
  })
})

describe('Lançamentos', () => {
  test('lista por pagar e pagos, totais e o mês', async () => {
    abrir('lancamentos')
    expect(await screen.findByText('setembro de 2026')).toBeInTheDocument()
    const por = screen.getByRole('region', { name: 'Por pagar ou receber' }), pagos = screen.getByRole('region', { name: 'Pagos ou recebidos' })
    expect(within(por).getByText('Luz')).toBeInTheDocument()
    expect(within(por).getByText('Vencido')).toBeInTheDocument()
    expect(within(pagos).getByText('Internet')).toBeInTheDocument()
  })
  test('marcar como paga executa a ação e oferece desfazer', async () => {
    const s = abrir('lancamentos', { 'POST /actions/financas.pagar': () => OK, 'POST /actions/financas.anular_pagamento': () => OK })
    await userEvent.click(await screen.findByRole('button', { name: 'Marcar como paga: Luz' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/financas.pagar')).toEqual({ params: { lancamento: 2 } }))
    await userEvent.click(await screen.findByRole('button', { name: /Desfazer/ }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/financas.anular_pagamento')).toEqual({ params: { lancamento: 2 } }))
  })
  test('anular o pagamento de uma conta paga', async () => {
    const s = abrir('lancamentos', { 'POST /actions/financas.anular_pagamento': () => OK })
    await userEvent.click(await screen.findByRole('button', { name: 'Anular pagamento: Internet' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/financas.anular_pagamento')).toEqual({ params: { lancamento: 3 } }))
  })
  test('criar um lançamento envia o formato certo e um cid', async () => {
    const s = abrir('lancamentos', { 'POST /actions/financas.criar': () => OK })
    await userEvent.click(await screen.findByRole('button', { name: 'Novo lançamento' }))
    await userEvent.type(screen.getByLabelText('Descrição'), 'Seguro')
    await userEvent.type(screen.getByLabelText('Valor (€)'), '45,5')
    await userEvent.clear(screen.getByLabelText('Vencimento')); await userEvent.type(screen.getByLabelText('Vencimento'), '2026-09-28')
    await userEvent.click(screen.getByRole('button', { name: 'Adicionar' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/financas.criar')).toBeTruthy())
    const { params } = corpo(s.pedidos, '/actions/financas.criar') as { params: Record<string, unknown> }
    expect(params).toMatchObject({ tipo: 'despesa', descricao: 'Seguro', valor: 45.5, categoriaId: 1, dataVencimento: '2026-09-28', recorrente: false })
    expect(String(params.cid).length).toBeGreaterThanOrEqual(8)
  })
  test('valor inválido não deixa adicionar', async () => {
    abrir('lancamentos')
    await userEvent.click(await screen.findByRole('button', { name: 'Novo lançamento' }))
    await userEvent.type(screen.getByLabelText('Descrição'), 'X'); await userEvent.type(screen.getByLabelText('Valor (€)'), '0')
    expect(screen.getByRole('button', { name: 'Adicionar' })).toBeDisabled()
  })
  test('apagar pede confirmação e o desfazer volta a criar', async () => {
    const s = abrir('lancamentos', { 'POST /actions/financas.apagar': () => OK, 'POST /actions/financas.criar': () => OK })
    await userEvent.click(await screen.findByRole('button', { name: 'Apagar Luz' }))
    const grupo = screen.getByRole('group', { name: 'Apagar Luz' })
    await userEvent.click(within(grupo).getByRole('button', { name: 'Apagar' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/financas.apagar')).toEqual({ params: { lancamento: 2 }, confirmado: true }))
    await userEvent.click(await screen.findByRole('button', { name: /Desfazer/ }))
    await waitFor(() => expect((corpo(s.pedidos, '/actions/financas.criar') as { params: unknown }).params).toMatchObject({ descricao: 'Luz', valor: 300, dataVencimento: '2026-09-20', categoriaId: 1 }))
  })
  test('editar só envia o que mudou de mês de referência quando o vencimento muda de mês', async () => {
    const s = abrir('lancamentos', { 'POST /actions/financas.editar': () => OK })
    await userEvent.click(await screen.findByRole('button', { name: 'Editar Luz' }))
    const form = screen.getByRole('form', { name: 'Editar Luz' })
    await userEvent.clear(within(form).getByLabelText('Valor (€)')); await userEvent.type(within(form).getByLabelText('Valor (€)'), '310')
    await userEvent.click(within(form).getByRole('button', { name: 'Guardar' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/financas.editar')).toBeTruthy())
    const p = (corpo(s.pedidos, '/actions/financas.editar') as { params: Record<string, unknown> }).params
    expect(p).toMatchObject({ lancamento: 2, valor: 310, dataVencimento: '2026-09-20' })
    expect(p).not.toHaveProperty('mesReferencia')
  })
  test('navegar para o mês seguinte pede esse mês', async () => {
    const pedidos: string[] = []
    abrir('lancamentos', { 'GET /finance?mes=2026-10&janela=mes': () => { pedidos.push('out'); return [200, { ...DADOS, mes: '2026-10', lancamentos: [] }] } })
    await userEvent.click(await screen.findByRole('button', { name: 'Mês seguinte' }))
    await waitFor(() => expect(pedidos).toEqual(['out']))
    expect(await screen.findByText('Sem lançamentos em outubro de 2026.')).toBeInTheDocument()
  })
})

describe('Relatórios', () => {
  test('pede os 6 meses que terminam no mês à vista', async () => {
    const REL = { de: '2026-04', ate: '2026-09', meses: [{ mes: '2026-08', rendimento: 0, despesas: 40, saldo: -40 }, { mes: '2026-09', rendimento: 1500, despesas: 50.5, saldo: 1449.5 }],
      categorias: [{ categoriaId: 1, nome: 'Casa', cor: '#111111', total: 90.5, meses: {} }], totais: { rendimento: 1500, despesas: 90.5 } }
    const s = abrir('relatorios', { 'GET /finance/reports?de=2026-04&ate=2026-09': () => [200, REL] })
    expect(await screen.findByText('Rendimento e despesas por mês')).toBeInTheDocument()
    expect(s.pedidos.some((p) => p.caminho === '/finance/reports?de=2026-04&ate=2026-09')).toBe(true)
    expect(screen.getByRole('region', { name: 'Despesas por categoria' })).toHaveTextContent('Casa')
  })
})

describe('Categorias', () => {
  test('criar, editar e apagar com confirmação', async () => {
    const s = abrir('categorias', { 'POST /actions/financas.categoria_criar': () => OK, 'POST /actions/financas.categoria_editar': () => OK, 'POST /actions/financas.categoria_eliminar': () => OK })
    await userEvent.type(await screen.findByLabelText('Nome da categoria'), 'Ginásio')
    await userEvent.click(screen.getByRole('button', { name: 'Adicionar' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/financas.categoria_criar')).toEqual({ params: { nome: 'Ginásio' } }))
    await userEvent.click(screen.getByRole('button', { name: 'Editar Casa' }))
    const f = screen.getByRole('form', { name: 'Editar Casa' })
    await userEvent.clear(within(f).getByLabelText('Nome')); await userEvent.type(within(f).getByLabelText('Nome'), 'Habitação')
    await userEvent.click(within(f).getByRole('button', { name: 'Guardar' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/financas.categoria_editar')).toEqual({ params: { categoria: 1, nome: 'Habitação' } }))
    await userEvent.click(await screen.findByRole('button', { name: 'Apagar Rendimentos' }))
    await userEvent.click(within(screen.getByRole('group', { name: 'Apagar Rendimentos' })).getByRole('button', { name: 'Apagar' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/financas.categoria_eliminar')).toEqual({ params: { categoria: 2 }, confirmado: true }))
  })
})

describe('Lembretes', () => {
  const LEM = { id: 5, titulo: 'IRS', nota: '', data: '2026-10-20', hora: '09:00', repeticao: 'mensal', ativo: true, ultimo_aviso: null }
  test('lista, pausa e agenda um novo', async () => {
    const s = abrir('lembretes', { 'GET /finance/reminders': () => [200, { lembretes: [LEM] }], 'POST /actions/financas.lembrete_editar': () => OK, 'POST /actions/financas.lembrete_criar': () => OK })
    expect(await screen.findByText(/20\/10\/2026 às 09:00 · todos os meses/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Pausar IRS' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/financas.lembrete_editar')).toEqual({ params: { lembrete: 5, ativo: false } }))
    await userEvent.type(screen.getByLabelText('Título'), 'Renda'); await userEvent.type(screen.getByLabelText('Data'), '2026-10-01')
    await userEvent.click(screen.getByRole('button', { name: 'Todos os meses' }))
    await userEvent.click(screen.getByRole('button', { name: 'Agendar' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/financas.lembrete_criar')).toEqual({ params: { titulo: 'Renda', nota: '', data: '2026-10-01', hora: '09:00', repeticao: 'mensal' } }))
  })
  test('sem lembretes mostra o estado vazio', async () => {
    abrir('lembretes', { 'GET /finance/reminders': () => [200, { lembretes: [] }] })
    expect(await screen.findByText('Sem lembretes agendados.')).toBeInTheDocument()
  })
})
