import { useMemo, useState, type FormEvent } from 'react'
import type { NotaRto } from '../../api/types'
import { Botao, Notice } from '../../components/ui'
import { fmtDataIso } from '../../lib/format'
import { intervaloNota } from '../../lib/rto'
import type { Ferramentas } from './tipos'

const CATEGORIAS = ['Férias', 'Astreinte', 'RTO Suspensão', 'Validação', 'Validação Batica']

function intervaloTexto(n: NotaRto): string {
  const iv = intervaloNota(n)
  if (!iv) return 'Sem data'
  return iv[0] === iv[1] ? fmtDataIso(iv[0]) : `${fmtDataIso(iv[0])} a ${fmtDataIso(iv[1])}`
}

export function NotasTab({ dados, executar, ocupado, avisos, admin }: Ferramentas & { admin: boolean }) {
  const [editar, setEditar] = useState<number | null>(null)
  const [inicio, setInicio] = useState('')
  const [fim, setFim] = useState('')
  const [categoria, setCategoria] = useState('')
  const [descricao, setDescricao] = useState('')
  const [apagar, setApagar] = useState<number | null>(null)
  const [verTodas, setVerTodas] = useState(false)
  const [erro, setErro] = useState<string | null>(null)
  const [gerar, setGerar] = useState(false)
  const [ref, setRef] = useState('')
  const [tipo, setTipo] = useState<'Validação' | 'Validação Batica'>('Validação')
  const [ate, setAte] = useState('')

  const ano = String(dados.ano)
  const notas = useMemo(() => [...dados.notas]
    .filter((n) => verTodas || [n.dataInicio, n.dataFim].some((d) => d?.startsWith(ano)))
    .sort((a, b) => (intervaloNota(a)?.[0] ?? '9999').localeCompare(intervaloNota(b)?.[0] ?? '9999') || a.id - b.id), [dados.notas, verTodas, ano])

  function limpar() { setEditar(null); setInicio(''); setFim(''); setCategoria(''); setDescricao(''); setErro(null) }
  function comecarEdicao(n: NotaRto) {
    setEditar(n.id); setInicio(n.dataInicio ?? ''); setFim(n.dataFim ?? ''); setCategoria(n.categoria); setDescricao(n.descricao); setErro(null)
    document.getElementById('nota-form')?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
  }

  async function guardar(ev: FormEvent) {
    ev.preventDefault()
    if (!inicio && !fim && !categoria.trim() && !descricao.trim()) { setErro('A nota não pode estar vazia.'); return }
    if (inicio && fim && fim < inicio) { setErro('A data de fim é anterior à de início.'); return }
    setErro(null)
    const corpo = { inicio: inicio || null, fim: fim || null, categoria: categoria.trim(), descricao: descricao.trim(), admin: admin }
    const ok = editar === null ? await executar('nota', 'rto.nota_criar', corpo) : await executar('nota', 'rto.nota_editar', { ...corpo, nota: editar })
    if (ok) { limpar(); avisos.mostrar(editar === null ? 'Nota criada.' : 'Nota atualizada.') }
  }

  async function eliminar(n: NotaRto) {
    const r = await executar(`del-${n.id}`, 'rto.nota_eliminar', { nota: n.id, admin: admin }, true)
    if (r) {
      setApagar(null)
      avisos.mostrar('Nota eliminada.', () => void executar('desfazer', 'rto.nota_restaurar', {
        nota: n.id, inicio: n.dataInicio, fim: n.dataFim, categoria: n.categoria, descricao: n.descricao, admin: true }))
    }
  }

  async function gerarValidacoes(ev: FormEvent) {
    ev.preventDefault()
    if (!ref || !ate) { setErro('Preenche a data de referência e a data limite.'); return }
    if (ate < ref) { setErro('A data limite tem de ser depois da data de referência.'); return }
    setErro(null)
    const r = await executar('gerar', 'rto.gerar_validacoes', { referencia: ref, ate, tipo }) as { criadas?: number; existentes?: number } | null
    if (r) { setGerar(false); avisos.mostrar(`${r.criadas ?? 0} validações criadas${r.existentes ? ` (${r.existentes} já existiam)` : ''}.`) }
  }

  return (
    <div className="stack">
      {!admin && <p className="t-meta">Notas em datas já passadas só se criam, alteram ou apagam no modo administrador (separador Calendário).</p>}

      <form className="card" id="nota-form" onSubmit={guardar} aria-label={editar === null ? 'Nova nota' : 'Editar nota'}>
        <h2 className="t-card">{editar === null ? 'Nova nota' : 'Editar nota'}</h2>
        {erro && <Notice tipo="error">{erro}</Notice>}
        <div className="fields">
          <div className="field"><label htmlFor="n-ini">Data de início</label><input id="n-ini" className="input" type="date" value={inicio} onChange={(e) => setInicio(e.target.value)} /></div>
          <div className="field"><label htmlFor="n-fim">Data de fim</label><input id="n-fim" className="input" type="date" value={fim} onChange={(e) => setFim(e.target.value)} /></div>
          <div className="field"><label htmlFor="n-cat">Categoria</label><input id="n-cat" className="input" list="rto-cats" maxLength={100} value={categoria} onChange={(e) => setCategoria(e.target.value)} />
            <datalist id="rto-cats">{CATEGORIAS.map((c) => <option key={c} value={c} />)}</datalist></div>
          <div className="field"><label htmlFor="n-desc">Descrição</label><input id="n-desc" className="input" maxLength={500} value={descricao} onChange={(e) => setDescricao(e.target.value)} /></div>
        </div>
        <div className="quick">
          <Botao type="submit" carregando={ocupado === 'nota'} disabled={ocupado !== null}>{editar === null ? 'Adicionar nota' : 'Guardar alterações'}</Botao>
          {editar !== null && <Botao type="button" variante="secondary" onClick={limpar}>Cancelar</Botao>}
        </div>
      </form>

      <section className="card" aria-label="Notas">
        <div className="card-head"><h2 className="t-card grow">Notas de {verTodas ? 'todos os anos' : ano} <span className="t-meta">{notas.length}</span></h2>
          <button type="button" className="link-btn" onClick={() => setVerTodas((v) => !v)}>{verTodas ? `Só ${ano}` : 'Ver todas'}</button></div>
        {notas.length === 0 ? <p className="t-body2">Sem notas.</p> : (
          <ul className="rows">{notas.slice(0, 300).map((n) => (
            <li key={n.id}>
              <div className="row-main"><div className="t-body">{n.categoria || 'Nota'}{n.descricao ? ` — ${n.descricao}` : ''}</div><div className="t-meta">{intervaloTexto(n)}</div></div>
              {apagar === n.id ? (
                <div className="quick" role="group" aria-label={`Eliminar nota ${n.categoria || n.id}`}>
                  <span className="t-meta">Eliminar?</span>
                  <Botao variante="danger" pequeno carregando={ocupado === `del-${n.id}`} disabled={ocupado !== null} onClick={() => void eliminar(n)}>Eliminar</Botao>
                  <Botao variante="secondary" pequeno onClick={() => setApagar(null)}>Cancelar</Botao>
                </div>
              ) : (
                <>
                  <button type="button" className="link-btn" aria-label={`Editar nota ${n.categoria || n.id} de ${intervaloTexto(n)}`} onClick={() => comecarEdicao(n)}>Editar</button>
                  <button type="button" className="link-btn link-danger" aria-label={`Eliminar nota ${n.categoria || n.id} de ${intervaloTexto(n)}`} onClick={() => setApagar(n.id)}>Eliminar</button>
                </>
              )}
            </li>
          ))}</ul>
        )}
        {notas.length > 300 && <p className="t-meta">A mostrar as 300 primeiras.</p>}
      </section>

      <section className="card" aria-label="Gerador de validações">
        <div className="card-head"><h2 className="t-card grow">Validações periódicas</h2><button type="button" className="link-btn" aria-expanded={gerar} onClick={() => setGerar((v) => !v)}>{gerar ? 'Fechar' : 'Gerar'}</button></div>
        {gerar && (
          <form onSubmit={gerarValidacoes} aria-label="Gerar validações">
            <p className="t-body2">Cria uma validação de 14 em 14 dias, alternando os dois tipos, a partir de uma conhecida.</p>
            <div className="fields">
              <div className="field"><label htmlFor="g-ref">Data de uma validação conhecida</label><input id="g-ref" className="input" type="date" value={ref} onChange={(e) => setRef(e.target.value)} /></div>
              <div className="field"><label htmlFor="g-tipo">Tipo dessa validação</label>
                <select id="g-tipo" className="input" value={tipo} onChange={(e) => setTipo(e.target.value as 'Validação' | 'Validação Batica')}><option value="Validação">Normal</option><option value="Validação Batica">Batica</option></select></div>
              <div className="field"><label htmlFor="g-ate">Gerar até</label><input id="g-ate" className="input" type="date" value={ate} onChange={(e) => setAte(e.target.value)} /></div>
            </div>
            <Botao type="submit" carregando={ocupado === 'gerar'} disabled={ocupado !== null}>Gerar validações</Botao>
          </form>
        )}
      </section>
    </div>
  )
}
