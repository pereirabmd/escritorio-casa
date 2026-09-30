import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App } from '../../App'
import { NOMES_ICONES } from '../../components/ShopIcon'
import { servidorFalso, UTILIZADOR, type Rotas } from '../../test/api-mock'

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '')
const OK = (r: unknown = {}): [number, unknown] => [200, { resultado: r }]

const CATEGORIAS = [{ id: 'frutas-legumes', nome: 'Frutas e legumes', oculta: false }, { id: 'mercearia', nome: 'Mercearia', oculta: false }, { id: 'laticinios', nome: 'Laticínios e ovos', oculta: false }, { id: 'bebe', nome: 'Bebé e crianças', oculta: false }, { id: 'outros', nome: 'Outros', oculta: false }]
const P = (id: number, nome: string, categoria: string, extra = {}) => ({ id, nome, categoria, icone: 'saco', builtin: true, criadoPor: null, favorito: false, oculto: false, item: null, estado: null, ...extra })
const I = (id: number, produto: number, nome: string, categoria: string, extra = {}) => ({ id, lista: 1, produto, nome, categoria, icone: 'saco', quantidade: null, nota: '', estado: 'pendente', adicionadoPor: 'camila@exemplo.pt', compradoEm: null, ...extra })
const CASA = { id: 1, nome: 'Casa', tipo: 'partilhada', padrao: true, pendentes: 2, total: 3 }
const MINHA = { id: 2, nome: 'Churrasco', tipo: 'pessoal', padrao: false, pendentes: 0, total: 0 }
const DADOS = {
  categorias: CATEGORIAS, listas: [CASA, MINHA], lista: CASA, pendentes: 2, ultimaChamada: null, sugestoes: { acabar: [], frequentes: [] },
  grupos: [{ categoria: CATEGORIAS[0], itens: [I(10, 1, 'Maçã', 'frutas-legumes', { quantidade: 6 })] }, { categoria: CATEGORIAS[2], itens: [I(11, 3, 'Leite meio-gordo', 'laticinios', { nota: '1 L' })] }],
  comprados: [I(12, 4, 'Ovos', 'laticinios', { estado: 'comprado', compradoEm: 100 })],
  produtos: [P(1, 'Maçã', 'frutas-legumes', { item: 10, estado: 'pendente' }), P(2, 'Pera', 'frutas-legumes'), P(3, 'Leite meio-gordo', 'laticinios', { item: 11, estado: 'pendente' }),
    P(4, 'Ovos', 'laticinios', { item: 12, estado: 'comprado', favorito: true }), P(5, 'Arroz agulha', 'mercearia'), P(6, 'Tofu', 'mercearia', { builtin: false, criadoPor: 1 }),
    P(7, 'Sal fino', 'mercearia', { oculto: true }), P(8, 'Fraldas', 'bebe'), P(9, 'Toalhetes de bebé', 'bebe')],
}

function abrir(aba = 'lista', extra: Rotas = {}, dados: unknown = DADOS) {
  window.history.pushState({}, '', `${BASE}/compras?aba=${aba}`)
  const s = servidorFalso({ 'GET /auth/me': () => [200, { utilizador: UTILIZADOR }], 'GET /shopping': () => [200, dados], ...extra })
  render(<App />)
  return s
}
const corpo = (p: { caminho: string; corpo: unknown }[], c: string) => p.find((x) => x.caminho === c)?.corpo

afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })

test('todos os ícones do JSON têm caminhos e o conjunto tem o tamanho esperado', () => {
  expect(NOMES_ICONES.length).toBeGreaterThanOrEqual(70)
  expect(NOMES_ICONES).toContain('cesto')
})

test('Mais leva às Compras', async () => {
  window.history.pushState({}, '', `${BASE}/mais`)
  servidorFalso({ 'GET /auth/me': () => [200, { utilizador: UTILIZADOR }], 'GET /shopping': () => [200, DADOS] })
  render(<App />)
  await userEvent.click(await screen.findByRole('link', { name: /Compras/ }))
  expect(await screen.findByRole('heading', { name: 'Compras' })).toBeInTheDocument()
})

