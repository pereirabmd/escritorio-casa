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

// --- Calendário -------------------------------------------------------------------------------------------------------------

const p2 = (n: number) => String(n).padStart(2, '0')
export const isoLocal = (d: Date) => `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}`
export const dataDeIso = (iso: string) => new Date(`${iso}T12:00:00`)          // meio-dia: imune a mudanças de hora
export const somarDias = (iso: string, n: number) => { const d = dataDeIso(iso); d.setDate(d.getDate() + n); return isoLocal(d) }
export const DIAS_CURTO = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb']

/** Primeiro e último dia da grelha do mês (semanas de domingo a sábado, como na app dedicada). */
export function intervaloMes(ancora: string): [string, string] {
  const d = dataDeIso(ancora)
  const primeiro = new Date(d.getFullYear(), d.getMonth(), 1, 12), ultimo = new Date(d.getFullYear(), d.getMonth() + 1, 0, 12)
  return [somarDias(isoLocal(primeiro), -primeiro.getDay()), somarDias(isoLocal(ultimo), 6 - ultimo.getDay())]
}
export function intervaloSemana(ancora: string): [string, string] {
  const ini = somarDias(ancora, -dataDeIso(ancora).getDay())
  return [ini, somarDias(ini, 6)]
}
export function tituloMes(ancora: string): string {
  const t = new Intl.DateTimeFormat('pt-PT', { month: 'long', year: 'numeric' }).format(dataDeIso(ancora))
  return t.charAt(0).toUpperCase() + t.slice(1)
}
export function tituloSemana(de: string, ate: string): string {
  const a = dataDeIso(de), b = dataDeIso(ate)
  const mes = (d: Date, estilo: 'long' | 'short') => new Intl.DateTimeFormat('pt-PT', { month: estilo }).format(d)
  return a.getMonth() === b.getMonth() ? `${a.getDate()}–${b.getDate()} de ${mes(b, 'long')}` : `${a.getDate()} ${mes(a, 'short')} – ${b.getDate()} ${mes(b, 'short')}`
}
/** Cor estável por categoria (as categorias são livres, por isso não há tabela fixa). */
export function corCategoria(nome: string): string {
  let h = 0
  for (const c of nome) h = (h * 31 + c.charCodeAt(0)) % 360
  return `hsl(${h} 55% 48%)`
}

// --- Horário ----------------------------------------------------------------------------------------------------------------

/** Exporta o histórico como CSV (com BOM, para o Excel abrir os acentos). */
export function csvHistorico(linhas: { tarefa: string; categoria: string; data: string; pessoa: string; estado: string; dataConclusao: string }[]): string {
  const cab = ['Tarefa', 'Categoria', 'Data', 'Pessoa', 'Estado', 'DataConclusao']
  const aspas = (v: string) => `"${String(v).replace(/"/g, '""')}"`
  return '﻿' + [cab, ...linhas.map((l) => [l.tarefa, l.categoria, l.data, l.pessoa, l.estado, l.dataConclusao])].map((l) => l.map(aspas).join(',')).join('\n')
}
