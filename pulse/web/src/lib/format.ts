// Formatos pt-PT do Design System: data 28/09/2026, data escrita «28 de setembro», hora 17:42, moeda 1 245,50 €, peso 104,8 kg.
const eur = new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR', useGrouping: 'always' })
const kg = new Intl.NumberFormat('pt-PT', { minimumFractionDigits: 1, maximumFractionDigits: 1 })

export const fmtEuro = (v: number) => eur.format(v)
export const fmtPeso = (v: number) => `${kg.format(v)} kg`

/** «segunda-feira, 28 de setembro» */
export function fmtDataLonga(d: Date): string {
  const dia = new Intl.DateTimeFormat('pt-PT', { weekday: 'long', day: 'numeric', month: 'long' }).format(d)
  return dia.replace(' de ', ' de ').replace(/^./, (c) => c.toUpperCase())
}

/** 2026-09-28 -> 28/09/2026 */
export function fmtDataIso(iso: string): string {
  const [a, m, d] = iso.slice(0, 10).split('-')
  return `${d}/${m}/${a}`
}

/** 2026-09-28 -> 28 de setembro */
export function fmtDiaMes(iso: string): string {
  const [a, m, d] = iso.slice(0, 10).split('-').map(Number)
  return new Intl.DateTimeFormat('pt-PT', { day: 'numeric', month: 'long' }).format(new Date(a, m - 1, d))
}

/** 2026-10-02 -> «hoje» / «amanhã» / «qui, 2 out» (para listas de eventos que não são só de hoje) */
export function fmtDiaCurto(iso: string, agora: Date = new Date()): string {
  const [a, m, d] = iso.slice(0, 10).split('-').map(Number)
  const dia = new Date(a, m - 1, d)
  const dias = Math.round((dia.getTime() - new Date(agora.getFullYear(), agora.getMonth(), agora.getDate()).getTime()) / 86400000)
  if (dias === 0) return 'Hoje'
  if (dias === 1) return 'Amanhã'
  const SEMANA = ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sáb'], MES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']
  return `${SEMANA[dia.getDay()]}, ${d} ${MES[m - 1]}`
}

export function saudacao(agora: Date): string {
  const h = agora.getHours()
  return h < 5 ? 'Boa noite' : h < 13 ? 'Bom dia' : h < 20 ? 'Boa tarde' : 'Boa noite'
}

/** Dias até uma data: «hoje», «amanhã», «em 5 dias», «há 3 dias». */
export function fmtDias(dias: number): string {
  if (dias === 0) return 'hoje'
  if (dias === 1) return 'amanhã'
  if (dias === -1) return 'ontem'
  return dias > 0 ? `em ${dias} dias` : `há ${-dias} dias`
}

export const plural = (n: number, um: string, varios: string) => (n === 1 ? `${n} ${um}` : `${n} ${varios}`)

/** Diferença em kg com sinal (a descer é bom no Peso): «−1,2 kg» / «+0,4 kg». */
export function fmtDeltaKg(d: number): string {
  if (Math.abs(d) < 0.05) return '0,0 kg'
  return `${d < 0 ? '−' : '+'}${kg.format(Math.abs(d))} kg`
}

export const fmtKg2 = (v: number) => `${new Intl.NumberFormat('pt-PT', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v)} kg`