describe('Listas', () => {
  test('mostra a Casa partilhada e a pessoal, e diz quem a vê', async () => {
    abrir()
    const listas = await screen.findByRole('group', { name: 'Listas' })
    expect(within(listas).getByRole('button', { name: /Casa/ })).toHaveAttribute('aria-pressed', 'true')
    expect(within(listas).getByRole('button', { name: /Churrasco/ })).toBeInTheDocument()
    expect(screen.getByText(/Lista partilhada: todas as contas a veem/)).toBeInTheDocument()
  })

  test('escolher outra lista pede-a ao servidor; a pessoal diz que só tu a vês', async () => {
    const pedidos: string[] = []
    abrir('lista', { 'GET /shopping?lista=2': () => { pedidos.push('2'); return [200, { ...DADOS, lista: MINHA, grupos: [], comprados: [], pendentes: 0 }] } })
    await userEvent.click(await screen.findByRole('button', { name: /Churrasco/ }))
    await waitFor(() => expect(pedidos).toEqual(['2']))
    expect(await screen.findByText(/Lista pessoal: só tu a vês/)).toBeInTheDocument()
    expect(screen.getByText(/A lista «Churrasco» está vazia/)).toBeInTheDocument()
  })

  test('criar uma lista pessoal e uma partilhada', async () => {
    const s = abrir('lista', { 'POST /actions/compras.lista_criar': () => OK({ id: 9, nome: 'Festa', tipo: 'partilhada' }) })
    await userEvent.click(await screen.findByRole('button', { name: '+ Nova lista' }))
    const f = screen.getByRole('form', { name: 'Nova lista' })
    await userEvent.type(within(f).getByLabelText('Nome'), 'Festa')
    await userEvent.click(within(f).getByRole('button', { name: 'Partilhada' }))
    await userEvent.click(within(f).getByRole('button', { name: 'Criar' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/compras.lista_criar')).toEqual({ params: { nome: 'Festa', tipo: 'partilhada' } }))
  })

  test('a Casa não se gere; uma lista própria pode ser renomeada e apagada com confirmação', async () => {
    const s = abrir('lista', { 'GET /shopping?lista=2': () => [200, { ...DADOS, lista: MINHA, grupos: [], comprados: [], pendentes: 0 }], 'POST /actions/compras.lista_apagar': () => OK(), 'POST /actions/compras.lista_editar': () => OK() })
    await screen.findByText('Maçã')
    expect(screen.queryByRole('button', { name: /Gerir esta lista/ })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Churrasco/ }))
    await userEvent.click(await screen.findByRole('button', { name: 'Gerir esta lista' }))
    const g = screen.getByRole('region', { name: 'Gerir a lista Churrasco' })
    const nome = within(g).getByLabelText('Nome da lista')
    await userEvent.clear(nome); await userEvent.type(nome, 'Jantar')
    await userEvent.click(within(g).getByRole('button', { name: 'Renomear' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/compras.lista_editar')).toEqual({ params: { lista: 2, nome: 'Jantar' } }))
    await userEvent.click(within(g).getByRole('button', { name: 'Apagar esta lista' }))
    await userEvent.click(within(screen.getByRole('group', { name: 'Confirmar apagar lista' })).getByRole('button', { name: 'Apagar lista' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/compras.lista_apagar')).toEqual({ params: { lista: 2 }, confirmado: true }))
  })
})

describe('Lista', () => {
  test('as categorias encolhem e expandem, e lembram-se', async () => {
    abrir()
    const fruta = await screen.findByRole('region', { name: 'Frutas e legumes' })
    await userEvent.click(within(fruta).getByRole('button', { name: /Frutas e legumes/ }))
    expect(within(fruta).queryByText('Maçã')).not.toBeInTheDocument()
    expect(localStorage.getItem('pulse.compras.fechadas.lista')).toBe('frutas-legumes')
    await userEvent.click(within(fruta).getByRole('button', { name: /Frutas e legumes/ }))
    expect(within(fruta).getByText('Maçã')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Encolher todas' }))
    expect(screen.queryByText('Maçã')).not.toBeInTheDocument()
    expect(screen.queryByText('Leite meio-gordo')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Expandir todas' }))
    expect(screen.getByText('Maçã')).toBeInTheDocument()
  })

  test('agrupa por corredor, mostra a quantidade só quando existe, a nota e quem adicionou', async () => {
    abrir()
    const fruta = await screen.findByRole('region', { name: 'Frutas e legumes' })
    expect(within(fruta).getByText('Maçã')).toBeInTheDocument()
    expect(within(fruta).getByText('6×')).toBeInTheDocument()
    const lat = screen.getByRole('region', { name: 'Laticínios e ovos' })
    expect(within(lat).getByText('Leite meio-gordo')).toBeInTheDocument()
    expect(within(lat).queryByText(/×/)).not.toBeInTheDocument()
    expect(within(lat).getByText('1 L · por camila')).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Comprados' })).getByText('Ovos')).toBeInTheDocument()
  })

  test('marcar como comprado tem «Desfazer»; voltar a pôr por comprar', async () => {
    const s = abrir('lista', { 'POST /actions/compras.comprado': () => OK() })
    await userEvent.click(await screen.findByRole('button', { name: 'Marcar como comprado: Maçã' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/compras.comprado')).toEqual({ params: { item: 10, comprado: true } }))
    await userEvent.click(await screen.findByRole('button', { name: 'Desfazer' }))
    await waitFor(() => expect(s.pedidos.filter((p) => p.caminho === '/actions/compras.comprado').map((p) => (p.corpo as { params: { comprado: boolean } }).params.comprado)).toEqual([true, false]))
    await userEvent.click(screen.getByRole('button', { name: 'Voltar a pôr por comprar: Ovos' }))
    await waitFor(() => expect(s.pedidos.filter((p) => p.caminho === '/actions/compras.comprado')).toHaveLength(3))
  })

  test('a quantidade é opcional e só se define nos detalhes (vazio = sem quantidade)', async () => {
    const s = abrir('lista', { 'POST /actions/compras.detalhes': () => OK() })
    await userEvent.click(await screen.findByRole('button', { name: 'Detalhes de Leite meio-gordo' }))
    const f = screen.getByRole('form', { name: 'Detalhes de Leite meio-gordo' })
    await userEvent.type(within(f).getByLabelText('Quantidade (opcional)'), '6')
    await userEvent.click(within(f).getByRole('button', { name: 'Guardar' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/compras.detalhes')).toEqual({ params: { item: 11, quantidade: 6, nota: '1 L' } }))
  })

  test('quantidade inválida não deixa guardar', async () => {
    abrir()
    await userEvent.click(await screen.findByRole('button', { name: 'Detalhes de Leite meio-gordo' }))
    const f = screen.getByRole('form', { name: 'Detalhes de Leite meio-gordo' })
    await userEvent.type(within(f).getByLabelText('Quantidade (opcional)'), '0')
    expect(within(f).getByRole('button', { name: 'Guardar' })).toBeDisabled()
  })

  test('remover um item oferece desfazer com o que ele era', async () => {
    const era = I(10, 1, 'Maçã', 'frutas-legumes', { quantidade: 6, nota: '' })
    const s = abrir('lista', { 'POST /actions/compras.remover': () => OK(era), 'POST /actions/compras.restaurar': () => OK({ repostos: 1 }) })
    await userEvent.click(await screen.findByRole('button', { name: 'Detalhes de Maçã' }))
    await userEvent.click(screen.getByRole('button', { name: 'Remover Maçã da lista' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/compras.remover')).toEqual({ params: { item: 10 } }))
    await userEvent.click(await screen.findByRole('button', { name: 'Desfazer' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/compras.restaurar')).toEqual({ params: { lista: 1, itens: [{ produto: 1, quantidade: 6, nota: '', estado: 'pendente' }] } }))
  })

  test('passar um item para outra lista', async () => {
    const s = abrir('lista', { 'POST /actions/compras.mover': () => OK() })
    await userEvent.click(await screen.findByRole('button', { name: 'Detalhes de Maçã' }))
    await userEvent.selectOptions(screen.getByLabelText('Passar Maçã para outra lista'), '2')
    await waitFor(() => expect(corpo(s.pedidos, '/actions/compras.mover')).toEqual({ params: { item: 10, lista: 2 } }))
  })

  test('limpar comprados pede confirmação e o desfazer repõe-nos', async () => {
    const removidos = [I(12, 4, 'Ovos', 'laticinios', { estado: 'comprado', compradoEm: 100 })]
    const s = abrir('lista', { 'POST /actions/compras.limpar_comprados': () => OK({ removidos }), 'POST /actions/compras.restaurar': () => OK({ repostos: 1 }) })
    await userEvent.click(await screen.findByRole('button', { name: 'Limpar comprados' }))
    expect(corpo(s.pedidos, '/actions/compras.limpar_comprados')).toBeUndefined()
    await userEvent.click(within(screen.getByRole('group', { name: 'Confirmar limpar comprados' })).getByRole('button', { name: 'Apagar' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/compras.limpar_comprados')).toEqual({ params: { lista: 1 }, confirmado: true }))
    await userEvent.click(await screen.findByRole('button', { name: 'Desfazer' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/compras.restaurar')).toEqual({ params: { lista: 1, itens: [{ produto: 4, quantidade: null, nota: '', estado: 'comprado' }] } }))
  })

  test('«Última chamada»: pede confirmação, envia a mensagem e depois mostra quem avisou', async () => {
    const s = abrir('lista', { 'POST /actions/compras.ultima_chamada': () => OK({ criado: 1, avisados: 1 }) })
    await userEvent.click(await screen.findByRole('button', { name: 'Última chamada' }))
    expect(screen.getByText(/Só se pode fazer uma vez/)).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText(/Mensagem/), 'Saio às 18h')
    await userEvent.click(screen.getByRole('button', { name: 'Avisar toda a gente' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/compras.ultima_chamada')).toEqual({ params: { lista: 1, mensagem: 'Saio às 18h' }, confirmado: true }))
  })

  test('com uma «Última chamada» ativa não há botão: mostra a faixa', async () => {
    abrir('lista', {}, { ...DADOS, ultimaChamada: { por: 'Camila', mensagem: 'Saio às 18h', criado: 1790000000 } })
    expect(await screen.findByLabelText('Última chamada')).toHaveTextContent(/Camila avisou toda a gente.*Saio às 18h/)
    expect(screen.queryByRole('button', { name: 'Última chamada' })).not.toBeInTheDocument()
  })

  test('lista vazia leva ao catálogo', async () => {
    abrir('lista', {}, { ...DADOS, grupos: [], comprados: [], pendentes: 0 })
    await userEvent.click(await screen.findByRole('button', { name: 'Abrir o catálogo' }))
    expect(await screen.findByLabelText('Procurar produto')).toBeInTheDocument()
  })
})

describe('Catálogo', () => {
  test('um toque põe o produto na lista e outro tira-o (sem contador)', async () => {
    const s = abrir('catalogo', { 'POST /actions/compras.adicionar': () => OK({ id: 20 }), 'POST /actions/compras.remover': () => OK(I(10, 1, 'Maçã', 'frutas-legumes')) })
    await userEvent.click(await screen.findByRole('button', { name: 'Pera' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/compras.adicionar')).toEqual({ params: { lista: 1, produto: 2 } }))
    expect(screen.getByRole('button', { name: 'Maçã (na lista)' })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(screen.getByRole('button', { name: 'Maçã (na lista)' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/compras.remover')).toEqual({ params: { item: 10 } }))
  })

  test('tocar num produto já comprado põe-no outra vez por comprar', async () => {
    const s = abrir('catalogo', { 'POST /actions/compras.adicionar': () => OK({ id: 12 }) })
    await userEvent.click(await screen.findByRole('button', { name: 'Ovos (comprado)' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/compras.adicionar')).toEqual({ params: { lista: 1, produto: 4 } }))
  })

  test('pesquisa sem acentos, filtro por categoria e favoritos', async () => {
    abrir('catalogo')
    await userEvent.type(await screen.findByLabelText('Procurar produto'), 'maca')
    expect(screen.getByRole('button', { name: 'Maçã (na lista)' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Pera' })).not.toBeInTheDocument()
    await userEvent.clear(screen.getByLabelText('Procurar produto'))
    await userEvent.click(screen.getByRole('button', { name: 'Favoritos' }))
    expect(screen.getByRole('button', { name: 'Ovos (comprado)' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Pera' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Mercearia' }))
    expect(await screen.findByRole('button', { name: 'Arroz agulha' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Ovos (comprado)' })).not.toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Procurar produto'), 'zzz')
    expect(await screen.findByText('Nenhum produto encontrado.')).toBeInTheDocument()
  })

  test('marcar favorito', async () => {
    const s = abrir('catalogo', { 'POST /actions/compras.favorito': () => OK() })
    await userEvent.click(await screen.findByRole('button', { name: 'Favorito: Pera' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/compras.favorito')).toEqual({ params: { produto: 2, valor: true } }))
  })

  test('os produtos escondidos não aparecem, excepto em «Gerir»', async () => {
    abrir('catalogo')
    await screen.findByRole('button', { name: 'Pera' })
    expect(screen.queryByRole('button', { name: 'Sal fino' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Gerir' }))
    expect(screen.getByRole('button', { name: 'Gerir Sal fino' })).toBeInTheDocument()
  })

  test('criar um produto que não existe e pô-lo na lista', async () => {
    const s = abrir('catalogo', { 'POST /actions/compras.adicionar': () => OK({ id: 30 }) })
    await userEvent.type(await screen.findByLabelText('Procurar produto'), 'Leite de coco')
    await userEvent.click(screen.getByRole('button', { name: 'Criar «Leite de coco»' }))
    const f = screen.getByRole('form', { name: 'Criar Leite de coco' })
    await userEvent.selectOptions(within(f).getByLabelText('Categoria'), 'mercearia')
    await userEvent.click(within(f).getByRole('button', { name: 'Ícone lata' }))
    await userEvent.click(within(f).getByRole('button', { name: 'Criar e pôr na lista' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/compras.adicionar')).toEqual({ params: { lista: 1, nome: 'Leite de coco', categoria: 'mercearia', icone: 'lata' } }))
  })

  test('não oferece criar quando o produto já existe', async () => {
    abrir('catalogo')
    await userEvent.type(await screen.findByLabelText('Procurar produto'), 'PERA')
    expect(screen.queryByRole('button', { name: /^Criar/ })).not.toBeInTheDocument()
  })

  test('gerir: um produto de série só se esconde; um próprio edita-se e apaga-se com confirmação', async () => {
    const s = abrir('catalogo', { 'POST /actions/compras.ocultar': () => OK(), 'POST /actions/compras.produto_editar': () => OK(), 'POST /actions/compras.produto_apagar': () => OK(), 'POST /actions/compras.produto_criar': () => OK() })
    await userEvent.click(await screen.findByRole('button', { name: 'Gerir' }))
    await userEvent.click(screen.getByRole('button', { name: 'Gerir Pera' }))
    const serie = screen.getByRole('region', { name: 'Gerir Pera' })
    expect(within(serie).getByText(/Produto de série/)).toBeInTheDocument()
    expect(within(serie).queryByLabelText('Nome')).not.toBeInTheDocument()
    await userEvent.click(within(serie).getByRole('button', { name: 'Esconder do catálogo' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/compras.ocultar')).toEqual({ params: { produto: 2, valor: true } }))

    await userEvent.click(screen.getByRole('button', { name: 'Gerir Tofu' }))
    const meu = await screen.findByRole('region', { name: 'Gerir Tofu' })
    await userEvent.clear(within(meu).getByLabelText('Nome')); await userEvent.type(within(meu).getByLabelText('Nome'), 'Tofu firme')
    await userEvent.click(within(meu).getByRole('button', { name: 'Guardar' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/compras.produto_editar')).toEqual({ params: { produto: 6, nome: 'Tofu firme' } }))

    await userEvent.click(screen.getByRole('button', { name: 'Gerir Tofu' }))
    const outra = await screen.findByRole('region', { name: 'Gerir Tofu' })
    await userEvent.click(within(outra).getByRole('button', { name: 'Apagar' }))
    await userEvent.click(within(screen.getByRole('group', { name: 'Apagar Tofu' })).getByRole('button', { name: 'Apagar produto' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/compras.produto_apagar')).toEqual({ params: { produto: 6 }, confirmado: true }))
  })
})

test('erro do servidor aparece no ecrã', async () => {
  abrir('catalogo', { 'POST /actions/compras.adicionar': () => [403, { erro: { codigo: 'modulo_desativado', mensagem: 'x' } }] })
  await userEvent.click(await screen.findByRole('button', { name: 'Pera' }))
  expect(await screen.findByText('Este módulo foi desativado pelo administrador.')).toBeInTheDocument()
})


describe('Esconder categorias', () => {
  const escondida = { ...DADOS, categorias: CATEGORIAS.map((c) => (c.id === 'bebe' ? { ...c, oculta: true } : c)) }

  test('uma categoria escondida sai do catálogo e dos filtros, mas a pesquisa ainda encontra os produtos', async () => {
    abrir('catalogo', {}, escondida)
    await screen.findByRole('button', { name: 'Pera' })
    expect(screen.queryByRole('button', { name: 'Fraldas' })).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Bebé e crianças' })).not.toBeInTheDocument()
    expect(within(screen.getByRole('group', { name: 'Categorias' })).queryByRole('button', { name: 'Bebé e crianças' })).not.toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Procurar produto'), 'fraldas')
    expect(screen.getByRole('button', { name: 'Fraldas' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Criar/ })).not.toBeInTheDocument()              // existe, só estava escondido
  })

  test('em «Gerir» esconde-se uma categoria inteira, com desfazer', async () => {
    const s = abrir('catalogo', { 'POST /actions/compras.categoria_ocultar': () => OK() })
    expect(screen.queryByRole('button', { name: /Esconder a categoria/ })).not.toBeInTheDocument()
    await userEvent.click(await screen.findByRole('button', { name: 'Gerir' }))
    await userEvent.click(screen.getByRole('button', { name: 'Esconder a categoria Bebé e crianças' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/compras.categoria_ocultar')).toEqual({ params: { categoria: 'bebe', valor: true } }))
    await userEvent.click(await screen.findByRole('button', { name: 'Desfazer' }))
    await waitFor(() => expect(s.pedidos.filter((p) => p.caminho === '/actions/compras.categoria_ocultar').map((p) => (p.corpo as { params: { valor: boolean } }).params.valor)).toEqual([true, false]))
  })

  test('as categorias escondidas listam-se em «Gerir» para voltar a mostrar', async () => {
    const s = abrir('catalogo', { 'POST /actions/compras.categoria_ocultar': () => OK() }, escondida)
    await userEvent.click(await screen.findByRole('button', { name: 'Gerir' }))
    const r = screen.getByRole('region', { name: 'Categorias escondidas' })
    expect(within(r).getByText('Bebé e crianças')).toBeInTheDocument()
    await userEvent.click(within(r).getByRole('button', { name: 'Mostrar a categoria Bebé e crianças' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/compras.categoria_ocultar')).toEqual({ params: { categoria: 'bebe', valor: false } }))
  })

  test('o que já está na lista continua na lista mesmo com a categoria escondida', async () => {
    const dados = { ...escondida, grupos: [{ categoria: CATEGORIAS[3], itens: [I(40, 8, 'Fraldas', 'bebe')] }], pendentes: 1, comprados: [] }
    abrir('lista', {}, dados)
    expect(await screen.findByText('Fraldas')).toBeInTheDocument()
  })
})

describe('Sugestões', () => {
  const sug = (extra = {}) => ({ produto: 2, nome: 'Pera', categoria: 'frutas-legumes', icone: 'fruta', ultima: '2026-09-16', diasDesde: 14, compras: 4, ...extra })
  const comSugestoes = { ...DADOS, sugestoes: { acabar: [sug({ intervaloDias: 14 })], frequentes: [sug({ produto: 5, nome: 'Arroz agulha', compras: 3, diasDesde: 1 })] } }

  test('sem sugestões não aparece o cartão', async () => {
    abrir()
    await screen.findByText('Maçã')
    expect(screen.queryByRole('region', { name: 'Sugestões' })).not.toBeInTheDocument()
  })

  test('mostra «talvez esteja a acabar» com o ritmo e «costumas comprar» com a frequência, sem adicionar nada sozinho', async () => {
    const s = abrir('lista', {}, comSugestoes)
    const r = await screen.findByRole('region', { name: 'Sugestões' })
    expect(within(r).getByText('Talvez esteja a acabar')).toBeInTheDocument()
    expect(within(r).getByText('Costumas comprar de 14 em 14 dias · última compra há 14 dias')).toBeInTheDocument()
    expect(within(r).getByText('3 vezes nos últimos 90 dias · última há 1 dia')).toBeInTheDocument()
    expect(within(r).getByText(/nada é adicionado sozinho/)).toBeInTheDocument()
    expect(s.pedidos.some((p) => p.metodo !== 'GET' && p.caminho.startsWith('/actions/'))).toBe(false)
  })

  test('adicionar uma sugestão à lista', async () => {
    const s = abrir('lista', { 'POST /actions/compras.adicionar': () => OK({ id: 50 }) }, comSugestoes)
    await userEvent.click(await screen.findByRole('button', { name: 'Adicionar Pera à lista' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/compras.adicionar')).toEqual({ params: { lista: 1, produto: 2 } }))
  })

  test('«Não sugerir» é por produto e tem desfazer', async () => {
    const s = abrir('lista', { 'POST /actions/compras.sugestao_ignorar': () => OK() }, comSugestoes)
    await userEvent.click(await screen.findByRole('button', { name: 'Não sugerir Arroz agulha' }))
    await waitFor(() => expect(corpo(s.pedidos, '/actions/compras.sugestao_ignorar')).toEqual({ params: { produto: 5, valor: true } }))
    await userEvent.click(await screen.findByRole('button', { name: 'Desfazer' }))
    await waitFor(() => expect(s.pedidos.filter((p) => p.caminho === '/actions/compras.sugestao_ignorar').map((p) => (p.corpo as { params: { valor: boolean } }).params.valor)).toEqual([true, false]))
  })
})
