import type { RtoModulo } from '../../api/types'
import { DIAS_SEMANA, MESES, marcaDaCelula, semanasDoMes } from '../../lib/rto'

/** Visão do ano: 12 meses em miniatura (mapa de calor). Tocar num mês abre-o no calendário. */
export function AnoTab({ dados, abrirMes }: { dados: RtoModulo; abrirMes: (mes: number) => void }) {
  return (
    <div className="stack">
      <p className="t-body2">Visão de {dados.ano}. Toca num mês para o abrir no calendário.</p>
      <div className="year">
        {MESES.map((nome, m) => {
          const resumo = dados.mensal[m]
          return (
            <button type="button" className="mini" key={nome} onClick={() => abrirMes(m)} aria-label={`${nome}: ${resumo.t} escritório, ${resumo.c} casa. Abrir no calendário`}>
              <span className="t-card">{nome}</span>
              <span className="mini-grid" aria-hidden="true">
                {DIAS_SEMANA.map((d, i) => <i key={`d${i}`} className="mini-dow">{d}</i>)}
                {semanasDoMes(dados.ano, m).flat().map((data, i) => data
                  ? <i key={i} className="mini-day" data-marca={marcaDaCelula(dados, data).classe} />
                  : <i key={i} className="mini-day empty" />)}
              </span>
              <span className="t-meta">{resumo.t} T · {resumo.c} C</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
