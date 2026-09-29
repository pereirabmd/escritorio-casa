import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, mensagemDeErro } from '../../api/client'
import type { ComprasModulo } from '../../api/types'
import { useAvisos } from '../../components/Avisos'
import { Icon } from '../../components/Icon'
import { BrandLoading, Botao, Notice } from '../../components/ui'
import { useAcao } from '../../lib/useAcao'
import { useAsync } from '../../lib/useAsync'
import { CatalogoTab } from './CatalogoTab'
import { ListaTab } from './ListaTab'

const ATUALIZAR_MS = 30000          // a lista é partilhada: vê-se o que os outros vão acrescentando

export function ComprasScreen() {
  const [params] = useSearchParams()
  const [aba, setAba] = useState<'lista' | 'catalogo'>(params.get('aba') === 'catalogo' ? 'catalogo' : 'lista')
  const [lista, setLista] = useState<number | null>(null)                 // null = a «Casa»
  const [estado, recarregar] = useAsync(() => api.get<ComprasModulo>(`/shopping${lista ? `?lista=${lista}` : ''}`), lista)
  const { ocupado, erro, executar, limparErro } = useAcao(recarregar)
  const avisos = useAvisos()
  const base = useId()
  const [nova, setNova] = useState(false)
  const [gerir, setGerir] = useState(false)
  const ultimo = useRef(recarregar)
  useEffect(() => { ultimo.current = recarregar })
  useEffect(() => {
    const t = setInterval(() => { if (document.visibilityState === 'visible') ultimo.current() }, ATUALIZAR_MS)
    const ao = () => { if (document.visibilityState === 'visible') ultimo.current() }
    document.addEventListener('visibilitychange', ao)
    return () => { clearInterval(t); document.removeEventListener('visibilitychange', ao) }
  }, [])
  const f = { executar, ocupado, avisos }

  return (
    <>
      <header className="hero">
        <Link to="/mais" className="back"><Icon nome="voltar" tamanho={20} />Mais</Link>
        <h1 className="t-page">Compras</h1>
      </header>

      {estado.fase === 'a-carregar' && <BrandLoading texto="A carregar as compras…" />}
      {estado.fase === 'erro' && (
        <div className="state">
          <Notice tipo="error">{mensagemDeErro(estado.erro)}</Notice>
          <Botao variante="secondary" pequeno onClick={recarregar}>Tentar de novo</Botao>
        </div>
      )}
      {estado.fase === 'pronto' && (() => {
        const d = estado.dados
        async function criar(nome: string, tipo: 'pessoal' | 'partilhada') {
          const r = await executar('nova-lista', 'compras.lista_criar', { nome, tipo })
          if (r) { setNova(false); setLista(r.id as number); avisos.mostrar('Lista criada.') }
        }
        return (
          <>
            <div className="chips" role="group" aria-label="Listas">
              {d.listas.map((l) => (
                <button key={l.id} type="button" className="chip" aria-pressed={l.id === d.lista.id} onClick={() => { setLista(l.id); setGerir(false) }}>
                  {l.nome}{l.pendentes > 0 && <> <span className="pill">{l.pendentes}</span></>}{l.tipo === 'pessoal' && <span className="sr-only"> (pessoal)</span>}
                </button>
              ))}
              <button type="button" className="chip" aria-expanded={nova} onClick={() => setNova((v) => !v)}>+ Nova lista</button>
            </div>
            {nova && <NovaLista criar={criar} ocupado={ocupado} fechar={() => setNova(false)} />}
            <p className="t-meta">{d.lista.tipo === 'partilhada' ? 'Lista partilhada: todas as contas a veem e alteram.' : 'Lista pessoal: só tu a vês.'}</p>

            <div className="segmented tabs" role="tablist" aria-label="Secções das Compras">
              <button role="tab" id={`${base}-lista`} aria-selected={aba === 'lista'} aria-controls={`${base}-p`} onClick={() => setAba('lista')}>Lista{d.pendentes > 0 ? ` (${d.pendentes})` : ''}</button>
              <button role="tab" id={`${base}-catalogo`} aria-selected={aba === 'catalogo'} aria-controls={`${base}-p`} onClick={() => setAba('catalogo')}>Catálogo</button>
            </div>
            {erro && <Notice tipo="error">{erro} <button type="button" className="link-btn" onClick={limparErro}>Fechar</button></Notice>}
            <div role="tabpanel" id={`${base}-p`} aria-labelledby={`${base}-${aba}`} className="tabpanel">
              {aba === 'lista' && <ListaTab dados={d} f={f} abrirCatalogo={() => setAba('catalogo')} gerir={gerir} setGerir={setGerir} aoApagarLista={() => setLista(null)} />}
              {aba === 'catalogo' && <CatalogoTab dados={d} f={f} />}
            </div>
          </>
        )
      })()}
    </>
  )
}

function NovaLista({ criar, ocupado, fechar }: { criar: (nome: string, tipo: 'pessoal' | 'partilhada') => Promise<void>; ocupado: string | null; fechar: () => void }) {
  const [nome, setNome] = useState('')
  const [tipo, setTipo] = useState<'pessoal' | 'partilhada'>('pessoal')
  async function submeter(ev: FormEvent) { ev.preventDefault(); if (nome.trim()) await criar(nome.trim(), tipo) }
  return (
    <form className="card stack" onSubmit={submeter} noValidate aria-label="Nova lista">
      <h2 className="t-card">Nova lista</h2>
      <div className="field"><label htmlFor="nl-nome">Nome</label><input id="nl-nome" className="input" maxLength={60} value={nome} onChange={(e) => setNome(e.target.value)} /></div>
      <div className="chips" role="group" aria-label="Tipo de lista">
        <button type="button" className="chip" aria-pressed={tipo === 'pessoal'} onClick={() => setTipo('pessoal')}>Pessoal</button>
        <button type="button" className="chip" aria-pressed={tipo === 'partilhada'} onClick={() => setTipo('partilhada')}>Partilhada</button>
      </div>
      <p className="t-meta">{tipo === 'pessoal' ? 'Só tu vês esta lista.' : 'Todas as contas veem e alteram esta lista.'}</p>
      <div className="quick">
        <Botao type="submit" pequeno carregando={ocupado === 'nova-lista'} disabled={!nome.trim() || ocupado !== null}>Criar</Botao>
        <Botao type="button" pequeno variante="secondary" onClick={fechar}>Cancelar</Botao>
      </div>
    </form>
  )
}
