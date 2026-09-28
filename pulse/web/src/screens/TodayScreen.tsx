import type { ReactNode } from 'react'
import { api, mensagemDeErro } from '../api/client'
import type { BilhetesDados, EstadoModulo, FinancasDados, Hoje, Modulo, PesoDados, RtoDados, TarefasDados } from '../api/types'
import { useUtilizador } from '../auth/AuthContext'
import { Icon, type IconName } from '../components/Icon'
import { BrandLoading, Botao, Esqueleto, Notice } from '../components/ui'
import { fmtDataIso, fmtDataLonga, fmtDias, fmtDiaMes, fmtEuro, fmtPeso, plural, saudacao } from '../lib/format'
import { useAsync } from '../lib/useAsync'

const NOMES: Record<string, string> = { tarefas: 'Tarefas', bilhetes: 'Bilhetes CP', rto: 'RTO', peso: 'Peso', financas: 'Finanças' }
const DIA = ['S', 'T', 'Q', 'Q', 'S', 'S', 'D']

function Cartao({ icone, titulo, extra, children }: { icone: IconName; titulo: string; extra?: ReactNode; children: ReactNode }) {
  return (
    <section className="card" aria-label={titulo}>
      <div className="card-head"><Icon nome={icone} tamanho={22} /><h2 className="t-card grow">{titulo}</h2>{extra}</div>
      {children}
    </section>
  )
}

/** Um módulo que não está `ok` mostra o motivo no próprio cartão; o resto do Hoje continua a funcionar. */
function Estado({ modulo, children }: { modulo: Modulo<unknown>; children: () => ReactNode }) {
  if (modulo.estado === 'ok' && modulo.dados) return <>{children()}</>
  const texto: Partial<Record<EstadoModulo, string>> = {
    indisponivel: 'Indisponível de momento. Tentamos de novo quando atualizares.',
    erro: 'Não foi possível carregar esta informação.',
  }
  return <div className="unavailable"><Icon nome="alerta" tamanho={18} />{texto[modulo.estado] ?? 'Sem dados.'}</div>
}

function Tarefas({ m }: { m: Modulo<TarefasDados> }) {
  return (
    <Cartao icone="tarefas" titulo="Tarefas de hoje" extra={m.dados && m.dados.totalHoje > 0 && <span className="t-meta">{m.dados.feitasHoje} de {m.dados.totalHoje}</span>}>
      <Estado modulo={m}>{() => {
        const d = m.dados!
        return (
          <>
            {d.hoje.length === 0
              ? <p className="t-body2">{d.totalHoje > 0 ? 'Tudo feito por hoje.' : 'Sem tarefas para hoje.'}</p>
              : <ul className="rows">{d.hoje.slice(0, 5).map((t) => (
                <li key={t.id}><span className="dot" data-p={t.prioridade} aria-hidden="true" />
                  <div className="row-main"><div className="t-body">{t.nome}</div>{t.categoria && <div className="t-meta">{t.categoria}</div>}</div>
                  {t.hora && <span className="t-meta row-end">{t.hora}</span>}</li>
              ))}</ul>}
            {d.hoje.length > 5 && <p className="t-meta">e mais {d.hoje.length - 5}</p>}
            {d.atrasadas > 0 && <p className="t-meta">{plural(d.atrasadas, 'tarefa por concluir de dias anteriores', 'tarefas por concluir de dias anteriores')}</p>}
          </>
        )
      }}</Estado>
    </Cartao>
  )
}

function Bilhetes({ m }: { m: Modulo<BilhetesDados> }) {
  return (
    <Cartao icone="bilhete" titulo="Próximo comboio">
      <Estado modulo={m}>{() => {
        const { proximo: v, passe } = m.dados!
        return (
          <>
            {v ? (
              <div className="rows">
                <div className="trip"><span className="t-section">{v.hora}</span><span className="t-body">{v.origem}</span><span className="arrow"><Icon nome="seta" tamanho={16} /></span><span className="t-body">{v.destino}</span></div>
                <div className="trip t-body2">
                  <span>{fmtDiaMes(v.data)}</span><span>Comboio {v.comboio}</span>
                  {v.compra ? <span className="pill pill-ok">Comprado · carruagem {v.compra.carruagem}, lugar {v.compra.lugar}</span> : <span className="pill">Por comprar</span>}
                </div>
              </div>
            ) : <p className="t-body2">Sem viagens agendadas.</p>}
            {passe && passe.diasRestantes !== null && passe.dataExpira && (
              <p className="t-meta">Passe válido até {fmtDataIso(passe.dataExpira)} ({plural(Math.max(passe.diasRestantes, 0), 'dia', 'dias')})</p>
            )}
          </>
        )
      }}</Estado>
    </Cartao>
  )
}

function Rto({ m }: { m: Modulo<RtoDados> }) {
  return (
    <Cartao icone="rto" titulo="RTO desta semana" extra={m.dados && <span className="t-meta">{m.dados.contagem.T} escritório · {m.dados.contagem.C} casa</span>}>
      <Estado modulo={m}>{() => (
        <>
          <div className="week" role="list">
            {m.dados!.dias.map((d) => (
              <div className="day" role="listitem" key={d.data} data-hoje={d.hoje} aria-label={`${DIA[d.diaSemana - 1]} ${fmtDiaMes(d.data)}: ${d.marca === 'T' ? 'escritório' : d.marca === 'C' ? 'casa' : 'sem marca'}`}>
                <span>{DIA[d.diaSemana - 1]}</span><b>{Number(d.data.slice(8))}</b><span className="mark" data-m={d.marca}>{d.marca || ''}</span>
              </div>
            ))}
          </div>
          <div className="legend t-meta"><span>T · Escritório</span><span>C · Casa</span></div>
        </>
      )}</Estado>
    </Cartao>
  )
}

