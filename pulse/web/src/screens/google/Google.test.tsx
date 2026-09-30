import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App } from '../../App'
import { HOJE, servidorFalso, UTILIZADOR, type Rotas } from '../../test/api-mock'
import { irPara } from '../../lib/navegacao'
import { quandoMensagem } from '../email/EmailScreen'

vi.mock('../../lib/navegacao', () => ({ irPara: vi.fn() }))

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '')
const OK = (r: unknown = {}): [number, unknown] => [200, { resultado: r }]
const corpo = (p: { caminho: string; corpo: unknown }[], c: string) => p.find((x) => x.caminho === c)?.corpo

function abrir(caminho: string, extra: Rotas = {}) {
  window.history.pushState({}, '', `${BASE}${caminho}`)
  const s = servidorFalso({ 'GET /auth/me': () => [200, { utilizador: UTILIZADOR }], ...extra })
  render(<App />)
  return s
}
beforeEach(() => { vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-09-30T10:00:00')) })
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.mocked(irPara).mockClear(); localStorage.clear() })

// --- Definições: contas Google -------------------------------------------------------------------------------------------------

const CONTA = { id: 1, email: 'ele@gmail.com', nome: 'Ele', servicos: ['gmail', 'calendar'], estado: 'ok' }
const contas = (lista: unknown[] = [CONTA], configurado = true) => ({ 'GET /google/accounts': (): [number, unknown] => [200, { configurado, servicos: ['gmail', 'calendar'], contas: lista }] })

describe('Definições → Contas Google', () => {
  test('lista as contas com os serviços e avisa quando uma pede nova autorização', async () => {
    abrir('/definicoes', contas([CONTA, { ...CONTA, id: 2, email: 'outra@gmail.com', servicos: ['gmail'], estado: 'reautorizar' }]))
    const r = await screen.findByRole('region', { name: 'Contas Google' })
    expect(await within(r).findByText('ele@gmail.com')).toBeInTheDocument()
    expect(within(r).getByText('Gmail · Calendário')).toBeInTheDocument()
    expect(within(r).getByText('Volta a ligar')).toBeInTheDocument()
  })

  test('sem configuração no servidor explica em vez de oferecer ligar', async () => {
    abrir('/definicoes', contas([], false))
    const r = await screen.findByRole('region', { name: 'Contas Google' })
    expect(await within(r).findByText(/ainda não está configurada neste servidor/)).toBeInTheDocument()
    expect(within(r).queryByRole('button', { name: 'Ligar conta Google' })).not.toBeInTheDocument()
  })

  test('ligar pede o endereço ao servidor e segue para a Google, com os serviços escolhidos', async () => {
    const s = abrir('/definicoes', { ...contas([]), 'POST /google/connect': () => [200, { url: 'https://accounts.google.com/o/oauth2/v2/auth?x=1' }] })
    const r = await screen.findByRole('region', { name: 'Contas Google' })
    await userEvent.click(await within(r).findByRole('button', { name: 'Calendário' }))                 // desliga o Calendário: fica só o Gmail
    await userEvent.click(within(r).getByRole('button', { name: 'Ligar conta Google' }))
    await waitFor(() => expect(corpo(s.pedidos, '/google/connect')).toEqual({ servicos: ['gmail'] }))
    expect(irPara).toHaveBeenCalledWith('https://accounts.google.com/o/oauth2/v2/auth?x=1')
  })

  test('sem nenhum serviço escolhido não deixa ligar', async () => {
    abrir('/definicoes', contas([]))
    const r = await screen.findByRole('region', { name: 'Contas Google' })
    await userEvent.click(await within(r).findByRole('button', { name: 'Gmail' })); await userEvent.click(within(r).getByRole('button', { name: 'Calendário' }))
    expect(within(r).getByRole('button', { name: 'Ligar conta Google' })).toBeDisabled()
  })

  test('remover pede confirmação', async () => {
    const s = abrir('/definicoes', { ...contas(), 'DELETE /google/accounts/1': () => [200, { id: 1 }] })
    const r = await screen.findByRole('region', { name: 'Contas Google' })
    await userEvent.click(await within(r).findByRole('button', { name: 'Remover a conta ele@gmail.com' }))
    expect(s.pedidos.some((p) => p.metodo === 'DELETE')).toBe(false)
    await userEvent.click(within(within(r).getByRole('group', { name: 'Remover ele@gmail.com' })).getByRole('button', { name: 'Remover' }))
    await waitFor(() => expect(s.pedidos.some((p) => p.metodo === 'DELETE' && p.caminho === '/google/accounts/1')).toBe(true))
  })

  test('o regresso da Google mostra o resultado', async () => {
    abrir('/definicoes?google=ok', contas())
    expect(await screen.findByText('Conta Google ligada.')).toBeInTheDocument()
  })
  test.each([['recusado', /Não deste as permissões/], ['sem_refresh_token', /myaccount\.google\.com\/permissions/], ['coisa_nova', /Não foi possível ligar/]])('erro «%s» explica', async (motivo, texto) => {
    abrir(`/definicoes?google=erro&motivo=${motivo}`, contas())
    expect(await screen.findByText(texto)).toBeInTheDocument()
  })
})

