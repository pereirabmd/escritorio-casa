import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App } from '../App'
import { HOJE, servidorFalso, UTILIZADOR, type Rotas } from '../test/api-mock'

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '')
const lista = (desativados: string[] = []) => ({
  modulos: [['tarefas', 'Tarefas', true], ['bilhetes', 'Bilhetes CP', true], ['rto', 'RTO', true], ['peso', 'Peso', true], ['financas', 'Finanças', true],
    ['compras', 'Compras', true], ['calendario', 'Calendário', true], ['email', 'Email', true]]
    .map(([id, nome, disponivel]) => ({ id, nome, disponivel, ativo: !desativados.includes(id as string) })),
})

function abrir(caminho: string, extra: Rotas = {}, utilizador = UTILIZADOR) {
  window.history.pushState({}, '', `${BASE}${caminho}`)
  const s = servidorFalso({ 'GET /auth/me': () => [200, { utilizador }], 'GET /modules': () => [200, lista()], ...extra })
  render(<App />)
  return s
}
afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })

test('Mais esconde os módulos desativados pelo administrador', async () => {
  abrir('/mais', { 'GET /modules': () => [200, lista(['peso', 'financas'])] })
  await screen.findByRole('link', { name: /Tarefas/ })
  await waitFor(() => expect(screen.queryByRole('link', { name: /Peso/ })).not.toBeInTheDocument())
  expect(screen.queryByRole('link', { name: /Finanças/ })).not.toBeInTheDocument()
  expect(screen.getByRole('link', { name: /RTO/ })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /Calendário/ })).toBeInTheDocument()
})

test('sem resposta de /modules não se esconde nada', async () => {
  abrir('/mais', { 'GET /modules': () => [500, { erro: { codigo: 'erro', mensagem: 'x' } }] })
  expect(await screen.findByRole('link', { name: /Peso/ })).toBeInTheDocument()
})

test('abrir directamente um módulo desativado explica em vez de mostrar erros', async () => {
  abrir('/peso', { 'GET /modules': () => [200, lista(['peso'])] })
  expect(await screen.findByText(/desativado pelo administrador/)).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Peso' })).toBeInTheDocument()
})

test('o Hoje não mostra o cartão de um módulo desativado', async () => {
  const hoje = { ...HOJE, modulos: { ...HOJE.modulos, financas: { estado: 'desativado', dados: null }, peso: { estado: 'desativado', dados: null } } }
  abrir('/hoje', { 'GET /dashboard/today': () => [200, hoje] })
  await screen.findByText('Próximo comboio')
  expect(screen.queryByText('Peso', { selector: 'h2, h3' })).not.toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: /Contas a pagar|Finanças/ })).not.toBeInTheDocument()
})

describe('Administração', () => {
  test('só os administradores veem a secção', async () => {
    abrir('/definicoes', {}, { ...UTILIZADOR, admin: false })
    await screen.findByRole('heading', { name: 'Definições' })
    expect(screen.queryByRole('region', { name: 'Administração' })).not.toBeInTheDocument()
  })

  test('desativar e voltar a ativar um módulo', async () => {
    const corpos: unknown[] = []
    abrir('/definicoes', { 'PUT /admin/modules': (c) => { corpos.push(c); const ativo = (c as { modulos: Record<string, boolean> }).modulos.peso; return [200, lista(ativo ? [] : ['peso'])] } })
    const adm = await screen.findByRole('region', { name: 'Administração' })
    await userEvent.click(await within(adm).findByRole('switch', { name: 'Peso: ativo' }))
    await userEvent.click(await within(adm).findByRole('switch', { name: 'Peso: desativado' }))
    await within(adm).findByRole('switch', { name: 'Peso: ativo' })
    expect(corpos).toEqual([{ modulos: { peso: false } }, { modulos: { peso: true } }])
    expect(within(adm).queryByText('Em breve')).not.toBeInTheDocument()                        // já não há módulos por chegar
  })

  test('um erro do servidor aparece e o interruptor não muda', async () => {
    abrir('/definicoes', { 'PUT /admin/modules': () => [403, { erro: { codigo: 'sem_permissao', mensagem: 'x' } }] })
    const adm = await screen.findByRole('region', { name: 'Administração' })
    await userEvent.click(await within(adm).findByRole('switch', { name: 'RTO: ativo' }))
    expect(await within(adm).findByText('Só o administrador pode fazer isto.')).toBeInTheDocument()
    expect(within(adm).getByRole('switch', { name: 'RTO: ativo' })).toBeInTheDocument()
  })
})

