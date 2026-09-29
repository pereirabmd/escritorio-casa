import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { ModuloInfo } from '../api/types'
import { Icon } from '../components/Icon'
import { Notice } from '../components/ui'
import { useAsync } from './useAsync'

interface Modulos {
  lista: ModuloInfo[]
  /** Um módulo está ativo enquanto o administrador não o desativar (e enquanto não se souber, para não esconder nada por engano). */
  ativo: (id: string) => boolean
  recarregar: () => Promise<void>
  definir: (lista: ModuloInfo[]) => void
}

const Ctx = createContext<Modulos>({ lista: [], ativo: () => true, recarregar: async () => undefined, definir: () => undefined })

export function ModulosProvider({ children }: { children: ReactNode }) {
  const [estado, repetir] = useAsync(() => api.get<{ modulos: ModuloInfo[] }>('/modules'))
  const [local, setLocal] = useState<ModuloInfo[] | null>(null)              // o que o administrador acabou de guardar, até ao próximo carregamento
  // sem resposta (rede, servidor mais antigo): lista vazia = tudo ativo — nunca se esconde um módulo por engano
  const recarregar = useCallback(async () => { setLocal(null); repetir() }, [repetir])
  const valor = useMemo<Modulos>(() => {
    const lista = local ?? (estado.fase === 'pronto' ? estado.dados.modulos : [])
    return { lista, ativo: (id) => lista.find((m) => m.id === id)?.ativo !== false, recarregar, definir: setLocal }
  }, [local, estado, recarregar])
  return <Ctx.Provider value={valor}>{children}</Ctx.Provider>
}

export const useModulos = () => useContext(Ctx)

/** Ecrã de um módulo: se o administrador o desativou, explica-o em vez de mostrar erros de API. */
export function ModuloAtivo({ id, nome, children }: { id: string; nome: string; children: ReactNode }) {
  const { ativo } = useModulos()
  if (ativo(id)) return <>{children}</>
  return (
    <>
      <header className="hero">
        <Link to="/mais" className="back"><Icon nome="voltar" tamanho={20} />Mais</Link>
        <h1 className="t-page">{nome}</h1>
      </header>
      <Notice tipo="info">Este módulo está desativado pelo administrador. Pode voltar a ativar-se em Definições → Administração.</Notice>
    </>
  )
}
