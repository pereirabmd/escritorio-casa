import { useCallback, useEffect, useRef, useState } from 'react'

export type Async<T> = { fase: 'a-carregar' } | { fase: 'erro'; erro: unknown } | { fase: 'pronto'; dados: T }

/** Carrega dados ao montar e permite repetir (mantendo os dados já mostrados). Ignora respostas de pedidos que já não interessam. */
export function useAsync<T>(carregar: () => Promise<T>): [Async<T>, () => void] {
  const [estado, setEstado] = useState<Async<T>>({ fase: 'a-carregar' })
  const fn = useRef(carregar)
  const geracao = useRef(0)
  useEffect(() => { fn.current = carregar })

  const buscar = useCallback(() => {
    const minha = ++geracao.current
    fn.current().then(
      (dados) => { if (minha === geracao.current) setEstado({ fase: 'pronto', dados }) },
      (erro) => { if (minha === geracao.current) setEstado({ fase: 'erro', erro }) },
    )
  }, [])

  useEffect(() => {
    buscar()
    // o contador é meu (não é um nó do DOM): invalida o pedido em curso quando o componente sai
    // eslint-disable-next-line react-hooks/exhaustive-deps
    return () => { geracao.current++ }
  }, [buscar])

  const repetir = useCallback(() => {
    setEstado((e) => (e.fase === 'pronto' ? e : { fase: 'a-carregar' }))
    buscar()
  }, [buscar])

  return [estado, repetir]
}
