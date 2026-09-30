import { useRef, useState } from 'react'
import { api, mensagemDeErro } from '../api/client'
import { useAvisos } from './Avisos'
import { Esqueleto, Notice } from './ui'
import { useAsync } from '../lib/useAsync'

const NOMES: Record<string, string> = { calendario: 'Calendário', tarefas: 'Tarefas', email: 'Email', bilhetes: 'Bilhetes CP', rto: 'RTO', peso: 'Peso', compras: 'Compras', financas: 'Finanças' }
const PEGA = <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">{[7, 12, 17].flatMap((y) => [9, 15].map((x) => <circle key={`${x}${y}`} cx={x} cy={y} r="1.6" />))}</svg>

/** Definições › Ordem do Hoje: arrastar a pega (ou setas ↑ ↓) muda a ordem dos cartões; fica guardada no servidor, por utilizador (ADR-054). */
function Lista({ inicial }: { inicial: string[] }) {
  const [ordem, setOrdem] = useState(inicial)
  const [arrastar, setArrastar] = useState<string | null>(null)
  const atual = useRef(ordem)
  const avisos = useAvisos()

  function guardar() {
    api.put('/dashboard/order', { ordem: atual.current }).catch((e) => avisos.mostrar(`Não foi possível guardar a ordem: ${mensagemDeErro(e)}`))
  }
  function mover(id: string, para: number) {
    const de = atual.current.indexOf(id)
    if (de < 0 || para < 0 || para >= atual.current.length || para === de) return
    const nova = atual.current.filter((x) => x !== id)
    nova.splice(para, 0, id)
    atual.current = nova
    setOrdem(nova)
  }
  function iniciar(e: React.PointerEvent, id: string) {
    e.preventDefault()
    setArrastar(id)
    const pega = e.currentTarget as HTMLElement
    pega.setPointerCapture(e.pointerId)
    const aoMover = (ev: PointerEvent) => {
      const alvo = document.elementFromPoint(ev.clientX, ev.clientY)?.closest<HTMLElement>('[data-cartao]')?.dataset.cartao
      if (alvo && alvo !== id) mover(id, atual.current.indexOf(alvo))
    }
    const fim = () => {
      pega.removeEventListener('pointermove', aoMover); pega.removeEventListener('pointerup', fim); pega.removeEventListener('pointercancel', fim)
      setArrastar(null)
      guardar()
    }
    pega.addEventListener('pointermove', aoMover); pega.addEventListener('pointerup', fim); pega.addEventListener('pointercancel', fim)
  }
  function teclas(e: React.KeyboardEvent, id: string) {
    const d = e.key === 'ArrowUp' ? -1 : e.key === 'ArrowDown' ? 1 : 0
    if (!d) return
    e.preventDefault()
    mover(id, atual.current.indexOf(id) + d)
    guardar()
    requestAnimationFrame(() => document.querySelector<HTMLElement>(`[data-cartao="${id}"] .pega`)?.focus())
  }

  return (
    <ul className="ordem-lista">
      {ordem.map((id) => (
        <li key={id} data-cartao={id} data-a-arrastar={arrastar === id}>
          <button type="button" className="pega" aria-label={`Mover ${NOMES[id] ?? id} (arrastar, ou setas para cima e para baixo)`}
            onPointerDown={(e) => iniciar(e, id)} onKeyDown={(e) => teclas(e, id)}>{PEGA}</button>
          <span className="row-main">{NOMES[id] ?? id}</span>
        </li>
      ))}
    </ul>
  )
}

export function OrdemHoje() {
  const [estado, recarregar] = useAsync(() => api.get<{ ordem: string[] }>('/dashboard/order'))
  return (
    <section className="section" aria-label="Ordem do Hoje">
      <h2 className="t-card muted">Ordem do Hoje</h2>
      <p className="t-body2">Arrasta para escolher a ordem dos cartões no Hoje. É só para ti e vale na app e na Web.</p>
      {estado.fase === 'a-carregar' && <Esqueleto linhas={3} />}
      {estado.fase === 'erro' && <Notice tipo="error">{mensagemDeErro(estado.erro)} <button type="button" className="link-btn" onClick={recarregar}>Tentar de novo</button></Notice>}
      {estado.fase === 'pronto' && <Lista inicial={estado.dados.ordem} />}
    </section>
  )
}
