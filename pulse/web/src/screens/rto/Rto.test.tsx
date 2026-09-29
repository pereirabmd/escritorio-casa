import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App } from '../../App'
import { servidorFalso, UTILIZADOR, type Rotas } from '../../test/api-mock'
import { marcaDaCelula, semanasDoMes, textoHoje, textoProximaMudanca } from '../../lib/rto'

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '')
const OK: [number, unknown] = [200, { resultado: {} }]

const NOTAS = [
  { id: 1, dataInicio: '2026-09-28', dataFim: '2026-10-02', categoria: 'Férias', descricao: 'Páscoa' },
  { id: 2, dataInicio: '2026-09-20', dataFim: '2026-09-21', categoria: 'Astreinte', descricao: '' },
  { id: 3, dataInicio: '2026-10-14', dataFim: '2026-10-14', categoria: 'Validação', descricao: '' },
]
const RTO = {
  ano: 2026, quotaAnual: 120,
  dias: { '2026-09-01': 'T', '2026-09-02': 'C', '2026-09-03': 'C', '2026-08-31': 'T', '2026-08-30': 'C' },
  notas: NOTAS,
  feriados: { '2026-10-05': 'Implantação da República', '2026-04-03': 'Sexta-feira Santa' },
  ferias: ['2026-09-28', '2026-09-29', '2026-09-30', '2026-10-01', '2026-10-02'], astreinte: ['2026-09-20', '2026-09-21'], suspensao: [],
  marcasNotas: { '2026-09-28': 'F', '2026-09-29': 'F', '2026-09-30': 'F', '2026-10-01': 'F', '2026-10-02': 'F', '2026-09-20': 'A', '2026-09-21': 'A' },
  totais: { T: 40, C: 55, CCondicional: 53, creditosAstreinte: 2, decorridos: 272, diasAno: 365, quotaAnual: 120, quotaProRata: 89.4, saldo: 34.4, saldoCondicional: 36.4, pctQuota: 46 },
  mensal: Array.from({ length: 12 }, (_, i) => (i === 8 ? { t: 1, c: 2 } : i === 7 ? { t: 1, c: 1 } : { t: 0, c: 0 })),
  dezembroAnterior: { t: 0, c: 0 },
  hoje: { estado: 'ferias', astreinte: false },
  proximaMudanca: { tipo: 'feriado', dias: 5, nome: 'Implantação da República', data: '2026-10-05' },
}

function abrir(extra: Rotas = {}, rto: unknown = RTO, caminho = '/rto') {
  window.history.pushState({}, '', `${BASE}${caminho}`)
  const s = servidorFalso({ 'GET /auth/me': () => [200, { utilizador: UTILIZADOR }], 'GET /rto?ano=2026': () => [200, rto], ...extra })
  render(<App />)
  return s
}
const tab = (nome: string) => screen.findByRole('tab', { name: nome })
const dia = (texto: RegExp) => screen.findByRole('gridcell', { name: texto })
async function ativarAdmin() {
  await userEvent.click(await screen.findByRole('button', { name: 'Administrador' }))
  await userEvent.click(within(screen.getByRole('alertdialog', { name: 'Ativar modo administrador' })).getByRole('button', { name: 'Ativar' }))
}

beforeEach(() => { vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-09-30T10:00:00')) })
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); localStorage.clear() })

