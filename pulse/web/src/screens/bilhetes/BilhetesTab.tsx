import type { BilheteCp, BilhetesModulo } from '../../api/types'
import { diaCurto } from '../../lib/bilhetes'

/** Um bilhete comprado: rota, hora, comboio e o lugar (carruagem e lugar). */
export function Bilhete({ b }: { b: BilheteCp }) {
  return (
    <article className="card" aria-label={`Bilhete de ${diaCurto(b.data)} às ${b.hora}`}>
      <div className="t-meta">{diaCurto(b.data)}</div>
      <div className="trip"><span className="t-section">{b.hora}</span><span className="t-body">{b.origem}</span><span className="arrow"><span className="sr-only">para</span>→</span><span className="t-body">{b.destino}</span></div>
      <div className="trip t-body2">
        <span>Comboio {b.comboio}</span>
        <span className="pill pill-ok">Carruagem {b.carruagem || '—'} · Lugar {b.lugar || '—'}</span>
        {b.referencia && <span className="t-meta">ref. {b.referencia}</span>}
      </div>
    </article>
  )
}

export function BilhetesTab({ dados }: { dados: BilhetesModulo }) {
  const { proximos, anteriores } = dados.bilhetes
  if (proximos.length + anteriores.length === 0) return <p className="t-body2">Ainda não há bilhetes comprados. Aparecem aqui quando o Pi os compra.</p>
  return (
    <div className="stack">
      {proximos.length > 0 && <section className="stack" aria-label="Próximos bilhetes"><h2 className="t-card">Próximos</h2>{proximos.map((b) => <Bilhete key={b.id} b={b} />)}</section>}
      {anteriores.length > 0 && <section className="stack" aria-label="Bilhetes anteriores"><h2 className="t-card">Anteriores</h2>{anteriores.map((b) => <Bilhete key={b.id} b={b} />)}</section>}
    </div>
  )
}
