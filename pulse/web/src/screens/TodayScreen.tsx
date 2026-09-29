import { useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { api, mensagemDeErro } from '../api/client'
import type { BilhetesDados, CalendarioHoje, ComprasHoje, EmailHoje, Conta, EstadoModulo, FinancasDados, Hoje, Modulo, PesoDados, RtoDados, TarefaHoje, TarefasDados } from '../api/types'
import { useUtilizador } from '../auth/AuthContext'
import { Icon, type IconName } from '../components/Icon'
import { ShopIcon } from '../components/ShopIcon'
import { BrandLoading, Botao, Esqueleto, Notice, Spinner } from '../components/ui'
import { fmtDataIso, fmtDataLonga, fmtDias, fmtDiaMes, fmtEuro, fmtPeso, plural, saudacao } from '../lib/format'
import { useAvisos } from '../components/Avisos'
import { diaBloqueado, proximaMarca } from '../lib/rto'
import { lerPeso, novoCid, useAcao } from '../lib/useAcao'
import { useAsync } from '../lib/useAsync'

type Executar = (chave: string, nome: string, params: Record<string, unknown>, confirmado?: boolean) => Promise<Record<string, unknown> | null>
interface Acoes { executar: Executar; ocupado: string | null; hoje: string }

/** Estados em que o cartão nem aparece: o utilizador não tem o módulo, ou o administrador desativou-o. */
const SEM = new Set<string>(['sem_acesso', 'desativado'])
const NOMES: Record<string, string> = { tarefas: 'Tarefas', bilhetes: 'Bilhetes CP', rto: 'RTO', peso: 'Peso', financas: 'Finanças', compras: 'Compras' }
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
    const r = await executar(t.id, 'tarefas.concluir', { instancia: t.id }) as { tambem?: string[] } | null
    if (r) avisos.mostrar('Tarefa concluída.', () => void executar(t.id, 'tarefas.reabrir', { instancia: t.id, tambem: r.tambem ?? [] }))
  }
  async function adiarPara(t: TarefaHoje, para?: string) {
    if (await executar(t.id, 'tarefas.adiar', para ? { instancia: t.id, data: para } : { instancia: t.id })) {
      setAdiar(null); setData('')
      avisos.mostrar(para ? `Tarefa adiada para ${fmtDataIso(para)}.` : 'Tarefa adiada para amanhã.')
    }
  }

  return (
    <Cartao icone="tarefas" titulo="Tarefas de hoje" extra={<>{m.dados && m.dados.totalHoje > 0 && <span className="t-meta">{m.dados.feitasHoje} de {m.dados.totalHoje}</span>}<Link to="/tarefas" className="link-btn">Abrir</Link></>}>
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
    <Cartao icone="bilhete" titulo="Próximo comboio" extra={<Link to="/bilhetes" className="link-btn">Abrir</Link>}>
      <Estado modulo={m}>{() => {
        const { proximo: v, passe } = m.dados!
        return (
          <>
            {v ? (
              <div className="rows">
                <div className="trip"><span className="t-section">{v.hora}</span><span className="t-body">{v.origem}</span><span className="arrow"><Icon nome="seta" tamanho={16} /></span><span className="t-body">{v.destino}</span></div>
                <div className="trip t-body2">
                  <span>{fmtDiaMes(v.data)}</span><span>Comboio {v.comboio}</span>
                  {v.emCurso && <span className="pill pill-soon">Em viagem · chega por volta das {v.fimEstimado}</span>}
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

/** Cartão de um módulo Google que o utilizador ainda não ligou: convida a ligar, sem ruído. */
function LigarGoogle({ icone, titulo, texto }: { icone: IconName; titulo: string; texto: string }) {
  return (
    <Cartao icone={icone} titulo={titulo}>
      <p className="t-body2">{texto}</p>
      <div><Link to="/definicoes" className="link-btn">Ligar conta Google</Link></div>
    </Cartao>
  )
}

const Problemas = ({ contas }: { contas: { id: number; email: string }[] }) => (
  contas.length > 0 ? <p className="t-meta">A conta {contas.map((c) => c.email).join(', ')} pede nova autorização. <Link to="/definicoes" className="link-btn">Volta a ligá-la</Link></p> : null
)

function Calendario({ m }: { m: Modulo<CalendarioHoje> }) {
  if (m.estado === 'nao_ligado') return <LigarGoogle icone="calendario" titulo="Calendário de hoje" texto="Liga uma conta Google para veres aqui os eventos de hoje." />
  return (
    <Cartao icone="calendario" titulo="Calendário de hoje" extra={<Link to="/calendario" className="link-btn">Abrir</Link>}>
      <Estado modulo={m}>{() => {
        const d = m.dados!
        return (
          <>
            {d.eventos.length === 0 ? <p className="t-body2">Sem eventos hoje.</p> : (
              <ul className="rows">
                {d.eventos.map((e) => (
                  <li key={`${e.conta}-${e.calendario}-${e.id}`}>
                    <span className="t-meta agenda-hora">{e.diaInteiro ? 'Dia todo' : e.inicio}</span>
                    <div className="row-main"><div className="t-body">{e.titulo}</div>{e.local && <div className="t-meta">{e.local}</div>}</div>
                  </li>
                ))}
              </ul>
            )}
            {d.total > d.eventos.length && <p className="t-meta">e mais {d.total - d.eventos.length}</p>}
            <Problemas contas={d.comProblemas} />
          </>
        )
      }}</Estado>
    </Cartao>
  )
}

function Email({ m }: { m: Modulo<EmailHoje> }) {
  if (m.estado === 'nao_ligado') return <LigarGoogle icone="email" titulo="Emails importantes" texto="Liga uma conta Google para veres aqui os emails importantes por ler." />
  return (
    <Cartao icone="email" titulo="Emails importantes" extra={<>{m.dados && m.dados.porLer > 0 && <span className="t-meta">{m.dados.porLer} por ler</span>}<Link to="/email" className="link-btn">Abrir</Link></>}>
      <Estado modulo={m}>{() => {
        const d = m.dados!
        return (
          <>
            {d.mensagens.length === 0 ? <p className="t-body2">Nada importante por ler.</p> : (
              <ul className="rows">
                {d.mensagens.map((x) => (
                  <li key={`${x.conta}-${x.id}`}><div className="row-main"><div className="t-body mail-nova">{x.de}</div><div className="t-body2">{x.assunto}</div></div></li>
                ))}
              </ul>
            )}
            {d.porLer > d.mensagens.length && <p className="t-meta">e mais {d.porLer - d.mensagens.length}</p>}
            <Problemas contas={d.comProblemas} />
          </>
        )
      }}</Estado>
    </Cartao>
  )
}

/** Alguns itens da lista «Casa»: tocar num marca-o como comprado e o seguinte ocupa o lugar (o Hoje volta a carregar). */
function Compras({ m, acoes }: { m: Modulo<ComprasHoje>; acoes: Acoes }) {
  const avisos = useAvisos()
  const { executar, ocupado } = acoes

  async function comprar(item: number, nome: string) {
    if (await executar(`compra-${item}`, 'compras.comprado', { item, comprado: true })) {
      avisos.mostrar(`${nome} comprado.`, () => void executar('desfazer', 'compras.comprado', { item, comprado: false }))
    }
  }
  return (
    <Cartao icone="compras" titulo="Lista de compras" extra={<>{m.dados && m.dados.pendentes > 0 && <span className="t-meta">{m.dados.pendentes} por comprar</span>}<Link to="/compras" className="link-btn">Abrir</Link></>}>
      <Estado modulo={m}>{() => {
        const d = m.dados!
        return d.itens.length === 0 ? <p className="t-body2">Nada por comprar. <Link to="/compras?aba=catalogo" className="link-btn">Escolher produtos</Link></p> : (
          <>
            <ul className="rows">
              {d.itens.map((i) => (
                <li key={i.item}>
                  <button type="button" className="check" data-done={false} aria-pressed={false} disabled={ocupado !== null}
                    aria-label={`Marcar como comprado: ${i.nome}`} onClick={() => void comprar(i.item, i.nome)}>
                    {ocupado === `compra-${i.item}` ? <Spinner /> : <Icon nome="certo" tamanho={16} />}
                  </button>
                  <span className="item-icon"><ShopIcon nome={i.icone} tamanho={22} /></span>
                  <div className="row-main"><div className="t-body">{i.nome}{i.quantidade !== null && <span className="pill"> {i.quantidade}×</span>}</div>{i.nota && <div className="t-meta">{i.nota}</div>}</div>
                </li>
              ))}
            </ul>
            {d.pendentes > d.itens.length && <p className="t-meta">e mais {d.pendentes - d.itens.length}</p>}
          </>
        )
      }}</Estado>
    </Cartao>
  )
}

function Rto({ m, acoes }: { m: Modulo<RtoDados>; acoes: Acoes }) {
  const avisos = useAvisos()
  const { executar, ocupado, hoje } = acoes
  const dias = m.dados?.dias ?? []
  const descreve = (marca: string) => (marca === 'T' ? 'escritório' : marca === 'C' ? 'casa' : 'sem marca')

  /** Toque num dia: vazio → T → C → vazio. Fins de semana e dias passados só no modo administrador do ecrã do RTO. */
  async function alternar(d: RtoDados['dias'][number]) {
    if (diaBloqueado(d.data, hoje)) { avisos.mostrar('Fim de semana ou dia passado: para alterar, usa o modo administrador no ecrã do RTO.'); return }
    await executar(`rto-${d.data}`, 'rto.marcar_dia', { data: d.data, marca: proximaMarca(d.marca) })
  }

  return (
    <Cartao icone="rto" titulo="RTO desta semana" extra={<>{m.dados && <span className="t-meta">{m.dados.contagem.T} escritório · {m.dados.contagem.C} casa</span>}<Link to="/rto" className="link-btn">Abrir</Link></>}>
      <Estado modulo={m}>{() => (
        <>
          <div className="week" role="group" aria-label="Dias da semana">
            {dias.map((d) => (
              <button type="button" className="day" key={d.data} data-hoje={d.hoje} disabled={ocupado !== null} onClick={() => void alternar(d)}
                aria-label={`${DIA[d.diaSemana - 1]} ${fmtDiaMes(d.data)}: ${descreve(d.marca)}`}>
                <span>{DIA[d.diaSemana - 1]}</span><b>{Number(d.data.slice(8))}</b><span className="mark" data-m={d.marca}>{d.marca || ''}</span>
              </button>
            ))}
          </div>
          <div className="legend t-meta"><span>Toca num dia: T · Escritório → C · Casa → vazio</span></div>
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
    <Cartao icone="peso" titulo="Peso" extra={<Link to="/peso" className="link-btn">Abrir</Link>}>
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
            {!SEM.has(estado.dados.modulos.calendario.estado) && <Calendario m={estado.dados.modulos.calendario} />}
            {!SEM.has(estado.dados.modulos.tarefas.estado) && <Tarefas m={estado.dados.modulos.tarefas} acoes={{ executar, ocupado, hoje: estado.dados.data }} />}
            {!SEM.has(estado.dados.modulos.email.estado) && <Email m={estado.dados.modulos.email} />}
            {!SEM.has(estado.dados.modulos.bilhetes.estado) && <Bilhetes m={estado.dados.modulos.bilhetes} />}
            {!SEM.has(estado.dados.modulos.rto.estado) && <Rto m={estado.dados.modulos.rto} acoes={{ executar, ocupado, hoje: estado.dados.data }} />}
            {!SEM.has(estado.dados.modulos.peso.estado) && <Peso m={estado.dados.modulos.peso} acoes={{ executar, ocupado, hoje: estado.dados.data }} />}
            {estado.dados.modulos.compras && !SEM.has(estado.dados.modulos.compras.estado) && <Compras m={estado.dados.modulos.compras} acoes={{ executar, ocupado, hoje: estado.dados.data }} />}
            {!SEM.has(estado.dados.modulos.financas.estado) && <Financas m={estado.dados.modulos.financas} acoes={{ executar, ocupado, hoje: estado.dados.data }} />}
          </div>
          <div><Botao variante="secondary" pequeno onClick={recarregar}>Atualizar</Botao></div>
        </>
      )}
    </>
  )
}