// --- Calendário ------------------------------------------------------------------------------------------------------------------

const ev = (id: string, titulo: string, extra = {}) => ({ id, conta: 1, contaEmail: 'ele@gmail.com', calendario: 'ele@gmail.com', calendarioNome: 'Ele', cor: '#039be5', titulo, data: '2026-09-30', dataFim: '2026-09-30',
  inicio: '09:00', fim: '10:30', diaInteiro: false, local: '', descricao: '', link: '', podeEditar: true, ...extra })
const dias = (de: string, ate: string, por: Record<string, unknown[]>) => {
  const out = []
  for (let d = new Date(`${de}T12:00:00`); d <= new Date(`${ate}T12:00:00`); d.setDate(d.getDate() + 1)) { const k = d.toISOString().slice(0, 10); out.push({ data: k, eventos: por[k] ?? [] }) }
  return out
}
const AGENDA = (por: Record<string, unknown[]> = {}, extra = {}) => ({ ligado: true, configurado: true, de: '2026-08-30', ate: '2026-10-03', contas: [{ id: 1, email: 'ele@gmail.com', estado: 'ok' }],
  calendarios: [{ conta: 1, id: 'ele@gmail.com', nome: 'Ele', cor: '#039be5', principal: true, podeEditar: true }, { conta: 1, id: 'fam', nome: 'Família', cor: '#7986cb', principal: false, podeEditar: false }],
  dias: dias('2026-08-30', '2026-10-03', por), ...extra })
const cal = (por: Record<string, unknown[]> = {}, extra = {}): Rotas => ({ 'GET /calendar?de=2026-08-30&ate=2026-10-03': () => [200, AGENDA(por, extra)] })

