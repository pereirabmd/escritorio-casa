import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App } from '../../App'
import { diasParaEditor, linhaVazia, segundaDe, somarDias, validarDias, viagensParaEnviar } from '../../lib/bilhetes'
import { servidorFalso, UTILIZADOR, type Rotas } from '../../test/api-mock'

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '')
const OK: [number, unknown] = [200, { resultado: { anteriores: [] } }]

const viagem = (id: number, data: string, hora: string, estado: string, extra = {}) =>
  ({ id, data, hora, origem: 'Aveiro', destino: 'Lisboa Oriente', comboio: 520 + id, ativo: estado !== 'inativa', estado, fimEstimado: '12:00', compra: null, ...extra })
const DIAS = ['2026-10-05', '2026-10-06', '2026-10-07', '2026-10-08', '2026-10-09', '2026-10-10', '2026-10-11']
const DADOS = {
  hoje: '2026-09-30',
  passe: { dataUltimaCompra: '2026-09-05', validadeDias: 29, dataExpira: '2026-10-05', diasRestantes: 5, estado: 'ok', percentagem: 17 },
  proxima: viagem(3, '2026-09-30', '09:00', 'em_curso', { compra: { carruagem: '5', lugar: '12', referencia: 'R2' } }),
  proximas: [],
  semanaSeguinte: { inicio: '2026-10-05', ativas: 2 },
  semana: { inicio: '2026-10-05', dias: DIAS, viagens: [viagem(6, '2026-10-05', '07:27', 'por_comprar'), viagem(7, '2026-10-06', '07:27', 'comprado', { compra: { carruagem: '21', lugar: '53', referencia: 'R7' } })] },
  bilhetes: {
    proximos: [{ id: 2, data: '2026-09-30', hora: '09:00', origem: 'Aveiro', destino: 'Lisboa Oriente', comboio: 522, carruagem: '5', lugar: '12', referencia: 'R2' }],
    anteriores: [{ id: 1, data: '2026-09-29', hora: '07:00', origem: 'Aveiro', destino: 'Lisboa Oriente', comboio: 520, carruagem: '21', lugar: '53', referencia: 'R1' }],
  },
  pedidos: [{ id: 4, data: '2026-10-08', hora: '07:00', origem: 'Aveiro', destino: 'Lisboa Oriente', comboio: 520, ativo: true, retry: false, intervaloMinutos: 15, forcar: false, estado: 'ESGOTADO', ultimaTentativa: null, referencia: null, mensagem: 'sem lugares' }],
  registo: [
    { ts: '2026-09-30 06:00:00', tipo: 'ERRO', data: '2026-09-30', perna: 'v1', comboio: 520, status: 500, resultado: 'FALHA', referencia: null, erro: 'a CP não respondeu' },
    { ts: '2026-09-29 06:00:00', tipo: 'COMPRA', data: '2026-09-29', perna: 'v1', comboio: 520, status: 200, resultado: 'CONFIRMED', referencia: 'R1', erro: null }],
  estacoes: ['Aveiro', 'Lisboa Oriente'], historico: [{ comboio: 525, origem: 'Aveiro', destino: 'Lisboa Oriente', hora: '07:27' }],
  favoritos: [{ id: 7, apelido: 'Manhã', comboio: 525, origem: 'Aveiro', destino: 'Lisboa Oriente', hora: '07:27' }],
}

function abrir(aba: string, extra: Rotas = {}, dados: unknown = DADOS) {
  window.history.pushState({}, '', `${BASE}/bilhetes?aba=${aba}`)
  const s = servidorFalso({ 'GET /auth/me': () => [200, { utilizador: UTILIZADOR }], 'GET /tickets': () => [200, dados], ...extra })
  render(<App />)
  return s
}
const corpo = (p: { caminho: string; corpo: unknown }[], c: string) => p.find((x) => x.caminho === c)?.corpo

afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })

