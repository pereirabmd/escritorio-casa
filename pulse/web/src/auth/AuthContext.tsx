import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, ApiError, definirAoPerderSessao } from '../api/client'
import type { Utilizador } from '../api/types'

type Estado = { fase: 'a-carregar' } | { fase: 'anonimo' } | { fase: 'autenticado'; utilizador: Utilizador } | { fase: 'servidor-indisponivel' }

interface Auth {
  estado: Estado
  entrar: (email: string, password: string) => Promise<void>
  sair: () => Promise<void>
  passwordMudada: () => void
  tentarDeNovo: () => void
}

const Ctx = createContext<Auth | null>(null)

/** Pergunta ao servidor quem sou. 401 = sem sessão; qualquer outra falha (rede, 5xx) não quer dizer que a sessão acabou. */
function consultar(): Promise<Estado> {
  return api.get<{ utilizador: Utilizador }>('/auth/me').then(
    (r): Estado => ({ fase: 'autenticado', utilizador: r.utilizador }),
    (e): Estado => (e instanceof ApiError && e.status === 401 ? { fase: 'anonimo' } : { fase: 'servidor-indisponivel' }),
  )
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [estado, setEstado] = useState<Estado>({ fase: 'a-carregar' })

  useEffect(() => {
    let vivo = true
    void consultar().then((e) => { if (vivo) setEstado(e) })
    definirAoPerderSessao(() => setEstado({ fase: 'anonimo' }))
    return () => { vivo = false; definirAoPerderSessao(null) }
  }, [])

  const valor = useMemo<Auth>(() => ({
    estado,
    entrar: async (email, password) => {
      const r = await api.post<{ utilizador: Utilizador }>('/auth/login', { email, password, cliente: 'web' })
      setEstado({ fase: 'autenticado', utilizador: r.utilizador })
    },
    sair: async () => {
      try {
        await api.post('/auth/logout')
      } finally {
        setEstado({ fase: 'anonimo' })
      }
    },
    passwordMudada: () => setEstado((e) => (e.fase === 'autenticado' ? { fase: 'autenticado', utilizador: { ...e.utilizador, mudarPassword: false } } : e)),
    tentarDeNovo: () => { setEstado({ fase: 'a-carregar' }); void consultar().then(setEstado) },
  }), [estado])

  return <Ctx.Provider value={valor}>{children}</Ctx.Provider>
}

export function useAuth(): Auth {
  const c = useContext(Ctx)
  if (!c) throw new Error('useAuth fora do AuthProvider')
  return c
}

export function useUtilizador(): Utilizador {
  const { estado } = useAuth()
  if (estado.fase !== 'autenticado') throw new Error('sem utilizador autenticado')
  return estado.utilizador
}
