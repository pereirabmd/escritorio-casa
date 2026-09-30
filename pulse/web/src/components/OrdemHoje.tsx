import { useRef, useState } from 'react'
import { api, mensagemDeErro } from '../api/client'
import { useAvisos } from './Avisos'
import { Esqueleto, Notice } from './ui'
import { useAsync } from '../lib/useAsync'

const NOMES: Record<string, string> = { calendario: 'Calendário', tarefas: 'Tarefas', email: 'Email', bilhetes: 'Bilhetes CP', rto: 'RTO', peso: 'Peso', compras: 'Compras', financas: 'Finanças' }
const PEGA = <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">{[7, 12, 17].flatMap((y) => [9, 15].map((x) => <circle key={`${x}${y}`} cx={x} cy={y} r="1.6" />))}</svg>

interface Estado { ordem: string[]; ocultos: string[]; disponiveis: string[] }

/** Definições › O meu Hoje: arrastar a pega (ou setas ↑ ↓) muda a ordem dos cartões e o botão mostra/esconde cada um. Fica no servidor, por pessoa (ADR-054/063). */
function Lista({ inicial }: { inicial: Estado }) {
  const [ordem, setOrdem] = useState(inicial.ordem.filter((id) => inicial.disponiveis.includes(id)))
  const [ocultos, setOcultos] = useState(inicial.ocultos)
  const [arrastar, setArrastar] = useState<string | null>(null)
  const atual = useRef(ordem)
  const escondidos = useRef(ocultos)
  const avisos = useAvisos()

  function guardar() {
    // a ordem completa = a dos cartões disponíveis seguida dos que a pessoa não tem (mantêm o lugar relativo)
    const resto = inicial.ordem.filter((id) => !atual.current.includes(id))
    api.put('/dashboard/order', { ordem: [...atual.current, ...resto], ocultos: escondidos.current }).catch((e) => avisos.mostrar(`Não foi possível guardar: ${mensagemDeErro(e)}`))
  }
  function mover(id: string, para: number) {
    const de = atual.current.indexOf(id)
    if (de < 0 || para < 0 || para >= atual.current.length || para === de) return
    const nova = atual.current.filter((x) => x !== id)
    nova.splice(para, 0, id)
    atual.current = nova
    setOrdem(nova)
  }
  function alternar(id: string) {
    const novos = escondidos.current.includes(id) ? escondidos.current.filter((x) => x !== id) : [...escondidos.current, id]
    escondidos.current = novos
    setOcultos(novos)
    guardar()
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

  if (ordem.length === 0) return <p className="t-body2">Ainda não tens nenhum módulo. Pede ao administrador.</p>
  return (
    <ul className="ordem-lista">
      {ordem.map((id) => {
        const visivel = !ocultos.includes(id)
        return (
          <li key={id} data-cartao={id} data-a-arrastar={arrastar === id}>
            <button type="button" className="pega" aria-label={`Mover ${NOMES[id] ?? id} (arrastar, ou setas para cima e para baixo)`}
              onPointerDown={(e) => iniciar(e, id)} onKeyDown={(e) => teclas(e, id)}>{PEGA}</button>
            <span className="row-main" data-escondido={!visivel}>{NOMES[id] ?? id}</span>
            <button type="button" role="switch" className="chip" aria-checked={visivel} aria-label={`${NOMES[id] ?? id} no Hoje: ${visivel ? 'visível' : 'escondido'}`}
              onClick={() => alternar(id)}>{visivel ? 'Visível' : 'Escondido'}</button>
          </li>
        )
      })}
    </ul>
  )
}

export function OrdemHoje() {
  const [estado, recarregar] = useAsync(() => api.get<Estado>('/dashboard/order'))
  return (
    <section className="section" aria-label="O meu Hoje">
      <h2 className="t-card muted">O meu Hoje</h2>
      <p className="t-body2">Escolhe que cartões aparecem no teu Hoje e por que ordem (arrasta). É só para ti e vale na app e na Web.</p>
      {estado.fase === 'a-carregar' && <Esqueleto linhas={3} />}
      {estado.fase === 'erro' && <Notice tipo="error">{mensagemDeErro(estado.erro)} <button type="button" className="link-btn" onClick={recarregar}>Tentar de novo</button></Notice>}
      {estado.fase === 'pronto' && <Lista inicial={{ ordem: estado.dados.ordem, ocultos: estado.dados.ocultos ?? [], disponiveis: estado.dados.disponiveis ?? estado.dados.ordem }} />}
    </section>
  )
}
