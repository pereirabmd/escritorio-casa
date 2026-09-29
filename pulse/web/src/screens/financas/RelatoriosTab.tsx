import { useState } from 'react'
import { api, mensagemDeErro } from '../../api/client'
import type { RelatorioFin } from '../../api/types'
import { BrandLoading, Notice } from '../../components/ui'
import { somarMeses, tituloMesFin } from '../../lib/financas'
import { fmtEuro } from '../../lib/format'
import { useAsync } from '../../lib/useAsync'

const PERIODOS = [{ n: 3, nome: '3 meses' }, { n: 6, nome: '6 meses' }, { n: 12, nome: '12 meses' }] as const

/** Os N meses que terminam no mês à vista: totais por mês e por categoria (calculados no servidor). */
export function RelatoriosTab({ mes }: { mes: string }) {
  const [n, setN] = useState<number>(6)
  const de = somarMeses(mes, -(n - 1))
  const [estado, recarregar] = useAsync(() => api.get<RelatorioFin>(`/finance/reports?de=${de}&ate=${mes}`), `${de}|${mes}`)
  return (
    <div className="stack">
      <div className="chips" role="group" aria-label="Período do relatório">
        {PERIODOS.map((p) => <button key={p.n} type="button" className="chip" aria-pressed={n === p.n} onClick={() => setN(p.n)}>{p.nome}</button>)}
      </div>
      <p className="t-meta">{tituloMesFin(de)} a {tituloMesFin(mes)}</p>
      {estado.fase === 'a-carregar' && <BrandLoading texto="A calcular o relatório…" />}
      {estado.fase === 'erro' && <Notice tipo="error">{mensagemDeErro(estado.erro)} <button type="button" className="link-btn" onClick={recarregar}>Tentar de novo</button></Notice>}
      {estado.fase === 'pronto' && <Corpo r={estado.dados} />}
    </div>
  )
}

function Corpo({ r }: { r: RelatorioFin }) {
  const maximo = Math.max(...r.meses.map((m) => Math.max(m.rendimento, m.despesas)), 1)
  return (
    <>
      <section className="card" aria-label="Por mês">
        <h2 className="t-card">Rendimento e despesas por mês</h2>
        <ul className="rows">
          {r.meses.map((m) => (
            <li key={m.mes}>
              <div className="row-main">
                <div className="split"><span className="t-body">{tituloMesFin(m.mes)}</span><span className={`t-body${m.saldo < 0 ? ' link-danger' : ''}`}>{fmtEuro(m.saldo)}</span></div>
                <div className="t-meta">Rendimento {fmtEuro(m.rendimento)} · Despesas {fmtEuro(m.despesas)}</div>
                <div className="barra" aria-hidden="true"><i style={{ width: `${(m.despesas / maximo) * 100}%`, background: 'var(--error)' }} /></div>
                <div className="barra" aria-hidden="true"><i style={{ width: `${(m.rendimento / maximo) * 100}%`, background: 'var(--accent)' }} /></div>
              </div>
            </li>
          ))}
        </ul>
        <div className="split"><strong>Total</strong><span className="t-meta">Rendimento {fmtEuro(r.totais.rendimento)} · Despesas {fmtEuro(r.totais.despesas)}</span></div>
      </section>
      <section className="card" aria-label="Despesas por categoria">
        <h2 className="t-card">Despesas por categoria</h2>
        {r.categorias.length === 0 ? <p className="t-body2">Sem despesas neste período.</p> : (
          <ul className="rows">
            {r.categorias.map((c) => (
              <li key={c.categoriaId}><div className="row-main">
                <div className="split"><span className="t-body">{c.nome}</span><span className="t-body">{fmtEuro(c.total)}</span></div>
                <div className="barra" aria-hidden="true"><i style={{ width: `${Math.max(2, (c.total / r.categorias[0].total) * 100)}%`, background: c.cor ?? 'var(--accent)' }} /></div>
              </div></li>
            ))}
          </ul>
        )}
      </section>
    </>
  )
}