describe('lib', () => {
  test('semanas de segunda a domingo e datas', () => {
    expect(segundaDe('2026-09-30')).toBe('2026-09-28')
    expect(segundaDe('2026-10-04')).toBe('2026-09-28')                    // domingo
    expect(somarDias('2026-12-31', 1)).toBe('2027-01-01')
  })
  test('validação por dia: origem/destino, comboio, hora, repetidas; dias passados e vazios não se validam', () => {
    const dias = [
      { data: 'a', ativo: true, passado: false, viagens: [linhaVazia('Aveiro', 'Aveiro'), { origem: 'Aveiro', destino: 'Lisboa', comboio: 'x', hora: '25:00' }] },
      { data: 'b', ativo: true, passado: false, viagens: [{ origem: 'A', destino: 'B', comboio: '520', hora: '07:00' }, { origem: 'A', destino: 'B', comboio: '520', hora: '07:00' }] },
      { data: 'c', ativo: true, passado: true, viagens: [linhaVazia()] }, { data: 'd', ativo: true, passado: false, viagens: [] },
    ]
    const e = validarDias(dias)
    expect(e[0]).toEqual(['Viagem 1: a origem e o destino são iguais.', 'Viagem 1: comboio inválido.', 'Viagem 1: hora inválida.', 'Viagem 2: comboio inválido.', 'Viagem 2: hora inválida.'])
    expect(e[1]).toEqual(['Viagem 2: repete a viagem 1.']); expect(e[2]).toEqual([]); expect(e[3]).toEqual([])
  })
  test('editor: o «ativo» é por dia; o corpo enviado tem tudo', () => {
    const dias = diasParaEditor(DIAS, DADOS.semana.viagens as never, '2026-09-30')
    expect(dias[0]).toMatchObject({ data: '2026-10-05', ativo: true, passado: false, viagens: [{ origem: 'Aveiro', destino: 'Lisboa Oriente', comboio: '526', hora: '07:27' }] })
    expect(viagensParaEnviar([{ ...dias[0], ativo: false }])).toEqual([{ data: '2026-10-05', origem: 'Aveiro', destino: 'Lisboa Oriente', comboio: 526, hora: '07:27', ativo: false }])
  })
})

test('Mais leva aos Bilhetes CP e o cartão do Hoje tem ligação', async () => {
  window.history.pushState({}, '', `${BASE}/mais`)
  servidorFalso({ 'GET /auth/me': () => [200, { utilizador: UTILIZADOR }], 'GET /tickets': () => [200, DADOS] })
  render(<App />)
  await userEvent.click(await screen.findByRole('link', { name: /Bilhetes CP/ }))
  expect(await screen.findByRole('heading', { name: 'Bilhetes CP' })).toBeInTheDocument()
})

