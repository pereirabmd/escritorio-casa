import { useMemo, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, mensagemDeErro } from '../../api/client'
import type { AgendaGoogle, EventoGoogle } from '../../api/types'
import { useAvisos } from '../../components/Avisos'
import { Icon } from '../../components/Icon'
import { BrandLoading, Botao, Notice } from '../../components/ui'
import { fmtDataLonga } from '../../lib/format'
import { DIAS_CURTO, dataDeIso, intervaloMes, isoLocal, tituloMes } from '../../lib/tarefas'
import { useAcao } from '../../lib/useAcao'
import { useAsync } from '../../lib/useAsync'

const hojeIso = () => isoLocal(new Date())
const hora = (e: EventoGoogle) => (e.diaInteiro ? 'Dia inteiro' : `${e.inicio}–${e.fim}`)

interface Rascunho { conta: string; calendario: string; titulo: string; data: string; dataFim: string; diaInteiro: boolean; inicio: string; fim: string; local: string; descricao: string }
const paraRascunho = (e: EventoGoogle): Rascunho => ({ conta: String(e.conta), calendario: e.calendario, titulo: e.titulo, data: e.data, dataFim: e.dataFim === e.data ? '' : e.dataFim,
  diaInteiro: e.diaInteiro, inicio: e.inicio ?? '09:00', fim: e.fim ?? '10:00', local: e.local, descricao: e.descricao })

