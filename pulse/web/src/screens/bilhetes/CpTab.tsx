import { useState, type FormEvent } from 'react'
import { api, mensagemDeErro } from '../../api/client'
import type { BilheteNaCp, FavoritoBilhetes, PasseNaCp } from '../../api/types'
import { useAvisos } from '../../components/Avisos'
import { BrandLoading, Botao, Notice } from '../../components/ui'
import { diaCurto } from '../../lib/bilhetes'
import { VerificacaoCp } from './SemanaTab'
import { fmtDataIso, plural } from '../../lib/format'
import { useAcao } from '../../lib/useAcao'
import { useAsync } from '../../lib/useAsync'

/** O que a CP diz (ao vivo, demora alguns segundos): a validade do Passe Verde e os bilhetes futuros, com «Cancelar» (ADR-075). */
/** «Trocar por outro comboio» (ADR-083): quando houver lugar no novo, reserva-o, cancela este bilhete e confirma o novo. */
function Troca({ b, utilizador, favoritos, aoMudar }: { b: BilheteNaCp; utilizador: number | null; favoritos: FavoritoBilhetes[]; aoMudar: () => void }) {
  const avisos = useAvisos()
  const { ocupado, erro, executar, limparErro } = useAcao(aoMudar)
  const [aberta, setAberta] = useState(false)
  const [comboio, setComboio] = useState('')
  const [hora, setHora] = useState('')
  const [sim, setSim] = useState<{ a: boolean; texto: string; ok?: boolean } | null>(null)   // «Simular devolução» (só leitura)
  const [inicio, setInicio] = useState('')                       // «AAAA-MM-DDTHH:MM»: só começa a tentar a partir daqui; vazio = já
  const [pedirConfirmacao, setPedirConfirmacao] = useState(false)
  const mesmoSentido = favoritos.filter((f) => f.origem.toLowerCase() === b.origem.toLowerCase() && f.destino.toLowerCase() === b.destino.toLowerCase() && f.comboio !== b.comboio)
  const valido = /^\d{1,5}$/.test(comboio) && Number(comboio) > 0 && /^([01]\d|2[0-3]):[0-5]\d$/.test(hora)

  const mesmoComboio = Number(comboio) === b.comboio                // «mudar de lugar» (ADR-087)

  async function simular() {
    setSim({ a: true, texto: 'A consultar a CP…' })
    try {
      const q = new URLSearchParams({ venda: String(b.venda), ...(utilizador ? { utilizador: String(utilizador) } : {}) })
      const r = await api.get<{ cancelavel: boolean; motivo: string; valor: string }>(`/tickets/cp/simular?${q}`)
      setSim({ a: false, ok: r.cancelavel, texto: r.cancelavel ? `A CP deixa devolver este bilhete${r.valor ? `; reembolso previsto: ${r.valor}` : ''}. Nada foi cancelado.` : (r.motivo || 'A CP não deixa devolver este bilhete.') })
    } catch (e) { setSim({ a: false, ok: false, texto: mensagemDeErro(e) }) }
  }

  async function ativar() {
    const r = await executar(`troca-${b.venda}`, 'bilhetes.troca_armar', { venda: b.venda, comboio: Number(comboio), hora, ...(inicio ? { inicio } : {}), ...(utilizador ? { utilizador } : {}) }, true)
    if (r) {
      setAberta(false); setPedirConfirmacao(false); setComboio(''); setHora(''); setInicio(''); setSim(null)
      avisos.mostrar(inicio ? `Troca agendada: começo a tentar o comboio ${comboio} em ${inicio.slice(8, 10)}/${inicio.slice(5, 7)} às ${inicio.slice(11)}, de 15 em 15 min, até 30 min antes da partida.` : `Troca ativada: tento o comboio ${comboio} de 15 em 15 min, até 30 min antes da partida.`)
    }
  }
  if (!aberta) return <div><button type="button" className="link-btn" onClick={() => setAberta(true)}>Trocar por outro comboio</button></div>
  return (
    <form className="stack" aria-label={`Trocar o bilhete de ${diaCurto(b.data)}`} onSubmit={(ev: FormEvent) => { ev.preventDefault(); if (valido) setPedirConfirmacao(true) }}>
      <p className="t-body2">Do mesmo dia e sentido. Quando houver lugar no comboio novo, o Pulse reserva-o, <b>cancela este bilhete</b> e confirma o novo. Tenta de 15 em 15 min, até 30 min antes da partida.</p>
      {mesmoSentido.length > 0 && (
        <select className="input input-sm" aria-label="Favoritos para a troca" value="" onChange={(e) => { const f = mesmoSentido[Number(e.target.value)]; if (f) { setComboio(String(f.comboio)); setHora(f.hora); setPedirConfirmacao(false) } }}>
          <option value="">Favoritos…</option>
          {mesmoSentido.map((f, n) => <option key={f.id} value={n}>{f.apelido ? `${f.apelido} · ` : ''}{f.comboio} ({f.hora})</option>)}
        </select>
      )}
      <div className="quick">
        <label className="sr-only" htmlFor={`tc-${b.venda}`}>Comboio novo</label>
        <input id={`tc-${b.venda}`} className="input input-sm peso-input" inputMode="numeric" placeholder="Comboio" value={comboio} onChange={(e) => { setComboio(e.target.value); setPedirConfirmacao(false) }} />
        <label className="sr-only" htmlFor={`th-${b.venda}`}>Hora de partida do comboio novo</label>
        <input id={`th-${b.venda}`} type="time" className="input input-sm" value={hora} onChange={(e) => { setHora(e.target.value); setPedirConfirmacao(false) }} />
      </div>
      <VerificacaoCp data={b.data} origem={b.origem} destino={b.destino} comboio={comboio} hora={hora} aoUsarHora={(h) => { setHora(h); setPedirConfirmacao(false) }} />
      <div className="stack">
        <label className="t-meta" htmlFor={`ti-${b.venda}`}>Começar a tentar em (opcional; vazio = já)</label>
        <input id={`ti-${b.venda}`} type="datetime-local" className="input input-sm" value={inicio} max={`${b.data}T${hora || '23:59'}`} onChange={(e) => { setInicio(e.target.value); setPedirConfirmacao(false) }} />
      </div>
      {mesmoComboio && <p className="t-meta" role="status">Mesmo comboio = <b>mudar de lugar</b>: reservo um lugar novo, aplico o corredor e só cancelo o lugar atual se o novo for corredor e o atual não. Se não houver, o atual mantém-se e volto a tentar.</p>}
      <div className="quick">
        <Botao variante="secondary" pequeno carregando={!!sim?.a} disabled={!!sim?.a || ocupado !== null} onClick={() => void simular()}>Simular devolução</Botao>
      </div>
      {sim && !sim.a && <Notice tipo={sim.ok ? 'info' : 'warning'}>{sim.texto}</Notice>}
      {erro && <Notice tipo="error">{erro} <button type="button" className="link-btn" onClick={limparErro}>Fechar</button></Notice>}
      {pedirConfirmacao ? (
        <div className="stack" role="group" aria-label="Confirmar a troca">
          <p className="t-body2">Confirmas? O bilhete atual (comboio {b.comboio}, {b.hora}) <b>só é cancelado depois de o lugar no comboio {comboio} estar reservado</b>.{inicio && <> Começo a tentar em {inicio.slice(8, 10)}/{inicio.slice(5, 7)} às {inicio.slice(11)}.</>}</p>
          <div className="quick">
            <Botao variante="danger" pequeno carregando={ocupado === `troca-${b.venda}`} disabled={ocupado !== null} onClick={() => void ativar()}>Ativar troca</Botao>
            <Botao variante="secondary" pequeno disabled={ocupado !== null} onClick={() => setPedirConfirmacao(false)}>Voltar</Botao>
          </div>
        </div>
      ) : (
        <div className="quick">
          <Botao type="submit" pequeno disabled={!valido || ocupado !== null}>Continuar</Botao>
          <Botao variante="secondary" pequeno onClick={() => setAberta(false)}>Fechar</Botao>
        </div>
      )}
    </form>
  )
}

export function CpTab({ utilizador, nome, favoritos = [], aoMudar = () => {} }: { utilizador: number | null; nome: string; favoritos?: FavoritoBilhetes[]; aoMudar?: () => void }) {
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
              {b.podeCancelar && aCancelar !== b.venda && <Troca b={b} utilizador={utilizador} favoritos={favoritos} aoMudar={aoMudar} />}
            </article>
          )))}
      </section>
    </div>
  )
}
