import { useCallback, useState } from 'react'
import { api, mensagemDeErro } from '../api/client'

/** Executa ações do Pulse (`POST /actions/<nome>`), com «a executar» por chave e erro em pt-PT. */
export function useAcao(depois: () => void) {
  const [ocupado, setOcupado] = useState<string | null>(null)
  const [erro, setErro] = useState<string | null>(null)

  /** Devolve o `resultado` da ação (um objeto, por isso verdadeiro) ou `null` se falhou. */
  const executar = useCallback(async (chave: string, nome: string, params: Record<string, unknown>, confirmado = false): Promise<Record<string, unknown> | null> => {
    setOcupado(chave)
    setErro(null)
    try {
      const r = await api.post<{ resultado?: Record<string, unknown> }>(`/actions/${nome}`, confirmado ? { params, confirmado: true } : { params })
      depois()
      return r.resultado ?? {}
    } catch (e) {
      setErro(mensagemDeErro(e))
      return null
    } finally {
      setOcupado(null)
    }
  }, [depois])

  return { ocupado, erro, executar, limparErro: () => setErro(null) }
}

/** «104,8» ou «104.8» -> 104.8; vazio ou inválido -> null. */
export function lerPeso(texto: string): number | null {
  const n = Number(texto.trim().replace(',', '.'))
  return texto.trim() !== '' && Number.isFinite(n) && n >= 1 && n <= 1000 ? Math.round(n * 100) / 100 : null
}

export function novoCid(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}
