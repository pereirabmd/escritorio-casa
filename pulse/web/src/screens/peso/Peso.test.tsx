import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App } from '../../App'
import { servidorFalso, UTILIZADOR, type Rotas } from '../../test/api-mock'
import { normalizarAtividade } from '../../lib/peso'
import { mediaMovel } from '../../components/LineChart'

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '')

const REGISTOS = [
  { id: 1, quando: '2026-09-01 08:00:00', peso: 110, nota: '' },
  { id: 2, quando: '2026-09-15 08:00:00', peso: 105, nota: 'jejum' },
  { id: 3, quando: '2026-09-30 07:30:00', peso: 100, nota: '' },
]
const RESUMO = {
  analise: { tendencia: { kgSemana: -1.5, dias: 29, pontos: 3 }, mensal: null, melhorSemana: { diff: -2.5 }, piorSemana: { diff: -1 } },
  previsao: { estado: 'ok', data: '2026-11-10', kgSemana: 1.75 },
  ultimo: { id: 3, quando: '2026-09-30 07:30:00', peso: 100 }, anterior: { quando: '2026-09-15 08:00:00', peso: 105, diferenca: -5 },
  sequenciaDias: 2, novoMinimo: true, controlo: 'dentro', progresso: { pct: 50, inicial: 110, alvo: 90 }, totalPerdido: 10,
  ritmo: { kgDia: 0.345, kgSemana: 2.41 }, faltam: { kg: 10, atingido: false }, imc: { valor: 30.86, classe: 'Obesidade grau I' }, gastoDiario: 2900,
  minimo: 100, maximo: 110, registos: 3,
}
const PESO = { registos: REGISTOS, config: { altura: 180, pesoAlvo: 90, atividade: 1.45, diaControlo: 1 }, resumo: RESUMO }
const OK: [number, unknown] = [200, { resultado: {} }]

function abrir(extra: Rotas = {}, peso: unknown = PESO) {
  window.history.pushState({}, '', `${BASE}/peso`)
  const s = servidorFalso({ 'GET /auth/me': () => [200, { utilizador: UTILIZADOR }], 'GET /weight': () => [200, peso], ...extra })
  render(<App />)
  return s
}
const tab = (nome: string) => screen.findByRole('tab', { name: nome })

afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })

test('lib: nível de atividade normalizado como na app dedicada', () => {
  expect([undefined, 1, 2, 3, 4, 1.55, 1.7, 9].map(normalizarAtividade)).toEqual([1.2, 1.2, 1.45, 1.7, 1.7, 1.45, 1.7, 1.2])
})

test('lib: média móvel de 7 dias', () => {
  const d = 86400000
  const m = mediaMovel([{ t: 0, v: 10 }, { t: d, v: 12 }, { t: 10 * d, v: 20 }], 7)
  expect(m.map((p) => p.v)).toEqual([10, 11, 20])
})

test('Mais leva ao Peso', async () => {
  window.history.pushState({}, '', `${BASE}/mais`)
  servidorFalso({ 'GET /auth/me': () => [200, { utilizador: UTILIZADOR }], 'GET /weight': () => [200, PESO] })
  render(<App />)
  await userEvent.click(await screen.findByRole('link', { name: /Peso/ }))
  expect(await screen.findByRole('heading', { name: 'Peso' })).toBeInTheDocument()
})

describe('Resumo', () => {
  test('mostra peso atual, diferença, etiquetas, objetivo, IMC, gasto e análise', async () => {
    abrir()
    expect(await screen.findByText('100,0 kg', { selector: '.t-metric' })).toBeInTheDocument()
    expect(screen.getByText(/↓ 5,0 kg desde 15\/09\/2026/)).toBeInTheDocument()
    expect(screen.getByText('Sequência de 2 dias')).toBeInTheDocument()
    expect(screen.getByText('Novo mínimo')).toBeInTheDocument()
    expect(screen.getByText('Dentro do controlo')).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'Progresso para o peso alvo' })).toHaveAttribute('value', '50')
    expect(screen.getByText('Total perdido').nextSibling).toHaveTextContent('10,0 kg')
    expect(screen.getByText('Ritmo semanal').nextSibling).toHaveTextContent('−2,41 kg')
    expect(screen.getByText('30,9')).toBeInTheDocument()
    expect(screen.getByText('Obesidade grau I')).toBeInTheDocument()
    expect(screen.getByText('2900 kcal')).toBeInTheDocument()
    expect(screen.getByText('100,0 / 110,0')).toBeInTheDocument()
    expect(screen.getByText(/objetivo previsto para 10\/11\/2026/)).toBeInTheDocument()
    expect(screen.getByText('1,50 kg/sem de perda')).toBeInTheDocument()
    expect(screen.getByText('−2,5 kg')).toBeInTheDocument()
  })

  test('sem registos e sem configuração: mensagens úteis', async () => {
    abrir({}, { registos: [], config: {}, resumo: { analise: { tendencia: null, mensal: null, melhorSemana: null, piorSemana: null }, previsao: { estado: 'poucos_registos' }, ultimo: null } })
    expect(await screen.findByText(/Ainda sem registos — regista o teu primeiro peso/)).toBeInTheDocument()
  })

  test('sem alvo/altura: diz o que falta configurar', async () => {
    const r = { ...RESUMO, progresso: null, faltam: null, imc: null, gastoDiario: null, previsao: { estado: 'sem_alvo' }, analise: { tendencia: null, mensal: null, melhorSemana: null, piorSemana: null }, controlo: null }
    abrir({}, { ...PESO, config: {}, resumo: r })
    expect(await screen.findByText('Define um peso alvo em Configuração para veres o progresso.')).toBeInTheDocument()
    expect(screen.getByText('Define a altura em Configuração')).toBeInTheDocument()
    expect(screen.getByText('Precisa de altura, nascimento e sexo')).toBeInTheDocument()
    expect(screen.getByText(/Regista pesos em pelo menos 3 semanas/)).toBeInTheDocument()
  })
})

