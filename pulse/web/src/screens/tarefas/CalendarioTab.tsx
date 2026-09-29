import { useMemo, useState } from 'react'
import { api, mensagemDeErro } from '../../api/client'
import type { CalendarioTarefas, TarefasModulo } from '../../api/types'
import { useAvisos } from '../../components/Avisos'
import { Icon } from '../../components/Icon'
import { Botao, Notice } from '../../components/ui'
import { fmtDataLonga } from '../../lib/format'
import { corCategoria, dataDeIso, DIAS_CURTO, intervaloMes, isoLocal, intervaloSemana, somarDias, tituloMes, tituloSemana } from '../../lib/tarefas'
import { useAcao } from '../../lib/useAcao'
import { useAsync } from '../../lib/useAsync'
import { Linha } from './HojeTab'

interface Props { principal: TarefasModulo; atualizar: () => void }

export function CalendarioTab({ principal, atualizar }: Props) {
  const hoje = principal.data
  const [vista, setVista] = useState<'mes' | 'semana'>('mes')
  const [ancora, setAncora] = useState(hoje)                 // um dia do mês ou da semana à vista
  const [escolhido, setEscolhido] = useState(hoje)
  const [de, ate] = useMemo(() => (vista === 'mes' ? intervaloMes(ancora) : intervaloSemana(ancora)), [vista, ancora])
  const [estado, recarregar] = useAsync(() => api.get<CalendarioTarefas>(`/tasks/calendar?de=${de}&ate=${ate}`), `${de}|${ate}`)
  const { ocupado, erro, executar, limparErro } = useAcao(() => { recarregar(); atualizar() })
  const avisos = useAvisos()
  const dias = useMemo(() => new Map(estado.fase === 'pronto' ? estado.dados.dias.map((d) => [d.data, d]) : []), [estado])

  const mover = (n: number) => {
    const d = dataDeIso(ancora)
    const nova = vista === 'mes' ? isoLocal(new Date(d.getFullYear(), d.getMonth() + n, 1, 12)) : somarDias(ancora, 7 * n)
    setAncora(nova)
    const dentro = vista === 'mes' ? hoje.slice(0, 7) === nova.slice(0, 7) : hoje >= intervaloSemana(nova)[0] && hoje <= intervaloSemana(nova)[1]
    setEscolhido(dentro ? hoje : vista === 'mes' ? nova : intervaloSemana(nova)[0])
  }
  const trocarVista = (v: 'mes' | 'semana') => { setVista(v); setAncora(escolhido) }

  const linhas = useMemo(() => {
    const out: string[][] = []
    for (let d = de; d <= ate; d = somarDias(d, 1)) { if (out.length === 0 || out[out.length - 1].length === 7) out.push([]); out[out.length - 1].push(d) }
    return out
  }, [de, ate])
  const mesAtual = ancora.slice(0, 7)
  const dia = dias.get(escolhido)
  const ferDaVista = [...dias.values()].filter((d) => d.feriado && (vista === 'semana' || d.data.startsWith(mesAtual)))

  return (
    <div className="stack">
      <section className="card" aria-label="Calendário">
        <div className="cal-head">
          <button type="button" className="icon-round" aria-label={vista === 'mes' ? 'Mês anterior' : 'Semana anterior'} onClick={() => mover(-1)}><Icon nome="voltar" tamanho={20} /></button>
          <h2 className="t-card grow" style={{ textAlign: 'center' }}>{vista === 'mes' ? tituloMes(ancora) : tituloSemana(de, ate)}</h2>
          <button type="button" className="icon-round" aria-label={vista === 'mes' ? 'Mês seguinte' : 'Semana seguinte'} onClick={() => mover(1)}><Icon nome="seta" tamanho={20} /></button>
        </div>
        <div className="quick">
          <div className="chips" role="group" aria-label="Vista">
            <button type="button" className="chip" aria-pressed={vista === 'mes'} onClick={() => trocarVista('mes')}>Mês</button>
            <button type="button" className="chip" aria-pressed={vista === 'semana'} onClick={() => trocarVista('semana')}>Semana</button>
          </div>
          <button type="button" className="link-btn" onClick={() => { setAncora(hoje); setEscolhido(hoje) }}>Hoje</button>
        </div>
        {estado.fase === 'erro' && <Notice tipo="error">{mensagemDeErro(estado.erro)} <button type="button" className="link-btn" onClick={recarregar}>Tentar de novo</button></Notice>}
        <div className="cal" role="group" aria-label="Dias">
          <div className="cal-row" aria-hidden="true">{DIAS_CURTO.map((d) => <div key={d} className="cal-dow">{d}</div>)}</div>
          {linhas.map((sem) => (
            <div className="cal-row" key={sem[0]}>
              {sem.map((d) => {
                const info = dias.get(d)
                const cores = [...new Set((info?.itens ?? []).map((i) => corCategoria(i.categoria)))].slice(0, 3)
                const dow = dataDeIso(d).getDay()
                return (
                  <button key={d} type="button" className="cal-cell" aria-pressed={d === escolhido} data-hoje={d === hoje} data-fds={dow === 0 || dow === 6}
                    data-fora={vista === 'mes' && !d.startsWith(mesAtual)} data-feriado={!!info?.feriado}
                    aria-label={`${Number(d.slice(8))} de ${new Intl.DateTimeFormat('pt-PT', { month: 'long' }).format(dataDeIso(d))}${info?.feriado ? `, ${info.feriado}` : ''}${info?.itens.length ? `, ${info.itens.length} tarefa${info.itens.length > 1 ? 's' : ''}` : ''}`}
                    title={info?.feriado ?? undefined} onClick={() => setEscolhido(d)}>
                    <span className="num">{Number(d.slice(8))}</span>
                    <span className="dots" aria-hidden="true">{cores.map((c) => <i key={c} style={{ background: c }} />)}</span>
                  </button>
                )
              })}
            </div>
          ))}
        </div>
        {ferDaVista.length > 0 && <p className="t-meta">{ferDaVista.map((d) => `${Number(d.data.slice(8))} — ${d.feriado}`).join(' · ')}</p>}
      </section>

      <section className="card" aria-label="Tarefas do dia">
        <h2 className="t-card">{fmtDataLonga(dataDeIso(escolhido))}{dia?.feriado && <> <span className="t-meta">· {dia.feriado}</span></>}</h2>
        {erro && <Notice tipo="error">{erro} <button type="button" className="link-btn" onClick={limparErro}>Fechar</button></Notice>}
        {estado.fase === 'pronto' && estado.dados.dias.length > 0 && (!dia || dia.itens.length === 0)
          ? <p className="t-body2">Sem tarefas neste dia.</p>
          : dia && <ul className="rows">{dia.itens.map((i) => <Linha key={i.id} i={i} dados={{ data: hoje, horaPadrao: principal.horaPadrao }} f={{ executar, ocupado, avisos }} />)}</ul>}
        <Botao variante="secondary" pequeno onClick={recarregar}>Atualizar</Botao>
      </section>
    </div>
  )
}
