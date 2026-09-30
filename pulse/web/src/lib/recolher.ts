import { useCallback, useState } from 'react'

const ler = (chave: string): string[] => { try { return (localStorage.getItem(chave) ?? '').split(',').filter(Boolean) } catch { return [] } }
const guardar = (chave: string, v: Set<string>) => { try { localStorage.setItem(chave, [...v].join(',')) } catch { /* sem armazenamento */ } }

/** Secções que se expandem e encolhem (categorias das Compras): o que ficou encolhido lembra-se neste navegador. */
export function useFechadas(chave: string) {
  const [fechadas, setFechadas] = useState<Set<string>>(() => new Set(ler(chave)))
  const alternar = useCallback((id: string) => setFechadas((atual) => {
    const novo = new Set(atual)
    if (novo.has(id)) novo.delete(id); else novo.add(id)
    guardar(chave, novo)
    return novo
  }), [chave])
  const todas = useCallback((ids: string[], fechar: boolean) => { const novo = new Set(fechar ? ids : []); guardar(chave, novo); setFechadas(novo) }, [chave])
  return { fechadas, alternar, todas }
}
