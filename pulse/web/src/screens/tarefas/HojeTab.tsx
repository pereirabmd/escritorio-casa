import { useRef, useState, type FormEvent } from 'react'
import type { InstanciaTarefa, TarefasModulo } from '../../api/types'
import { Icon } from '../../components/Icon'
import { Botao, Spinner } from '../../components/ui'
import { novoCid } from '../../lib/useAcao'
import { fmtDataIso } from '../../lib/format'
import { guardarFiltro, lerFiltro, passaFiltro, quando, urlGoogleCalendar } from '../../lib/tarefas'
import type { Ferramentas } from './tipos'

/** Uma ocorrência com as ações (concluir, adiar, saltar). Só precisa da data de hoje e da hora padrão. */
export function Linha({ i, dados, f }: { i: InstanciaTarefa; dados: Pick<TarefasModulo, 'data' | 'horaPadrao'>; f: Ferramentas }) {
  const { executar, ocupado, avisos } = f
  const [adiar, setAdiar] = useState(false)
  const [data, setData] = useState('')
  const feita = i.estado === 'Feita', saltada = i.estado === 'Saltada'

  async function alternar() {
    if (feita) {
      if (await executar(i.id, 'tarefas.reabrir', { instancia: i.id })) avisos.mostrar('Tarefa reaberta.')
      return
    }
    const r = await executar(i.id, 'tarefas.concluir', { instancia: i.id }) as { tambem?: string[] } | null
    if (r) {
      const extra = r.tambem?.length ?? 0
      avisos.mostrar(`Tarefa concluída${extra ? ` · +${extra} atrasada${extra > 1 ? 's' : ''} anterior${extra > 1 ? 'es' : ''}` : ''}.`,
        () => void executar(i.id, 'tarefas.reabrir', { instancia: i.id, tambem: r.tambem ?? [] }))
    }
  }
  async function saltar() {
    if (await executar(i.id, 'tarefas.saltar', { instancia: i.id })) avisos.mostrar('Tarefa saltada.', () => void executar(i.id, 'tarefas.reabrir', { instancia: i.id }))
  }
  async function adiarPara(para?: string) {
    if (await executar(i.id, 'tarefas.adiar', para ? { instancia: i.id, data: para } : { instancia: i.id })) {
      setAdiar(false); setData('')
      avisos.mostrar(para ? `Tarefa adiada para ${fmtDataIso(para)}.` : 'Tarefa adiada para amanhã.')
    }
  }

  return (
    <li className={adiar ? 'open' : undefined} data-estado={i.estado}>
      <button type="button" className="check" data-done={feita} aria-pressed={feita} disabled={ocupado !== null}
        aria-label={`${feita ? 'Marcar como não concluída' : 'Marcar como concluída'}: ${i.nome}`} onClick={() => void alternar()}>
        {ocupado === i.id ? <Spinner /> : <Icon nome="certo" tamanho={16} />}
      </button>
      <div className="row-main">
        <div className={`t-body${feita || saltada ? ' struck' : ''}`}>{i.nome}</div>
        <div className="t-meta">
          {feita ? `Concluída por ${i.pessoa}${i.dataConclusao ? ` · ${quando(i.dataConclusao, dados.data)}` : ''}`
            : <>{[i.pessoa, i.hora].filter(Boolean).join(' · ')}{i.estado === 'Atrasada' && <> · <span className="pill pill-soon">Atrasada</span></>}{saltada && ' · Saltada'}</>}
        </div>
      </div>
      {!feita && !saltada && (
        <>
          <a className="link-btn" href={urlGoogleCalendar(i, dados.horaPadrao)} target="_blank" rel="noopener noreferrer" aria-label={`Adicionar ${i.nome} ao Google Calendar`}>Calendário</a>
          <button type="button" className="link-btn" aria-expanded={adiar} aria-label={`Adiar ${i.nome}`} onClick={() => setAdiar((v) => !v)}>Adiar</button>
          <button type="button" className="link-btn" aria-label={`Saltar ${i.nome}`} disabled={ocupado !== null} onClick={() => void saltar()}>Saltar</button>
        </>
      )}
      {adiar && (
        <div className="adiar" role="group" aria-label={`Adiar ${i.nome}`}>
          <Botao variante="secondary" pequeno disabled={ocupado !== null} onClick={() => void adiarPara()}>Amanhã</Botao>
          <input type="date" className="input input-sm" aria-label="Escolher data" min={dados.data} value={data} onChange={(e) => setData(e.target.value)} />
          <Botao pequeno disabled={!data || data < dados.data || ocupado !== null} onClick={() => void adiarPara(data)}>Adiar para essa data</Botao>
        </div>
      )}
    </li>
  )
}