describe('Semana', () => {
  test('mostra a viagem em curso, o passe e as viagens da semana com o estado', async () => {
    abrir('semana')
    const em = await screen.findByRole('region', { name: 'Próximo comboio' })
    expect(within(em).getByText('Em viagem')).toBeInTheDocument()
    expect(within(em).getByText(/chega por volta das 12:00/)).toBeInTheDocument()
    expect(within(em).getByText(/Carruagem 5, lugar 12/)).toBeInTheDocument()
    expect(screen.getByText(/Válido até 05\/10/)).toBeInTheDocument()
    const sem = screen.getByRole('region', { name: 'Viagens da semana' })
    expect(within(sem).getByText('Por comprar')).toBeInTheDocument()
    expect(within(sem).getByText('Comprado')).toBeInTheDocument()
    expect(within(sem).getByText(/carruagem 21, lugar 53/)).toBeInTheDocument()
  })

  test('aviso quando falta configurar a semana seguinte', async () => {
    abrir('semana', {}, { ...DADOS, semanaSeguinte: { inicio: '2026-10-05', ativas: 0 } })
    expect(await screen.findByText(/Falta configurar a semana de 05\/10 a 11\/10/)).toBeInTheDocument()
  })

  test('atualizar o passe envia a data', async () => {
    const s = abrir('semana', { 'POST /actions/bilhetes.passe': () => OK })
    await userEvent.click(await screen.findByRole('button', { name: 'Atualizar carregamento' }))
    const campo = screen.getByLabelText('Data do último carregamento')
    await userEvent.clear(campo); await userEvent.type(campo, '2026-09-30')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/bilhetes.passe')).toEqual({ params: { dataUltimaCompra: '2026-09-30' } }))
  })

  test('navegar de semana pede essa semana ao servidor', async () => {
    const pedidos: string[] = []
    abrir('semana', { 'GET /tickets?semana=2026-10-12': () => { pedidos.push('12'); return [200, { ...DADOS, semana: { inicio: '2026-10-12', dias: DIAS.map((d) => somarDias(d, 7)), viagens: [] } }] } })
    await userEvent.click(await screen.findByRole('button', { name: 'Semana seguinte' }))
    await waitFor(() => expect(pedidos).toEqual(['12']))
    expect(await screen.findByText('Sem viagens nesta semana.')).toBeInTheDocument()
  })

  test('configurar a semana: adicionar uma viagem e guardar; «Desfazer» repõe a anterior', async () => {
    const anteriores = [{ data: '2026-10-05', origem: 'Aveiro', destino: 'Lisboa Oriente', comboio: 526, hora: '07:27', ativo: true }]
    const s = abrir('semana', { 'POST /actions/bilhetes.semana': () => [200, { resultado: { anteriores } }] })
    await userEvent.click(await screen.findByRole('button', { name: 'Configurar semana' }))
    await userEvent.click(screen.getByRole('button', { name: 'Adicionar viagem a qua 07/10' }))
    const grupo = screen.getByRole('group', { name: 'qua 07/10, viagem 1' })
    await userEvent.type(within(grupo).getByLabelText('Comboio'), '4609')
    await userEvent.type(within(grupo).getByLabelText('Hora de partida'), '18:10')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar semana' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/bilhetes.semana')).toBeTruthy())
    const { params } = corpo(s.pedidos, '/actions/bilhetes.semana') as { params: { inicio: string; viagens: Record<string, unknown>[] } }
    expect(params.inicio).toBe('2026-10-05')
    expect(params.viagens).toHaveLength(3)
    expect(params.viagens[2]).toEqual({ data: '2026-10-07', origem: 'Aveiro', destino: 'Lisboa Oriente', comboio: 4609, hora: '18:10', ativo: true })
    await userEvent.click(await screen.findByRole('button', { name: 'Desfazer' }))
    await waitFor(() => expect(s.pedidos.filter((p) => p.caminho === '/actions/bilhetes.semana')).toHaveLength(2))
    expect((s.pedidos.filter((p) => p.caminho === '/actions/bilhetes.semana')[1].corpo as { params: { viagens: unknown } }).params.viagens).toEqual(anteriores)
  })

  test('validação: sem comboio nem hora não guarda e explica', async () => {
    const s = abrir('semana', { 'POST /actions/bilhetes.semana': () => OK })
    await userEvent.click(await screen.findByRole('button', { name: 'Configurar semana' }))
    await userEvent.click(screen.getByRole('button', { name: 'Adicionar viagem a qui 08/10' }))
    await userEvent.click(screen.getByRole('button', { name: 'Guardar semana' }))
    expect(await screen.findByText('Viagem 1: comboio inválido.')).toBeInTheDocument()
    expect(screen.getByText('Viagem 1: hora inválida.')).toBeInTheDocument()
    expect(corpo(s.pedidos, '/actions/bilhetes.semana')).toBeUndefined()
  })

  test('favoritos: guardar a viagem de uma linha e remover um favorito (com «Desfazer»)', async () => {
    const s = abrir('semana', { 'POST /actions/bilhetes.favorito_guardar': () => OK, 'POST /actions/bilhetes.favorito_apagar': () => OK })
    await userEvent.click(await screen.findByRole('button', { name: 'Configurar semana' }))
    await userEvent.click(screen.getByRole('button', { name: 'Adicionar viagem a sex 09/10' }))
    const dia = screen.getByRole('group', { name: 'sex 09/10, viagem 1' })
    await userEvent.selectOptions(within(dia).getByLabelText('Origem'), 'Lisboa Oriente')
    await userEvent.selectOptions(within(dia).getByLabelText('Destino'), 'Aveiro')
    await userEvent.type(within(dia).getByLabelText('Comboio'), '731')
    await userEvent.type(within(dia).getByLabelText('Hora de partida'), '17:30')
    await userEvent.click(within(dia).getByRole('button', { name: /Guardar a viagem 1 de sex 09\/10 nos favoritos/ }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/bilhetes.favorito_guardar')).toEqual({ params: { comboio: 731, hora: '17:30', origem: 'Lisboa Oriente', destino: 'Aveiro' } }))
    await userEvent.click(screen.getByRole('button', { name: /Remover o favorito 525 das 07:27/ }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/bilhetes.favorito_apagar')).toEqual({ params: { favorito: 7 } }))
  })

  test('o interruptor «Ativo» é por dia e a viagem dos favoritos preenche a linha', async () => {
    const s = abrir('semana', { 'POST /actions/bilhetes.semana': () => OK })
    await userEvent.click(await screen.findByRole('button', { name: 'Configurar semana' }))
    const dia = screen.getByRole('group', { name: 'seg 05/10' })
    await userEvent.click(within(dia).getByLabelText('Ativo'))
    await userEvent.click(screen.getByRole('button', { name: 'Adicionar viagem a sex 09/10' }))
    await userEvent.selectOptions(screen.getByLabelText(/Favoritos \(viagem 1 de sex 09\/10\)/), '0')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar semana' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/bilhetes.semana')).toBeTruthy())
    const v = (corpo(s.pedidos, '/actions/bilhetes.semana') as { params: { viagens: { data: string; ativo: boolean; comboio: number }[] } }).params.viagens
    expect(v.find((x) => x.data === '2026-10-05')!.ativo).toBe(false)
    expect(v.find((x) => x.data === '2026-10-09')).toMatchObject({ comboio: 525, hora: '07:27', ativo: true })
  })
})

