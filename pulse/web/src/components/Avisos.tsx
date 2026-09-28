import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

interface Aviso { id: number; texto: string; desfazer?: () => void }
interface Avisos { mostrar: (texto: string, desfazer?: () => void) => void }

const Ctx = createContext<Avisos>({ mostrar: () => {} })
const DURACAO_MS = 6000

/** Confirmação curta de uma ação já feita (com «Desfazer» quando dá). Avisos de condições que se mantêm NÃO vão aqui. */
export function AvisosProvider({ children }: { children: ReactNode }) {
  const [aviso, setAviso] = useState<Aviso | null>(null)
  const seq = useRef(0)
  const mostrar = useCallback((texto: string, desfazer?: () => void) => setAviso({ id: ++seq.current, texto, desfazer }), [])
  const valor = useMemo(() => ({ mostrar }), [mostrar])

  useEffect(() => {
    if (!aviso) return
    const t = setTimeout(() => setAviso(null), DURACAO_MS)
    return () => clearTimeout(t)
  }, [aviso])

  return (
    <Ctx.Provider value={valor}>
      {children}
      <div className="avisos" role="status" aria-live="polite">
        {aviso && (
          <div className="aviso" key={aviso.id}>
            <span>{aviso.texto}</span>
            {aviso.desfazer && <button type="button" onClick={() => { const f = aviso.desfazer; setAviso(null); f?.() }}>Desfazer</button>}
          </div>
        )}
      </div>
    </Ctx.Provider>
  )
}

export const useAvisos = () => useContext(Ctx)