describe('Gráfico', () => {
  test('mostra a série com descrição acessível e muda de período', async () => {
    abrir()
    await userEvent.click(await tab('Gráfico'))
    const g = await screen.findByRole('img', { name: /3 registos, de 110,0 kg em 01\/09\/2026 a 100,0 kg em 30\/09\/2026/ })
    expect(g.querySelectorAll('circle').length).toBe(3)
    await userEvent.click(screen.getByRole('button', { name: '7 dias' }))      // rótulo curto «7 d», nome acessível completo
    expect(screen.getByRole('img', { name: /1 registos|1 registo/ })).toBeInTheDocument()
    expect(screen.getByText(/Peso alvo \(90,0 kg\)/)).toBeInTheDocument()
  })
})

describe('Registos', () => {
  test('lista o mais recente primeiro; registar leva o cid e a nota', async () => {
    const { pedidos } = abrir({ 'POST /actions/peso.registar': () => OK })
    await userEvent.click(await tab('Registos'))
    const linhas = within(screen.getByRole('region', { name: 'Lista de registos' })).getAllByRole('listitem')
    expect(linhas[0]).toHaveTextContent('100,0 kg')
    expect(linhas[2]).toHaveTextContent('110,0 kg')
    const campo = screen.getByLabelText('Peso em quilogramas', { selector: '#peso-novo' })
    expect(campo).toHaveValue('100')
    await userEvent.clear(campo); await userEvent.type(campo, '99,4')
    await userEvent.type(screen.getByLabelText('Nota (opcional)'), 'manhã')
    await userEvent.click(screen.getByRole('button', { name: 'Registar' }))
    expect(await screen.findByText('Peso registado.')).toBeInTheDocument()
    const c = pedidos.find((p) => p.caminho === '/actions/peso.registar')!.corpo as { params: Record<string, unknown> }
    expect(c.params).toMatchObject({ peso: 99.4, nota: 'manhã' })
    expect(c.params.cid).toMatch(/^[A-Za-z0-9-]{8,64}$/)
  })

  test('editar envia o registo completo', async () => {
    const { pedidos } = abrir({ 'POST /actions/peso.editar': () => OK })
    await userEvent.click(await tab('Registos'))
    await userEvent.click(screen.getByRole('button', { name: 'Editar registo de 15/09/2026' }))
    const form = screen.getByRole('form', { name: 'Editar registo de 15/09/2026' })
    const peso = within(form).getByLabelText('Peso em quilogramas')
    await userEvent.clear(peso); await userEvent.type(peso, '104,5')
    await userEvent.click(within(form).getByRole('button', { name: 'Guardar' }))
    await waitFor(() => expect(pedidos.some((p) => p.caminho === '/actions/peso.editar')).toBe(true))
    expect(pedidos.find((p) => p.caminho === '/actions/peso.editar')!.corpo).toEqual({ params: { registo: 2, quando: '2026-09-15 08:00:00', peso: 104.5, nota: 'jejum' } })
  })

  test('eliminar pede confirmação, confirma com o servidor e permite desfazer com a data original', async () => {
    const { pedidos } = abrir({ 'POST /actions/peso.eliminar': () => [200, { resultado: { id: 2, quando: '2026-09-15 08:00:00', peso: 105, nota: 'jejum' } }], 'POST /actions/peso.registar': () => OK })
    await userEvent.click(await tab('Registos'))
    await userEvent.click(screen.getByRole('button', { name: 'Eliminar registo de 15/09/2026' }))
    expect(pedidos.some((p) => p.caminho === '/actions/peso.eliminar')).toBe(false)          // ainda só a pergunta
    await userEvent.click(within(screen.getByRole('group', { name: 'Eliminar registo de 15/09/2026' })).getByRole('button', { name: 'Eliminar' }))
    expect(await screen.findByText('Registo eliminado.')).toBeInTheDocument()
    expect(pedidos.find((p) => p.caminho === '/actions/peso.eliminar')!.corpo).toEqual({ params: { registo: 2 }, confirmado: true })
    await userEvent.click(screen.getByRole('button', { name: 'Desfazer' }))
    await waitFor(() => expect(pedidos.some((p) => p.caminho === '/actions/peso.registar')).toBe(true))
    expect(pedidos.find((p) => p.caminho === '/actions/peso.registar')!.corpo).toEqual({ params: { peso: 105, quando: '2026-09-15 08:00:00', nota: 'jejum' } })
  })

  test('cancelar a eliminação não escreve nada', async () => {
    const { pedidos } = abrir()
    await userEvent.click(await tab('Registos'))
    await userEvent.click(screen.getByRole('button', { name: 'Eliminar registo de 15/09/2026' }))
    await userEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(pedidos.filter((p) => p.metodo !== 'GET')).toEqual([])
  })
})

