import { useState } from 'react'
import { api, mensagemDeErro } from '../../api/client'
import type { HorarioDados, HorarioDia } from '../../api/types'
import { Notice, Botao, BrandLoading } from '../../components/ui'
import { useAvisos } from '../../components/Avisos'
import { useAcao } from '../../lib/useAcao'
import { useAsync } from '../../lib/useAsync'

const NOMES_DIA = ['', 'Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']

function Aulas({ aulas }: { aulas: { disciplina: string; sala: string }[] }) {
  return <>{aulas.map((a, k) => <div className="hor-aula" key={k}><b>{a.disciplina}</b>{a.sala && <span>{a.sala}</span>}</div>)}</>
}

function VistaDia({ dia, hoje }: { dia: HorarioDia; hoje: boolean }) {
  const agora = new Date()
  const min = agora.getHours() * 60 + agora.getMinutes()
  const m = (hhmm: string) => Number(hhmm.slice(0, 2)) * 60 + Number(hhmm.slice(3))
  return (
    <>
      <p className="t-body2">Entra às <b>{dia.entra}</b> · sai às <b>{dia.sai}</b> · {dia.totalAulas} aulas</p>
      <ul className="rows">
        {dia.slots.map((s) => {
          const agoraAqui = hoje && min >= m(s.ini) && min < m(s.fim)
          return (
            <li key={s.ini + s.fim} className="hor-slot" data-agora={agoraAqui}>
              <div className="hor-hora"><b>{s.ini}</b><span>{s.fim}</span></div>
              <div className="row-main">
                <Aulas aulas={s.aulas} />
                {s.dividida && <div className="t-meta">turma dividida</div>}
                {s.ultima && <div className="t-meta">Saída às {s.fim} · aviso às {dia.aviso}</div>}
                {agoraAqui && <span className="pill pill-ok">A decorrer</span>}
              </div>
            </li>
          )
        })}
      </ul>
    </>
  )
}

export function HorarioTab() {
  const [estado, recarregar] = useAsync(() => api.get<HorarioDados>('/tasks/schedule'))
  const { ocupado, erro, executar, limparErro } = useAcao(recarregar)
  const avisos = useAvisos()
  const [aluno, setAluno] = useState<string | null>(null)
  const [vista, setVista] = useState<'dia' | 'semana'>('dia')
  const [dia, setDia] = useState<number | null>(null)

  if (estado.fase === 'a-carregar') return <BrandLoading texto="A carregar o horário…" />
  if (estado.fase === 'erro') return <div className="state"><Notice tipo="error">{mensagemDeErro(estado.erro)}</Notice><Botao variante="secondary" pequeno onClick={recarregar}>Tentar de novo</Botao></div>
  const d = estado.dados
  if (!d.disponivel) return <Notice tipo="warning">O horário não está disponível de momento. <button type="button" className="link-btn" onClick={recarregar}>Tentar de novo</button></Notice>
  if (d.alunos.length === 0) return <p className="t-body2">Ainda não há horário importado.</p>

  const al = d.alunos.find((a) => a.nome === aluno) ?? d.alunos[0]
  const comAulas = al.dias.map((x) => x.dia)
  const escolhido = dia !== null && comAulas.includes(dia) ? dia : comAulas.includes(d.diaHoje) ? d.diaHoje : comAulas.find((x) => x > d.diaHoje) ?? comAulas[0]
  const atual = al.dias.find((x) => x.dia === escolhido)
  const slotsSemana = [...new Set(al.dias.flatMap((x) => x.slots.map((s) => `${s.ini}|${s.fim}`)))].sort()
  const av = d.avisos

  async function alternar() {
    if (!av) return
    if (await executar('avisos', 'tarefas.avisos_horario', { ativos: !av.ativos })) {
      avisos.mostrar(av.ativos ? 'Avisos do horário pausados (os já agendados são cancelados em poucos minutos).' : 'Avisos do horário ativos.')
    }
  }

  return (
    <div className="stack">
      {erro && <Notice tipo="error">{erro} <button type="button" className="link-btn" onClick={limparErro}>Fechar</button></Notice>}
      <section className="card" aria-label="Horário escolar">
        <h2 className="t-card">Horário escolar <span className="t-meta">ano letivo {d.anoLetivo}</span></h2>
        {d.alunos.length > 1 && (
          <div className="chips" role="group" aria-label="Aluno">{d.alunos.map((a) => <button key={a.nome} type="button" className="chip" aria-pressed={a.nome === al.nome} onClick={() => setAluno(a.nome)}>{a.nome}</button>)}</div>
        )}
        <div className="chips" role="group" aria-label="Vista">
          <button type="button" className="chip" aria-pressed={vista === 'dia'} onClick={() => setVista('dia')}>Dia</button>
          <button type="button" className="chip" aria-pressed={vista === 'semana'} onClick={() => setVista('semana')}>Semana</button>
        </div>
        {vista === 'dia' ? (
          <>
            <div className="chips" role="group" aria-label="Dia da semana">
              {al.dias.map((x) => <button key={x.dia} type="button" className="chip" aria-pressed={x.dia === escolhido} aria-label={NOMES_DIA[x.dia]} onClick={() => setDia(x.dia)}>{x.nome}{x.dia === d.diaHoje ? ' •' : ''}</button>)}
            </div>
            {atual ? <VistaDia dia={atual} hoje={escolhido === d.diaHoje} /> : <p className="t-body2">Sem aulas neste dia.</p>}
          </>
        ) : (
          <div className="hor-semana-wrap">
            <table className="hor-semana">
              <thead><tr><th scope="col"><span className="sr-only">Hora</span></th>{al.dias.map((x) => <th key={x.dia} scope="col" data-hoje={x.dia === d.diaHoje}><button type="button" className="link-btn" onClick={() => { setDia(x.dia); setVista('dia') }}>{x.nome}</button></th>)}</tr></thead>
              <tbody>
                {slotsSemana.map((k) => {
                  const [ini, fim] = k.split('|')
                  return (
                    <tr key={k}>
                      <th scope="row" className="h"><b>{ini}</b><span>{fim}</span></th>
                      {al.dias.map((x) => {
                        const s = x.slots.find((y) => y.ini === ini && y.fim === fim)
                        return <td key={x.dia} data-hoje={x.dia === d.diaHoje} data-dividida={!!s?.dividida}>{s && <Aulas aulas={s.aulas} />}</td>
                      })}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {av && (
        <section className="card" aria-label="Avisos do horário">
          <p className="t-body2">{av.ativos ? `Aviso ${av.minutos} min antes de acabar a última aula do dia.` : 'Avisos do horário pausados.'}</p>
          <Botao variante="secondary" pequeno carregando={ocupado === 'avisos'} disabled={ocupado !== null} onClick={() => void alternar()}>{av.ativos ? 'Pausar avisos' : 'Ativar avisos'}</Botao>
        </section>
      )}
    </div>
  )
}
