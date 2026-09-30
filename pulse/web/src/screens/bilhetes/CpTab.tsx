import { useState } from 'react'
import { api, mensagemDeErro } from '../../api/client'
import type { BilheteNaCp, PasseNaCp } from '../../api/types'
import { useAvisos } from '../../components/Avisos'
import { BrandLoading, Botao, Notice } from '../../components/ui'
import { diaCurto } from '../../lib/bilhetes'
import { fmtDataIso, plural } from '../../lib/format'
import { useAcao } from '../../lib/useAcao'
import { useAsync } from '../../lib/useAsync'

/** O que a CP diz (ao vivo, demora alguns segundos): a validade do Passe Verde e os bilhetes futuros, com «Cancelar» (ADR-075). */
export function CpTab({ utilizador, nome }: { utilizador: number | null; nome: string }) {
  const q = utilizador ? `?utilizador=${utilizador}` : ''
  const [passe, recarregarPasse] = useAsync(() => api.get<{ passes: PasseNaCp[] }>(`/tickets/cp/passe${q}`), q)
  const [bilhetes, recarregarBilhetes] = useAsync(() => api.get<{ bilhetes: BilheteNaCp[] }>(`/tickets/cp/futuros${q}`), q)
  const avisos = useAvisos()
  const { ocupado, erro, executar, limparErro } = useAcao(() => recarregarBilhetes())
  const [aCancelar, setACancelar] = useState<number | null>(null)

  async function cancelar(b: BilheteNaCp) {
    const r = await executar(`cp-${b.venda}`, 'bilhetes.cp_cancelar', { venda: b.venda, ...(utilizador ? { utilizador } : {}) }, true)
    setACancelar(null)
    if (r) avisos.mostrar('Bilhete cancelado na CP.')
  }

  return (
    <div className="stack">
      <section className="stack" aria-label="Passe Verde">
        <h2 className="t-card">Passe Verde{utilizador ? ` de ${nome}` : ''}</h2>
        {passe.fase === 'a-carregar' && <BrandLoading texto="A consultar a CP…" />}
        {passe.fase === 'erro' && <><Notice tipo="error">{mensagemDeErro(passe.erro)}</Notice><div><Botao variante="secondary" pequeno onClick={recarregarPasse}>Tentar de novo</Botao></div></>}
        {passe.fase === 'pronto' && (passe.dados.passes.length === 0
          ? <p className="t-body2">A CP não mostra nenhum passe nesta conta.</p>
          : passe.dados.passes.map((p, i) => (
            <article key={i} className="card" aria-label={p.designacao}>
              <div className="t-body">{p.designacao || p.cartao}</div>
              <div className="t-meta">{p.origem} → {p.destino}</div>
              <div className="trip t-body2">
                <span>{p.inicio ? `Desde ${fmtDataIso(p.inicio)}` : ''}</span>
                <span className={`pill ${p.diasRestantes !== null && p.diasRestantes <= 3 ? 'pill-soon' : 'pill-ok'}`}>
                  {p.validade ? `Válido até ${fmtDataIso(p.validade)}` : 'Sem validade'}
                  {p.diasRestantes !== null && (p.diasRestantes < 0 ? ' · expirado' : p.diasRestantes === 0 ? ' · expira hoje' : ` · ${plural(p.diasRestantes, 'dia', 'dias')}`)}
                </span>
              </div>
            </article>
          )))}
      </section>

      <section className="stack" aria-label="Bilhetes futuros na CP">
        <h2 className="t-card">Bilhetes futuros na CP</h2>
        {erro && <Notice tipo="error">{erro} <button type="button" className="link-btn" onClick={limparErro}>Fechar</button></Notice>}
        {bilhetes.fase === 'a-carregar' && <BrandLoading texto="A consultar a CP…" />}
        {bilhetes.fase === 'erro' && <><Notice tipo="error">{mensagemDeErro(bilhetes.erro)}</Notice><div><Botao variante="secondary" pequeno onClick={recarregarBilhetes}>Tentar de novo</Botao></div></>}
        {bilhetes.fase === 'pronto' && (bilhetes.dados.bilhetes.length === 0
          ? <p className="t-body2">Sem bilhetes futuros na CP.</p>
          : bilhetes.dados.bilhetes.map((b) => (
            <article key={b.venda} className="card" aria-label={`Bilhete de ${diaCurto(b.data)} às ${b.hora}`}>
              <div className="t-meta">{diaCurto(b.data)}</div>
              <div className="trip"><span className="t-section">{b.hora}</span><span className="t-body">{b.origem}</span><span className="arrow"><span className="sr-only">para</span>→</span><span className="t-body">{b.destino}</span></div>
              <div className="trip t-body2">
                {b.comboio && <span>Comboio {b.comboio}</span>}
                {b.lugar && <span className="pill pill-ok">Carruagem {b.carruagem ?? '—'} · Lugar {b.lugar}</span>}
                {b.referencia && <span className="t-meta">ref. {b.referencia}</span>}
              </div>
              {b.podeCancelar && (aCancelar === b.venda
                ? (
                  <div className="stack">
                    <p className="t-body2">Cancelar este bilhete na CP? O lugar fica livre e não dá para desfazer.</p>
                    <div className="quick" role="group" aria-label={`Cancelar o bilhete de ${diaCurto(b.data)}`}>
                      <Botao variante="danger" pequeno carregando={ocupado === `cp-${b.venda}`} disabled={ocupado !== null} onClick={() => void cancelar(b)}>Cancelar bilhete</Botao>
                      <Botao variante="secondary" pequeno disabled={ocupado !== null} onClick={() => setACancelar(null)}>Manter</Botao>
                    </div>
                  </div>
                )
                : <div><button type="button" className="link-btn link-danger" onClick={() => setACancelar(b.venda)}>Cancelar bilhete</button></div>)}
            </article>
          )))}
      </section>
    </div>
  )
}
