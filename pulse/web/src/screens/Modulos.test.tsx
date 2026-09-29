import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App } from '../App'
import { HOJE, servidorFalso, UTILIZADOR, type Rotas } from '../test/api-mock'

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '')
const lista = (desativados: string[] = []) => ({
  modulos: [['tarefas', 'Tarefas', true], ['bilhetes', 'Bilhetes CP', true], ['rto', 'RTO', true], ['peso', 'Peso', true], ['financas', 'Finanças', true],
    ['calendario', 'Calendário', false], ['email', 'Email', false], ['compras', 'Compras', false]]
    .map(([id, nome, disponivel]) => ({ id, nome, disponivel, ativo: !desativados.includes(id as string) })),
})

function abrir(caminho: string, extra: Rotas = {}, utilizador = UTILIZADOR) {
  window.history.pushState({}, '', `${BASE}${caminho}`)
  const s = servidorFalso({ 'GET /auth/me': () => [200, { utilizador }], 'GET /modules': () => [200, lista()], ...extra })
  render(<App />)
  return s
}
afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })

test('Mais esconde os módulos desativados pelo administrador (e mantém os «Em breve»)', async () => {
  abrir('/mais', { 'GET /modules': () => [200, lista(['peso', 'financas'])] })
  await screen.findByRole('link', { name: /Tarefas/ })
  await waitFor(() => expect(screen.queryByRole('link', { name: /Peso/ })).not.toBeInTheDocument())
  expect(screen.queryByRole('link', { name: /Finanças/ })).not.toBeInTheDocument()
  expect(screen.getByRole('link', { name: /RTO/ })).toBeInTheDocument()
  expect(screen.getAllByText('Em breve')).toHaveLength(3)
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
    expect(within(adm).getAllByText('Em breve')).toHaveLength(3)                              // Calendário, Email e Compras não se alteram
  })

  test('um erro do servidor aparece e o interruptor não muda', async () => {
    abrir('/definicoes', { 'PUT /admin/modules': () => [403, { erro: { codigo: 'sem_permissao', mensagem: 'x' } }] })
    const adm = await screen.findByRole('region', { name: 'Administração' })
    await userEvent.click(await within(adm).findByRole('switch', { name: 'RTO: ativo' }))
    expect(await within(adm).findByText('Só o administrador pode fazer isto.')).toBeInTheDocument()
    expect(within(adm).getByRole('switch', { name: 'RTO: ativo' })).toBeInTheDocument()
  })
})
