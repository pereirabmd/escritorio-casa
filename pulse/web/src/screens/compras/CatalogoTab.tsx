import { useMemo, useState, type FormEvent } from 'react'
import type { ComprasModulo, ItemCompras, ProdutoCompras } from '../../api/types'
import { useUtilizador } from '../../auth/AuthContext'
import { NOMES_ICONES, ShopIcon } from '../../components/ShopIcon'
import { Icon } from '../../components/Icon'
import { Botao } from '../../components/ui'
import { useFechadas } from '../../lib/recolher'
import type { Ferramentas } from './tipos'

const semAcentos = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

function Seletor({ dados, categoria, setCategoria, icone, setIcone }: { dados: ComprasModulo; categoria: string; setCategoria: (v: string) => void; icone: string | null; setIcone: (v: string | null) => void }) {
  return (
    <>
      <div className="field"><label htmlFor="pc-cat">Categoria</label>
        <select id="pc-cat" className="input" value={categoria} onChange={(e) => setCategoria(e.target.value)}>{dados.categorias.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}</select></div>
      <div role="group" aria-label="Ícone" className="icon-grid">
        <button type="button" className="tile tile-sm" aria-pressed={icone === null} aria-label="Ícone da categoria" onClick={() => setIcone(null)}>Auto</button>
        {NOMES_ICONES.map((n) => <button key={n} type="button" className="tile tile-sm" aria-pressed={icone === n} aria-label={`Ícone ${n}`} onClick={() => setIcone(n)}><ShopIcon nome={n} tamanho={22} /></button>)}
      </div>
    </>
  )
}

function CriarProduto({ nome, dados, f, fechar }: { nome: string; dados: ComprasModulo; f: Ferramentas; fechar: () => void }) {
  const [categoria, setCategoria] = useState('outros')
  const [icone, setIcone] = useState<string | null>(null)
  async function criar(ev: FormEvent) {
    ev.preventDefault()
    if (await f.executar('criar', 'compras.adicionar', { lista: dados.lista.id, nome, categoria, ...(icone ? { icone } : {}) })) { f.avisos.mostrar(`${nome} criado e posto na lista.`); fechar() }
  }
  return (
    <form className="card stack" onSubmit={criar} aria-label={`Criar ${nome}`}>
      <h2 className="t-card">Criar «{nome}»</h2>
      <Seletor dados={dados} categoria={categoria} setCategoria={setCategoria} icone={icone} setIcone={setIcone} />
      <div className="quick">
        <Botao type="submit" pequeno carregando={f.ocupado === 'criar'} disabled={f.ocupado !== null}>Criar e pôr na lista</Botao>
        <Botao type="button" pequeno variante="secondary" onClick={fechar}>Cancelar</Botao>
      </div>
    </form>
  )
}

function EditarProduto({ p, dados, f, fechar, souAdmin }: { p: ProdutoCompras; dados: ComprasModulo; f: Ferramentas; fechar: () => void; souAdmin: boolean }) {
  const { executar, ocupado, avisos } = f
  const [nome, setNome] = useState(p.nome)
  const [categoria, setCategoria] = useState(p.categoria)
  const [icone, setIcone] = useState<string | null>(p.icone)
  const [apagar, setApagar] = useState(false)
  const proprio = !p.builtin
  async function guardar(ev: FormEvent) {
    ev.preventDefault()
    const params: Record<string, unknown> = { produto: p.id }
    if (nome.trim() !== p.nome) params.nome = nome.trim()
    if (categoria !== p.categoria) params.categoria = categoria
    if (icone && icone !== p.icone) params.icone = icone
    if (Object.keys(params).length === 1) { fechar(); return }
    if (await executar('prod', 'compras.produto_editar', params)) { avisos.mostrar('Produto atualizado.'); fechar() }
  }
  async function eliminar() {
    const r = await executar('prod', 'compras.produto_apagar', { produto: p.id }, true)
    if (r) {
      avisos.mostrar(`${p.nome} apagado.`, () => void executar('desfazer', 'compras.produto_criar', { nome: p.nome, categoria: p.categoria, icone: p.icone }))
      fechar()
    }
  }
  return (
    <section className="card stack" aria-label={`Gerir ${p.nome}`}>
      <h2 className="t-card">{p.nome}</h2>
      {proprio ? (
        <form className="stack" onSubmit={guardar} noValidate>
          <div className="field"><label htmlFor="pe-nome">Nome</label><input id="pe-nome" className="input" maxLength={80} value={nome} onChange={(e) => setNome(e.target.value)} /></div>
          <Seletor dados={dados} categoria={categoria} setCategoria={setCategoria} icone={icone} setIcone={setIcone} />
          <div className="quick">
            <Botao type="submit" pequeno carregando={ocupado === 'prod'} disabled={!nome.trim() || ocupado !== null}>Guardar</Botao>
            <Botao type="button" pequeno variante="secondary" onClick={fechar}>Cancelar</Botao>
          </div>
        </form>
      ) : <p className="t-meta">Produto de série: podes escondê-lo ou marcá-lo como favorito, mas não alterá-lo.</p>}
      <div className="quick">
        <Botao pequeno variante="secondary" disabled={ocupado !== null} onClick={() => void executar('oculto', 'compras.ocultar', { produto: p.id, valor: !p.oculto }).then((r) => { if (r) fechar() })}>{p.oculto ? 'Mostrar no catálogo' : 'Esconder do catálogo'}</Botao>
        {!p.builtin && (apagar ? (
          <span role="group" aria-label={`Apagar ${p.nome}`} className="quick">
            <Botao variante="danger" pequeno carregando={ocupado === 'prod'} disabled={ocupado !== null} onClick={() => void eliminar()}>Apagar produto</Botao>
            <Botao variante="secondary" pequeno onClick={() => setApagar(false)}>Cancelar</Botao>
          </span>
        ) : <button type="button" className="link-btn link-danger" onClick={() => setApagar(true)}>Apagar</button>)}
        {!p.builtin && !souAdmin && <span className="t-meta">Só quem o criou (ou o administrador) altera ou apaga.</span>}
      </div>
    </section>
  )
}