function Formulario({ inicial, agenda, editar, fechar, executar, ocupado, avisos }: { inicial: Rascunho; agenda: AgendaGoogle; editar?: EventoGoogle; fechar: () => void
  executar: ReturnType<typeof useAcao>['executar']; ocupado: string | null; avisos: ReturnType<typeof useAvisos> }) {
  const [r, setR] = useState<Rascunho>(inicial)
  const atual = (p: Partial<Rascunho>) => setR((x) => ({ ...x, ...p }))
  const contasCal = agenda.contas.filter((c) => c.estado === 'ok')
  const editaveis = agenda.calendarios.filter((c) => c.conta === Number(r.conta) && c.podeEditar)
  const horasOk = r.diaInteiro || (r.inicio !== '' && r.fim !== '' && (r.dataFim || r.data) + r.fim > r.data + r.inicio)
  const ok = r.titulo.trim() !== '' && r.data !== '' && horasOk && (!r.dataFim || r.dataFim >= r.data) && (editar !== undefined || editaveis.length > 0)

  async function guardar(ev: FormEvent) {
    ev.preventDefault()
    if (!ok) return
    const comum = { titulo: r.titulo.trim(), data: r.data, ...(r.dataFim && r.dataFim !== r.data ? { dataFim: r.dataFim } : {}), ...(r.diaInteiro ? {} : { inicio: r.inicio, fim: r.fim }),
      local: r.local.trim(), descricao: r.descricao.trim() }
    const feito = editar
      ? await executar('evento', 'calendario.editar', { conta: editar.conta, calendario: editar.calendario, evento: editar.id, ...comum })
      : await executar('evento', 'calendario.criar', { conta: Number(r.conta), calendario: r.calendario || 'primary', ...comum })
    if (feito) { avisos.mostrar(editar ? 'Evento atualizado.' : 'Evento criado.'); fechar() }
  }
  const id = editar ? `ev-${editar.id}` : 'ev-novo'
  return (
    <form className="card stack" onSubmit={guardar} noValidate aria-label={editar ? `Editar ${editar.titulo}` : 'Novo evento'}>
      <h2 className="t-card">{editar ? 'Editar evento' : 'Novo evento'}</h2>
      <div className="field"><label htmlFor={`${id}-t`}>Título</label><input id={`${id}-t`} className="input" maxLength={200} value={r.titulo} onChange={(e) => atual({ titulo: e.target.value })} /></div>
      {!editar && contasCal.length > 0 && (
        <div className="quick">
          {contasCal.length > 1 && <div className="field"><label htmlFor={`${id}-c`}>Conta</label>
            <select id={`${id}-c`} className="input" value={r.conta} onChange={(e) => atual({ conta: e.target.value, calendario: '' })}>{contasCal.map((c) => <option key={c.id} value={c.id}>{c.email}</option>)}</select></div>}
          {editaveis.length > 1 && <div className="field"><label htmlFor={`${id}-k`}>Calendário</label>
            <select id={`${id}-k`} className="input" value={r.calendario || editaveis.find((c) => c.principal)?.id || editaveis[0].id} onChange={(e) => atual({ calendario: e.target.value })}>{editaveis.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}</select></div>}
        </div>
      )}
      <div className="quick">
        <div className="field"><label htmlFor={`${id}-d`}>Data</label><input id={`${id}-d`} type="date" className="input" value={r.data} onChange={(e) => atual({ data: e.target.value })} /></div>
        <div className="field"><label htmlFor={`${id}-f`}>Até (opcional)</label><input id={`${id}-f`} type="date" className="input" min={r.data} value={r.dataFim} onChange={(e) => atual({ dataFim: e.target.value })} /></div>
      </div>
      <label className="check-line"><input type="checkbox" checked={r.diaInteiro} onChange={(e) => atual({ diaInteiro: e.target.checked })} /> Dia inteiro</label>
      {!r.diaInteiro && (
        <div className="quick">
          <div className="field"><label htmlFor={`${id}-i`}>Início</label><input id={`${id}-i`} type="time" className="input" value={r.inicio} onChange={(e) => atual({ inicio: e.target.value })} /></div>
          <div className="field"><label htmlFor={`${id}-h`}>Fim</label><input id={`${id}-h`} type="time" className="input" value={r.fim} onChange={(e) => atual({ fim: e.target.value })} aria-invalid={!horasOk ? true : undefined} /></div>
        </div>
      )}
      <div className="field"><label htmlFor={`${id}-l`}>Local (opcional)</label><input id={`${id}-l`} className="input" maxLength={200} value={r.local} onChange={(e) => atual({ local: e.target.value })} /></div>
      <div className="field"><label htmlFor={`${id}-n`}>Notas (opcional)</label><input id={`${id}-n`} className="input" maxLength={500} value={r.descricao} onChange={(e) => atual({ descricao: e.target.value })} /></div>
      {!editar && editaveis.length === 0 && <p className="t-meta">Esta conta não tem nenhum calendário onde possas criar eventos.</p>}
      <div className="quick">
        <Botao type="submit" pequeno carregando={ocupado === 'evento'} disabled={!ok || ocupado !== null}>{editar ? 'Guardar' : 'Criar evento'}</Botao>
        <Botao type="button" pequeno variante="secondary" onClick={fechar}>Cancelar</Botao>
      </div>
    </form>
  )
}

