const MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']

/** 2026-09 -> «setembro de 2026» */
export function tituloMesFin(mes: string): string {
  return `${MESES[Number(mes.slice(5)) - 1]} de ${mes.slice(0, 4)}`
}

/** Soma (ou subtrai) meses a «AAAA-MM». */
export function somarMeses(mes: string, n: number): string {
  const i = Number(mes.slice(0, 4)) * 12 + Number(mes.slice(5)) - 1 + n
  return `${String(Math.floor(i / 12)).padStart(4, '0')}-${String((i % 12) + 1).padStart(2, '0')}`
}

/** «12,5», «12.5» ou «1 234,50» -> 12.5; vazio, zero, negativo ou inválido -> null. */
export function lerValor(texto: string): number | null {
  const n = Number(texto.trim().replace(/\s/g, '').replace(',', '.'))
  return texto.trim() !== '' && Number.isFinite(n) && n > 0 && n <= 1_000_000_000 ? Math.round(n * 100) / 100 : null
}

export const paraInputValor = (v: number) => String(v).replace('.', ',')

export const ESTADO_TXT: Record<string, string> = { pago: 'Pago', vencido: 'Vencido', hoje: 'Vence hoje', pendente: 'Por pagar' }
