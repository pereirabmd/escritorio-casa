import type { useAvisos } from '../../components/Avisos'
import type { CategoriaFin } from '../../api/types'

export interface Ferramentas {
  executar: (chave: string, nome: string, params: Record<string, unknown>, confirmado?: boolean) => Promise<Record<string, unknown> | null>
  ocupado: string | null
  avisos: ReturnType<typeof useAvisos>
}

export interface ComCategorias extends Ferramentas { categorias: CategoriaFin[] }