describe('Configuração', () => {
  test('traz os valores atuais e guarda tudo (campos vazios apagam)', async () => {
    const { pedidos } = abrir({ 'POST /actions/peso.configurar': () => OK })
    await userEvent.click(await tab('Configuração'))
    expect(screen.getByLabelText('Altura (cm)')).toHaveValue('180')
    expect(screen.getByLabelText('Peso alvo (kg)')).toHaveValue('90')
    expect(screen.getByLabelText('Nível de atividade')).toHaveValue('1.45')
    await userEvent.clear(screen.getByLabelText('Peso alvo (kg)'))
    await userEvent.selectOptions(screen.getByLabelText('Sexo'), 'F')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar configuração' }))
    expect(await screen.findByText('Configuração guardada.')).toBeInTheDocument()
    expect(pedidos.find((p) => p.caminho === '/actions/peso.configurar')!.corpo).toEqual({ params: {
      altura: 180, pesoAlvo: null, pesoMin: null, pesoMax: null, nascimento: null, sexo: 'F', atividade: 1.45, diaControlo: 1 } })
  })

  test('valida no cliente: mínimo maior do que o máximo e valores inválidos', async () => {
    const { pedidos } = abrir()
    await userEvent.click(await tab('Configuração'))
    await userEvent.type(screen.getByLabelText('Peso mínimo de controlo (kg)'), '100')
    await userEvent.type(screen.getByLabelText('Peso máximo de controlo (kg)'), '90')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar configuração' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('O peso mínimo não pode ser maior do que o máximo.')
    await userEvent.clear(screen.getByLabelText('Peso mínimo de controlo (kg)')); await userEvent.clear(screen.getByLabelText('Peso máximo de controlo (kg)'))
    await userEvent.clear(screen.getByLabelText('Altura (cm)')); await userEvent.type(screen.getByLabelText('Altura (cm)'), 'abc')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar configuração' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Valor inválido em Altura.')
    expect(pedidos.filter((p) => p.metodo !== 'GET')).toEqual([])
  })
})

describe('estados', () => {
  test('erro a carregar tem «Tentar de novo» e funciona', async () => {
    let falha = true
    abrir({ 'GET /weight': () => (falha ? [503, { erro: { codigo: 'modulo_indisponivel', mensagem: 'x' } }] : [200, PESO]) })
    expect(await screen.findByRole('alert')).toHaveTextContent('não está disponível de momento')
    falha = false
    await userEvent.click(screen.getByRole('button', { name: 'Tentar de novo' }))
    expect(await screen.findByText('100,0 kg', { selector: '.t-metric' })).toBeInTheDocument()
  })

  test('sem acesso ao módulo: mensagem do servidor', async () => {
    abrir({ 'GET /weight': () => [403, { erro: { codigo: 'sem_acesso', mensagem: 'sem acesso a esta aplicação' } }] })
    expect(await screen.findByRole('alert')).toHaveTextContent('sem acesso a esta aplicação')
  })

  test('tablist: separadores com estado selecionado', async () => {
    abrir()
    const r = await tab('Resumo')
    expect(r).toHaveAttribute('aria-selected', 'true')
    await userEvent.click(await tab('Registos'))
    expect(screen.getByRole('tab', { name: 'Registos' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'Resumo' })).toHaveAttribute('aria-selected', 'false')
  })
})

test('ligação direta a um separador: /peso?aba=registos', async () => {
  window.history.pushState({}, '', `${BASE}/peso?aba=registos`)
  servidorFalso({ 'GET /auth/me': () => [200, { utilizador: UTILIZADOR }], 'GET /weight': () => [200, PESO] })
  render(<App />)
  expect(await screen.findByRole('tab', { name: 'Registos' })).toHaveAttribute('aria-selected', 'true')
  expect(await screen.findByRole('form', { name: 'Registar peso' })).toBeInTheDocument()
})
