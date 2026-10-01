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
/** O último Hoje carregado nesta sessão: ao voltar ao Hoje mostra-se logo (e atualiza-se em segundo plano) em vez de recomeçar do zero. */
let ultimoHoje: { utilizador: number; dados: Hoje } | null = null
/** Só para os testes: esquece o que ficou guardado entre ecrãs. */
export const esquecerUltimoHoje = () => { ultimoHoje = null }

export function useHoje(utilizador: number) {
  // só o Hoje desta mesma conta: nunca se mostra o de outra pessoa
  const [estado, setEstado] = useState<Async<Hoje>>(() => (ultimoHoje?.utilizador === utilizador ? { fase: 'pronto', dados: ultimoHoje.dados } : { fase: 'a-carregar' }))
  const geracao = useRef(0)

  const buscar = useCallback(() => {
    const minha = ++geracao.current
    api.get<Hoje>('/dashboard/today').then(
      (dados) => { if (minha === geracao.current) setEstado({ fase: 'pronto', dados }) },
      (erro) => { if (minha === geracao.current) setEstado((e) => (e.fase === 'pronto' ? e : { fase: 'erro', erro })) },     // com o último Hoje à vista, uma falha não o apaga
    )
  }, [])

  const recarregar = useCallback(() => {
    setEstado((e) => (e.fase === 'pronto' ? e : { fase: 'a-carregar' }))      // com dados à vista mantém-nos enquanto volta a pedir
    buscar()
  }, [buscar])

  useEffect(() => { if (estado.fase === 'pronto') ultimoHoje = { utilizador, dados: estado.dados } }, [estado, utilizador])

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
