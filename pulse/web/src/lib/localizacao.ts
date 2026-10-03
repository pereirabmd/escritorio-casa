import { useCallback, useEffect, useRef, useState } from 'react'

export interface Posicao { lat: number; lon: number }
export type EstadoLocalizacao = 'a-pedir' | 'ok' | 'negada' | 'indisponivel'

const CHAVE = 'pulse.posicao'

function lerGuardada(): Posicao | null {
  try {
    const p = JSON.parse(localStorage.getItem(CHAVE) || 'null')
    return p && typeof p.lat === 'number' && typeof p.lon === 'number' ? p : null
  } catch { return null }
}

/** A localização do aparelho (pedida ao browser; só aproximada serve para o tempo). A última conhecida fica guardada para o cartão aparecer logo.
 *  `pedir()` repete o pedido (por exemplo depois de o utilizador dar a permissão). Sem permissão ou sem GPS/rede, `pos` fica `null` e o servidor usa Aveiro. */
function consultar(vivo: { current: boolean }, setPos: (p: Posicao) => void, setEstado: (e: EstadoLocalizacao) => void) {
  navigator.geolocation.getCurrentPosition(
    (g) => {
      if (!vivo.current) return
      const p = { lat: Math.round(g.coords.latitude * 100) / 100, lon: Math.round(g.coords.longitude * 100) / 100 }
      try { localStorage.setItem(CHAVE, JSON.stringify(p)) } catch { /* modo privado */ }
      setPos(p); setEstado('ok')
    },
    (e) => { if (vivo.current) setEstado(e.code === 1 ? 'negada' : 'indisponivel') },
    { enableHighAccuracy: false, maximumAge: 30 * 60_000, timeout: 10_000 },
  )
}

/** A localização do aparelho (pedida ao browser; só aproximada serve para o tempo). A última conhecida fica guardada para o cartão aparecer logo.
 *  `pedir()` repete o pedido (por exemplo depois de o utilizador dar a permissão). Sem permissão ou sem GPS/rede, `pos` fica `null` e o servidor usa Aveiro. */
export function useLocalizacao(): { pos: Posicao | null; estado: EstadoLocalizacao; pedir: () => void } {
  const [pos, setPos] = useState<Posicao | null>(() => lerGuardada())
  const [estado, setEstado] = useState<EstadoLocalizacao>(() => (typeof navigator !== 'undefined' && navigator.geolocation ? (lerGuardada() ? 'ok' : 'a-pedir') : 'indisponivel'))
  const vivo = useRef(true)
  const pedir = useCallback(() => {
    if (typeof navigator === 'undefined' || !navigator.geolocation) { setEstado('indisponivel'); return }
    consultar(vivo, setPos, setEstado)
  }, [])
  useEffect(() => {
    vivo.current = true
    if (typeof navigator !== 'undefined' && navigator.geolocation) consultar(vivo, setPos, setEstado)
    return () => { vivo.current = false }
  }, [])
  return { pos, estado, pedir }
}
