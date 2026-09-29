import type { NotaRto, RtoModulo } from '../api/types'

export const MESES = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
export const DIAS_SEMANA = ['S', 'T', 'Q', 'Q', 'S', 'S', 'D']          // segunda a domingo
const pad = (n: number) => String(n).padStart(2, '0')
export const iso = (a: number, m: number, d: number) => `${a}-${pad(m + 1)}-${pad(d)}`

export function hojeLocal(): string {
  const h = new Date()
  return iso(h.getFullYear(), h.getMonth(), h.getDate())
}

/** Semanas (segunda a domingo) de um mês, com `null` nas posições fora do mês. */
export function semanasDoMes(ano: number, mes: number): (string | null)[][] {
  const primeiro = (new Date(ano, mes, 1).getDay() + 6) % 7        // 0 = segunda
  const dias = new Date(ano, mes + 1, 0).getDate()
  const celulas: (string | null)[] = [...Array<null>(primeiro).fill(null), ...Array.from({ length: dias }, (_, i) => iso(ano, mes, i + 1))]
  while (celulas.length % 7) celulas.push(null)
  return Array.from({ length: celulas.length / 7 }, (_, i) => celulas.slice(i * 7, i * 7 + 7))
}

export function intervaloNota(n: NotaRto): [string, string] | null {
  const ini = n.dataInicio || n.dataFim
  if (!ini) return null
  const fim = n.dataFim || ini
  return fim >= ini ? [ini, fim] : null
}

export const notasDoDia = (notas: NotaRto[], data: string) => notas.filter((n) => { const iv = intervaloNota(n); return iv && iv[0] <= data && data <= iv[1] })

/** O que a célula mostra (igual à app dedicada): T/C manda; senão feriado (com A por cima), senão a letra da nota (F/A). */
export function marcaDaCelula(d: RtoModulo, data: string): { texto: string; classe: string } {
  const marca = d.dias[data] ?? ''
  const feriado = data in d.feriados
  const letra = !marca ? d.marcasNotas[data] ?? '' : ''
  if (marca) return { texto: marca, classe: marca }
  if (feriado && letra === 'A') return { texto: 'Af', classe: 'A' }
  if (feriado) return { texto: 'f', classe: 'holiday' }
  if (letra) return { texto: letra, classe: letra }
  return { texto: '', classe: '' }
}

export const textoHoje = (h: RtoModulo['hoje']) => ({
  escritorio: 'Escritório', casa: 'Casa', ferias: 'Férias', feriado: 'Feriado', fim_de_semana: 'Fim de semana', astreinte: 'Astreinte', por_definir: 'Ainda por definir',
} as const)[h.estado]

export function textoProximaMudanca(m: NonNullable<RtoModulo['proximaMudanca']>): string {
  const quando = m.dias === 1 ? 'amanhã' : `daqui a ${m.dias} dias`
  return m.tipo === 'feriado' ? `Feriado ${m.dias === 1 ? 'amanhã' : `a ${m.dias} dias`} — ${m.nome}` : `Férias a começar ${quando}`
}

export const nomeMes = (mes: number) => MESES[((mes % 12) + 12) % 12]

/** No modo normal só se marcam dias úteis de hoje em diante (regra da app dedicada); o modo administrador levanta a restrição. */
export function diaBloqueado(data: string, hoje: string): boolean {
  const [a, m, d] = data.split('-').map(Number)
  const dow = new Date(a, m - 1, d).getDay()
  return dow === 0 || dow === 6 || data < hoje
}
