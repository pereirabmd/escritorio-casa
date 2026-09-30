import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { Hoje } from '../api/types'
import type { Async } from './useAsync'

/** O módulo do Hoje que uma ação altera (`tarefas.concluir` → `tarefas`); depois de uma ação só esse módulo volta a ser pedido. */
export const moduloDaAcao = (nome: string): string => nome.split('.')[0]

/**
 * O «Hoje» com três formas de atualizar: tudo (`recarregar`), só alguns módulos (`atualizar`, o que as ações usam: o resto não mudou e
 * a Google é lenta) e uma alteração local imediata (`otimista`, que o pedido seguinte confirma ou corrige).
 */
export function useHoje() {
  const [estado, setEstado] = useState<Async<Hoje>>({ fase: 'a-carregar' })
  const geracao = useRef(0)

  const buscar = useCallback(() => {
    const minha = ++geracao.current
    api.get<Hoje>('/dashboard/today').then(
      (dados) => { if (minha === geracao.current) setEstado({ fase: 'pronto', dados }) },
      (erro) => { if (minha === geracao.current) setEstado({ fase: 'erro', erro }) },
    )
  }, [])

  const recarregar = useCallback(() => {
    setEstado((e) => (e.fase === 'pronto' ? e : { fase: 'a-carregar' }))      // com dados à vista mantém-nos enquanto volta a pedir
    buscar()
  }, [buscar])

  // o contador é meu (não é um nó do DOM): invalida o pedido em curso quando o ecrã sai
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { buscar(); return () => { geracao.current++ } }, [buscar])

  const atualizar = useCallback((modulos: string[]) => {
    const minha = geracao.current
    api.get<Hoje>(`/dashboard/today?modulos=${modulos.join(',')}`).then(
      (novo) => {
        if (minha !== geracao.current) return
        setEstado((e) => {
          if (e.fase !== 'pronto') return e
          const mods = { ...e.dados.modulos, ...novo.modulos }
          const degradado = Object.values(mods).some((m) => m.estado === 'indisponivel' || m.estado === 'erro')
          return { fase: 'pronto', dados: { ...e.dados, modulos: mods, estado: degradado ? 'degradado' : 'ok', geradoEm: novo.geradoEm, ordem: novo.ordem ?? e.dados.ordem } }
        })
      },
      () => recarregar(),           // não consegui só esses: volta a pedir tudo para não ficar com dados que já não valem
    )
  }, [recarregar])

  const otimista = useCallback((alterar: (h: Hoje) => Hoje) => {
    setEstado((e) => (e.fase === 'pronto' ? { fase: 'pronto', dados: alterar(e.dados) } : e))
  }, [])

  return { estado, recarregar, atualizar, otimista }
}
