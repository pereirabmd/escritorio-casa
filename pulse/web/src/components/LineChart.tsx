import { fmtDataIso } from '../lib/format'

export interface Ponto { t: number; v: number }

/** Gráfico de linha em SVG (sem bibliotecas): série, média móvel, linha do peso alvo e eixos. Legível por leitores de ecrã. */
export function LineChart({ pontos, media, alvo, resumoAcessivel }: { pontos: Ponto[]; media?: Ponto[]; alvo?: number | null; resumoAcessivel: string }) {
  const W = 360, H = 240, L = 40, R = 10, T = 10, B = 26
  if (pontos.length === 0) return <p className="t-body2">Sem registos neste período.</p>
  const ts = pontos.map((p) => p.t), vs = pontos.map((p) => p.v)
  const t0 = Math.min(...ts), t1 = Math.max(...ts)
  let v0 = Math.min(...vs), v1 = Math.max(...vs)
  if (v1 - v0 < 1) { v0 -= 0.5; v1 += 0.5 }
  const margem = (v1 - v0) * 0.12
  v0 -= margem; v1 += margem
  const alvoVisivel = alvo != null && alvo >= v0 && alvo <= v1      // um alvo longe da série não achata o gráfico: fica só na legenda
  const x = (t: number) => L + (t1 === t0 ? (W - L - R) / 2 : ((t - t0) / (t1 - t0)) * (W - L - R))
  const y = (v: number) => T + (1 - (v - v0) / (v1 - v0)) * (H - T - B)
  const linha = (ps: Ponto[]) => ps.map((p, i) => `${i ? 'L' : 'M'}${x(p.t).toFixed(1)} ${y(p.v).toFixed(1)}`).join(' ')
  const graduacoes = [0, 1, 2, 3].map((i) => v0 + ((v1 - v0) * i) / 3)
  const iso = (t: number) => new Date(t).toISOString().slice(0, 10)

  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={resumoAcessivel}>
      {graduacoes.map((v) => (
        <g key={v}>
          <line className="chart-grid" x1={L} x2={W - R} y1={y(v)} y2={y(v)} />
          <text className="chart-text" x={L - 8} y={y(v) + 4} textAnchor="end">{v.toFixed(1).replace('.', ',')}</text>
        </g>
      ))}
      {alvoVisivel && alvo != null ? <line className="chart-goal" x1={L} x2={W - R} y1={y(alvo)} y2={y(alvo)} /> : null}
      {media && media.length > 1 ? <path className="chart-avg" d={linha(media)} fill="none" /> : null}
      <path className="chart-line" d={linha(pontos)} fill="none" />
      {pontos.length <= 60 && pontos.map((p) => <circle key={p.t} className="chart-dot" cx={x(p.t)} cy={y(p.v)} r={3} />)}
      <text className="chart-text" x={L} y={H - 6} textAnchor="start">{fmtDataIso(iso(t0))}</text>
      {t1 !== t0 && <text className="chart-text" x={W - R} y={H - 6} textAnchor="end">{fmtDataIso(iso(t1))}</text>}
    </svg>
  )
}

/** Média móvel de `dias` dias (como na app dedicada): média dos registos da janela que termina em cada ponto. */
export function mediaMovel(pontos: Ponto[], dias = 7): Ponto[] {
  const janela = (dias - 1) * 86400000
  return pontos.map((p) => {
    const dentro = pontos.filter((q) => q.t >= p.t - janela && q.t <= p.t)
    return { t: p.t, v: dentro.reduce((s, q) => s + q.v, 0) / dentro.length }
  })
}
