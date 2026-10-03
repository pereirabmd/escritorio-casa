import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App } from '../App'
import { HOJE, servidorFalso, UTILIZADOR, type Rotas } from '../test/api-mock'

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '')

const dia = (i: number, extra = {}) => ({ data: `2026-10-0${2 + i}`, diaSemana: ['sexta', 'sábado', 'domingo', 'segunda', 'terça', 'quarta'][i], diaCurto: 'x', icone: 'chuva', descricao: 'Chuva', max: 20 - i, min: 12 - i, chuva: 60, nascer: '07:41', poer: '19:12', ...extra })
const PREV = (extra = {}) => ({
  localizacao: 'omissao', atualizadoEm: '2026-10-02T15:20',
  agora: { temp: 17.4, icone: 'nublado', descricao: 'Nublado', vento: 14, dia: true },
  hoje: dia(0, { icone: 'nublado', descricao: 'Nublado', chuva: 10 }),
  horas: [{ hora: '15:00', dia: '2026-10-02', temp: 17.4, chuva: 0, icone: 'nublado' }, { hora: '16:00', dia: '2026-10-02', temp: 16.9, chuva: 40, icone: 'chuva' }],
  dias: [dia(0, { icone: 'nublado', descricao: 'Nublado', chuva: 10 }), dia(1), dia(2)], ...extra,
})

function abrir(caminho: string, extra: Rotas = {}) {
  window.history.pushState({}, '', `${BASE}${caminho}`)
  const s = servidorFalso({ 'GET /auth/me': () => [200, { utilizador: UTILIZADOR }], 'GET /dashboard/today': () => [200, HOJE], ...extra })
  render(<App />)
  return s
}

afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })

describe('cartão do tempo no Hoje', () => {
  test('aparece à direita da saudação com a temperatura, máxima, mínima e chuva, e abre o ecrã Tempo', async () => {
    abrir('/hoje', { 'GET /weather': () => [200, PREV()] })
    const chip = await screen.findByRole('link', { name: /Tempo: Nublado, 17°, máxima 20°, mínima 12°, chuva 10%/ })
    expect(within(chip).getByText('17°')).toBeInTheDocument()
    await userEvent.click(chip)
    expect(await screen.findByRole('heading', { name: 'Tempo' })).toBeInTheDocument()
    expect(window.location.pathname).toBe(`${BASE}/tempo`)
  })

  test('se a previsão falhar o cartão não aparece e o resto do Hoje funciona', async () => {
    abrir('/hoje', { 'GET /weather': () => [503, { erro: { codigo: 'tempo_indisponivel', mensagem: 'x' } }] })
    expect(await screen.findByText('Limpar WC')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Tempo:/ })).not.toBeInTheDocument()
  })
})

describe('ecrã Tempo', () => {
  test('mostra agora, próximas horas e dias, e diz que o local é por omissão (Aveiro)', async () => {
    abrir('/tempo', { 'GET /weather': () => [200, PREV()] })
    expect(await screen.findByText('Nublado', { selector: '.t-body' })).toBeInTheDocument()
    expect(screen.getByText(/Local por omissão: Aveiro/)).toBeInTheDocument()
    const horas = screen.getByRole('region', { name: 'Próximas 24 horas' })
    expect(within(horas).getByText('16:00')).toBeInTheDocument(); expect(within(horas).getByText('40%')).toBeInTheDocument()
    const dias = screen.getByRole('region', { name: 'Próximos dias' })
    expect(within(dias).getAllByRole('listitem')).toHaveLength(3); expect(within(dias).getByText('sábado')).toBeInTheDocument()
    expect(screen.getByText(/Previsão da Open-Meteo, atualizada às 15:20/)).toBeInTheDocument()
  })

  test('com a localização do aparelho pede a previsão para essas coordenadas e não mostra a nota de omissão', async () => {
    vi.stubGlobal('navigator', { ...navigator, geolocation: { getCurrentPosition: (ok: (p: unknown) => void) => ok({ coords: { latitude: 38.7412, longitude: -9.1527 } }) } })
    const s = abrir('/tempo', { 'GET /weather?lat=38.74&lon=-9.15': () => [200, PREV({ localizacao: 'dispositivo' })] })
    expect(await screen.findByRole('region', { name: 'Agora' })).toBeInTheDocument()
    expect(screen.queryByText(/Local por omissão/)).not.toBeInTheDocument()
    expect(s.pedidos.some((p) => p.caminho === '/weather?lat=38.74&lon=-9.15')).toBe(true)                 // coordenadas arredondadas a 2 casas
    expect(localStorage.getItem('pulse.posicao')).toBe(JSON.stringify({ lat: 38.74, lon: -9.15 }))
  })
})