describe('Calendário', () => {
  test('sem conta ligada convida a ligar', async () => {
    abrir('/calendario', { 'GET /calendar?de=2026-08-30&ate=2026-10-03': () => [200, { ligado: false, configurado: true, de: '', ate: '', contas: [], calendarios: [], dias: [] }] })
    expect(await screen.findByText(/Liga uma conta Google com o Calendário/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ir às Definições' })).toHaveAttribute('href', `${BASE}/definicoes`)
  })

  test('mostra os eventos do dia (dia inteiro e com horas) e assinala os dias com eventos', async () => {
    abrir('/calendario', cal({ '2026-09-30': [ev('a', 'Reunião', { local: 'Sala 1' }), ev('b', 'Feriado local', { diaInteiro: true, inicio: null, fim: null })], '2026-10-01': [ev('c', 'Dentista', { data: '2026-10-01', dataFim: '2026-10-01' })] }))
    const dia = await screen.findByRole('region', { name: 'Eventos do dia' })
    expect(within(dia).getByText('Reunião')).toBeInTheDocument()
    expect(within(dia).getByText('09:00–10:30 · Sala 1')).toBeInTheDocument()
    expect(within(dia).getByText('Dia inteiro')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '30 de setembro, 2 eventos' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '1 de outubro, 1 evento' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '1 de outubro, 1 evento' }))
    expect(within(screen.getByRole('region', { name: 'Eventos do dia' })).getByText('Dentista')).toBeInTheDocument()
  })

  test('um calendário só de leitura não tem editar nem apagar', async () => {
    abrir('/calendario', cal({ '2026-09-30': [ev('a', 'Da família', { podeEditar: false })] }))
    await screen.findByText('Da família')
    expect(screen.queryByRole('button', { name: 'Editar Da família' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Apagar Da família' })).not.toBeInTheDocument()
  })

  test('criar um evento com horas', async () => {
    const s = abrir('/calendario', { ...cal(), 'POST /actions/calendario.criar': () => OK({ id: 'novo' }) })
    await userEvent.click(await screen.findByRole('button', { name: 'Novo evento' }))
    const f = screen.getByRole('form', { name: 'Novo evento' })
    await userEvent.type(within(f).getByLabelText('Título'), 'Jantar')
    await userEvent.clear(within(f).getByLabelText('Início')); await userEvent.type(within(f).getByLabelText('Início'), '20:00')
    await userEvent.clear(within(f).getByLabelText('Fim')); await userEvent.type(within(f).getByLabelText('Fim'), '22:00')
    await userEvent.type(within(f).getByLabelText('Local (opcional)'), 'Casa da Ana')
    await userEvent.click(within(f).getByRole('button', { name: 'Criar evento' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/calendario.criar')).toEqual({ params: { conta: 1, calendario: 'primary', titulo: 'Jantar', data: '2026-09-30', inicio: '20:00', fim: '22:00', local: 'Casa da Ana', descricao: '' } }))
  })

  test('criar um evento de vários dias e dia inteiro não envia horas', async () => {
    const s = abrir('/calendario', { ...cal(), 'POST /actions/calendario.criar': () => OK({ id: 'novo' }) })
    await userEvent.click(await screen.findByRole('button', { name: 'Novo evento' }))
    const f = screen.getByRole('form', { name: 'Novo evento' })
    await userEvent.type(within(f).getByLabelText('Título'), 'Viagem')
    await userEvent.click(within(f).getByLabelText('Dia inteiro'))
    await userEvent.type(within(f).getByLabelText('Até (opcional)'), '2026-10-03')
    expect(within(f).queryByLabelText('Início')).not.toBeInTheDocument()
    await userEvent.click(within(f).getByRole('button', { name: 'Criar evento' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/calendario.criar')).toEqual({ params: { conta: 1, calendario: 'primary', titulo: 'Viagem', data: '2026-09-30', dataFim: '2026-10-03', local: '', descricao: '' } }))
  })

  test('o fim antes do início não deixa criar', async () => {
    abrir('/calendario', cal())
    await userEvent.click(await screen.findByRole('button', { name: 'Novo evento' }))
    const f = screen.getByRole('form', { name: 'Novo evento' })
    await userEvent.type(within(f).getByLabelText('Título'), 'X')
    await userEvent.clear(within(f).getByLabelText('Fim')); await userEvent.type(within(f).getByLabelText('Fim'), '08:00')
    expect(within(f).getByRole('button', { name: 'Criar evento' })).toBeDisabled()
  })

  test('editar envia o evento com os campos do formulário', async () => {
    const s = abrir('/calendario', { ...cal({ '2026-09-30': [ev('a', 'Reunião')] }), 'POST /actions/calendario.editar': () => OK() })
    await userEvent.click(await screen.findByRole('button', { name: 'Editar Reunião' }))
    const f = screen.getByRole('form', { name: 'Editar Reunião' })
    await userEvent.clear(within(f).getByLabelText('Título')); await userEvent.type(within(f).getByLabelText('Título'), 'Reunião de equipa')
    await userEvent.click(within(f).getByRole('button', { name: 'Guardar' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/calendario.editar')).toEqual({ params: { conta: 1, calendario: 'ele@gmail.com', evento: 'a', titulo: 'Reunião de equipa', data: '2026-09-30', inicio: '09:00', fim: '10:30', local: '', descricao: '' } }))
  })

  test('apagar pede confirmação e o desfazer volta a criar o evento', async () => {
    const s = abrir('/calendario', { ...cal({ '2026-09-30': [ev('a', 'Reunião', { local: 'Sala 1' })] }), 'POST /actions/calendario.apagar': () => OK(), 'POST /actions/calendario.criar': () => OK({ id: 'outro' }) })
    await userEvent.click(await screen.findByRole('button', { name: 'Apagar Reunião' }))
    expect(corpo(s.pedidos, '/actions/calendario.apagar')).toBeUndefined()
    await userEvent.click(within(screen.getByRole('group', { name: 'Apagar Reunião' })).getByRole('button', { name: 'Apagar' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/calendario.apagar')).toEqual({ params: { conta: 1, calendario: 'ele@gmail.com', evento: 'a' }, confirmado: true }))
    await userEvent.click(await screen.findByRole('button', { name: 'Desfazer' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/calendario.criar')).toEqual({ params: { conta: 1, calendario: 'ele@gmail.com', titulo: 'Reunião', data: '2026-09-30', inicio: '09:00', fim: '10:30', local: 'Sala 1', descricao: '' } }))
  })

  test('uma conta a pedir nova autorização avisa; navegar de mês pede o mês novo', async () => {
    const pedidos: string[] = []
    abrir('/calendario', { ...cal({}, { contas: [{ id: 1, email: 'ele@gmail.com', estado: 'ok' }, { id: 2, email: 'velha@gmail.com', estado: 'reautorizar', erro: 'x' }] }),
      'GET /calendar?de=2026-09-27&ate=2026-10-31': () => { pedidos.push('out'); return [200, AGENDA({}, { de: '2026-09-27', ate: '2026-10-31', dias: dias('2026-09-27', '2026-10-31', {}) })] } })
    expect(await screen.findByText(/A conta velha@gmail\.com pede nova autorização/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Mês seguinte' }))
    await waitFor(() => expect(pedidos).toEqual(['out']))
    expect(await screen.findByRole('heading', { name: 'Outubro de 2026' })).toBeInTheDocument()
  })
})

// --- Email -------------------------------------------------------------------------------------------------------------------------

const msg = (id: string, assunto: string, extra = {}) => ({ id, conta: 1, contaEmail: 'ele@gmail.com', thread: 't', de: 'Ana', deEmail: 'ana@x.pt', assunto, resumo: 'resumo…', data: '2026-09-30T09:30:00',   // sem fuso: o teste não depende do fuso da máquina
 
  lida: false, estrela: false, importante: true, entrada: true, link: `https://mail.google.com/mail/u/ele@gmail.com/#all/${id}`, ...extra })
const CAIXA = (mensagens: unknown[], extra = {}) => ({ ligado: true, configurado: true, filtro: 'importantes', contas: [{ id: 1, email: 'ele@gmail.com', estado: 'ok', total: mensagens.length }], mensagens, ...extra })
const mail = (mensagens: unknown[] = [msg('m1', 'Reunião amanhã'), msg('m2', 'Fatura', { lida: true })], extra = {}): Rotas => ({ 'GET /mail?filtro=importantes': () => [200, CAIXA(mensagens, extra)] })
const DET = (m: unknown, corpo = 'Olá,\n\ncorpo da mensagem.') => ({ ...(m as object), para: 'ele@gmail.com', corpo, temAnexos: false })

describe('Email', () => {
  test('sem conta ligada convida a ligar', async () => {
    abrir('/email', { 'GET /mail?filtro=importantes': () => [200, { ligado: false, configurado: true, filtro: 'importantes', contas: [], mensagens: [] }] })
    expect(await screen.findByText(/Liga uma conta Google com o Gmail/)).toBeInTheDocument()
  })

  test('lista com as por ler em destaque e o resumo', async () => {
    abrir('/email', mail())
    const nova = await screen.findByRole('button', { name: 'Por ler: Reunião amanhã, de Ana' })
    expect(nova).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Fatura, de Ana' })).toBeInTheDocument()
    expect(within(nova).getByText('há 30 min')).toBeInTheDocument()
  })

  test('os filtros pedem outra caixa ao servidor', async () => {
    const pedidos: string[] = []
    abrir('/email', { ...mail(), 'GET /mail?filtro=por_ler': () => { pedidos.push('por_ler'); return [200, CAIXA([], { filtro: 'por_ler' })] } })
    await userEvent.click(await screen.findByRole('button', { name: 'Por ler' }))
    await waitFor(() => expect(pedidos).toEqual(['por_ler']))
    expect(await screen.findByText('Nada por ler.')).toBeInTheDocument()
  })

  test('várias contas: filtro por conta e a conta em cada mensagem', async () => {
    const pedidos: string[] = []
    abrir('/email', { ...mail([msg('m1', 'Um'), msg('m2', 'Dois', { conta: 2, contaEmail: 'outra@gmail.com' })], { contas: [{ id: 1, email: 'ele@gmail.com', estado: 'ok' }, { id: 2, email: 'outra@gmail.com', estado: 'ok' }] }),
      'GET /mail?filtro=importantes&conta=2': () => { pedidos.push('2'); return [200, CAIXA([msg('m2', 'Dois', { conta: 2, contaEmail: 'outra@gmail.com' })], { contas: [{ id: 2, email: 'outra@gmail.com', estado: 'ok' }] })] } })
    const contas = await screen.findByRole('group', { name: 'Conta' })
    await userEvent.click(within(contas).getByRole('button', { name: 'outra@gmail.com' }))
    await waitFor(() => expect(pedidos).toEqual(['2']))
  })

  test('abrir uma mensagem mostra o corpo como texto (o HTML de um email nunca é interpretado)', async () => {
    const perigoso = 'Olá <img src=x onerror="alert(1)"> <script>alert(2)</script>'
    abrir('/email', { ...mail(), 'GET /mail/1/m1': () => [200, DET(msg('m1', 'Reunião amanhã'), perigoso)] })
    await userEvent.click(await screen.findByRole('button', { name: 'Por ler: Reunião amanhã, de Ana' }))
    const r = await screen.findByRole('region', { name: 'Mensagem: Reunião amanhã' })
    expect(await within(r).findByText(perigoso)).toBeInTheDocument()
    expect(r.querySelector('img, script')).toBeNull()
  })

  test('abrir não marca como lida; marcar como lida é uma ação explícita', async () => {
    const s = abrir('/email', { ...mail(), 'GET /mail/1/m1': () => [200, DET(msg('m1', 'Reunião amanhã'))], 'POST /actions/email.lida': () => OK({}) })
    await userEvent.click(await screen.findByRole('button', { name: 'Por ler: Reunião amanhã, de Ana' }))
    await screen.findByText(/corpo da mensagem/)
    expect(s.pedidos.some((p) => p.caminho === '/actions/email.lida')).toBe(false)
    await userEvent.click(screen.getByRole('button', { name: 'Marcar como lida' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/email.lida')).toEqual({ params: { conta: 1, mensagem: 'm1', lida: true } }))
  })

  test('arquivar tem desfazer; estrela alterna', async () => {
    const s = abrir('/email', { ...mail(), 'GET /mail/1/m1': () => [200, DET(msg('m1', 'Reunião amanhã'))], 'POST /actions/email.arquivar': () => OK({}), 'POST /actions/email.estrela': () => OK({}) })
    await userEvent.click(await screen.findByRole('button', { name: 'Por ler: Reunião amanhã, de Ana' }))
    await screen.findByText(/corpo da mensagem/)
    await userEvent.click(screen.getByRole('button', { name: 'Arquivar' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/email.arquivar')).toEqual({ params: { conta: 1, mensagem: 'm1', arquivado: true } }))
    await userEvent.click(await screen.findByRole('button', { name: 'Desfazer' }))
    await waitFor(() => expect(s.pedidos.filter((p) => p.caminho === '/actions/email.arquivar').map((p) => (p.corpo as { params: { arquivado: boolean } }).params.arquivado)).toEqual([true, false]))
    await userEvent.click(screen.getByRole('button', { name: 'Pôr estrela' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/email.estrela')).toEqual({ params: { conta: 1, mensagem: 'm1', estrela: true } }))
  })

  test('uma conta a pedir nova autorização avisa mas as outras aparecem', async () => {
    abrir('/email', mail([msg('m1', 'Um')], { contas: [{ id: 1, email: 'ele@gmail.com', estado: 'ok' }, { id: 2, email: 'velha@gmail.com', estado: 'reautorizar' }] }))
    expect(await screen.findByText(/A conta velha@gmail\.com pede nova autorização/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Um, de Ana/ })).toBeInTheDocument()
  })

  test('anexos são avisados mas não mostrados', async () => {
    abrir('/email', { ...mail(), 'GET /mail/1/m1': () => [200, { ...DET(msg('m1', 'Reunião amanhã')), temAnexos: true }] })
    await userEvent.click(await screen.findByRole('button', { name: 'Por ler: Reunião amanhã, de Ana' }))
    expect(await screen.findByText(/tem anexos, que o Pulse não mostra/)).toBeInTheDocument()
  })

  test('quandoMensagem', () => {
    const agora = new Date('2026-09-30T10:00:00')
    expect(quandoMensagem('2026-09-30T09:58:00', agora)).toBe('há 2 min')
    expect(quandoMensagem('2026-09-30T09:59:40', agora)).toBe('agora')
    expect(quandoMensagem('2026-09-30T07:05:00', agora)).toBe('hoje 07:05')
    expect(quandoMensagem('2026-09-29T20:00:00', agora)).toBe('ontem')
    expect(quandoMensagem('2026-09-20T20:00:00', agora)).toBe('20/09')
    expect(quandoMensagem('', agora)).toBe('')
  })
})

// --- Hoje ------------------------------------------------------------------------------------------------------------------------

describe('Hoje: calendário e email', () => {
  const hoje = (calendario: unknown, email: unknown) => ({ ...HOJE, modulos: { ...HOJE.modulos, calendario, email } })
  const abrirHoje = (h: unknown) => abrir('/hoje', { 'GET /dashboard/today': () => [200, h] })

  test('mostra os eventos de hoje e os emails importantes por ler, com ligação aos módulos', async () => {
    abrirHoje(hoje({ estado: 'ok', dados: { eventos: [ev('a', 'Reunião', { local: 'Sala 1' }), ev('b', 'Aniversário', { diaInteiro: true, inicio: null, fim: null })], total: 4, contas: 1, comProblemas: [] } },
      { estado: 'ok', dados: { porLer: 5, mensagens: [msg('m1', 'Urgente')], contas: 1, comProblemas: [] } }))
    const c = (await screen.findByRole('heading', { name: 'Próximos eventos' })).closest('section')!
    expect(within(c).getByText('Reunião')).toBeInTheDocument(); expect(within(c).getByText('09:00')).toBeInTheDocument(); expect(within(c).getByText('Dia todo')).toBeInTheDocument()
    expect(within(c).getByRole('link', { name: 'Abrir' })).toHaveAttribute('href', `${BASE}/calendario`)
    const e = screen.getByRole('heading', { name: 'Emails importantes' }).closest('section')!
    expect(within(e).getByRole('link', { name: /Urgente/ })).toHaveAttribute('href', 'https://mail.google.com/mail/u/ele@gmail.com/#all/m1'); expect(within(e).getByText('Urgente')).toBeInTheDocument(); expect(within(e).getByText('5 por ler')).toBeInTheDocument(); expect(within(e).getByText('e mais 4')).toBeInTheDocument()
    expect(within(e).getByRole('link', { name: 'Abrir' })).toHaveAttribute('href', `${BASE}/email`)
  })

  test('sem eventos nem emails', async () => {
    abrirHoje(hoje({ estado: 'ok', dados: { eventos: [], total: 0, contas: 1, comProblemas: [] } }, { estado: 'ok', dados: { porLer: 0, mensagens: [], contas: 1, comProblemas: [] } }))
    expect(await screen.findByText('Sem eventos marcados.')).toBeInTheDocument()
    expect(screen.getByText('Nada importante por ler.')).toBeInTheDocument()
  })

  test('sem conta Google os cartões convidam a ligar', async () => {
    abrirHoje(HOJE)
    expect((await screen.findAllByRole('link', { name: 'Ligar conta Google' }))).toHaveLength(2)
  })

  test('uma conta a pedir nova autorização é dita no cartão', async () => {
    abrirHoje(hoje({ estado: 'ok', dados: { eventos: [], total: 0, contas: 1, comProblemas: [{ id: 1, email: 'velha@gmail.com', estado: 'reautorizar' }] } }, { estado: 'nao_ligado', dados: null }))
    expect(await screen.findByText(/A conta velha@gmail\.com pede nova autorização/)).toBeInTheDocument()
  })

  test('desativado pelo administrador não aparece', async () => {
    abrirHoje(hoje({ estado: 'desativado', dados: null }, { estado: 'desativado', dados: null }))
    await screen.findByText('Próximo comboio')
    expect(screen.queryByRole('heading', { name: 'Próximos eventos' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Emails importantes' })).not.toBeInTheDocument()
  })
})
