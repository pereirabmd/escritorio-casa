import type { PesoModulo } from '../../api/types'
import { fmtDataIso, fmtDeltaKg, fmtKg2, fmtPeso, plural } from '../../lib/format'

const CONTROLO = { acima: 'Acima do controlo', abaixo: 'Abaixo do controlo', dentro: 'Dentro do controlo' } as const

function Estatistica({ rotulo, valor, nota }: { rotulo: string; valor: string; nota?: string }) {
  return <div className="stat"><div className="t-meta">{rotulo}</div><div className="t-card stat-val">{valor}</div>{nota && <div className="t-meta">{nota}</div>}</div>
}

export function ResumoTab({ dados }: { dados: PesoModulo }) {
  const r = dados.resumo
  if (!r.ultimo) return <div className="card"><p className="t-body2">Ainda sem registos — regista o teu primeiro peso no separador Registos.</p></div>
  const a = r.analise
  const previsao = r.previsao
  const insights: { rotulo: string; valor: string }[] = []
  if (a.tendencia) insights.push({ rotulo: `Tendência (${a.tendencia.pontos} registos em ${a.tendencia.dias} dias)`, valor: `${Math.abs(a.tendencia.kgSemana).toFixed(2).replace('.', ',')} kg/sem de ${a.tendencia.kgSemana <= 0 ? 'perda' : 'ganho'}` })
  if (a.mensal) insights.push({ rotulo: 'Evolução mensal', valor: `${fmtDeltaKg(a.mensal.diff)} vs mês anterior` })
  if (a.melhorSemana) insights.push({ rotulo: 'Melhor semana', valor: fmtDeltaKg(a.melhorSemana.diff) })
  if (a.piorSemana) insights.push({ rotulo: 'Semana mais difícil', valor: fmtDeltaKg(a.piorSemana.diff) })

  return (
    <div className="stack">
      <section className="card" aria-label="Peso atual">
        <div><span className="t-metric">{fmtPeso(r.ultimo.peso)}</span></div>
        <p className="t-body2">
          {r.anterior
            ? (Math.abs(r.anterior.diferenca) < 0.05 ? `Igual ao registo de ${fmtDataIso(r.anterior.quando)}` : `${r.anterior.diferenca > 0 ? '↑' : '↓'} ${fmtPeso(Math.abs(r.anterior.diferenca))} desde ${fmtDataIso(r.anterior.quando)}`)
            : 'Primeiro registo.'}
        </p>
        <div className="tags">
          {(r.sequenciaDias ?? 0) >= 2 && <span className="pill">Sequência de {plural(r.sequenciaDias!, 'dia', 'dias')}</span>}
          {r.novoMinimo && <span className="pill pill-ok">Novo mínimo</span>}
          {r.controlo && <span className={`pill ${r.controlo === 'dentro' ? 'pill-ok' : 'pill-soon'}`}>{CONTROLO[r.controlo]}</span>}
        </div>
      </section>

      <section className="card" aria-label="Progresso">
        <h2 className="t-card">Objetivo</h2>
        {r.progresso ? (
          <>
            <progress className="meter" value={Math.round(r.progresso.pct)} max={100} aria-label="Progresso para o peso alvo" />
            <div className="split t-body2"><span>{fmtPeso(r.progresso.inicial)}</span><span>{Math.round(r.progresso.pct)}%</span><span>{fmtPeso(r.progresso.alvo)}</span></div>
          </>
        ) : <p className="t-body2">Define um peso alvo em Configuração para veres o progresso.</p>}
        <div className="stats">
          <Estatistica rotulo="Total perdido" valor={(r.totalPerdido ?? 0) >= 0 ? fmtPeso(r.totalPerdido ?? 0) : `+${fmtPeso(-(r.totalPerdido ?? 0))}`} nota={(r.totalPerdido ?? 0) < 0 ? 'Mais do que no primeiro registo' : undefined} />
          <Estatistica rotulo="Ritmo semanal" valor={r.ritmo ? `${r.ritmo.kgSemana >= 0 ? '−' : '+'}${fmtKg2(Math.abs(r.ritmo.kgSemana))}` : '—'} nota={r.ritmo ? `${r.ritmo.kgDia >= 0 ? '−' : '+'}${Math.abs(r.ritmo.kgDia).toFixed(3).replace('.', ',')} kg/dia` : undefined} />
          <Estatistica rotulo="Faltam" valor={r.faltam ? (r.faltam.atingido ? 'Atingido' : fmtPeso(r.faltam.kg)) : '—'} />
        </div>
        <p className="t-body2">
          {previsao.estado === 'ok' && previsao.data && `Ao ritmo atual (~${(previsao.kgSemana ?? 0).toFixed(2).replace('.', ',')} kg/sem): objetivo previsto para ${fmtDataIso(previsao.data)}.`}
          {previsao.estado === 'atingido' && 'Objetivo já atingido.'}
          {previsao.estado === 'poucos_registos' && 'Regista mais alguns pesos para veres uma previsão.'}
          {previsao.estado === 'sem_alvo' && 'Define o peso alvo em Configuração para veres uma previsão de data.'}
          {previsao.estado === 'sem_tendencia' && 'Sem tendência de perda clara nos últimos registos — sem previsão de data.'}
        </p>
      </section>

      <section className="card" aria-label="Corpo">
        <h2 className="t-card">Corpo</h2>
        <div className="stats">
          <Estatistica rotulo="IMC" valor={r.imc ? r.imc.valor.toFixed(1).replace('.', ',') : '—'} nota={r.imc?.classe ?? (dados.config.altura ? undefined : 'Define a altura em Configuração')} />
          <Estatistica rotulo="Gasto diário" valor={r.gastoDiario ? `${r.gastoDiario} kcal` : '—'} nota={r.gastoDiario ? undefined : 'Precisa de altura, nascimento e sexo'} />
          <Estatistica rotulo="Mín / Máx" valor={r.minimo !== undefined ? `${r.minimo.toFixed(1).replace('.', ',')} / ${r.maximo!.toFixed(1).replace('.', ',')}` : '—'} />
        </div>
      </section>

      <section className="card" aria-label="Análise">
        <h2 className="t-card">Análise</h2>
        {insights.length ? (
          <ul className="rows">{insights.map((i) => <li key={i.rotulo}><span className="row-main t-body2">{i.rotulo}</span><span className="row-end t-body">{i.valor}</span></li>)}</ul>
        ) : <p className="t-body2">Regista pesos em pelo menos 3 semanas diferentes para veres tendências e comparações aqui.</p>}
      </section>
    </div>
  )
}
