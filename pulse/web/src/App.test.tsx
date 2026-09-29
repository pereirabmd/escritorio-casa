import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App } from './App'
import { HOJE, servidorFalso, UTILIZADOR, type Rotas } from './test/api-mock'

const ERRO_401 = [401, { erro: { codigo: 'nao_autenticado', mensagem: 'inicia sessão' } }] as [number, unknown]

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '')   // '/pulse' na build, '' no vitest

function abrir(rotas: Rotas, caminho = '/hoje') {
  window.history.pushState({}, '', BASE + caminho)
  const servidor = servidorFalso(rotas)
  render(<App />)
  return servidor
}

afterEach(() => { vi.unstubAllGlobals(); document.documentElement.removeAttribute('data-theme'); localStorage.clear() })

describe('arranque e acesso', () => {
  test('sem sessão mostra o início de sessão, em pt-PT, e nada do resto', async () => {
    abrir({ 'GET /auth/me': () => ERRO_401 })
    expect(await screen.findByRole('heading', { name: 'Iniciar sessão' })).toBeInTheDocument()
    expect(screen.getByLabelText('E-mail')).toBeInTheDocument()
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
  })

  test('palavra-passe errada mostra o erro e limpa o campo', async () => {
    abrir({ 'GET /auth/me': () => ERRO_401, 'POST /auth/login': () => [401, { erro: { codigo: 'credenciais_invalidas', mensagem: 'x' } }] })
    await userEvent.type(await screen.findByLabelText('E-mail'), 'a@b.pt')
    await userEvent.type(screen.getByLabelText('Palavra-passe'), 'errada')
    await userEvent.click(screen.getByRole('button', { name: 'Iniciar sessão' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('E-mail ou palavra-passe incorretos.')
    expect(screen.getByLabelText('Palavra-passe')).toHaveValue('')
  })

  test('login certo leva ao Hoje e envia o cliente «web»', async () => {
    const { pedidos } = abrir({ 'GET /auth/me': () => ERRO_401, 'POST /auth/login': () => [200, { utilizador: UTILIZADOR }], 'GET /dashboard/today': () => [200, HOJE] })
    await userEvent.type(await screen.findByLabelText('E-mail'), ' pereirabmd@gmail.com ')
    await userEvent.type(screen.getByLabelText('Palavra-passe'), 'segredo-1234')
    await userEvent.click(screen.getByRole('button', { name: 'Iniciar sessão' }))
    expect(await screen.findByText('Levar o lixo')).toBeInTheDocument()
    expect(pedidos.find((p) => p.caminho === '/auth/login')!.corpo).toEqual({ email: 'pereirabmd@gmail.com', password: 'segredo-1234', cliente: 'web' })
  })

  test('mostrar/ocultar a palavra-passe', async () => {
    abrir({ 'GET /auth/me': () => ERRO_401 })
    const campo = await screen.findByLabelText('Palavra-passe')
    expect(campo).toHaveAttribute('type', 'password')
    await userEvent.click(screen.getByRole('button', { name: 'Mostrar palavra-passe' }))
    expect(campo).toHaveAttribute('type', 'text')
  })

  test('servidor em baixo não é «sem sessão»: mostra o aviso e deixa tentar de novo', async () => {
    let falha = true
    abrir({ 'GET /auth/me': () => (falha ? new Error('rede') : [200, { utilizador: UTILIZADOR }]), 'GET /dashboard/today': () => [200, HOJE] })
    expect(await screen.findByRole('heading', { name: 'Sem ligação ao servidor' })).toBeInTheDocument()
    falha = false
    await userEvent.click(screen.getByRole('button', { name: 'Tentar de novo' }))
    expect(await screen.findByText('Levar o lixo')).toBeInTheDocument()
  })

  test('sessão que expira a meio volta ao início de sessão', async () => {
    let n = 0
    abrir({ 'GET /auth/me': () => [200, { utilizador: UTILIZADOR }], 'GET /dashboard/today': () => (n++ === 0 ? [200, HOJE] : ERRO_401) })
    await screen.findByText('Levar o lixo')
    await userEvent.click(screen.getByRole('button', { name: 'Atualizar' }))
    expect(await screen.findByRole('heading', { name: 'Iniciar sessão' })).toBeInTheDocument()
  })
})

describe('mudança obrigatória de palavra-passe (primeiro acesso)', () => {
  const rotas = (extra: Rotas = {}): Rotas => ({
    'GET /auth/me': () => [200, { utilizador: { ...UTILIZADOR, mudarPassword: true } }],
    'GET /dashboard/today': () => [200, HOJE], ...extra })

  test('mostra só este ecrã, sem navegação, e o botão fica bloqueado até as regras se cumprirem', async () => {
    abrir(rotas())
    expect(await screen.findByRole('heading', { name: 'Define a tua palavra-passe' })).toBeInTheDocument()
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
    const botao = screen.getByRole('button', { name: 'Mudar palavra-passe' })
    expect(botao).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Palavra-passe atual'), '1234qweR')
    await userEvent.type(screen.getByLabelText('Palavra-passe nova'), 'curta')
    expect(botao).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Palavra-passe nova'), '-e-agora-comprida')
    await userEvent.type(screen.getByLabelText('Confirmar palavra-passe nova'), 'diferente')
    expect(screen.getByText('As palavras-passe não coincidem.')).toBeInTheDocument()
    expect(botao).toBeDisabled()
  })

  test('as regras vão ficando cumpridas enquanto se escreve', async () => {
    abrir(rotas())
    await userEvent.type(await screen.findByLabelText('Palavra-passe nova'), 'Outra-Palavra-Segura-7')
    const regras = within(screen.getByRole('list', { name: 'Regras da palavra-passe nova' }))
    expect(regras.getByText(/Pelo menos 10 caracteres/).closest('li')).toHaveAttribute('data-ok', 'true')
    expect(regras.getByText(/Diferente da palavra-passe atual/).closest('li')).toHaveAttribute('data-ok', 'true')
  })

  test('mudar com sucesso leva ao Hoje', async () => {
    const { pedidos } = abrir(rotas({ 'POST /auth/password': () => [200, { ok: true }] }))
    await userEvent.type(await screen.findByLabelText('Palavra-passe atual'), '1234qweR')
    await userEvent.type(screen.getByLabelText('Palavra-passe nova'), 'Outra-Palavra-Segura-7')
    await userEvent.type(screen.getByLabelText('Confirmar palavra-passe nova'), 'Outra-Palavra-Segura-7')
    await userEvent.click(screen.getByRole('button', { name: 'Mudar palavra-passe' }))
    expect(await screen.findByText('Levar o lixo')).toBeInTheDocument()
    expect(pedidos.find((p) => p.caminho === '/auth/password')!.corpo).toEqual({ atual: '1234qweR', nova: 'Outra-Palavra-Segura-7' })
  })

  test('erro do servidor aparece em pt-PT e mantém o ecrã', async () => {
    abrir(rotas({ 'POST /auth/password': () => [401, { erro: { codigo: 'password_atual_errada', mensagem: 'x' } }] }))
    await userEvent.type(await screen.findByLabelText('Palavra-passe atual'), 'errada-errada')
    await userEvent.type(screen.getByLabelText('Palavra-passe nova'), 'Outra-Palavra-Segura-7')
    await userEvent.type(screen.getByLabelText('Confirmar palavra-passe nova'), 'Outra-Palavra-Segura-7')
    await userEvent.click(screen.getByRole('button', { name: 'Mudar palavra-passe' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('A palavra-passe atual não está certa.')
    expect(screen.getByRole('heading', { name: 'Define a tua palavra-passe' })).toBeInTheDocument()
  })

  test('dá para terminar sessão a partir deste ecrã', async () => {
    abrir(rotas({ 'POST /auth/logout': () => [200, { ok: true }] }))
    await userEvent.click(await screen.findByRole('button', { name: 'Terminar sessão' }))
    expect(await screen.findByRole('heading', { name: 'Iniciar sessão' })).toBeInTheDocument()
  })
})

describe('Hoje', () => {
  const base: Rotas = { 'GET /auth/me': () => [200, { utilizador: UTILIZADOR }] }

  test('mostra os cinco cartões com os formatos pt-PT', async () => {
    abrir({ ...base, 'GET /dashboard/today': () => [200, HOJE] })
    await screen.findByText('Levar o lixo')
    expect(screen.getByText('Limpar WC')).toBeInTheDocument()
    expect(screen.getByText('1 de 3', { exact: false })).toBeInTheDocument()
    expect(screen.getByText('07:27')).toBeInTheDocument()
    expect(screen.getByText(/Comprado · carruagem 21, lugar 53/)).toBeInTheDocument()
    expect(screen.getByText('104,8 kg')).toBeInTheDocument()
    expect(screen.getByText('Registo de hoje feito.')).toBeInTheDocument()
    expect(screen.getByText(/1\s245,50\s€/)).toBeInTheDocument()
    expect(screen.getByText('Vence em 5 dias')).toBeInTheDocument()
    expect(screen.getByText('Venceu há 3 dias')).toBeInTheDocument()
    expect(screen.getByText('2 escritório · 1 casa')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/Bruno$/)
    expect(screen.getByText('Calendário e Email ainda não estão ligados.')).toBeInTheDocument()
  })

  test('não escreve nada nem usa emojis: só lê o agregado', async () => {
    const { pedidos } = abrir({ ...base, 'GET /dashboard/today': () => [200, HOJE] })
    await screen.findByText('Levar o lixo')
    expect(pedidos.filter((p) => p.metodo !== 'GET')).toEqual([])
    expect(document.body.textContent).not.toMatch(/\p{Extended_Pictographic}/u)
  })

  test('estado de carregamento usa o asset de marca', async () => {
    abrir({ ...base, 'GET /dashboard/today': () => new Promise(() => {}) as never })
    const estado = (await screen.findByText('A preparar o teu dia…')).closest('[role="status"]')!
    expect(estado.querySelector('img')!.getAttribute('src')).toBe(`${import.meta.env.BASE_URL}pulse-loading.webp`)
  })

  test('erro geral: mensagem e «Tentar de novo» que funciona', async () => {
    let falha = true
    abrir({ ...base, 'GET /dashboard/today': () => (falha ? [500, { erro: { codigo: 'erro_interno', mensagem: 'x' } }] : [200, HOJE]) })
    expect(await screen.findByRole('alert')).toHaveTextContent(/servidor não conseguiu responder/)
    falha = false
    await userEvent.click(screen.getByRole('button', { name: 'Tentar de novo' }))
    expect(await screen.findByText('Levar o lixo')).toBeInTheDocument()
  })

  test('modo degradado: aviso persistente, módulo afetado indicado e os outros a funcionar', async () => {
    const degradado = { ...HOJE, estado: 'degradado', modulos: { ...HOJE.modulos, rto: { estado: 'indisponivel', erro: { codigo: 'modulo_indisponivel', mensagem: 'x' } } } }
    abrir({ ...base, 'GET /dashboard/today': () => [200, degradado] })
    const aviso = await screen.findByText(/Alguns módulos não responderam \(RTO\)/)
    expect(aviso.closest('.notice')).toHaveAttribute('role', 'status')
    expect(screen.getByText('Levar o lixo')).toBeInTheDocument()
    expect(screen.getByText('104,8 kg')).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'RTO desta semana' })).getByText(/Indisponível de momento/)).toBeInTheDocument()
  })

  test('módulo sem acesso desaparece sem ser tratado como falha', async () => {
    const semAcesso = { ...HOJE, modulos: { ...HOJE.modulos, financas: { estado: 'sem_acesso', erro: { codigo: 'sem_acesso', mensagem: 'x' } } } }
    abrir({ ...base, 'GET /dashboard/today': () => [200, semAcesso] })
    await screen.findByText('Levar o lixo')
    expect(screen.queryByRole('region', { name: 'Contas a pagar' })).not.toBeInTheDocument()
    expect(screen.queryByText(/não responderam/)).not.toBeInTheDocument()
  })

  test('estados vazios', async () => {
    const vazio = { ...HOJE, modulos: { ...HOJE.modulos,
      tarefas: { estado: 'ok', dados: { hoje: [], atrasadas: 0, feitasHoje: 0, totalHoje: 0, pessoa: null } },
      bilhetes: { estado: 'ok', dados: { proximo: null, passe: null } },
      peso: { estado: 'ok', dados: { ultimo: null, registadoHoje: false, sugestao: null } },
      financas: { estado: 'ok', dados: { proximas: [], vencidas: 0, total: 0, valorTotal: 0 } } } }
    abrir({ ...base, 'GET /dashboard/today': () => [200, vazio] })
    expect(await screen.findByText('Sem tarefas para hoje.')).toBeInTheDocument()
    expect(screen.getByText('Sem viagens agendadas.')).toBeInTheDocument()
    expect(screen.getByText('Ainda sem registos de peso.')).toBeInTheDocument()
    expect(screen.getByText('Sem contas pendentes nos próximos 30 dias.')).toBeInTheDocument()
  })
})

describe('navegação e definições', () => {
  const base: Rotas = { 'GET /auth/me': () => [200, { utilizador: UTILIZADOR }], 'GET /dashboard/today': () => [200, HOJE] }

  test('rota desconhecida cai no Hoje; navegação principal tem Hoje e Mais', async () => {
    abrir(base, '/qualquer-coisa')
    await screen.findByText('Levar o lixo')
    const nav = screen.getByRole('navigation', { name: 'Principal' })
    expect(within(nav).getByRole('link', { name: 'Hoje' })).toHaveAttribute('aria-current', 'page')
    await userEvent.click(within(nav).getByRole('link', { name: 'Mais' }))
    expect(await screen.findByRole('heading', { name: 'Mais' })).toBeInTheDocument()
    expect(screen.getAllByText('Em breve').length).toBe(5)     // Peso, RTO e Tarefas já têm ecrã
  })

  test('sessões: lista, marca a atual e termina outra', async () => {
    let sessoes = [
      { id: 1, criada: 1, ultimoUso: 1790000000, expira: 2, dispositivo: 'Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0', ip: '', cliente: 'web', atual: true },
      { id: 2, criada: 1, ultimoUso: 1790000000, expira: 2, dispositivo: '', ip: '', cliente: 'android', atual: false }]
    const { pedidos } = abrir({ ...base, 'GET /auth/sessions': () => [200, { sessoes }],
      'DELETE /auth/sessions/2': () => { sessoes = sessoes.slice(0, 1); return [200, { ok: true }] } }, '/definicoes')
    expect(await screen.findByText('Firefox em Linux')).toBeInTheDocument()
    expect(screen.getByText('Esta sessão')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /Terminar sessão em/ }).length).toBe(1)
    await userEvent.click(screen.getByRole('button', { name: 'Terminar sessão em Aplicação Android' }))
    await waitFor(() => expect(screen.queryByText('Aplicação Android')).not.toBeInTheDocument())
    expect(pedidos.some((p) => p.metodo === 'DELETE' && p.caminho === '/auth/sessions/2')).toBe(true)
  })

  test('mudar de tema aplica-se ao documento e fica guardado', async () => {
    abrir({ ...base, 'GET /auth/sessions': () => [200, { sessoes: [] }] }, '/definicoes')
    await userEvent.click(await screen.findByRole('button', { name: 'Escuro' }))
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
    expect(localStorage.getItem('pulse.tema')).toBe('escuro')
    await userEvent.click(screen.getByRole('button', { name: 'Sistema' }))
    expect(document.documentElement).not.toHaveAttribute('data-theme')
  })

  test('Definições → Mudar palavra-passe: mesmo formulário, com aviso de que as outras sessões terminam', async () => {
    abrir({ ...base, 'GET /auth/sessions': () => [200, { sessoes: [] }], 'POST /auth/password': () => [200, { ok: true }] }, '/definicoes')
    await userEvent.click(await screen.findByRole('link', { name: /Mudar palavra-passe/ }))
    await userEvent.type(await screen.findByLabelText('Palavra-passe atual'), 'Antiga-Palavra-1')
    await userEvent.type(screen.getByLabelText('Palavra-passe nova'), 'Outra-Palavra-Segura-7')
    await userEvent.type(screen.getByLabelText('Confirmar palavra-passe nova'), 'Outra-Palavra-Segura-7')
    await userEvent.click(screen.getByRole('button', { name: 'Mudar palavra-passe' }))
    expect(await screen.findByText(/Terminámos as outras sessões/)).toBeInTheDocument()
  })

  test('terminar sessão volta ao início de sessão', async () => {
    abrir({ ...base, 'GET /auth/sessions': () => [200, { sessoes: [] }], 'POST /auth/logout': () => [200, { ok: true }] }, '/definicoes')
    await userEvent.click(await screen.findByRole('button', { name: 'Terminar sessão' }))
    expect(await screen.findByRole('heading', { name: 'Iniciar sessão' })).toBeInTheDocument()
  })
})