export function CalendarioScreen() {
  const hoje = hojeIso()
  const [ancora, setAncora] = useState(hoje)
  const [escolhido, setEscolhido] = useState(hoje)
  const [modo, setModo] = useState<'ver' | 'novo' | { editar: EventoGoogle } | { apagar: EventoGoogle }>('ver')
  const [de, ate] = useMemo(() => intervaloMes(ancora), [ancora])
  const [estado, recarregar] = useAsync(() => api.get<AgendaGoogle>(`/calendar?de=${de}&ate=${ate}`), `${de}|${ate}`)
  const { ocupado, erro, executar, limparErro } = useAcao(recarregar)
  const avisos = useAvisos()
  const dias = useMemo(() => new Map(estado.fase === 'pronto' ? estado.dados.dias.map((d) => [d.data, d.eventos]) : []), [estado])
  const mesAtual = ancora.slice(0, 7)
  const linhas = useMemo(() => {
    const out: string[][] = []
    for (let d = de; d <= ate; d = isoLocal(new Date(dataDeIso(d).getTime() + 86400000))) { if (out.length === 0 || out[out.length - 1].length === 7) out.push([]); out[out.length - 1].push(d) }
    return out
  }, [de, ate])

  function mover(n: number) {
    const d = dataDeIso(ancora)
    const nova = isoLocal(new Date(d.getFullYear(), d.getMonth() + n, 1, 12))
    setAncora(nova); setEscolhido(nova.slice(0, 7) === hoje.slice(0, 7) ? hoje : nova); setModo('ver')
  }
  const eventosDia = dias.get(escolhido) ?? []

  async function apagar(e: EventoGoogle) {
    const r = await executar('apagar', 'calendario.apagar', { conta: e.conta, calendario: e.calendario, evento: e.id }, true)
    if (r) {
      setModo('ver')
      avisos.mostrar('Evento apagado.', () => void executar('desfazer', 'calendario.criar', { conta: e.conta, calendario: e.calendario, titulo: e.titulo, data: e.data,
        ...(e.dataFim !== e.data ? { dataFim: e.dataFim } : {}), ...(e.diaInteiro ? {} : { inicio: e.inicio, fim: e.fim }), local: e.local, descricao: e.descricao }))
    }
  }

  return (
    <>
      <header className="hero">
        <Link to="/mais" className="back"><Icon nome="voltar" tamanho={20} />Mais</Link>
        <h1 className="t-page">Calendário</h1>
      </header>

      {estado.fase === 'a-carregar' && <BrandLoading texto="A carregar a agenda…" />}
      {estado.fase === 'erro' && (
        <div className="state">
          <Notice tipo="error">{mensagemDeErro(estado.erro)}</Notice>
          <Botao variante="secondary" pequeno onClick={recarregar}>Tentar de novo</Botao>
        </div>
      )}
      {estado.fase === 'pronto' && !estado.dados.ligado && (
        <div className="stack">
          <Notice tipo="info">{estado.dados.configurado ? 'Liga uma conta Google com o Calendário para veres aqui os teus eventos.' : 'A integração com a Google ainda não está configurada neste servidor.'}</Notice>
          <div><Link to="/definicoes" className="btn btn-secondary btn-sm">Ir às Definições</Link></div>
        </div>
      )}
      {estado.fase === 'pronto' && estado.dados.ligado && (
        <div className="stack">
          {estado.dados.contas.filter((c) => c.estado !== 'ok').map((c) => (
            <Notice key={c.id} tipo="warning">{c.estado === 'reautorizar' ? <>A conta {c.email} pede nova autorização. <Link to="/definicoes" className="link-btn">Volta a ligá-la</Link>.</> : <>Não foi possível ler a conta {c.email}: {c.erro}</>}</Notice>
          ))}
          <section className="card" aria-label="Calendário">
            <div className="cal-head">
              <button type="button" className="icon-round" aria-label="Mês anterior" onClick={() => mover(-1)}><Icon nome="voltar" tamanho={20} /></button>
              <h2 className="t-card grow" style={{ textAlign: 'center' }}>{tituloMes(ancora)}</h2>
              <button type="button" className="icon-round" aria-label="Mês seguinte" onClick={() => mover(1)}><Icon nome="seta" tamanho={20} /></button>
            </div>
            <div className="quick"><button type="button" className="link-btn" onClick={() => { setAncora(hoje); setEscolhido(hoje) }}>Hoje</button></div>
            <div className="cal" role="group" aria-label="Dias">
              <div className="cal-row" aria-hidden="true">{DIAS_CURTO.map((d) => <div key={d} className="cal-dow">{d}</div>)}</div>
              {linhas.map((sem) => (
                <div className="cal-row" key={sem[0]}>
                  {sem.map((d) => {
                    const evs = dias.get(d) ?? []
                    const cores = [...new Set(evs.map((e) => e.cor ?? 'var(--accent)'))].slice(0, 3)
                    const dow = dataDeIso(d).getDay()
                    return (
                      <button key={d} type="button" className="cal-cell" aria-pressed={d === escolhido} data-hoje={d === hoje} data-fds={dow === 0 || dow === 6} data-fora={!d.startsWith(mesAtual)}
                        aria-label={`${Number(d.slice(8))} de ${new Intl.DateTimeFormat('pt-PT', { month: 'long' }).format(dataDeIso(d))}${evs.length ? `, ${evs.length} ${evs.length === 1 ? 'evento' : 'eventos'}` : ''}`}
                        onClick={() => { setEscolhido(d); setModo('ver') }}>
                        <span className="num">{Number(d.slice(8))}</span>
                        <span className="dots" aria-hidden="true">{cores.map((c) => <i key={c} style={{ background: c }} />)}</span>
                      </button>
                    )
                  })}
                </div>
              ))}
            </div>
          </section>

          {erro && <Notice tipo="error">{erro} <button type="button" className="link-btn" onClick={limparErro}>Fechar</button></Notice>}
          {modo === 'novo' && <Formulario inicial={{ conta: String(estado.dados.contas.find((c) => c.estado === 'ok')?.id ?? ''), calendario: '', titulo: '', data: escolhido, dataFim: '', diaInteiro: false, inicio: '09:00', fim: '10:00', local: '', descricao: '' }}
            agenda={estado.dados} fechar={() => setModo('ver')} executar={executar} ocupado={ocupado} avisos={avisos} />}
          {typeof modo === 'object' && 'editar' in modo && <Formulario key={modo.editar.id} inicial={paraRascunho(modo.editar)} agenda={estado.dados} editar={modo.editar} fechar={() => setModo('ver')} executar={executar} ocupado={ocupado} avisos={avisos} />}

          <section className="card" aria-label="Eventos do dia">
            <div className="split"><h2 className="t-card">{fmtDataLonga(dataDeIso(escolhido))}</h2>
              {modo === 'ver' && <Botao pequeno variante="secondary" onClick={() => setModo('novo')}>Novo evento</Botao>}</div>
            {eventosDia.length === 0 ? <p className="t-body2">Sem eventos neste dia.</p> : (
              <ul className="rows">
                {eventosDia.map((e) => {
                  const apagando = typeof modo === 'object' && 'apagar' in modo && modo.apagar.id === e.id
                  return (
                    <li key={`${e.conta}-${e.calendario}-${e.id}`}>
                      <span className="bolinha" style={{ background: e.cor ?? 'var(--accent)' }} aria-hidden="true" />
                      <div className="row-main">
                        <div className="t-body">{e.titulo}</div>
                        <div className="t-meta">{hora(e)}{e.dataFim !== e.data ? ` · até ${e.dataFim.slice(8)}/${e.dataFim.slice(5, 7)}` : ''}{e.local ? ` · ${e.local}` : ''}{estado.dados.contas.length > 1 ? ` · ${e.contaEmail}` : ''}</div>
                        {e.descricao && <div className="t-meta">{e.descricao}</div>}
                      </div>
                      {e.podeEditar && !apagando && (
                        <>
                          <button type="button" className="link-btn" aria-label={`Editar ${e.titulo}`} onClick={() => setModo({ editar: e })}>Editar</button>
                          <button type="button" className="link-btn link-danger" aria-label={`Apagar ${e.titulo}`} onClick={() => setModo({ apagar: e })}>Apagar</button>
                        </>
                      )}
                      {apagando && (
                        <div className="quick" role="group" aria-label={`Apagar ${e.titulo}`}>
                          <Botao variante="danger" pequeno carregando={ocupado === 'apagar'} disabled={ocupado !== null} onClick={() => void apagar(e)}>Apagar</Botao>
                          <Botao variante="secondary" pequeno onClick={() => setModo('ver')}>Cancelar</Botao>
                        </div>
                      )}
                    </li>
                  )
                })}
              </ul>
            )}
          </section>
        </div>
      )}
    </>
  )
}
