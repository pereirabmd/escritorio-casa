import type { InstanciaTarefa } from '../api/types'

export const DIAS = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab'] as const
export const DIAS_NOME: Record<string, string> = { Dom: 'Domingo', Seg: 'Segunda', Ter: 'Terça', Qua: 'Quarta', Qui: 'Quinta', Sex: 'Sexta', Sab: 'Sábado' }
export const RECORRENCIAS = [
  ['Diaria', 'Todos os dias'], ['Semanal', 'Semanal'], ['Dias especificos', 'Dias específicos'], ['Mensal', 'Mensal'],
  ['Trimestral', 'A cada 3 meses'], ['Semestral', 'A cada 6 meses'], ['Pontual', 'Uma só vez'],
] as const
export const COM_DIAS = ['Semanal', 'Dias especificos']
export const COM_DATA = ['Pontual', 'Trimestral', 'Semestral']

const CHAVE_FILTRO = 'pulse.tarefas.filtro'
export const lerFiltro = (): string => { try { return localStorage.getItem(CHAVE_FILTRO) || 'todas' } catch { return 'todas' } }
export const guardarFiltro = (v: string) => { try { localStorage.setItem(CHAVE_FILTRO, v) } catch { /* sem armazenamento */ } }

/** «hoje às 08:00», «ontem às 21:10» ou «29/09 às 07:00» a partir de «AAAA-MM-DD HH:MM». */
export function quando(dataConclusao: string, hoje: string): string {
  const [d, h] = dataConclusao.split(' ')
  if (!d || !h) return dataConclusao
  const ontem = new Date(`${hoje}T12:00:00`); ontem.setDate(ontem.getDate() - 1)
  const ontemIso = `${ontem.getFullYear()}-${String(ontem.getMonth() + 1).padStart(2, '0')}-${String(ontem.getDate()).padStart(2, '0')}`
  if (d === hoje) return `hoje às ${h}`
  if (d === ontemIso) return `ontem às ${h}`
  return `${d.slice(8)}/${d.slice(5, 7)} às ${h}`
}

export const passaFiltro = (i: InstanciaTarefa, filtro: string, minha: string | null) =>
  filtro === 'todas' ? true : filtro === 'minhas' ? i.pessoa === minha : i.pessoa === filtro

/** Liga ao Google Calendar com o evento pré-preenchido (sem sincronização automática). */
export function urlGoogleCalendar(i: InstanciaTarefa, horaPadrao: string): string {
  const hora = i.hora || horaPadrao || '08:00'
  const [h, m] = hora.split(':')
  const ini = `${i.data.replace(/-/g, '')}T${h.padStart(2, '0')}${m.padStart(2, '0')}00`
  const fim = new Date(`${i.data}T${hora}:00`); fim.setMinutes(fim.getMinutes() + 30)
  const p = (n: number) => String(n).padStart(2, '0')
  const fimTxt = `${fim.getFullYear()}${p(fim.getMonth() + 1)}${p(fim.getDate())}T${p(fim.getHours())}${p(fim.getMinutes())}00`
  return `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${encodeURIComponent(i.nome)}&dates=${ini}/${fimTxt}&details=${encodeURIComponent(`Tarefa de casa — ${i.pessoa}`)}`
}