describe('lib', () => {
  test('semanas do mês começam à segunda-feira', () => {
    const s = semanasDoMes(2026, 8)                       // setembro de 2026 começa a uma terça
    expect(s[0][0]).toBeNull()
    expect(s[0][1]).toBe('2026-09-01')
    expect(s.flat().filter(Boolean).length).toBe(30)
    expect(s.every((sem) => sem.length === 7)).toBe(true)
  })
  test('o que a célula mostra: T/C, feriado, astreinte+feriado, letra da nota', () => {
    const d = { ...RTO, dias: { '2026-10-05': 'C' }, feriados: { '2026-10-05': 'X', '2026-10-06': 'Y', '2026-10-07': 'Z' }, marcasNotas: { '2026-10-06': 'A', '2026-09-28': 'F' } } as never
    expect(marcaDaCelula(d, '2026-10-05')).toEqual({ texto: 'C', classe: 'C' })
    expect(marcaDaCelula(d, '2026-10-06')).toEqual({ texto: 'Af', classe: 'A' })
    expect(marcaDaCelula(d, '2026-10-07')).toEqual({ texto: 'f', classe: 'holiday' })
    expect(marcaDaCelula(d, '2026-09-28')).toEqual({ texto: 'F', classe: 'F' })
    expect(marcaDaCelula(d, '2026-11-11')).toEqual({ texto: '', classe: '' })
  })
  test('textos de hoje e da próxima mudança', () => {
    expect(textoHoje({ estado: 'por_definir', astreinte: false })).toBe('Ainda por definir')
    expect(textoProximaMudanca({ tipo: 'feriado', dias: 1, nome: 'Natal', data: 'x' })).toBe('Feriado amanhã — Natal')
    expect(textoProximaMudanca({ tipo: 'feriado', dias: 5, nome: 'Natal', data: 'x' })).toBe('Feriado a 5 dias — Natal')
    expect(textoProximaMudanca({ tipo: 'ferias', dias: 1, data: 'x' })).toBe('Férias a começar amanhã')
    expect(textoProximaMudanca({ tipo: 'ferias', dias: 9, data: 'x' })).toBe('Férias a começar daqui a 9 dias')
  })
})

