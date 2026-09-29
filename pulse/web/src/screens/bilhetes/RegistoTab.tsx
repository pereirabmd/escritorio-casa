import { useState } from 'react'
import type { BilhetesModulo } from '../../api/types'
import { classeRegisto, diaMes, RESULTADO_REGISTO, TIPO_REGISTO } from '../../lib/bilhetes'

const FILTROS = [{ id: 'tudo', nome: 'Tudo' }, { id: 'compras', nome: 'Compras' }, { id: 'problemas', nome: 'Problemas' }] as const

const hora = (ts: string) => ts.slice(11, 16)

export function RegistoTab({ dados }: { dados: BilhetesModulo }) {
  const [filtro, setFiltro] = useState<(typeof FILTROS)[number]['id']>('tudo')
  const linhas = dados.registo.filter((r) => filtro === 'tudo' || (filtro === 'compras' ? /COMPRA/i.test(r.tipo) : ['err', 'warn'].includes(classeRegisto(r))))
  return (
    <div className="stack">
      <div className="chips" role="group" aria-label="Filtro do registo">
        {FILTROS.map((x) => <button key={x.id} type="button" className="chip" aria-pressed={filtro === x.id} onClick={() => setFiltro(x.id)}>{x.nome}</button>)}
      </div>
      {linhas.length === 0 ? <p className="t-body2">Sem registos para mostrar.</p> : (
        <section className="card" aria-label="Registo"><ul className="rows">
          {linhas.map((r, i) => {
            const classe = classeRegisto(r)
            const oQue = [r.comboio && `comboio ${r.comboio}`, r.data && diaMes(r.data)].filter(Boolean).join(' · ')
            return (
              <li key={`${r.ts}-${i}`}>
                <div className="row-main">
                  <div className="t-body">{r.ts.slice(0, 10) && `${diaMes(r.ts.slice(0, 10))} ${hora(r.ts)}`} <span className={`pill${classe === 'ok' ? ' pill-ok' : classe ? ' pill-soon' : ''}`}>{RESULTADO_REGISTO[r.resultado ?? ''] ?? r.resultado ?? TIPO_REGISTO[r.tipo] ?? r.tipo}</span> <span className="t-meta">{TIPO_REGISTO[r.tipo] ?? r.tipo}</span></div>
                  {oQue && <div className="t-meta">{oQue}</div>}
                  {r.erro && <div className="t-meta">{r.erro}</div>}
                </div>
              </li>
            )
          })}
        </ul></section>
      )}
    </div>
  )
}
