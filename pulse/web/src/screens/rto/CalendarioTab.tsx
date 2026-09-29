import { useMemo, useState } from 'react'
import type { RtoModulo } from '../../api/types'
import { Icon } from '../../components/Icon'
import { Botao } from '../../components/ui'
import { fmtDataIso, fmtDataLonga, plural } from '../../lib/format'
import { DIAS_SEMANA, diaBloqueado, hojeLocal, iso, marcaDaCelula, nomeMes, notasDoDia, semanasDoMes, textoHoje, textoProximaMudanca } from '../../lib/rto'
import type { Ferramentas } from './tipos'

interface Props extends Ferramentas { mes: number; ano: number; irPara: (ano: number, mes: number) => void; admin: boolean; setAdmin: (v: boolean) => void }

const marcaTexto = (m: string) => (m === 'T' ? 'escritório' : m === 'C' ? 'casa' : m === 'F' ? 'férias' : m === 'A' ? 'astreinte' : m === 'f' ? 'feriado' : 'sem marca')

function Totais({ dados }: { dados: RtoModulo }) {
  const t = dados.totais
  const tier = (v: number) => (v < 0 ? 'bad' : v <= 10 ? 'warn' : 'ok')
  const num = (v: number) => String(v).replace('.', ',')
  return (
    <section className="card" aria-label={`Totais de ${dados.ano}`}>
      <h2 className="t-card">Totais de {dados.ano}</h2>
      <div className="stats">
        <div className="stat"><div className="t-meta">Escritório</div><div className="t-card stat-val">{t.T}</div></div>
        <div className="stat"><div className="t-meta">Casa</div><div className="t-card stat-val">{t.C}</div><div className="t-meta">{t.pctQuota}% da quota anual</div></div>
        <div className="stat"><div className="t-meta">Quota até hoje</div><div className="t-card stat-val">{num(t.quotaProRata)}</div><div className="t-meta">de {t.quotaAnual} por ano</div></div>
      </div>
      <div className="stats two">
        <div className="stat" data-tier={tier(t.saldo)}><div className="t-meta">Saldo</div><div className="t-metric stat-val">{num(t.saldo)}</div></div>
        <div className="stat" data-tier={tier(t.saldoCondicional)}><div className="t-meta">Saldo condicional</div><div className="t-metric stat-val">{num(t.saldoCondicional)}</div></div>
      </div>
      <details className="explain">
        <summary>Como se calcula o saldo</summary>
        <ul className="rows">
          <li><span className="row-main">Dias em casa (marcados)</span><span className="row-end">{t.C}</span></li>
          <li><span className="row-main">Astreinte (crédito de 1 dia cada)</span><span className="row-end">−{t.creditosAstreinte}</span></li>
          <li><span className="row-main">Dias em casa (ajustado)</span><span className="row-end">{t.CCondicional}</span></li>
          <li><span className="row-main">Dias decorridos do ano</span><span className="row-end">{t.decorridos} de {t.diasAno}</span></li>
          <li><span className="row-main">Quota pro-rata</span><span className="row-end">{t.quotaAnual} × {t.decorridos}/{t.diasAno} = {num(t.quotaProRata)}</span></li>
          <li><span className="row-main">Saldo</span><span className="row-end">{num(t.quotaProRata)} − {t.C} = {num(t.saldo)}</span></li>
          <li><span className="row-main">Saldo condicional</span><span className="row-end">{num(t.quotaProRata)} − {t.CCondicional} = {num(t.saldoCondicional)}</span></li>
        </ul>
        <p className="t-meta">Dias de férias nunca contam. Durante a «RTO suspensão» os dias em casa não contam no saldo condicional.</p>
      </details>
    </section>
  )
}