describe('Ordem do Hoje (Definições)', () => {
  test('as setas mudam a ordem e guardam-na', async () => {
    const { pedidos } = abrir('/definicoes', { 'GET /dashboard/order': () => [200, { ordem: ['calendario', 'tarefas', 'peso'] }], 'PUT /dashboard/order': () => [200, { ordem: [] }] })
    const pega = await screen.findByRole('button', { name: /Mover Tarefas/ })
    pega.focus()
    await userEvent.keyboard('{ArrowDown}')
    const nomes = screen.getAllByRole('button', { name: /^Mover / }).map((b) => b.getAttribute('aria-label'))
    expect(nomes[1]).toMatch(/Peso/); expect(nomes[2]).toMatch(/Tarefas/)
    await waitFor(() => expect(pedidos.some((p) => p.metodo === 'PUT' && p.caminho.includes('/dashboard/order') && JSON.stringify(p.corpo).includes('"peso","tarefas"'))).toBe(true))
  })
})

describe('O meu Hoje (Definições)', () => {
  test('só mostra os cartões que a pessoa tem e deixa esconder um', async () => {
    const { pedidos } = abrir('/definicoes', {
      'GET /dashboard/order': () => [200, { ordem: ['calendario', 'tarefas', 'peso', 'rto'], ocultos: [], disponiveis: ['tarefas', 'peso'] }],
      'PUT /dashboard/order': () => [200, { ordem: [], ocultos: [], disponiveis: [] }],
    })
    await screen.findByRole('button', { name: /Mover Tarefas/ })
    expect(screen.queryByRole('button', { name: /Mover RTO/ })).not.toBeInTheDocument()         // sem acesso: nem aparece
    await userEvent.click(screen.getByRole('switch', { name: /Peso no Hoje/ }))
    await waitFor(() => expect(pedidos.some((p) => p.metodo === 'PUT' && p.caminho.includes('/dashboard/order') && JSON.stringify(p.corpo).includes('"ocultos":["peso"]'))).toBe(true))
    expect(screen.getByRole('switch', { name: /Peso no Hoje: escondido/ })).toBeInTheDocument()
  })
})

describe('Pessoas (administração)', () => {
  const PESSOAS = [{ id: 1, email: 'a@b.pt', nome: 'Bruno', admin: true, ativo: true, mudarPassword: false, ultimoLogin: 1, modulos: ['tarefas', 'peso'] },
    { id: 2, email: 'c@d.pt', nome: 'Camila', admin: false, ativo: true, mudarPassword: true, ultimoLogin: null, modulos: ['compras'] }]

  test('só os administradores veem a secção', async () => {
    abrir('/definicoes', {}, { ...UTILIZADOR, admin: false })
    await screen.findByRole('heading', { name: 'Definições' })
    expect(screen.queryByRole('region', { name: 'Pessoas' })).not.toBeInTheDocument()
  })

  test('dar um módulo a uma pessoa e criar uma conta', async () => {
    const { pedidos } = abrir('/definicoes', {
      'GET /admin/users': () => [200, { pessoas: PESSOAS }],
      'PUT /admin/users/2/modules': () => [200, PESSOAS[1]],
      'POST /admin/users': () => [201, PESSOAS[1]],
    })
    const camila = await screen.findByRole('group', { name: 'Módulos de Camila' })
    await userEvent.click(within(camila).getByRole('button', { name: 'Tarefas' }))
    await waitFor(() => expect(pedidos.some((p) => p.metodo === 'PUT' && p.caminho.endsWith('/admin/users/2/modules') && JSON.stringify(p.corpo) === '{"modulos":["compras","tarefas"]}')).toBe(true))
    await userEvent.click(screen.getByRole('button', { name: 'Adicionar pessoa' }))
    await userEvent.type(screen.getByLabelText('E-mail'), 'nova@x.pt')
    await userEvent.type(screen.getByLabelText(/Palavra-passe provisória \(mínimo 8\)/), 'provisoria1')
    await userEvent.click(screen.getByRole('button', { name: 'Criar conta' }))
    await waitFor(() => expect(pedidos.some((p) => p.metodo === 'POST' && p.caminho.endsWith('/admin/users') && JSON.stringify(p.corpo).includes('"modulos":["compras"]'))).toBe(true))
  })
})
