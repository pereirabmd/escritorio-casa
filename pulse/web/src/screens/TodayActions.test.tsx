import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App } from '../App'
import { HOJE, servidorFalso, UTILIZADOR, type Rotas } from '../test/api-mock'
import { lerPeso } from '../lib/useAcao'

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '')
const OK: [number, unknown] = [200, { resultado: {} }]

function abrir(extra: Rotas = {}, hoje: unknown = HOJE) {
  window.history.pushState({}, '', `${BASE}/hoje`)
  const s = servidorFalso({ 'GET /auth/me': () => [200, { utilizador: UTILIZADOR }], 'GET /dashboard/today': () => [200, hoje], ...extra })
  render(<App />)
  return s
}
const escritas = (p: { metodo: string }[]) => p.filter((x) => x.metodo !== 'GET')

afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })

describe('tarefas', () => {
  test('concluir chama a ação, atualiza o Hoje e oferece desfazer', async () => {
    let n = 0
    const { pedidos } = abrir({ 'POST /actions/tarefas.concluir': () => OK, 'POST /actions/tarefas.reabrir': () => OK, 'GET /dashboard/today': () => [200, n++ ? { ...HOJE, modulos: { ...HOJE.modulos, tarefas: { estado: 'ok', dados: { ...HOJE.modulos.tarefas.dados, hoje: HOJE.modulos.tarefas.dados.hoje.slice(1) } } } } : HOJE] })
    await userEvent.click(await screen.findByRole('button', { name: 'Concluir Limpar WC' }))
    await waitFor(() => expect(screen.queryByText('Limpar WC')).not.toBeInTheDocument())
    expect(pedidos.find((p) => p.caminho === '/actions/tarefas.concluir')!.corpo).toEqual({ params: { instancia: 'I1' } })
    expect(await screen.findByText('Tarefa concluída.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Desfazer' }))
    await waitFor(() => expect(pedidos.some((p) => p.caminho === '/actions/tarefas.reabrir')).toBe(true))
    expect(pedidos.find((p) => p.caminho === '/actions/tarefas.reabrir')!.corpo).toEqual({ params: { instancia: 'I1', tambem: [] } })
  })

  test('adiar para amanhã', async () => {
    const { pedidos } = abrir({ 'POST /actions/tarefas.adiar': () => OK })
    await userEvent.click(await screen.findByRole('button', { name: 'Adiar Limpar WC' }))
    await userEvent.click(within(screen.getByRole('group', { name: 'Adiar Limpar WC' })).getByRole('button', { name: 'Amanhã' }))
    await waitFor(() => expect(pedidos.some((p) => p.caminho === '/actions/tarefas.adiar')).toBe(true))
    expect(pedidos.find((p) => p.caminho === '/actions/tarefas.adiar')!.corpo).toEqual({ params: { instancia: 'I1' } })
    expect(await screen.findByText('Tarefa adiada para amanhã.')).toBeInTheDocument()
  })

  test('adiar para uma data escolhida (não aceita datas passadas)', async () => {
    const { pedidos } = abrir({ 'POST /actions/tarefas.adiar': () => OK })
    await userEvent.click(await screen.findByRole('button', { name: 'Adiar Limpar WC' }))
    const grupo = within(screen.getByRole('group', { name: 'Adiar Limpar WC' }))
    const enviar = grupo.getByRole('button', { name: 'Adiar para essa data' })
    expect(enviar).toBeDisabled()
    await userEvent.type(grupo.getByLabelText('Escolher data'), '2026-09-01')
    expect(enviar).toBeDisabled()                                   // antes de hoje (2026-09-30)
    await userEvent.clear(grupo.getByLabelText('Escolher data'))
    await userEvent.type(grupo.getByLabelText('Escolher data'), '2026-10-15')
    await userEvent.click(enviar)
    await waitFor(() => expect(pedidos.some((p) => p.caminho === '/actions/tarefas.adiar')).toBe(true))
    expect(pedidos.find((p) => p.caminho === '/actions/tarefas.adiar')!.corpo).toEqual({ params: { instancia: 'I1', data: '2026-10-15' } })
    expect(await screen.findByText('Tarefa adiada para 15/10/2026.')).toBeInTheDocument()
  })

  test('conflito ao adiar mostra a explicação em pt-PT e não muda nada no ecrã', async () => {
    abrir({ 'POST /actions/tarefas.adiar': () => [409, { erro: { codigo: 'conflito', mensagem: 'x' } }] })
    await userEvent.click(await screen.findByRole('button', { name: 'Adiar Limpar WC' }))
    await userEvent.click(within(screen.getByRole('group', { name: 'Adiar Limpar WC' })).getByRole('button', { name: 'Amanhã' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Já existe esta tarefa nesse dia. Conclui ou salta a de hoje.')
    expect(screen.getByText('Limpar WC')).toBeInTheDocument()
  })
})

describe('peso', () => {
  test('o campo vem pré-preenchido com o último peso e regista com cid', async () => {
    const hoje = { ...HOJE, modulos: { ...HOJE.modulos, peso: { estado: 'ok', dados: { ultimo: { quando: '2026-09-29 07:30:00', peso: 104.8 }, registadoHoje: false, sugestao: 104.8 } } } }
    const { pedidos } = abrir({ 'POST /actions/peso.registar': () => OK }, hoje)
    const campo = await screen.findByLabelText('Peso de hoje em quilogramas')
    expect(campo).toHaveValue('104,8')
    await userEvent.clear(campo)
    await userEvent.type(campo, '104,2')
    await userEvent.click(screen.getByRole('button', { name: 'Registar' }))
    expect(await screen.findByText('Peso registado.')).toBeInTheDocument()
    const corpo = pedidos.find((p) => p.caminho === '/actions/peso.registar')!.corpo as { params: { peso: number; cid: string } }
    expect(corpo.params.peso).toBe(104.2)
    expect(corpo.params.cid).toMatch(/^[A-Za-z0-9-]{8,64}$/)
  })

  test('valor inválido bloqueia o botão; se já registou hoje não pede outro', async () => {
    const hoje = { ...HOJE, modulos: { ...HOJE.modulos, peso: { estado: 'ok', dados: { ultimo: null, registadoHoje: false, sugestao: null } } } }
    abrir({}, hoje)
    const campo = await screen.findByLabelText('Peso de hoje em quilogramas')
    expect(screen.getByRole('button', { name: 'Registar' })).toBeDisabled()
    await userEvent.type(campo, 'abc')
    expect(screen.getByRole('button', { name: 'Registar' })).toBeDisabled()
    expect(campo).toHaveAttribute('aria-invalid', 'true')
  })

  test('registo de hoje feito: sem formulário', async () => {
    abrir()
    await screen.findByText('Registo de hoje feito.')
    expect(screen.queryByLabelText('Peso de hoje em quilogramas')).not.toBeInTheDocument()
  })

  test('lerPeso aceita vírgula e ponto e recusa o resto', () => {
    expect([lerPeso('104,8'), lerPeso('104.8'), lerPeso(' 80 ')]).toEqual([104.8, 104.8, 80])
    expect([lerPeso(''), lerPeso('abc'), lerPeso('0'), lerPeso('1001'), lerPeso('Infinity')]).toEqual([null, null, null, null, null])
  })
})

describe('rto', () => {
  test('por omissão está escolhido o dia de hoje; marcar Casa envia a data e a marca', async () => {
    const { pedidos } = abrir({ 'POST /actions/rto.marcar_dia': () => OK })
    const grupo = await screen.findByRole('group', { name: /Marcar 30 de setembro/ })
    await userEvent.click(within(grupo).getByRole('button', { name: 'Casa' }))
    await waitFor(() => expect(pedidos.some((p) => p.caminho === '/actions/rto.marcar_dia')).toBe(true))
    expect(pedidos.find((p) => p.caminho === '/actions/rto.marcar_dia')!.corpo).toEqual({ params: { data: '2026-09-30', marca: 'C' } })
  })

  test('«Limpar» só aparece se o dia tem marca (hoje tem T); fins de semana e dias passados ficam bloqueados', async () => {
    const { pedidos } = abrir({ 'POST /actions/rto.marcar_dia': () => OK })
    const grupo = await screen.findByRole('group', { name: /Marcar 30 de setembro/ })
    await userEvent.click(within(grupo).getByRole('button', { name: 'Limpar' }))
    await waitFor(() => expect(pedidos.some((p) => p.caminho === '/actions/rto.marcar_dia')).toBe(true))
    expect(pedidos.find((p) => p.caminho === '/actions/rto.marcar_dia')!.corpo).toEqual({ params: { data: '2026-09-30', marca: '' } })
    await userEvent.click(screen.getByRole('button', { name: /29 de setembro: casa/ }))                 // ontem: bloqueado
    const ontem = screen.getByRole('group', { name: /Marcar 29 de setembro/ })
    for (const nome of ['Escritório', 'Casa', 'Limpar']) expect(within(ontem).getByRole('button', { name: nome })).toBeDisabled()
    expect(screen.getByText(/Fim de semana ou dia passado/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'ecrã do RTO' })).toHaveAttribute('href', `${BASE}/rto`)
    await userEvent.click(screen.getByRole('button', { name: /1 de outubro: sem marca/ }))            // amanhã (quinta): livre
    expect(within(screen.getByRole('group', { name: /Marcar 1 de outubro/ })).getByRole('button', { name: 'Escritório' })).toBeEnabled()
  })
})

describe('finanças', () => {
  test('pagar marca como paga e permite desfazer', async () => {
    const { pedidos } = abrir({ 'POST /actions/financas.pagar': () => OK, 'POST /actions/financas.anular_pagamento': () => OK })
    await userEvent.click(await screen.findByRole('button', { name: 'Marcar Luz como paga' }))
    expect(await screen.findByText('Luz marcada como paga.')).toBeInTheDocument()
    expect(pedidos.find((p) => p.caminho === '/actions/financas.pagar')!.corpo).toEqual({ params: { lancamento: 2 } })
    await userEvent.click(screen.getByRole('button', { name: 'Desfazer' }))
    await waitFor(() => expect(pedidos.some((p) => p.caminho === '/actions/financas.anular_pagamento')).toBe(true))
  })
})

describe('erros e segurança', () => {
  test('módulo indisponível ao escrever: mensagem clara e o botão volta a estar disponível', async () => {
    abrir({ 'POST /actions/financas.pagar': () => [503, { erro: { codigo: 'modulo_indisponivel', mensagem: 'x' } }] })
    await userEvent.click(await screen.findByRole('button', { name: 'Marcar Luz como paga' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Este módulo não está disponível de momento')
    expect(screen.getByRole('button', { name: 'Marcar Luz como paga' })).toBeEnabled()
    await userEvent.click(screen.getByRole('button', { name: 'Fechar' }))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  test('só escreve quando o utilizador pede: abrir o Hoje não faz nenhum pedido que altere', async () => {
    const { pedidos } = abrir()
    await screen.findByText('Levar o lixo')
    expect(escritas(pedidos)).toEqual([])
  })

  test('todas as ações levam o cabeçalho anti-CSRF', async () => {
    const { pedidos } = abrir({ 'POST /actions/tarefas.concluir': () => OK })
    await userEvent.click(await screen.findByRole('button', { name: 'Concluir Limpar WC' }))
    await waitFor(() => expect(escritas(pedidos).length).toBe(1))
    expect(escritas(pedidos)[0]).toMatchObject({ cabecalhos: { 'X-Pulse-Client': 'web' } })
  })
})