function Peso({ m }: { m: Modulo<PesoDados> }) {
  return (
    <Cartao icone="peso" titulo="Peso">
      <Estado modulo={m}>{() => {
        const d = m.dados!
        return d.ultimo ? (
          <>
            <div><span className="t-metric">{fmtPeso(d.ultimo.peso)}</span></div>
            <p className="t-body2">{d.registadoHoje ? 'Registo de hoje feito.' : `Último registo a ${fmtDataIso(d.ultimo.quando)}. Ainda não registaste hoje.`}</p>
          </>
        ) : <p className="t-body2">Ainda sem registos de peso.</p>
      }}</Estado>
    </Cartao>
  )
}

function Financas({ m }: { m: Modulo<FinancasDados> }) {
  return (
    <Cartao icone="financas" titulo="Contas a pagar" extra={m.dados && m.dados.total > 0 && <span className="t-meta">{fmtEuro(m.dados.valorTotal)} em {m.dados.total}</span>}>
      <Estado modulo={m}>{() => {
        const d = m.dados!
        return d.proximas.length === 0 ? <p className="t-body2">Sem contas pendentes nos próximos 30 dias.</p> : (
          <ul className="rows">{d.proximas.map((c) => (
            <li key={c.id}>
              <div className="row-main"><div className="t-body">{c.descricao}</div><div className="t-meta">{c.categoria}</div></div>
              <div className="row-end"><div className="t-body">{fmtEuro(c.valor)}</div><div className="t-meta">{c.vencida ? `Venceu ${fmtDias(c.diasAte)}` : `Vence ${fmtDias(c.diasAte)}`}</div></div>
            </li>
          ))}</ul>
        )
      }}</Estado>
    </Cartao>
  )
}

function resumo(h: Hoje): string {
  const partes: string[] = []
  const t = h.modulos.tarefas
  if (t.estado === 'ok' && t.dados) partes.push(t.dados.hoje.length ? plural(t.dados.hoje.length, 'tarefa para hoje', 'tarefas para hoje') : 'Sem tarefas por fazer hoje')
  const b = h.modulos.bilhetes
  if (b.estado === 'ok' && b.dados?.proximo) partes.push(`próximo comboio ${fmtDiaMes(b.dados.proximo.data)} às ${b.dados.proximo.hora}`)
  return partes.join(' · ')
}

export function TodayScreen() {
  const utilizador = useUtilizador()
  const [estado, recarregar] = useAsync(() => api.get<Hoje>('/dashboard/today'))
  const agora = new Date()
  const nome = utilizador.nome.split(' ')[0]

  return (
    <>
      <header className="hero">
        <p className="t-body2">{fmtDataLonga(agora)}</p>
        <h1 className="t-page">{saudacao(agora)}{nome ? `, ${nome}` : ''}</h1>
        {estado.fase === 'pronto' && <p className="t-body2">{resumo(estado.dados)}</p>}
      </header>

      {estado.fase === 'a-carregar' && (
        <>
          <BrandLoading texto="A preparar o teu dia…" />
          <div className="grid" aria-hidden="true">{[0, 1, 2, 3].map((i) => <div className="card" key={i}><div className="skeleton skel-title" /><Esqueleto linhas={3} /></div>)}</div>
        </>
      )}

      {estado.fase === 'erro' && (
        <div className="state">
          <Notice tipo="error">{mensagemDeErro(estado.erro)}</Notice>
          <Botao variante="secondary" pequeno onClick={recarregar}>Tentar de novo</Botao>
        </div>
      )}

      {estado.fase === 'pronto' && (
        <>
          {estado.dados.estado === 'degradado' && (
            <Notice tipo="warning" role="status">
              Alguns módulos não responderam ({Object.entries(estado.dados.modulos).filter(([, m]) => m.estado === 'indisponivel' || m.estado === 'erro').map(([k]) => NOMES[k] ?? k).join(', ')}).
              O resto está atualizado.
            </Notice>
          )}
          <div className="grid">
            {estado.dados.modulos.tarefas.estado !== 'sem_acesso' && <Tarefas m={estado.dados.modulos.tarefas} />}
            {estado.dados.modulos.bilhetes.estado !== 'sem_acesso' && <Bilhetes m={estado.dados.modulos.bilhetes} />}
            {estado.dados.modulos.rto.estado !== 'sem_acesso' && <Rto m={estado.dados.modulos.rto} />}
            {estado.dados.modulos.peso.estado !== 'sem_acesso' && <Peso m={estado.dados.modulos.peso} />}
            {estado.dados.modulos.financas.estado !== 'sem_acesso' && <Financas m={estado.dados.modulos.financas} />}
          </div>
          <>
            <p className="t-meta">Calendário e Email ainda não estão ligados.</p>
            <div><Botao variante="secondary" pequeno onClick={recarregar}>Atualizar</Botao></div>
          </>
        </>
      )}
    </>
  )
}
