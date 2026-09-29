import { useState } from 'react'
import type { BilhetesModulo, PedidoCp } from '../../api/types'
import { Botao } from '../../components/ui'
import { diaCurto, ESTADO_PEDIDO } from '../../lib/bilhetes'
import type { Ferramentas } from './tipos'

function Linha({ p, f }: { p: PedidoCp; f: Ferramentas }) {
  const { executar, ocupado, avisos } = f
  const [minutos, setMinutos] = useState(String(p.intervaloMinutos ?? 15))
  const n = Number(minutos)
  const minutosOk = /^\d{1,4}$/.test(minutos) && n >= 1 && n <= 1440
  const ambiguo = p.estado === 'AMBIGUO', aTentar = p.estado === 'A_TENTAR'

  async function forcar() {
    if (await executar(`forcar-${p.id}`, 'bilhetes.pedido_forcar', { pedido: p.id })) avisos.mostrar('Pedido marcado para tentar já. O Pi corre a fila a cada minuto.')
  }
  async function repetir(retry: boolean) {
    if (retry && !minutosOk) return
    if (await executar(`retry-${p.id}`, 'bilhetes.pedido_repetir', { pedido: p.id, retry, ...(retry ? { intervaloMinutos: n } : p.intervaloMinutos ? { intervaloMinutos: p.intervaloMinutos } : {}) })) {
      avisos.mostrar(retry ? `Repetição automática ligada, de ${n} em ${n} min.` : 'Repetição automática desligada.')
    }
  }
  return (
    <li>
      <div className="row-main">
        <div className="t-body">{diaCurto(p.data)} · {p.hora} <span className={`pill${ambiguo ? ' pill-soon' : p.estado === 'CONFIRMADO' ? ' pill-ok' : ''}`}>{ESTADO_PEDIDO[p.estado] ?? p.estado}</span></div>
        <div className="t-meta">{p.origem} → {p.destino} · comboio {p.comboio}</div>
        {p.mensagem && <div className="t-meta">{p.mensagem}</div>}
        {ambiguo ? <p className="t-meta">Confirma na App CP se a compra chegou a ser feita antes de tentares outra vez.</p> : (
          <div className="quick" role="group" aria-label={`Pedido de ${diaCurto(p.data)} às ${p.hora}`}>
            <Botao variante="secondary" pequeno carregando={ocupado === `forcar-${p.id}`} disabled={aTentar || ocupado !== null} onClick={() => void forcar()}>{aTentar ? 'A tentar…' : 'Tentar agora'}</Botao>
            <label className="check-line"><input type="checkbox" checked={p.retry} disabled={ocupado !== null || (!p.retry && !minutosOk)} onChange={(e) => void repetir(e.target.checked)} /> Repetir de</label>
            <input className="input input-sm peso-input" inputMode="numeric" aria-label="Minutos entre tentativas" value={minutos} disabled={p.retry} onChange={(e) => setMinutos(e.target.value)} aria-invalid={!minutosOk ? true : undefined} />
            <span className="t-meta">min</span>
          </div>
        )}
      </div>
    </li>
  )
}

export function PedidosTab({ dados, f }: { dados: BilhetesModulo; f: Ferramentas }) {
  if (dados.pedidos.length === 0) {
    return <p className="t-body2">Sem pedidos pendentes. Aparecem aqui viagens da semana que esgotaram as tentativas normais: podes forçar uma nova tentativa ou deixar o Pi repetir sozinho.</p>
  }
  return <section className="card" aria-label="Pedidos pendentes"><h2 className="t-card">Pedidos pendentes <span className="t-meta">{dados.pedidos.length}</span></h2><ul className="rows">{dados.pedidos.map((p) => <Linha key={p.id} p={p} f={f} />)}</ul></section>
}