export function CalendarioTab({ dados, executar, ocupado, avisos, mes, ano, irPara, admin, setAdmin }: Props) {
  const hojeIso = hojeLocal()
  const [escolhido, setEscolhido] = useState<string | null>(null)
  const [confirmarAdmin, setConfirmarAdmin] = useState(false)
  const semanas = useMemo(() => semanasDoMes(ano, mes), [ano, mes])
  const ferias = useMemo(() => new Set(dados.ferias), [dados.ferias])
  const dia = escolhido && escolhido.startsWith(`${ano}-${String(mes + 1).padStart(2, '0')}`) ? escolhido : null
  const anterior = mes === 0 ? { a: ano - 1, m: 11 } : { a: ano, m: mes - 1 }
  const seguinte = mes === 11 ? { a: ano + 1, m: 0 } : { a: ano, m: mes + 1 }

  const contar = (a: number, m: number) => {
    const prefixo = `${a}-${String(m + 1).padStart(2, '0')}-`
    let t = 0, c = 0
    for (const [d, v] of Object.entries(dados.dias)) {
      if (!d.startsWith(prefixo) || ferias.has(d)) continue
      if (v === 'T') t++
      else c++
    }
    return { t, c }
  }
  const atual = contar(ano, mes), ant = contar(anterior.a, anterior.m)
  const dif = (n: number) => (n === 0 ? 'sem alteração' : `${n > 0 ? '↑' : '↓'} ${plural(Math.abs(n), 'dia', 'dias')}`)

  async function marcar(data: string, marca: 'T' | 'C' | '') {
    await executar(`dia-${data}`, 'rto.marcar_dia', { data, marca, admin })
  }
  async function alternarFerias(data: string, ativo: boolean) {
    if (await executar(`ferias-${data}`, 'rto.ferias_dia', { data, admin })) avisos.mostrar(ativo ? 'Dia de férias removido.' : 'Dia marcado como férias.', () => void executar(`ferias-${data}`, 'rto.ferias_dia', { data, admin }))
  }

  return (
    <div className="stack">
      <section className="card" aria-label="Hoje">
        <h2 className="t-card">Hoje: {textoHoje(dados.hoje)}{dados.hoje.estado === 'feriado' && dados.hoje.nome ? ` — ${dados.hoje.nome}` : ''}</h2>
        <p className="t-body2">
          {dados.hoje.astreinte && dados.hoje.estado !== 'astreinte' ? 'Astreinte' : dados.proximaMudanca ? textoProximaMudanca(dados.proximaMudanca) : ' '}
        </p>
      </section>

      <section className="card" aria-label="Calendário">
        <div className="mode-row">
          <div className="segmented" role="group" aria-label="Modo do calendário">
            <button type="button" aria-pressed={!admin} onClick={() => { setAdmin(false); setConfirmarAdmin(false) }}>Normal</button>
            <button type="button" aria-pressed={admin || confirmarAdmin} onClick={() => { if (!admin) setConfirmarAdmin(true) }}>Administrador</button>
          </div>
          <span className="t-meta">{admin ? 'Sem restrições de data' : 'Fins de semana e dias passados bloqueados'}</span>
        </div>
        {confirmarAdmin && !admin && (
          <div className="notice notice-warning" role="alertdialog" aria-label="Ativar modo administrador">
            <div>
              <strong>Ativar o modo administrador?</strong> Vais poder alterar qualquer registo, incluindo dias e notas já passados e fins de semana, sem restrições.
              <div className="quick"><Botao pequeno onClick={() => { setAdmin(true); setConfirmarAdmin(false) }}>Ativar</Botao><Botao variante="secondary" pequeno onClick={() => setConfirmarAdmin(false)}>Cancelar</Botao></div>
            </div>
          </div>
        )}
        <div className="cal-head">
          <button type="button" className="icon-round" aria-label="Mês anterior" onClick={() => irPara(anterior.a, anterior.m)}><Icon nome="voltar" tamanho={20} /></button>
          <h2 className="t-card grow">{nomeMes(mes)} {ano}</h2>
          <button type="button" className="link-btn" onClick={() => { const h = new Date(); irPara(h.getFullYear(), h.getMonth()); setEscolhido(iso(h.getFullYear(), h.getMonth(), h.getDate())) }}>Hoje</button>
          <button type="button" className="icon-round" aria-label="Mês seguinte" onClick={() => irPara(seguinte.a, seguinte.m)}><Icon nome="seta" tamanho={20} /></button>
        </div>
        <div className="cal" role="grid" aria-label={`${nomeMes(mes)} ${ano}`}>
          <div className="cal-row" role="row">{DIAS_SEMANA.map((d, i) => <div key={i} className="cal-dow" role="columnheader">{d}</div>)}</div>
          {semanas.map((s, i) => (
            <div className="cal-row" role="row" key={i}>
              {s.map((data, j) => {
                if (!data) return <div key={j} className="cal-cell empty" role="gridcell" />
                const c = marcaDaCelula(dados, data)
                const info = notasDoDia(dados.notas, data).length > 0 || data in dados.feriados
                const desc = c.texto === 'Af' ? 'astreinte e feriado' : marcaTexto(c.texto || (data in dados.feriados ? 'f' : ''))
                return (
                  <button key={j} type="button" role="gridcell" className="cal-cell" data-marca={c.classe} data-hoje={data === hojeIso} data-fds={j >= 5} data-info={info}
                    aria-pressed={dia === data} aria-label={`${Number(data.slice(8))} de ${nomeMes(mes)}: ${desc}`} onClick={() => setEscolhido(dia === data ? null : data)}>
                    <span className="num">{Number(data.slice(8))}</span><span className="mk">{c.texto}</span>
                  </button>
                )
              })}
            </div>
          ))}
        </div>
        <div className="legend t-meta"><span>T · Escritório</span><span>C · Casa</span><span>F · Férias</span><span>A · Astreinte</span><span>f · Feriado</span></div>

        {dia && (
          <div className="day-panel" role="group" aria-label={`Dia ${fmtDataIso(dia)}`}>
            <div className="t-card">{fmtDataLonga(new Date(`${dia}T12:00:00`))}</div>
            {[...(dia in dados.feriados ? [{ k: 'Feriado', v: dados.feriados[dia] }] : []), ...notasDoDia(dados.notas, dia).map((n) => ({ k: n.categoria || 'Nota', v: n.descricao }))]
              .map((l, i) => <div className="t-body2" key={i}><strong>{l.k}</strong>{l.v ? ` — ${l.v}` : ''}</div>)}
            {ferias.has(dia) && <p className="t-meta">Dia de férias: não conta para o RTO.</p>}
            {diaBloqueado(dia, hojeIso) && !admin && <p className="t-meta">Fim de semana ou dia já passado: bloqueado. Ativa o modo administrador para o alterar.</p>}
            <div className="quick">
              <Botao variante="secondary" pequeno aria-pressed={dados.dias[dia] === 'T'} disabled={ocupado !== null || ferias.has(dia) || (!admin && diaBloqueado(dia, hojeIso))} onClick={() => void marcar(dia, 'T')}>Escritório</Botao>
              <Botao variante="secondary" pequeno aria-pressed={dados.dias[dia] === 'C'} disabled={ocupado !== null || ferias.has(dia) || (!admin && diaBloqueado(dia, hojeIso))} onClick={() => void marcar(dia, 'C')}>Casa</Botao>
              {dados.dias[dia] && <Botao variante="secondary" pequeno disabled={ocupado !== null || (!admin && diaBloqueado(dia, hojeIso))} onClick={() => void marcar(dia, '')}>Limpar</Botao>}
              <Botao variante="secondary" pequeno aria-pressed={ferias.has(dia)} disabled={ocupado !== null || (!admin && diaBloqueado(dia, hojeIso))} onClick={() => void alternarFerias(dia, ferias.has(dia))}>{ferias.has(dia) ? 'Remover férias' : 'Férias'}</Botao>
            </div>
          </div>
        )}
      </section>

      {ant.t + ant.c > 0 && (
        <section className="card" aria-label="Comparação com o mês anterior">
          <h2 className="t-card">{`${ano === new Date().getFullYear() && mes === new Date().getMonth() ? 'Este mês' : nomeMes(mes)} vs ${nomeMes(anterior.m)}`}</h2>
          <ul className="rows"><li><span className="row-main">Escritório</span><span className="row-end">{dif(atual.t - ant.t)}</span></li><li><span className="row-main">Casa</span><span className="row-end">{dif(atual.c - ant.c)}</span></li></ul>
        </section>
      )}
      <Totais dados={dados} />
    </div>
  )
}