describe('Bilhetes', () => {
  test('próximos e anteriores com carruagem e lugar', async () => {
    abrir('bilhetes')
    const p = await screen.findByRole('region', { name: 'Próximos bilhetes' })
    expect(within(p).getByText('Carruagem 5 · Lugar 12')).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Bilhetes anteriores' })).getByText('Carruagem 21 · Lugar 53')).toBeInTheDocument()
  })
  test('sem bilhetes mostra o estado vazio', async () => {
    abrir('bilhetes', {}, { ...DADOS, bilhetes: { proximos: [], anteriores: [] } })
    expect(await screen.findByText(/Ainda não há bilhetes comprados/)).toBeInTheDocument()
  })
})

describe('Pedidos', () => {
  test('tentar agora e ligar a repetição com os minutos', async () => {
    const s = abrir('pedidos', { 'POST /actions/bilhetes.pedido_forcar': () => OK, 'POST /actions/bilhetes.pedido_repetir': () => OK })
    expect(await screen.findByText('Esgotado')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Tentar agora' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/bilhetes.pedido_forcar')).toEqual({ params: { pedido: 4 } }))
    const min = screen.getByLabelText('Minutos entre tentativas')
    await userEvent.clear(min); await userEvent.type(min, '20')
    await userEvent.click(screen.getByLabelText('Repetir de'))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/bilhetes.pedido_repetir')).toEqual({ params: { pedido: 4, retry: true, intervaloMinutos: 20 } }))
  })
  test('estado incerto pede para confirmar na App CP e não deixa tentar', async () => {
    abrir('pedidos', {}, { ...DADOS, pedidos: [{ ...DADOS.pedidos[0], estado: 'AMBIGUO' }] })
    expect(await screen.findByText(/Confirma na App CP/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Tentar agora' })).not.toBeInTheDocument()
  })
  test('sem pedidos', async () => {
    abrir('pedidos', {}, { ...DADOS, pedidos: [] })
    expect(await screen.findByText(/Sem pedidos pendentes/)).toBeInTheDocument()
  })
})

