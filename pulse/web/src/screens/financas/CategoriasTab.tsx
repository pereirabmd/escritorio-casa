import { useState, type FormEvent } from 'react'
import type { CategoriaFin } from '../../api/types'
import { Botao } from '../../components/ui'
import type { Ferramentas } from './tipos'

const COR_OK = /^#[0-9A-Fa-f]{6}$/

function Linha({ c, f }: { c: CategoriaFin; f: Ferramentas }) {
  const { executar, ocupado, avisos } = f
  const [modo, setModo] = useState<'ver' | 'editar' | 'apagar'>('ver')
  const [nome, setNome] = useState(c.nome)
  const [cor, setCor] = useState(c.cor ?? '#8A918E')

  async function guardar(ev: FormEvent) {
    ev.preventDefault()
    const params: Record<string, unknown> = { categoria: c.id }
    if (nome.trim() !== c.nome) params.nome = nome.trim()
    if (COR_OK.test(cor) && cor.toLowerCase() !== (c.cor ?? '').toLowerCase()) params.cor = cor
    if (Object.keys(params).length === 1) { setModo('ver'); return }
    if (await executar(`cat-${c.id}`, 'financas.categoria_editar', params)) { setModo('ver'); avisos.mostrar('Categoria atualizada.') }
  }
  async function apagar() {
    if (await executar(`cat-${c.id}`, 'financas.categoria_eliminar', { categoria: c.id }, true)) {
      avisos.mostrar('Categoria apagada.', () => void executar('desfazer', 'financas.categoria_criar', { nome: c.nome, ...(c.cor ? { cor: c.cor } : {}) }))
    }
  }
  if (modo === 'editar') {
    return (
      <li className="edit">
        <form className="quick" onSubmit={guardar} aria-label={`Editar ${c.nome}`}>
          <input className="input input-sm grow-input" aria-label="Nome" maxLength={40} value={nome} onChange={(e) => setNome(e.target.value)} />
          <input type="color" aria-label="Cor" value={COR_OK.test(cor) ? cor : '#8A918E'} onChange={(e) => setCor(e.target.value)} />
          <Botao type="submit" pequeno carregando={ocupado === `cat-${c.id}`} disabled={nome.trim() === '' || ocupado !== null}>Guardar</Botao>
          <Botao type="button" variante="secondary" pequeno onClick={() => setModo('ver')}>Cancelar</Botao>
        </form>
      </li>
    )
  }
  return (
    <li>
      <span className="bolinha" style={{ background: c.cor ?? '#8A918E' }} aria-hidden="true" />
      <div className="row-main t-body">{c.nome}</div>
      {modo === 'apagar' ? (
        <div className="quick" role="group" aria-label={`Apagar ${c.nome}`}>
          <span className="t-meta">Só apaga se não tiver lançamentos.</span>
          <Botao variante="danger" pequeno carregando={ocupado === `cat-${c.id}`} disabled={ocupado !== null} onClick={() => void apagar()}>Apagar</Botao>
          <Botao variante="secondary" pequeno onClick={() => setModo('ver')}>Cancelar</Botao>
        </div>
      ) : (
        <>
          <button type="button" className="link-btn" aria-label={`Editar ${c.nome}`} onClick={() => setModo('editar')}>Editar</button>
          <button type="button" className="link-btn link-danger" aria-label={`Apagar ${c.nome}`} onClick={() => setModo('apagar')}>Apagar</button>
        </>
      )}
    </li>
  )
}

export function CategoriasTab({ categorias, ...f }: { categorias: CategoriaFin[] } & Ferramentas) {
  const [nome, setNome] = useState('')
  async function criar(ev: FormEvent) {
    ev.preventDefault()
    if (!nome.trim()) return
    if (await f.executar('nova-cat', 'financas.categoria_criar', { nome: nome.trim() })) { setNome(''); f.avisos.mostrar('Categoria criada.') }
  }
  return (
    <div className="stack">
      <form className="card" onSubmit={criar} noValidate aria-label="Nova categoria">
        <h2 className="t-card">Nova categoria</h2>
        <div className="quick">
          <label className="sr-only" htmlFor="cat-nome">Nome da categoria</label>
          <input id="cat-nome" className="input input-sm grow-input" maxLength={40} value={nome} onChange={(e) => setNome(e.target.value)} />
          <Botao type="submit" pequeno carregando={f.ocupado === 'nova-cat'} disabled={!nome.trim() || f.ocupado !== null}>Adicionar</Botao>
        </div>
      </form>
      <section className="card" aria-label="Categorias"><h2 className="t-card">Categorias <span className="t-meta">{categorias.length}</span></h2>
        <ul className="rows">{categorias.map((c) => <Linha key={c.id} c={c} f={f} />)}</ul></section>
    </div>
  )
}
