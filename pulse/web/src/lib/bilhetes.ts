import type { EstadoViagem, ViagemBilhetes } from '../api/types'

const WD = ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sáb']

const utc = (iso: string) => { const [y, m, d] = iso.split('-').map(Number); return Date.UTC(y, m - 1, d) }
const paraIso = (ms: number) => new Date(ms).toISOString().slice(0, 10)
export const somarDias = (iso: string, n: number) => paraIso(utc(iso) + n * 86400000)
export const segundaDe = (iso: string) => { const d = new Date(utc(iso)).getUTCDay(); return somarDias(iso, d === 0 ? -6 : 1 - d) }

/** «seg 05/10» */
export const diaCurto = (iso: string) => `${WD[new Date(utc(iso)).getUTCDay()]} ${iso.slice(8)}/${iso.slice(5, 7)}`
export const diaMes = (iso: string) => `${iso.slice(8)}/${iso.slice(5, 7)}`
export const intervaloSemana = (segunda: string) => `${diaMes(segunda)} a ${diaMes(somarDias(segunda, 6))}`

export const ESTADO_VIAGEM: Record<EstadoViagem, { texto: string; classe: string }> = {
  comprado: { texto: 'Comprado', classe: 'pill-ok' }, por_comprar: { texto: 'Por comprar', classe: '' }, inativa: { texto: 'Inativa', classe: '' },
  em_curso: { texto: 'Em viagem', classe: 'pill-soon' }, passada: { texto: 'Concluída', classe: '' },
}

export const ESTADO_PEDIDO: Record<string, string> = { PENDENTE: 'Pendente', A_TENTAR: 'A tentar…', ESGOTADO: 'Esgotado', FALHOU: 'Falhou', AMBIGUO: 'Confirmar na App CP', CONFIRMADO: 'Comprado', EXPIRADO: 'Expirou', DESARMADO: 'Desativada' }
export const RESULTADO_REGISTO: Record<string, string> = { CONFIRMED: 'Comprado', SALE_CREATED: 'Venda criada', SOLD_OUT: 'Esgotado', FAILED: 'Falhou', AMBIGUOUS: 'Estado incerto', OK: 'OK', FALHA: 'Falha', EXCECAO: 'Erro inesperado' }
export const TIPO_REGISTO: Record<string, string> = { COMPRA: 'Compra', ERRO: 'Erro', PREFLIGHT: 'Verificação' }

/** ok / aviso / erro / neutro, para a cor do registo. */
export function classeRegisto(r: { resultado: string | null; tipo: string }): 'ok' | 'warn' | 'err' | '' {
  const res = r.resultado ?? ''
  if (/^(OK|CONFIRMED|SALE_CREATED)$/i.test(res)) return 'ok'
  if (/SOLD_OUT/i.test(res)) return 'warn'
  if (/FAIL|FALHA|AMBIG|EXCECAO|ERRO/i.test(res + r.tipo)) return 'err'
  return ''
}

// --- editor da semana ---
export interface LinhaEditor { origem: string; destino: string; comboio: string; hora: string }
export interface DiaEditor { data: string; ativo: boolean; passado: boolean; viagens: LinhaEditor[] }

export const linhaVazia = (origem = '', destino = ''): LinhaEditor => ({ origem, destino, comboio: '', hora: '' })

/** Os 7 dias da semana com as viagens já configuradas; o interruptor «ativo» é por dia (como na app dedicada). */
export function diasParaEditor(dias: string[], viagens: ViagemBilhetes[], hoje: string): DiaEditor[] {
  return dias.map((data) => {
    const doDia = viagens.filter((v) => v.data === data)
    return {
      data, passado: data < hoje, ativo: doDia.length === 0 || doDia.some((v) => v.ativo),
      viagens: doDia.map((v) => ({ origem: v.origem, destino: v.destino, comboio: String(v.comboio), hora: v.hora })),
    }
  })
}

const HORA = /^([01]\d|2[0-3]):[0-5]\d$/

/** Uma lista de avisos por dia (vazia = válido). Dias passados não se validam nem se alteram; dias sem viagens não pedem nada. */
export function validarDias(dias: DiaEditor[]): string[][] {
  return dias.map((d) => {
    if (d.passado || d.viagens.length === 0) return []
    const erros: string[] = []
    const vistas = new Map<string, number>()
    d.viagens.forEach((v, i) => {
      const n = i + 1
      if (!v.origem || !v.destino) erros.push(`Viagem ${n}: escolhe a origem e o destino.`)
      else if (v.origem.toLowerCase() === v.destino.toLowerCase()) erros.push(`Viagem ${n}: a origem e o destino são iguais.`)
      const comboio = Number(v.comboio)
      const comboioOk = /^\d{1,5}$/.test(v.comboio.trim()) && comboio >= 1
      if (!comboioOk) erros.push(`Viagem ${n}: comboio inválido.`)
      if (!HORA.test(v.hora)) erros.push(`Viagem ${n}: hora inválida.`)
      if (comboioOk && HORA.test(v.hora)) {
        const chave = `${comboio}|${v.hora}`
        if (vistas.has(chave)) erros.push(`Viagem ${n}: repete a viagem ${vistas.get(chave)! + 1}.`)
        else vistas.set(chave, i)
      }
    })
    return erros
  })
}

/** O corpo da ação `bilhetes.semana`: dias passados enviam-se tal como estavam (o servidor substitui a semana toda). */
export function viagensParaEnviar(dias: DiaEditor[]) {
  return dias.flatMap((d) => d.viagens.map((v) => ({
    data: d.data, origem: v.origem.trim(), destino: v.destino.trim(), comboio: Number(v.comboio), hora: v.hora, ativo: d.ativo,
  })))
}
