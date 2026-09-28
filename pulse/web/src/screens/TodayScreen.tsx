import { useRef, useState, type ReactNode } from 'react'
import { api, mensagemDeErro } from '../api/client'
import type { BilhetesDados, Conta, EstadoModulo, FinancasDados, Hoje, Modulo, PesoDados, RtoDados, TarefaHoje, TarefasDados } from '../api/types'
import { useUtilizador } from '../auth/AuthContext'
import { Icon, type IconName } from '../components/Icon'
import { BrandLoading, Botao, Esqueleto, Notice, Spinner } from '../components/ui'
import { fmtDataIso, fmtDataLonga, fmtDias, fmtDiaMes, fmtEuro, fmtPeso, plural, saudacao } from '../lib/format'
import { useAvisos } from '../components/Avisos'
import { lerPeso, novoCid, useAcao } from '../lib/useAcao'
import { useAsync } from '../lib/useAsync'

type Executar = (chave: string, nome: string, params: Record<string, unknown>) => Promise<boolean>
interface Acoes { executar: Executar; ocupado: string | null; hoje: string }

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

function Tarefas({ m, acoes }: { m: Modulo<TarefasDados>; acoes: Acoes }) {
  const avisos = useAvisos()
  const [adiar, setAdiar] = useState<string | null>(null)
  const [data, setData] = useState('')
  const { executar, ocupado, hoje } = acoes

  async function concluir(t: TarefaHoje) {
    if (await executar(t.id, 'tarefas.concluir', { instancia: t.id }))
      avisos.mostrar('Tarefa concluída.', () => void executar(t.id, 'tarefas.reabrir', { instancia: t.id }))
  }
  async function adiarPara(t: TarefaHoje, para?: string) {
    if (await executar(t.id, 'tarefas.adiar', para ? { instancia: t.id, data: para } : { instancia: t.id })) {
      setAdiar(null); setData('')
      avisos.mostrar(para ? `Tarefa adiada para ${fmtDataIso(para)}.` : 'Tarefa adiada para amanhã.')
    }
  }

  return (
    <Cartao icone="tarefas" titulo="Tarefas de hoje" extra={m.dados && m.dados.totalHoje > 0 && <span className="t-meta">{m.dados.feitasHoje} de {m.dados.totalHoje}</span>}>
      <Estado modulo={m}>{() => {
        const d = m.dados!
        return (
          <>
            {d.hoje.length === 0
              ? <p className="t-body2">{d.totalHoje > 0 ? 'Tudo feito por hoje.' : 'Sem tarefas para hoje.'}</p>
              : <ul className="rows">{d.hoje.slice(0, 5).map((t) => (
                <li key={t.id} className={adiar === t.id ? 'open' : undefined}>
                  <button type="button" className="check" aria-label={`Concluir ${t.nome}`} disabled={ocupado !== null} onClick={() => void concluir(t)}>
                    {ocupado === t.id ? <Spinner /> : <Icon nome="certo" tamanho={16} />}
                  </button>
                  <div className="row-main"><div className="t-body">{t.nome}</div><div className="t-meta">{[t.categoria, t.hora].filter(Boolean).join(' · ')}</div></div>
                  <button type="button" className="link-btn" aria-expanded={adiar === t.id} aria-label={`Adiar ${t.nome}`} onClick={() => setAdiar(adiar === t.id ? null : t.id)}>Adiar</button>
                  {adiar === t.id && (
                    <div className="adiar" role="group" aria-label={`Adiar ${t.nome}`}>
                      <Botao variante="secondary" pequeno disabled={ocupado !== null} onClick={() => void adiarPara(t)}>Amanhã</Botao>
                      <input type="date" className="input input-sm" aria-label="Escolher data" min={hoje} value={data} onChange={(e) => setData(e.target.value)} />
                      <Botao pequeno disabled={!data || data < hoje || ocupado !== null} onClick={() => void adiarPara(t, data)}>Adiar para essa data</Botao>
                    </div>
                  )}
                </li>
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

function Rto({ m, acoes }: { m: Modulo<RtoDados>; acoes: Acoes }) {
  const [escolhido, setEscolhido] = useState<string | null>(null)
  const { executar, ocupado } = acoes
  const dias = m.dados?.dias ?? []
  const dia = dias.find((d) => d.data === (escolhido ?? dias.find((x) => x.hoje)?.data))

  async function marcar(marca: 'T' | 'C' | '') {
    if (dia) await executar(`rto-${dia.data}`, 'rto.marcar_dia', { data: dia.data, marca })
  }
  const descreve = (marca: string) => (marca === 'T' ? 'escritório' : marca === 'C' ? 'casa' : 'sem marca')

  return (
    <Cartao icone="rto" titulo="RTO desta semana" extra={m.dados && <span className="t-meta">{m.dados.contagem.T} escritório · {m.dados.contagem.C} casa</span>}>
      <Estado modulo={m}>{() => (
        <>
          <div className="week" role="group" aria-label="Dias da semana">
            {dias.map((d) => (
              <button type="button" className="day" key={d.data} data-hoje={d.hoje} aria-pressed={dia?.data === d.data} onClick={() => setEscolhido(d.data)}
                aria-label={`${DIA[d.diaSemana - 1]} ${fmtDiaMes(d.data)}: ${descreve(d.marca)}`}>
                <span>{DIA[d.diaSemana - 1]}</span><b>{Number(d.data.slice(8))}</b><span className="mark" data-m={d.marca}>{d.marca || ''}</span>
              </button>
            ))}
          </div>
          {dia && (
            <div className="quick" role="group" aria-label={`Marcar ${fmtDiaMes(dia.data)}`}>
              <span className="t-meta">{fmtDiaMes(dia.data)}:</span>
              <Botao variante="secondary" pequeno aria-pressed={dia.marca === 'T'} disabled={ocupado !== null} onClick={() => void marcar('T')}>Escritório</Botao>
              <Botao variante="secondary" pequeno aria-pressed={dia.marca === 'C'} disabled={ocupado !== null} onClick={() => void marcar('C')}>Casa</Botao>
              {dia.marca && <Botao variante="secondary" pequeno disabled={ocupado !== null} onClick={() => void marcar('')}>Limpar</Botao>}
            </div>
          )}
          <div className="legend t-meta"><span>T · Escritório</span><span>C · Casa</span></div>
        </>
      )}</Estado>
    </Cartao>
  )
}

function Peso({ m, acoes }: { m: Modulo<PesoDados>; acoes: Acoes }) {
  const avisos = useAvisos()
  const { executar, ocupado } = acoes
  const [texto, setTexto] = useState(() => (m.dados?.sugestao != null ? String(m.dados.sugestao).replace('.', ',') : ''))
  const cid = useRef(novoCid())          // o mesmo cid até haver sucesso: repetir um pedido que falhou não duplica o registo
  const valor = lerPeso(texto)

  async function registar() {
    if (valor === null) return
    if (await executar('peso', 'peso.registar', { peso: valor, cid: cid.current })) {
      cid.current = novoCid()
      avisos.mostrar('Peso registado.')
    }
  }

  return (
    <Cartao icone="peso" titulo="Peso">
      <Estado modulo={m}>{() => {
        const d = m.dados!
        return (
          <>
            {d.ultimo ? (
              <>
                <div><span className="t-metric">{fmtPeso(d.ultimo.peso)}</span></div>
                <p className="t-body2">{d.registadoHoje ? 'Registo de hoje feito.' : `Último registo a ${fmtDataIso(d.ultimo.quando)}. Ainda não registaste hoje.`}</p>
              </>
            ) : <p className="t-body2">Ainda sem registos de peso.</p>}
            {!d.registadoHoje && (
              <form className="quick" onSubmit={(e) => { e.preventDefault(); void registar() }}>
                <label className="sr-only" htmlFor="peso-hoje">Peso de hoje em quilogramas</label>
                <input id="peso-hoje" className="input input-sm peso-input" inputMode="decimal" autoComplete="off" value={texto} onChange={(e) => setTexto(e.target.value)} aria-invalid={texto !== '' && valor === null ? true : undefined} />
                <span className="t-body2">kg</span>
                <Botao type="submit" pequeno carregando={ocupado === 'peso'} disabled={valor === null || ocupado !== null}>Registar</Botao>
              </form>
            )}
          </>
        )
      }}</Estado>
    </Cartao>
  )
}

function Financas({ m, acoes }: { m: Modulo<FinancasDados>; acoes: Acoes }) {
  const avisos = useAvisos()
  const { executar, ocupado } = acoes

  async function pagar(c: Conta) {
    const p = { lancamento: c.id }
    if (await executar(`conta-${c.id}`, 'financas.pagar', p))
      avisos.mostrar(`${c.descricao} marcada como paga.`, () => void executar(`conta-${c.id}`, 'financas.anular_pagamento', p))
  }

  return (
    <Cartao icone="financas" titulo="Contas a pagar" extra={m.dados && m.dados.total > 0 && <span className="t-meta">{fmtEuro(m.dados.valorTotal)} em {m.dados.total}</span>}>
      <Estado modulo={m}>{() => {
        const d = m.dados!
        return d.proximas.length === 0 ? <p className="t-body2">Sem contas pendentes nos próximos 30 dias.</p> : (
          <ul className="rows">{d.proximas.map((c) => (
            <li key={c.id}>
              <div className="row-main"><div className="t-body">{c.descricao}</div><div className="t-meta">{c.categoria}</div></div>
              <div className="row-end"><div className="t-body">{fmtEuro(c.valor)}</div><div className="t-meta">{c.vencida ? `Venceu ${fmtDias(c.diasAte)}` : `Vence ${fmtDias(c.diasAte)}`}</div></div>
              <button type="button" className="link-btn" aria-label={`Marcar ${c.descricao} como paga`} disabled={ocupado !== null} onClick={() => void pagar(c)}>
                {ocupado === `conta-${c.id}` ? <Spinner /> : 'Pagar'}
              </button>
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
  const { ocupado, erro, executar, limparErro } = useAcao(recarregar)
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
          {erro && (
            <Notice tipo="error">{erro} <button type="button" className="link-btn" onClick={limparErro}>Fechar</button></Notice>
          )}
          <div className="grid">
            {estado.dados.modulos.tarefas.estado !== 'sem_acesso' && <Tarefas m={estado.dados.modulos.tarefas} acoes={{ executar, ocupado, hoje: estado.dados.data }} />}
            {estado.dados.modulos.bilhetes.estado !== 'sem_acesso' && <Bilhetes m={estado.dados.modulos.bilhetes} />}
            {estado.dados.modulos.rto.estado !== 'sem_acesso' && <Rto m={estado.dados.modulos.rto} acoes={{ executar, ocupado, hoje: estado.dados.data }} />}
            {estado.dados.modulos.peso.estado !== 'sem_acesso' && <Peso m={estado.dados.modulos.peso} acoes={{ executar, ocupado, hoje: estado.dados.data }} />}
            {estado.dados.modulos.financas.estado !== 'sem_acesso' && <Financas m={estado.dados.modulos.financas} acoes={{ executar, ocupado, hoje: estado.dados.data }} />}
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
