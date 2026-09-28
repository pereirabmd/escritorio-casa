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