export function CatalogoTab({ dados, f }: { dados: ComprasModulo; f: Ferramentas }) {
  const { executar, ocupado, avisos } = f
  const souAdmin = useUtilizador().admin
  const [busca, setBusca] = useState('')
  const [filtro, setFiltro] = useState<string>('todos')
  const [gerir, setGerir] = useState(false)
  const [criar, setCriar] = useState(false)
  const [editar, setEditar] = useState<number | null>(null)
  const q = semAcentos(busca.trim())
  const { fechadas, alternar, todas } = useFechadas('pulse.compras.fechadas.catalogo')

  const ocultas = useMemo(() => new Set(dados.categorias.filter((c) => c.oculta).map((c) => c.id)), [dados.categorias])
  const visiveis = useMemo(() => dados.produtos.filter((p) => {
    if (p.oculto && !gerir && p.estado === null) return false                          // os escondidos só aparecem em «Gerir» (ou se já estiverem na lista)
    if (ocultas.has(p.categoria) && !q && p.estado === null) return false               // categoria escondida: fora, mas a pesquisa ainda a encontra e o que está na lista fica
    if (q && !semAcentos(p.nome).includes(q)) return false
    if (filtro === 'favoritos') return p.favorito
    return filtro === 'todos' || p.categoria === filtro
  }), [dados.produtos, gerir, q, filtro, ocultas])
  const porCategoria = dados.categorias.filter((c) => !ocultas.has(c.id) || q || visiveis.some((p) => p.categoria === c.id)).map((c) => ({ ...c, produtos: visiveis.filter((p) => p.categoria === c.id) })).filter((c) => c.produtos.length > 0)
  const existeExato = !!q && dados.produtos.some((p) => semAcentos(p.nome) === q)
  const editado = editar !== null ? dados.produtos.find((p) => p.id === editar) : undefined

  async function tocar(p: ProdutoCompras) {
    if (gerir) { setEditar(p.id); return }
    if (p.estado === 'pendente' && p.item !== null) {
      const r = await executar(`p-${p.id}`, 'compras.remover', { item: p.item })
      if (r) avisos.mostrar(`${p.nome} tirado da lista.`, () => void executar('desfazer', 'compras.restaurar', { lista: dados.lista.id, itens: [{ produto: p.id, quantidade: (r as unknown as ItemCompras).quantidade, nota: (r as unknown as ItemCompras).nota, estado: 'pendente' }] }))
      return
    }
    if (await executar(`p-${p.id}`, 'compras.adicionar', { lista: dados.lista.id, produto: p.id })) avisos.mostrar(`${p.nome} na lista.`)
  }

  async function esconderCategoria(id: string, nome: string, valor: boolean) {
    const filtroAtual = filtro
    if (await executar(`cat-${id}`, 'compras.categoria_ocultar', { categoria: id, valor })) {
      if (valor && filtroAtual === id) setFiltro('todos')
      avisos.mostrar(valor ? `${nome} escondida.` : `${nome} visível outra vez.`, () => void executar('desfazer', 'compras.categoria_ocultar', { categoria: id, valor: !valor }))
    }
  }

  const Tile = ({ p }: { p: ProdutoCompras }) => (
    <div className="tile-wrap" data-oculto={p.oculto}>
      <button type="button" className="tile" aria-pressed={p.estado === 'pendente'} data-comprado={p.estado === 'comprado'} disabled={ocupado !== null}
        aria-label={gerir ? `Gerir ${p.nome}` : `${p.nome}${p.estado === 'pendente' ? ' (na lista)' : p.estado === 'comprado' ? ' (comprado)' : ''}`} onClick={() => void tocar(p)}>
        <ShopIcon nome={p.icone} tamanho={28} /><span className="tile-nome">{p.nome}</span>
      </button>
      <button type="button" className="star" aria-pressed={p.favorito} aria-label={`Favorito: ${p.nome}`} disabled={ocupado !== null}
        onClick={() => void executar(`f-${p.id}`, 'compras.favorito', { produto: p.id, valor: !p.favorito })}>{p.favorito ? '★' : '☆'}</button>
    </div>
  )

  return (
    <div className="stack">
      <div className="field"><label htmlFor="cat-busca">Procurar produto</label>
        <input id="cat-busca" className="input" type="search" autoComplete="off" value={busca} onChange={(e) => { setBusca(e.target.value); setCriar(false) }} /></div>
      <div className="chips" role="group" aria-label="Categorias">
        {[{ id: 'todos', nome: 'Tudo' }, { id: 'favoritos', nome: 'Favoritos' }, ...dados.categorias.filter((c) => !c.oculta && dados.produtos.some((p) => p.categoria === c.id))].map((c) => (
          <button key={c.id} type="button" className="chip" aria-pressed={filtro === c.id} onClick={() => setFiltro(c.id)}>{c.nome}</button>
        ))}
        <button type="button" className="chip" aria-pressed={gerir} onClick={() => { setGerir((v) => !v); setEditar(null) }}>Gerir</button>
      </div>
      {gerir && <p className="t-meta">Toca num produto para o gerir (esconder, e editar ou apagar os teus).</p>}

      {q && !existeExato && !criar && <div><Botao pequeno variante="secondary" onClick={() => setCriar(true)}>Criar «{busca.trim()}»</Botao></div>}
      {criar && <CriarProduto nome={busca.trim()} dados={dados} f={f} fechar={() => { setCriar(false); setBusca('') }} />}
      {editado && <EditarProduto key={editado.id} p={editado} dados={dados} f={f} fechar={() => setEditar(null)} souAdmin={souAdmin} />}

      {gerir && !q && dados.categorias.some((c) => c.oculta) && (
        <section className="card stack" aria-label="Categorias escondidas">
          <h2 className="t-card">Categorias escondidas</h2>
          <ul className="rows">{dados.categorias.filter((c) => c.oculta).map((c) => (
            <li key={c.id}><div className="row-main t-body">{c.nome}</div>
              <button type="button" className="link-btn" disabled={ocupado !== null} aria-label={`Mostrar a categoria ${c.nome}`} onClick={() => void esconderCategoria(c.id, c.nome, false)}>Mostrar</button></li>
          ))}</ul>
        </section>
      )}
      {visiveis.length === 0 && <p className="t-body2">{filtro === 'favoritos' ? 'Ainda não marcaste favoritos. Toca na estrela de um produto.' : 'Nenhum produto encontrado.'}</p>}
      {porCategoria.length > 1 && !q && (() => {
        const ids = porCategoria.map((c) => c.id), todasFechadas = ids.every((id) => fechadas.has(id))
        return <div><button type="button" className="link-btn" onClick={() => todas(ids, !todasFechadas)}>{todasFechadas ? 'Expandir todas' : 'Encolher todas'}</button></div>
      })()}
      {porCategoria.map((c) => {
        const aberto = !!q || !fechadas.has(c.id)          // a pesquisa mostra sempre os resultados
        return (
          <section key={c.id} aria-label={c.nome} className="stack">
            <div className="split"><h2 className="t-card"><button type="button" className="sec-toggle" aria-expanded={aberto} disabled={!!q} onClick={() => alternar(c.id)}>
              <Icon nome="seta" tamanho={16} />{c.nome} <span className="t-meta">{c.produtos.length}</span></button></h2>
              {gerir && !q && <button type="button" className="link-btn" disabled={ocupado !== null} aria-label={`Esconder a categoria ${c.nome}`} onClick={() => void esconderCategoria(c.id, c.nome, true)}>Esconder categoria</button>}</div>
            {aberto && <div className="tiles">{c.produtos.map((p) => <Tile key={p.id} p={p} />)}</div>}
          </section>
        )
      })}
    </div>
  )
}