describe('Registo', () => {
  test('filtros Tudo / Compras / Problemas', async () => {
    abrir('registo')
    const reg = await screen.findByRole('region', { name: 'Registo' })
    expect(within(reg).getAllByRole('listitem')).toHaveLength(2)
    await userEvent.click(screen.getByRole('button', { name: 'Compras' }))
    expect(within(screen.getByRole('region', { name: 'Registo' })).getAllByRole('listitem')).toHaveLength(1)
    expect(screen.getByText('Comprado')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Problemas' }))
    expect(screen.getByText('a CP não respondeu')).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Registo' })).getAllByRole('listitem')).toHaveLength(1)
  })
})

describe('Histórico dos pedidos à CP (administrador)', () => {
  const pessoas = [{ id: 1, nome: 'Bruno', eu: true }, { id: 2, nome: 'Camila', eu: false }]
  const admin = { ...DADOS, utilizador: { id: 1, nome: 'Bruno', eu: true }, pessoas }
  const HIST = { dias: 90, truncado: false, desfechos: [], pedidos: [
    { ts: '2026-10-01T17:20:00.100+01:00', data: '2026-10-01', perna: 'v102', pessoa: 'Camila', comboio: 731, fase: 'retencao', http: 200, resultado: 'sold_out', relTms: -600000, rttMs: 90, ligacaoNova: 0, codigo: '', detalhe: 'sem lugares' },
    { ts: '2026-10-01T17:19:45.000+01:00', data: '2026-10-01', perna: 'v101', pessoa: 'Bruno', comboio: 731, fase: 'retencao', http: 200, resultado: 'ok', relTms: -615000, rttMs: 80, ligacaoNova: 1, codigo: '', detalhe: '' }] }

  test('a aba abre pelo link da notificação e mostra hora, pessoa e resposta de cada pedido; filtra por pessoa', async () => {
    abrir('historico', { 'GET /tickets/history?dias=90': () => [200, HIST] }, admin)
    const reg = await screen.findByRole('region', { name: 'Histórico' })
    expect(within(reg).getAllByRole('listitem')).toHaveLength(2)
    expect(within(reg).getByText('Esgotado')).toBeInTheDocument()
    expect(within(reg).getByText(/10\.0 min de T/)).toBeInTheDocument()
    await userEvent.click(within(screen.getByRole('group', { name: 'Pessoa' })).getByRole('button', { name: 'Camila' }))
    expect(within(screen.getByRole('region', { name: 'Histórico' })).getAllByRole('listitem')).toHaveLength(1)
  })
  test('quem não é administrador não vê a aba', async () => {
    abrir('semana')
    await screen.findByRole('tablist', { name: 'Secções dos Bilhetes CP' })
    expect(screen.queryByRole('tab', { name: 'Histórico' })).toBeNull()
  })
})

describe('verificação do horário na CP (editor da semana)', () => {
  const abrirEditor = async (rota: unknown) => {
    const s = abrir('semana', { 'GET /tickets/timetable?comboio=526&data=2026-10-05&origem=Aveiro&destino=Lisboa+Oriente&hora=07%3A27': () => rota as [number, unknown] })
    await userEvent.click(await screen.findByRole('button', { name: 'Configurar semana' }))
    return s
  }

  test('um aviso da CP aparece bem visível e oferece usar a hora certa; nunca bloqueia', async () => {
    const s = await abrirEditor([200, { estado: 'aviso', mensagem: 'A CP indica 07:30 (Aveiro) e 07:30 (Aveiro); tens 07:27.', sugestaoHora: '07:30' }])
    const comboio = (await screen.findAllByPlaceholderText('Comboio'))[0]
    await userEvent.clear(comboio); await userEvent.type(comboio, '526')
    const aviso = await screen.findByRole('alert', {}, { timeout: 3000 })
    expect(aviso).toHaveTextContent('Verifica na CP')
    await userEvent.click(within(aviso).getByRole('button', { name: 'Usar 07:30' }))
    expect(s.pedidos.some((p) => p.metodo === 'GET' && p.caminho.includes('/tickets/timetable?') && p.caminho.includes('comboio=526'))).toBe(true)
  })

  test('desligado no servidor: não mostra nada', async () => {
    await abrirEditor([200, { estado: 'desligado', mensagem: '' }])
    const c0 = (await screen.findAllByPlaceholderText('Comboio'))[0]; await userEvent.clear(c0); await userEvent.type(c0, '526')
    await new Promise((r) => setTimeout(r, 900))
    expect(screen.queryByText(/Verifica na CP/)).not.toBeInTheDocument()
  })
})

describe('marcar para outras pessoas (administrador)', () => {
  const pessoas = [{ id: 1, nome: 'Bruno', eu: true }, { id: 2, nome: 'Camila', eu: false }]
  const meus = { ...DADOS, utilizador: { id: 1, nome: 'Bruno', eu: true }, pessoas }
  const dela = { ...DADOS, utilizador: { id: 2, nome: 'Camila', eu: false }, pessoas, semana: { ...DADOS.semana, viagens: [] } }

  test('sem pessoas (conta normal) não há seletor', async () => {
    abrir('semana')
    await screen.findByRole('button', { name: 'Configurar semana' })
    expect(screen.queryByRole('group', { name: 'Ver e marcar bilhetes de' })).not.toBeInTheDocument()
  })

  test('escolher a Camila carrega a semana dela e guardar marca para ela', async () => {
    const s = abrir('semana', { 'GET /tickets?utilizador=2': () => [200, dela], 'POST /actions/bilhetes.semana': () => [200, { resultado: { anteriores: [] } }] }, meus)
    const grupo = await screen.findByRole('group', { name: 'Ver e marcar bilhetes de' })
    expect(within(grupo).getByRole('button', { name: 'Bruno (eu)' })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(within(grupo).getByRole('button', { name: 'Camila' }))
    expect(await screen.findByText(/A marcar para/)).toHaveTextContent('Camila')
    await userEvent.click(await screen.findByRole('button', { name: 'Configurar semana' }))
    await userEvent.click(screen.getByRole('button', { name: 'Adicionar viagem a seg 05/10' }))
    await userEvent.type(screen.getAllByPlaceholderText('Comboio')[0], '520')
    await userEvent.type(screen.getAllByLabelText('Hora de partida')[0], '07:27')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar semana' }))
    await waitFor(() => expect(s.pedidos.some((p) => p.metodo === 'POST' && p.caminho === '/actions/bilhetes.semana' && (p.corpo as { params: { utilizador?: number } }).params.utilizador === 2)).toBe(true))
  })
})

describe('Na CP (ADR-075)', () => {
  const PASSE = { passes: [{ cartao: 'Cartão CP', designacao: 'Passe Ferroviário Verde Digital 30', origem: 'Aveiro', destino: 'Lisboa Oriente', inicio: '2026-09-21', validade: '2026-10-20', renovavel: false, diasRestantes: 20 }] }
  const FUTUROS = { bilhetes: [{ venda: 77, referencia: 'CP-X', estado: 'CONFIRMED', origem: 'Lisboa Oriente', destino: 'Aveiro', data: '2026-10-01', hora: '19:39', chegada: '22:02', comboio: 723, servico: 'IC', carruagem: 22, lugar: 77, valor: 0, podeCancelar: true }] }

  test('mostra a validade do Passe Verde e os bilhetes futuros da CP', async () => {
    abrir('cp', { 'GET /tickets/cp/passe': () => [200, PASSE], 'GET /tickets/cp/futuros': () => [200, FUTUROS] })
    expect(await screen.findByText('Passe Ferroviário Verde Digital 30')).toBeInTheDocument()
    expect(screen.getByText(/Válido até 20\/10\/2026 · 20 dias/)).toBeInTheDocument()
    expect(await screen.findByText(/Carruagem 22 · Lugar 77/)).toBeInTheDocument()
  })

  test('cancelar pede confirmação e só então envia a ação sensível', async () => {
    let restam = [...FUTUROS.bilhetes]
    const s = abrir('cp', {
      'GET /tickets/cp/passe': () => [200, PASSE], 'GET /tickets/cp/futuros': () => [200, { bilhetes: restam }],
      'POST /actions/bilhetes.cp_cancelar': () => { restam = []; return [200, { resultado: { estado: 'CONFIRMED' } }] },
    })
    await userEvent.click(await screen.findByRole('button', { name: 'Cancelar bilhete' }))
    expect(s.pedidos.some((p) => p.caminho === '/actions/bilhetes.cp_cancelar')).toBe(false)         // ainda não cancelou nada
    await userEvent.click(within(await screen.findByRole('group', { name: /Cancelar o bilhete/ })).getByRole('button', { name: 'Cancelar bilhete' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/bilhetes.cp_cancelar')).toEqual({ params: { venda: 77 }, confirmado: true }))
    expect(await screen.findByText('Sem bilhetes futuros na CP.')).toBeInTheDocument()
  })

  test('trocar por outro comboio: explica, pede confirmação e só então ativa a troca (ADR-083)', async () => {
    const s = abrir('cp', { 'GET /tickets/cp/passe': () => [200, PASSE], 'GET /tickets/cp/futuros': () => [200, FUTUROS], 'POST /actions/bilhetes.troca_armar': () => [200, { resultado: { id: 104 } }] },
      { ...DADOS, favoritos: [{ id: 8, apelido: 'Tarde', comboio: 731, origem: 'Lisboa Oriente', destino: 'Aveiro', hora: '17:30' }, { id: 9, apelido: 'Manhã', comboio: 520, origem: 'Aveiro', destino: 'Lisboa Oriente', hora: '06:45' }] })
    await userEvent.click(await screen.findByRole('button', { name: 'Trocar por outro comboio' }))
    expect(screen.getByText(/cancela este bilhete/)).toBeInTheDocument()
    const sel = screen.getByLabelText('Favoritos para a troca')
    expect(within(sel).queryByText(/Manhã/)).not.toBeInTheDocument()                    // só favoritos do mesmo sentido
    await userEvent.selectOptions(sel, '0')
    expect(screen.getByLabelText('Comboio novo')).toHaveValue('731')
    await userEvent.click(screen.getByRole('button', { name: 'Continuar' }))
    expect(s.pedidos.some((p) => p.caminho === '/actions/bilhetes.troca_armar')).toBe(false)           // ainda não ativou nada
    expect(screen.getByText(/só é cancelado depois de o lugar no comboio 731 estar reservado/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Ativar troca' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/bilhetes.troca_armar')).toEqual({ params: { venda: 77, comboio: 731, hora: '17:30' }, confirmado: true }))
  })

  test('trocar: a hora de partida do comboio novo vem da CP e a troca pode ser agendada para uma data e hora (ADR-086)', async () => {
    const s = abrir('cp', { 'GET /tickets/cp/passe': () => [200, PASSE], 'GET /tickets/cp/futuros': () => [200, FUTUROS],
      'GET /tickets/timetable?comboio=731&data=2026-10-01&origem=Lisboa+Oriente&destino=Aveiro': () => [200, { estado: 'preenchido', mensagem: 'Hora da partida do comboio (Lisboa Oriente) às 17:30.', sugestaoHora: '17:30' }],
      'POST /actions/bilhetes.troca_armar': () => [200, { resultado: { id: 104 } }] })
    await userEvent.click(await screen.findByRole('button', { name: 'Trocar por outro comboio' }))
    await userEvent.type(screen.getByLabelText('Comboio novo'), '731')
    await waitFor(() => expect(screen.getByLabelText('Hora de partida do comboio novo')).toHaveValue('17:30'))      // preenchida pela CP, sem escrever
    fireEvent.change(screen.getByLabelText(/Começar a tentar em/), { target: { value: '2026-10-01T08:00' } })
    await userEvent.click(screen.getByRole('button', { name: 'Continuar' }))
    expect(screen.getByText(/Começo a tentar em 01\/10 às 08:00/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Ativar troca' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/bilhetes.troca_armar')).toEqual({ params: { venda: 77, comboio: 731, hora: '17:30', inicio: '2026-10-01T08:00' }, confirmado: true }))
  })

  test('mesmo comboio: o botão ativa, explica que serve para ter o desconto, avisa se já custa 0 € e a devolução pode ser simulada sem cancelar (ADR-088)', async () => {
    const s = abrir('cp', { 'GET /tickets/cp/passe': () => [200, PASSE], 'GET /tickets/cp/futuros': () => [200, FUTUROS],
      'GET /tickets/cp/simular?venda=77': () => [200, { venda: 77, cancelavel: true, valor: '€ 6,10', motivo: '' }] })
    await userEvent.click(await screen.findByRole('button', { name: 'Trocar por outro comboio' }))
    await userEvent.type(screen.getByLabelText('Comboio novo'), '723')                  // o comboio do próprio bilhete
    fireEvent.change(screen.getByLabelText('Hora de partida do comboio novo'), { target: { value: '19:39' } })
    expect(screen.getByText(/Mesmo comboio: serve para trocar um bilhete comprado/)).toBeInTheDocument()
    expect(screen.getByText(/já custa 0 €/)).toBeInTheDocument()                          // o bilhete de teste custa 0
    expect(screen.getByRole('button', { name: 'Continuar' })).toBeEnabled()
    await userEvent.click(screen.getByRole('button', { name: 'Simular devolução' }))
    expect(await screen.findByText(/reembolso previsto: € 6,10\. Nada foi cancelado/)).toBeInTheDocument()
    expect(s.pedidos.some((p) => p.caminho.startsWith('/actions/'))).toBe(false)         // simular não executa nenhuma ação
  })

  test('uma troca ativa aparece nos Pedidos e pode ser desativada', async () => {
    const troca = { ...DADOS.pedidos[0], id: 104, comboio: 731, hora: '17:30', retry: true, estado: 'PENDENTE', trocaVenda: 77, trocaReferencia: 'CP-X', trocaAntecedenciaMin: 30 }
    const s = abrir('pedidos', { 'POST /actions/bilhetes.troca_desarmar': () => [200, { resultado: { estado: 'DESARMADO' } }] }, { ...DADOS, pedidos: [troca] })
    expect(await screen.findByText(/Troca: cancela o bilhete CP-X quando houver lugar/)).toBeInTheDocument()
    expect(screen.queryByLabelText('Minutos entre tentativas')).not.toBeInTheDocument()               // uma troca tem o seu ritmo (15 min)
    await userEvent.click(screen.getByRole('button', { name: 'Desativar troca' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/bilhetes.troca_desarmar')).toEqual({ params: { pedido: 104 } }))
  })

  test('um erro da CP aparece com a mensagem e deixa tentar de novo', async () => {
    abrir('cp', { 'GET /tickets/cp/passe': () => [409, { erro: { codigo: 'cp_credenciais', mensagem: 'faltam dados de Davi: NIF' } }], 'GET /tickets/cp/futuros': () => [200, { bilhetes: [] }] })
    expect(await screen.findByText(/faltam dados de Davi/)).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Tentar de novo' }).length).toBeGreaterThan(0)
  })
})