function Lista({ titulo, itens, vazio, dados, f }: { titulo: string; itens: InstanciaTarefa[]; vazio: string; dados: TarefasModulo; f: Ferramentas }) {
  return (
    <section className="card" aria-label={titulo}>
      <h2 className="t-card">{titulo}</h2>
      {itens.length === 0 ? <p className="t-body2">{vazio}</p> : <ul className="rows">{itens.map((i) => <Linha key={i.id} i={i} dados={dados} f={f} />)}</ul>}
    </section>
  )
}

/** Tarefa pontual para hoje, com o mínimo de campos (como a «tarefa rápida» da app dedicada). */
function TarefaRapida({ dados, f }: { dados: TarefasModulo; f: Ferramentas }) {
  const [aberta, setAberta] = useState(false)
  const [nome, setNome] = useState('')
  const [pessoa, setPessoa] = useState(dados.pessoa ?? dados.pessoas[0] ?? '')
  const cid = useRef(novoCid())
  if (!aberta) return <div><Botao pequeno variante="secondary" onClick={() => setAberta(true)}>Adicionar tarefa a hoje</Botao></div>
  async function guardar(ev: FormEvent) {
    ev.preventDefault()
    if (!nome.trim()) return
    const categoria = dados.categorias.includes('Outros') ? 'Outros' : dados.categorias[0] ?? 'Outros'
    if (await f.executar('rapida', 'tarefas.criar', { nome: nome.trim(), categoria, recorrencia: 'Pontual', data: dados.data, pessoa, cid: cid.current })) {
      cid.current = novoCid(); setNome(''); setAberta(false); f.avisos.mostrar('Tarefa adicionada a hoje.')
    }
  }
  return (
    <form className="card" onSubmit={guardar} noValidate aria-label="Tarefa rápida">
      <h2 className="t-card">Tarefa para hoje</h2>
      <div className="field"><label htmlFor="tr-nome">Nome</label><input id="tr-nome" className="input" maxLength={200} value={nome} onChange={(e) => setNome(e.target.value)} /></div>
      {dados.pessoas.length > 0 && (
        <div className="field"><label htmlFor="tr-pessoa">Pessoa</label>
          <select id="tr-pessoa" className="input" value={pessoa} onChange={(e) => setPessoa(e.target.value)}>{dados.pessoas.map((p) => <option key={p}>{p}</option>)}</select></div>
      )}
      <div className="quick">
        <Botao type="submit" pequeno carregando={f.ocupado === 'rapida'} disabled={!nome.trim() || f.ocupado !== null}>Adicionar</Botao>
        <Botao type="button" pequeno variante="secondary" onClick={() => setAberta(false)}>Cancelar</Botao>
      </div>
    </form>
  )
}

export function HojeTab({ dados, f }: { dados: TarefasModulo; f: Ferramentas }) {
  const [filtro, setFiltro] = useState(() => {
    const v = lerFiltro()
    return v === 'todas' || (v === 'minhas' && dados.pessoa) || dados.pessoas.includes(v) ? v : 'todas'
  })
  const escolher = (v: string) => { setFiltro(v); guardarFiltro(v) }
  const ok = (i: InstanciaTarefa) => passaFiltro(i, filtro, dados.pessoa)
  const hoje = dados.hoje.filter(ok), feitas = dados.feitas.filter(ok)
  const total = hoje.length + feitas.length

  return (
    <div className="stack">
      <div className="chips" role="group" aria-label="Filtrar por pessoa">
        {[['todas', 'Todas'], ...(dados.pessoa ? [['minhas', 'Minhas']] : []), ...dados.pessoas.map((p) => [p, p])].map(([v, l]) => (
          <button key={v} type="button" className="chip" aria-pressed={filtro === v} onClick={() => escolher(v)}>{l}</button>
        ))}
      </div>
      {total > 0 && <p className="t-body2">{feitas.length} de {total} concluídas{hoje.length === 0 && <> <span className="pill pill-ok">Tudo feito por hoje</span></>}</p>}
      <Lista titulo="Hoje" itens={[...hoje, ...feitas]} vazio="Sem tarefas para hoje." dados={dados} f={f} />
      <Lista titulo="Atrasadas" itens={dados.atrasadas.filter(ok)} vazio="Nenhuma tarefa atrasada." dados={dados} f={f} />
      <Lista titulo="Amanhã" itens={dados.amanha.filter(ok)} vazio="Nada agendado para amanhã." dados={dados} f={f} />
      <TarefaRapida dados={dados} f={f} />
    </div>
  )
}
