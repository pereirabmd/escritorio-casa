import { useState } from 'react'
import type { PesoModulo } from '../../api/types'
import { LineChart, mediaMovel, type Ponto } from '../../components/LineChart'
import { fmtDataIso, fmtPeso } from '../../lib/format'

const PERIODOS = [
  { id: '7d', nome: '7 d', longo: '7 dias', dias: 7 }, { id: '30d', nome: '30 d', longo: '30 dias', dias: 30 }, { id: '90d', nome: '90 d', longo: '90 dias', dias: 90 },
  { id: '6m', nome: '6 m', longo: '6 meses', dias: 182 }, { id: '1a', nome: '1 a', longo: '1 ano', dias: 365 }, { id: 'tudo', nome: 'Tudo', longo: 'Todo o período', dias: null },
] as const

const instante = (quando: string) => new Date(quando.replace(' ', 'T')).getTime()

export function GraficoTab({ dados }: { dados: PesoModulo }) {
  const [periodo, setPeriodo] = useState<(typeof PERIODOS)[number]['id']>('90d')
  const todos: Ponto[] = dados.registos.map((r) => ({ t: instante(r.quando), v: r.peso }))
  const dias = PERIODOS.find((p) => p.id === periodo)!.dias
  const fim = todos.length ? todos[todos.length - 1].t : 0
  const pontos = dias === null ? todos : todos.filter((p) => p.t >= fim - dias * 86400000)
  const resumo = pontos.length
    ? `Evolução do peso: ${pontos.length} registos, de ${fmtPeso(pontos[0].v)} em ${fmtDataIso(new Date(pontos[0].t).toISOString())} a ${fmtPeso(pontos[pontos.length - 1].v)} em ${fmtDataIso(new Date(pontos[pontos.length - 1].t).toISOString())}.`
    : 'Sem registos neste período.'

  return (
    <div className="stack">
      <div className="segmented periodos" role="group" aria-label="Período do gráfico">
        {PERIODOS.map((p) => <button key={p.id} aria-pressed={periodo === p.id} aria-label={p.longo} onClick={() => setPeriodo(p.id)}>{p.nome}</button>)}
      </div>
      <section className="card" aria-label="Gráfico de evolução do peso">
        <LineChart pontos={pontos} media={mediaMovel(pontos)} alvo={dados.config.pesoAlvo ?? null} resumoAcessivel={resumo} />
        <div className="legend t-meta">
          <span><i className="swatch swatch-line" />Peso</span><span><i className="swatch swatch-avg" />Média de 7 dias</span>
          {dados.config.pesoAlvo ? <span><i className="swatch swatch-goal" />Peso alvo ({fmtPeso(dados.config.pesoAlvo)})</span> : null}
        </div>
      </section>
    </div>
  )
}
