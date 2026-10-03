import type { IconName } from '../components/Icon'

export interface DiaTempo { data: string; diaSemana: string; diaCurto: string; icone: string; descricao: string; max: number | null; min: number | null; chuva: number | null; nascer: string; poer: string }
export interface HoraTempo { hora: string; dia: string; temp: number | null; chuva: number | null; icone: string }
export interface Previsao {
  localizacao: 'dispositivo' | 'omissao'; atualizadoEm: string
  agora: { temp: number | null; icone: string; descricao: string; vento: number | null; dia: boolean }
  hoje: DiaTempo | null; horas: HoraTempo[]; dias: DiaTempo[]
}

export const iconeTempo = (icone: string): IconName => (`tempo-${icone}` in ICONES ? `tempo-${icone}` : 'tempo-nublado') as IconName
const ICONES: Record<string, true> = { 'tempo-sol': true, 'tempo-lua': true, 'tempo-pouco_nublado': true, 'tempo-nublado': true, 'tempo-nevoeiro': true, 'tempo-chuva': true, 'tempo-aguaceiros': true, 'tempo-neve': true, 'tempo-trovoada': true }

export const graus = (v: number | null | undefined) => (v == null ? '–' : `${Math.round(v)}°`)