describe('Calendário', () => {
  test('mostra hoje, próxima mudança, o mês e as marcas', async () => {
    abrir()
    expect(await screen.findByRole('heading', { name: 'Hoje: Férias' })).toBeInTheDocument()
    expect(screen.getByText('Feriado a 5 dias — Implantação da República')).toBeInTheDocument()
    expect(screen.getByRole('grid', { name: 'Setembro 2026' })).toBeInTheDocument()
    expect(await dia(/^1 de Setembro: escritório/)).toHaveAttribute('data-marca', 'T')
    expect(await dia(/^2 de Setembro: casa/)).toHaveAttribute('data-marca', 'C')
    expect(await dia(/^28 de Setembro: férias/)).toHaveAttribute('data-marca', 'F')
    expect(await dia(/^20 de Setembro: astreinte/)).toHaveAttribute('data-fds', 'true')
    expect((await dia(/^30 de Setembro/)).getAttribute('data-hoje')).toBe('true')
  })

  test('totais, saldo com semáforo e explicação do cálculo', async () => {
    abrir()
    const totais = await screen.findByRole('region', { name: 'Totais de 2026' })
    expect(within(totais).getByText('40')).toBeInTheDocument()
    expect(within(totais).getByText('46% da quota anual')).toBeInTheDocument()
    expect(within(totais).getByText('89,4')).toBeInTheDocument()
    expect(within(totais).getByText('Saldo', { selector: '.t-meta' }).closest('.stat')).toHaveAttribute('data-tier', 'ok')
    expect(within(totais).getByText('Saldo condicional', { selector: '.t-meta' }).nextSibling).toHaveTextContent('36,4')
    await userEvent.click(within(totais).getByText('Como se calcula o saldo'))
    expect(within(totais).getByText('120 × 272/365 = 89,4')).toBeInTheDocument()
    expect(within(totais).getByText('89,4 − 55 = 34,4')).toBeInTheDocument()
  })

  test('saldo negativo fica a vermelho (tier bad) e baixo a amarelo', async () => {
    abrir({}, { ...RTO, totais: { ...RTO.totais, saldo: -3.2, saldoCondicional: 4 } })
    const totais = await screen.findByRole('region', { name: 'Totais de 2026' })
    expect(within(totais).getByText('Saldo', { selector: '.t-meta' }).closest('.stat')).toHaveAttribute('data-tier', 'bad')
    expect(within(totais).getByText('Saldo condicional', { selector: '.t-meta' }).closest('.stat')).toHaveAttribute('data-tier', 'warn')
  })

  test('comparação com o mês anterior', async () => {
    abrir()
    const c = await screen.findByRole('region', { name: 'Comparação com o mês anterior' })
    expect(within(c).getByRole('heading')).toHaveTextContent('Este mês vs Agosto')
    expect(within(c).getByText('Casa').nextSibling).toHaveTextContent('↑ 1 dia')
    expect(within(c).getByText('Escritório').nextSibling).toHaveTextContent('sem alteração')
  })

  test('modo normal: dias passados e fins de semana bloqueados, com a explicação; dias úteis futuros livres', async () => {
    const { pedidos } = abrir({ 'POST /actions/rto.marcar_dia': () => OK })
    await userEvent.click(await dia(/^9 de Setembro/))                                    // passado
    let painel = screen.getByRole('group', { name: 'Dia 09/09/2026' })
    for (const nome of ['Escritório', 'Casa', 'Férias']) expect(within(painel).getByRole('button', { name: nome })).toBeDisabled()
    expect(within(painel).getByText(/bloqueado\. Ativa o modo administrador/)).toBeInTheDocument()
    await userEvent.click(await dia(/^12 de Setembro/))                                   // sábado (e passado)
    expect(within(screen.getByRole('group', { name: 'Dia 12/09/2026' })).getByRole('button', { name: 'Casa' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Mês seguinte' }))
    await userEvent.click(await dia(/^6 de Outubro/))                                     // terça futura
    painel = screen.getByRole('group', { name: 'Dia 06/10/2026' })
    await userEvent.click(within(painel).getByRole('button', { name: 'Escritório' }))
    await waitFor(() => expect(pedidos.some((p) => p.caminho === '/actions/rto.marcar_dia')).toBe(true))
    expect(pedidos.find((p) => p.caminho === '/actions/rto.marcar_dia')!.corpo).toEqual({ params: { data: '2026-10-06', marca: 'T', admin: false } })
    await userEvent.click(await dia(/^10 de Outubro/))                                    // sábado futuro
    expect(within(screen.getByRole('group', { name: 'Dia 10/10/2026' })).getByRole('button', { name: 'Escritório' })).toBeDisabled()
  })

  test('modo administrador: pede confirmação, mostra o aviso e liberta fins de semana e dias passados', async () => {
    const { pedidos } = abrir({ 'POST /actions/rto.marcar_dia': () => OK })
    await userEvent.click(await screen.findByRole('button', { name: 'Administrador' }))
    await userEvent.click(within(screen.getByRole('alertdialog', { name: 'Ativar modo administrador' })).getByRole('button', { name: 'Cancelar' }))
    expect(screen.queryByText(/Modo administrador ativo/)).not.toBeInTheDocument()       // cancelar mantém o modo normal
    await ativarAdmin()
    expect(screen.getByText(/Modo administrador ativo/)).toBeInTheDocument()
    expect(screen.getByText('Sem restrições de data')).toBeInTheDocument()
    await userEvent.click(await dia(/^12 de Setembro/))                                   // sábado passado
    const painel = screen.getByRole('group', { name: 'Dia 12/09/2026' })
    await userEvent.click(within(painel).getByRole('button', { name: 'Casa' }))
    await waitFor(() => expect(pedidos.some((p) => p.caminho === '/actions/rto.marcar_dia')).toBe(true))
    expect(pedidos.find((p) => p.caminho === '/actions/rto.marcar_dia')!.corpo).toEqual({ params: { data: '2026-09-12', marca: 'C', admin: true } })
    await userEvent.click(screen.getByRole('button', { name: 'Desativar' }))
    expect(screen.queryByText(/Modo administrador ativo/)).not.toBeInTheDocument()
    expect(within(screen.getByRole('group', { name: 'Dia 12/09/2026' })).getByRole('button', { name: 'Casa' })).toBeDisabled()
  })

  test('dia com marca: «Limpar»; dia de férias: T/C desativados e «Remover férias»', async () => {
    const { pedidos } = abrir({ 'POST /actions/rto.marcar_dia': () => OK, 'POST /actions/rto.ferias_dia': () => OK })
    await ativarAdmin()
    await userEvent.click(await dia(/^2 de Setembro/))
    await userEvent.click(within(screen.getByRole('group', { name: 'Dia 02/09/2026' })).getByRole('button', { name: 'Limpar' }))
    await waitFor(() => expect(pedidos.some((p) => p.caminho === '/actions/rto.marcar_dia')).toBe(true))
    expect(pedidos.find((p) => p.caminho === '/actions/rto.marcar_dia')!.corpo).toEqual({ params: { data: '2026-09-02', marca: '', admin: true } })
    await userEvent.click(await dia(/^29 de Setembro/))
    const painel = screen.getByRole('group', { name: 'Dia 29/09/2026' })
    expect(within(painel).getByRole('button', { name: 'Escritório' })).toBeDisabled()
    expect(within(painel).getByText('Dia de férias: não conta para o RTO.')).toBeInTheDocument()
    expect(within(painel).getByText(/Páscoa/)).toBeInTheDocument()
    await userEvent.click(within(painel).getByRole('button', { name: 'Remover férias' }))
    expect(await screen.findByText('Dia de férias removido.')).toBeInTheDocument()
    expect(pedidos.find((p) => p.caminho === '/actions/rto.ferias_dia')!.corpo).toEqual({ params: { data: '2026-09-29', admin: true } })
  })

  test('marcar férias num dia útil futuro oferece desfazer (repete a ação, que alterna)', async () => {
    const { pedidos } = abrir({ 'POST /actions/rto.ferias_dia': () => OK })
    await userEvent.click(await screen.findByRole('button', { name: 'Mês seguinte' }))
    await userEvent.click(await dia(/^6 de Outubro/))
    await userEvent.click(within(screen.getByRole('group', { name: 'Dia 06/10/2026' })).getByRole('button', { name: 'Férias' }))
    expect(await screen.findByText('Dia marcado como férias.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Desfazer' }))
    await waitFor(() => expect(pedidos.filter((p) => p.caminho === '/actions/rto.ferias_dia').length).toBe(2))
  })

  test('feriado aparece na informação do dia', async () => {
    abrir({ 'GET /rto?ano=2026': () => [200, RTO] })
    await userEvent.click(await screen.findByRole('button', { name: 'Mês seguinte' }))
    await userEvent.click(await dia(/^5 de Outubro: feriado/))
    expect(within(screen.getByRole('group', { name: 'Dia 05/10/2026' })).getByText(/Implantação da República/)).toBeInTheDocument()
  })

  test('navegar para o ano seguinte pede os dados desse ano; «Hoje» volta ao mês atual', async () => {
    const pedidos = abrir({ 'GET /rto?ano=2027': () => [200, { ...RTO, ano: 2027 }] }).pedidos
    await screen.findByRole('grid', { name: 'Setembro 2026' })
    for (let i = 0; i < 4; i++) await userEvent.click(screen.getByRole('button', { name: 'Mês seguinte' }))     // Out, Nov, Dez, Jan
    expect(await screen.findByRole('grid', { name: 'Janeiro 2027' })).toBeInTheDocument()
    await waitFor(() => expect(pedidos.some((p) => p.caminho === '/rto?ano=2027')).toBe(true))
    await userEvent.click(screen.getByRole('button', { name: 'Hoje' }))
    expect(await screen.findByRole('grid', { name: 'Setembro 2026' })).toBeInTheDocument()
  })
})

describe('Ano', () => {
  test('12 meses com resumo e abrir um mês no calendário', async () => {
    abrir()
    await userEvent.click(await tab('Ano'))
    expect(screen.getAllByRole('button', { name: /Abrir no calendário/ }).length).toBe(12)
    await userEvent.click(screen.getByRole('button', { name: 'Agosto: 1 escritório, 1 casa. Abrir no calendário' }))
    expect(await screen.findByRole('grid', { name: 'Agosto 2026' })).toBeInTheDocument()
  })
})

describe('Notas', () => {
  const abrirNotas = (extra: Rotas = {}, rto: unknown = RTO) => abrir(extra, rto, '/rto?aba=notas')

  test('lista as notas do ano por data e cria uma (modo normal não permite passado)', async () => {
    const { pedidos } = abrirNotas({ 'POST /actions/rto.nota_criar': () => OK })
    const lista = within(await screen.findByRole('region', { name: 'Notas' }))
    const itens = lista.getAllByRole('listitem')
    expect(itens[0]).toHaveTextContent('Astreinte')
    expect(itens[1]).toHaveTextContent('Férias — Páscoa')
    expect(itens[1]).toHaveTextContent('28/09/2026 a 02/10/2026')
    await userEvent.type(screen.getByLabelText('Data de início'), '2026-11-02')
    await userEvent.type(screen.getByLabelText('Categoria'), 'Astreinte')
    await userEvent.click(screen.getByRole('button', { name: 'Adicionar nota' }))
    expect(await screen.findByText('Nota criada.')).toBeInTheDocument()
    expect(pedidos.find((p) => p.caminho === '/actions/rto.nota_criar')!.corpo).toEqual({ params: { inicio: '2026-11-02', fim: null, categoria: 'Astreinte', descricao: '', admin: false } })
  })

  test('validações no cliente: vazia e fim antes do início', async () => {
    const { pedidos } = abrirNotas()
    await userEvent.click(await screen.findByRole('button', { name: 'Adicionar nota' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('A nota não pode estar vazia.')
    await userEvent.type(screen.getByLabelText('Data de início'), '2026-11-10')
    await userEvent.type(screen.getByLabelText('Data de fim'), '2026-11-01')
    await userEvent.click(screen.getByRole('button', { name: 'Adicionar nota' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('A data de fim é anterior à de início.')
    expect(pedidos.filter((p) => p.metodo !== 'GET')).toEqual([])
  })

  test('o modo administrador do calendário vale nas notas (envia admin) e o aviso fica visível', async () => {
    const { pedidos } = abrir({ 'POST /actions/rto.nota_criar': () => OK })
    await ativarAdmin()
    await userEvent.click(await tab('Notas'))
    expect(screen.getByText(/Modo administrador ativo/)).toBeInTheDocument()
    await userEvent.type(await screen.findByLabelText('Categoria'), 'Validação')
    await userEvent.type(screen.getByLabelText('Data de início'), '2026-01-05')
    await userEvent.click(screen.getByRole('button', { name: 'Adicionar nota' }))
    await waitFor(() => expect(pedidos.some((p) => p.caminho === '/actions/rto.nota_criar')).toBe(true))
    expect((pedidos.find((p) => p.caminho === '/actions/rto.nota_criar')!.corpo as { params: { admin: boolean } }).params.admin).toBe(true)
  })

  test('a data no passado sem modo administrador mostra a explicação do servidor', async () => {
    abrirNotas({ 'POST /actions/rto.nota_criar': () => [400, { erro: { codigo: 'data_passada', mensagem: 'x' } }] })
    await userEvent.type(await screen.findByLabelText('Categoria'), 'Validação')
    await userEvent.type(screen.getByLabelText('Data de início'), '2026-01-05')
    await userEvent.click(screen.getByRole('button', { name: 'Adicionar nota' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Escolhe hoje ou uma data futura.')
  })

  test('editar preenche o formulário e guarda com o id', async () => {
    const { pedidos } = abrirNotas({ 'POST /actions/rto.nota_editar': () => OK })
    await userEvent.click(await screen.findByRole('button', { name: /Editar nota Férias de 28\/09\/2026 a 02\/10\/2026/ }))
    expect(screen.getByLabelText('Categoria')).toHaveValue('Férias')
    expect(screen.getByLabelText('Descrição')).toHaveValue('Páscoa')
    await userEvent.clear(screen.getByLabelText('Descrição')); await userEvent.type(screen.getByLabelText('Descrição'), 'Verão')
    await userEvent.click(screen.getByRole('button', { name: 'Guardar alterações' }))
    expect(await screen.findByText('Nota atualizada.')).toBeInTheDocument()
    expect(pedidos.find((p) => p.caminho === '/actions/rto.nota_editar')!.corpo).toEqual({ params: {
      inicio: '2026-09-28', fim: '2026-10-02', categoria: 'Férias', descricao: 'Verão', admin: false, nota: 1 } })
  })

  test('eliminar pergunta, confirma com o servidor e o desfazer restaura com o mesmo id', async () => {
    const { pedidos } = abrirNotas({ 'POST /actions/rto.nota_eliminar': () => [200, { resultado: NOTAS[2] }], 'POST /actions/rto.nota_restaurar': () => OK })
    await userEvent.click(await screen.findByRole('button', { name: /Eliminar nota Validação de 14\/10\/2026/ }))
    expect(pedidos.some((p) => p.caminho === '/actions/rto.nota_eliminar')).toBe(false)
    await userEvent.click(within(screen.getByRole('group', { name: 'Eliminar nota Validação' })).getByRole('button', { name: 'Eliminar' }))
    expect(await screen.findByText('Nota eliminada.')).toBeInTheDocument()
    expect(pedidos.find((p) => p.caminho === '/actions/rto.nota_eliminar')!.corpo).toEqual({ params: { nota: 3, admin: false }, confirmado: true })
    await userEvent.click(screen.getByRole('button', { name: 'Desfazer' }))
    await waitFor(() => expect(pedidos.some((p) => p.caminho === '/actions/rto.nota_restaurar')).toBe(true))
    expect(pedidos.find((p) => p.caminho === '/actions/rto.nota_restaurar')!.corpo).toEqual({ params: {
      nota: 3, inicio: '2026-10-14', fim: '2026-10-14', categoria: 'Validação', descricao: '', admin: true } })
  })

  test('gerador de validações valida e mostra o resultado', async () => {
    const { pedidos } = abrirNotas({ 'POST /actions/rto.gerar_validacoes': () => [200, { resultado: { criadas: 5, existentes: 1 } }] })
    await userEvent.click(await screen.findByRole('button', { name: 'Gerar' }))
    await userEvent.click(screen.getByRole('button', { name: 'Gerar validações' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Preenche a data de referência e a data limite.')
    await userEvent.type(screen.getByLabelText('Data de uma validação conhecida'), '2026-10-14')
    await userEvent.type(screen.getByLabelText('Gerar até'), '2026-12-31')
    await userEvent.selectOptions(screen.getByLabelText('Tipo dessa validação'), 'Validação Batica')
    await userEvent.click(screen.getByRole('button', { name: 'Gerar validações' }))
    expect(await screen.findByText('5 validações criadas (1 já existiam).')).toBeInTheDocument()
    expect(pedidos.find((p) => p.caminho === '/actions/rto.gerar_validacoes')!.corpo).toEqual({ params: { referencia: '2026-10-14', ate: '2026-12-31', tipo: 'Validação Batica' } })
  })
})

describe('estados', () => {
  test('erro a carregar com «Tentar de novo»', async () => {
    let falha = true
    abrir({ 'GET /rto?ano=2026': () => (falha ? [503, { erro: { codigo: 'modulo_indisponivel', mensagem: 'x' } }] : [200, RTO]) })
    expect(await screen.findByRole('alert')).toHaveTextContent('não está disponível de momento')
    falha = false
    await userEvent.click(screen.getByRole('button', { name: 'Tentar de novo' }))
    expect(await screen.findByRole('grid', { name: 'Setembro 2026' })).toBeInTheDocument()
  })

  test('Mais leva ao RTO', async () => {
    window.history.pushState({}, '', `${BASE}/mais`)
    servidorFalso({ 'GET /auth/me': () => [200, { utilizador: UTILIZADOR }], 'GET /rto?ano=2026': () => [200, RTO] })
    render(<App />)
    await userEvent.click(await screen.findByRole('link', { name: /RTO/ }))
    expect(await screen.findByRole('heading', { name: 'RTO' })).toBeInTheDocument()
  })
})
