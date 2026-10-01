import { useState } from 'react'
import { api, mensagemDeErro } from '../../api/client'
import type { HistoricoBilhetes } from '../../api/types'
import { BrandLoading, Botao, Notice } from '../../components/ui'
import { classeRegisto, RESULTADO_REGISTO } from '../../lib/bilhetes'
import { useAsync } from '../../lib/useAsync'

const RESPOSTA: Record<string, string> = { ok: 'Aceite', sold_out: 'Esgotado', not_open: 'Ainda não abriu', recusado: 'Recusado', transient: 'Erro temporário', erro: 'Erro', '429': 'Demasiados pedidos' }
const FASE: Record<string, string> = { retencao: 'Reter lugar', venda: 'Venda a T', lugar: 'Mudar de lugar', desconto: 'Desconto do passe' }
const PERIODOS = [{ id: 90, nome: '90 dias' }, { id: 30, nome: '30 dias' }, { id: 7, nome: '7 dias' }, { id: 1, nome: 'Hoje' }] as const
const MAX_LINHAS = 200

const nomeResposta = (r: string) => RESPOSTA[r] ?? RESULTADO_REGISTO[r] ?? (r || '—')
const classeResposta = (r: string) => (r === 'ok' ? 'pill-ok' : r ? 'pill-soon' : '')
const hora = (ts: string) => `${ts.slice(0, 10)} ${ts.slice(11, 23)}`
const relativo = (ms: number | null) => (ms == null ? '' : Math.abs(ms) >= 60000 ? `${ms < 0 ? '−' : '+'}${(Math.abs(ms) / 60000).toFixed(1)} min` : Math.abs(ms) >= 1000 ? `${ms < 0 ? '−' : '+'}${(Math.abs(ms) / 1000).toFixed(1)} s` : `${ms < 0 ? '−' : '+'}${Math.abs(ms)} ms`)

/** Todos os pedidos feitos à CP nas compras (retenção do lugar, venda a T, mudança de lugar, desconto) e o desfecho de cada compra, até 90 dias.
 *  Só o administrador. É o mesmo que a página `bilhetes_historico/`, dentro da app. */
export function HistoricoTab() {
  const [dias, setDias] = useState<number>(90)
  const [pessoa, setPessoa] = useState('')
  const [vista, setVista] = useState<'pedidos' | 'desfechos'>('pedidos')
  const [mais, setMais] = useState(false)
  const [estado, recarregar] = useAsync(() => api.get<HistoricoBilhetes>(`/tickets/history?dias=${dias}`), String(dias))
  if (estado.fase === 'a-carregar') return <BrandLoading texto="A carregar o histórico…" />
  if (estado.fase === 'erro') return <div className="state"><Notice tipo="error">{mensagemDeErro(estado.erro)}</Notice><Botao variante="secondary" pequeno onClick={recarregar}>Tentar de novo</Botao></div>
  const d = estado.dados
  const pessoas = [...new Set([...d.pedidos, ...d.desfechos].map((l) => l.pessoa).filter(Boolean))].sort()
  const pedidos = d.pedidos.filter((l) => !pessoa || l.pessoa === pessoa)
  const desfechos = d.desfechos.filter((l) => !pessoa || l.pessoa === pessoa)
  const linhas = vista === 'pedidos' ? pedidos : desfechos
  return (
    <div className="stack">
      <div className="chips" role="group" aria-label="Período">
        {PERIODOS.map((p) => <button key={p.id} type="button" className="chip" aria-pressed={dias === p.id} onClick={() => { setDias(p.id); setMais(false) }}>{p.nome}</button>)}
      </div>
      {pessoas.length > 1 && (
        <div className="chips" role="group" aria-label="Pessoa">
          <button type="button" className="chip" aria-pressed={pessoa === ''} onClick={() => setPessoa('')}>Todas</button>
          {pessoas.map((n) => <button key={n} type="button" className="chip" aria-pressed={pessoa === n} onClick={() => setPessoa(n)}>{n}</button>)}
        </div>
      )}
      <div className="chips" role="group" aria-label="O que mostrar">
        <button type="button" className="chip" aria-pressed={vista === 'pedidos'} onClick={() => { setVista('pedidos'); setMais(false) }}>Pedidos à CP ({pedidos.length})</button>
        <button type="button" className="chip" aria-pressed={vista === 'desfechos'} onClick={() => { setVista('desfechos'); setMais(false) }}>Desfecho das compras ({desfechos.length})</button>
      </div>
      {d.truncado && <p className="t-meta">Só os 5000 pedidos mais recentes; reduz o período.</p>}
      {linhas.length === 0 ? <p className="t-body2">Sem registos para mostrar.</p> : (
        <section className="card" aria-label="Histórico"><ul className="rows">
          {(mais ? linhas : linhas.slice(0, MAX_LINHAS)).map((l, i) => (
            <li key={`${l.ts}-${i}`}>
              <div className="row-main">
                {'fase' in l ? (
                  <>
                    <div className="t-body"><span className="t-meta">#{l.id}</span> {hora(l.ts)} <span className={`pill ${classeResposta(l.resultado)}`}>{nomeResposta(l.resultado)}</span></div>
                    <div className="t-meta">{[l.pessoa, l.comboio && `comboio ${l.comboio}`, l.data && `viagem ${l.data}`, l.perna, FASE[l.fase] ?? l.fase].filter(Boolean).join(' · ')}</div>
                    <div className="t-meta">{[l.http ? `HTTP ${l.http}` : 'sem resposta', l.codigo, relativo(l.relTms) && `${relativo(l.relTms)} de T`, l.rttMs != null && `${l.rttMs} ms`, l.detalhe].filter(Boolean).join(' · ')}</div>
                  </>
                ) : (
                  <>
                    <div className="t-body"><span className="t-meta">#{l.id}</span> {hora(l.ts)} <span className={`pill${classeRegisto(l) === 'ok' ? ' pill-ok' : classeRegisto(l) ? ' pill-soon' : ''}`}>{nomeResposta(l.resultado ?? '')}</span></div>
                    <div className="t-meta">{[l.pessoa, l.comboio && `comboio ${l.comboio}`, l.data && `viagem ${l.data}`, l.perna, l.tipo].filter(Boolean).join(' · ')}</div>
                    {(l.referencia || l.erro) && <div className="t-meta">{l.referencia || l.erro}</div>}
                  </>
                )}
              </div>
            </li>
          ))}
        </ul></section>
      )}
      {!mais && linhas.length > MAX_LINHAS && <Botao variante="secondary" pequeno onClick={() => setMais(true)}>Mostrar todos ({linhas.length})</Botao>}
    </div>
  )
}
