import type { PesoModulo } from '../../api/types'
import type { useAvisos } from '../../components/Avisos'

export interface Ferramentas {
  dados: PesoModulo
  executar: (chave: string, nome: string, params: Record<string, unknown>, confirmado?: boolean) => Promise<Record<string, unknown> | null>
  ocupado: string | null
  avisos: ReturnType<typeof useAvisos>
}
