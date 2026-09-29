import { useState, type FormEvent } from 'react'
import { api, mensagemDeErro } from '../../api/client'
import type { DefinicoesTarefas, HistoricoTarefas, PainelAdmin } from '../../api/types'
import { useAvisos } from '../../components/Avisos'
import { Botao, BrandLoading, Notice } from '../../components/ui'
import { csvHistorico, isoLocal } from '../../lib/tarefas'
import { useAcao } from '../../lib/useAcao'
import { useAsync } from '../../lib/useAsync'
import type { Ferramentas } from './tipos'

type Def = DefinicoesTarefas

function quandoAuditoria(ts: string): string {
  const d = new Date(ts)
  return Number.isNaN(d.getTime()) ? ts : new Intl.DateTimeFormat('pt-PT', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }).format(d)
}

function Pessoas({ d, f }: { d: Def; f: Ferramentas }) {
  const { executar, ocupado, avisos } = f
  const [nome, setNome] = useState('')
  const [email, setEmail] = useState('')
  const [editar, setEditar] = useState<{ nome: string; novoNome: string; email: string } | null>(null)
  const [remover, setRemover] = useState<{ nome: string; substituto: string } | null>(null)
  const [massa, setMassa] = useState<{ de: string; para: string } | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const nomes = d.pessoas.map((p) => p.nome)

  async function adicionar(ev: FormEvent) {
    ev.preventDefault()
    if (!nome.trim()) { setErro('Escreve um nome.'); return }
    if (nome.includes(',')) { setErro('O nome não pode ter vírgulas.'); return }
    setErro(null)
    if (await executar('pessoa-add', 'tarefas.pessoa_adicionar', { nome: nome.trim(), email: email.trim() })) { setNome(''); setEmail(''); avisos.mostrar('Pessoa adicionada.') }
  }
  async function guardarEdicao() {
    if (!editar) return
    if (!editar.novoNome.trim() || editar.novoNome.includes(',')) { setErro('Indica um nome válido (sem vírgulas).'); return }
    setErro(null)
    if (await executar('pessoa-edit', 'tarefas.pessoa_editar', { nome: editar.nome, novoNome: editar.novoNome.trim(), email: editar.email.trim() })) { setEditar(null); avisos.mostrar('Pessoa atualizada.') }
  }
  async function confirmarRemocao() {
    if (!remover) return
    const params = remover.substituto ? { nome: remover.nome, substituto: remover.substituto } : { nome: remover.nome }
    const r = await executar('pessoa-rem', 'tarefas.pessoa_remover', params, true) as { reatribuidas?: number } | null
    if (r) { setRemover(null); avisos.mostrar(r.reatribuidas ? `Pessoa removida · ${r.reatribuidas} tarefa(s) passada(s) para ${remover.substituto}.` : 'Pessoa removida.') }
  }
  async function confirmarMassa() {
    if (!massa || massa.de === massa.para) { setErro('Escolhe pessoas diferentes.'); return }
    setErro(null)
    if (await executar('massa', 'tarefas.reatribuir', massa, true)) { setMassa(null); avisos.mostrar(`Tarefas por fazer passadas de ${massa.de} para ${massa.para}.`) }
  }
  const outras = (n: string) => nomes.filter((x) => x !== n)

  return (
    <section className="card" aria-label="Pessoas">
      <h2 className="t-card">Pessoas</h2>
      {d.pessoaAtual ? <p className="t-body2">A tua conta corresponde a <b>{d.pessoaAtual}</b> (pelo e-mail); é o que o filtro «Minhas» usa.</p>
        : <p className="t-body2">Associa o teu e-mail a uma pessoa para poderes usar o filtro «Minhas».</p>}
      {erro && <Notice tipo="error">{erro}</Notice>}
      {d.pessoas.length === 0 && <p className="t-body2">Ainda não há pessoas. Adiciona a primeira.</p>}
      <ul className="rows">
        {d.pessoas.map((p) => (
          <li key={p.nome} className={editar?.nome === p.nome || remover?.nome === p.nome ? 'open' : undefined}>
            {editar?.nome === p.nome ? (
              <div className="stack grow" role="group" aria-label={`Editar ${p.nome}`}>
                <div className="field"><label htmlFor="pe-nome">Nome</label><input id="pe-nome" className="input" maxLength={60} value={editar.novoNome} onChange={(e) => setEditar({ ...editar, novoNome: e.target.value })} /></div>
                <div className="field"><label htmlFor="pe-email">E-mail Google</label><input id="pe-email" className="input" type="email" value={editar.email} onChange={(e) => setEditar({ ...editar, email: e.target.value })} /></div>
                <div className="quick">
                  <Botao pequeno carregando={ocupado === 'pessoa-edit'} disabled={ocupado !== null} onClick={() => void guardarEdicao()}>Guardar</Botao>
                  <Botao pequeno variante="secondary" onClick={() => setEditar(null)}>Cancelar</Botao>
                </div>
              </div>
            ) : remover?.nome === p.nome ? (
              <div className="stack grow" role="group" aria-label={`Remover ${p.nome}`}>
                <p className="t-body2">Remover {p.nome}? As tarefas por fazer passam para quem escolheres (se não houver nenhuma, não é preciso).</p>
                <div className="chips" role="group" aria-label="Quem fica responsável">
                  {outras(p.nome).map((n) => <button key={n} type="button" className="chip" aria-pressed={remover.substituto === n} onClick={() => setRemover({ ...remover, substituto: n })}>{n}</button>)}
                </div>
                <div className="quick">
                  <Botao pequeno variante="danger" carregando={ocupado === 'pessoa-rem'} disabled={ocupado !== null} onClick={() => void confirmarRemocao()}>Remover</Botao>
                  <Botao pequeno variante="secondary" onClick={() => setRemover(null)}>Cancelar</Botao>
                </div>
              </div>
            ) : (
              <>
                <div className="row-main"><div className="t-body">{p.nome}</div><div className="t-meta">{p.email || 'sem e-mail definido'}</div></div>
                <button type="button" className="link-btn" aria-label={`Editar ${p.nome}`} onClick={() => { setErro(null); setEditar({ nome: p.nome, novoNome: p.nome, email: p.email }) }}>Editar</button>
                <button type="button" className="link-btn link-danger" aria-label={`Remover ${p.nome}`} disabled={d.pessoas.length <= 1}
                  onClick={() => { setErro(null); setRemover({ nome: p.nome, substituto: outras(p.nome)[0] ?? '' }) }}>Remover</button>
              </>
            )}
          </li>
        ))}
      </ul>
      <form className="stack" onSubmit={adicionar} noValidate aria-label="Nova pessoa">
        <div className="field"><label htmlFor="pn-nome">Adicionar pessoa</label><input id="pn-nome" className="input" maxLength={60} placeholder="Nome" value={nome} onChange={(e) => setNome(e.target.value)} /></div>
        <div className="field"><label htmlFor="pn-email">E-mail Google (opcional, para o filtro «Minhas»)</label><input id="pn-email" className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} /></div>
        <div><Botao type="submit" pequeno carregando={ocupado === 'pessoa-add'} disabled={ocupado !== null}>Adicionar</Botao></div>
      </form>
      {d.pessoas.length > 1 && (
        massa ? (
          <div className="stack" role="group" aria-label="Reatribuir tarefas em massa">
            <p className="t-body2">Passar todas as tarefas por fazer de uma pessoa para outra:</p>
            <div className="fields">
              <div className="field"><label htmlFor="m-de">De</label><select id="m-de" className="input" value={massa.de} onChange={(e) => setMassa({ ...massa, de: e.target.value })}>{nomes.map((n) => <option key={n}>{n}</option>)}</select></div>
              <div className="field"><label htmlFor="m-para">Para</label><select id="m-para" className="input" value={massa.para} onChange={(e) => setMassa({ ...massa, para: e.target.value })}>{nomes.map((n) => <option key={n}>{n}</option>)}</select></div>
            </div>
            <div className="quick">
              <Botao pequeno variante="danger" carregando={ocupado === 'massa'} disabled={ocupado !== null} onClick={() => void confirmarMassa()}>Reatribuir</Botao>
              <Botao pequeno variante="secondary" onClick={() => setMassa(null)}>Cancelar</Botao>
            </div>
          </div>
        ) : <div><Botao pequeno variante="secondary" onClick={() => { setErro(null); setMassa({ de: nomes[0], para: nomes[1] }) }}>Reatribuir tarefas em massa</Botao></div>
      )}
    </section>
  )
}

function NaoIncomodar({ d, f }: { d: Def; f: Ferramentas }) {
  const [ini, setIni] = useState(d.preferencias.naoIncomodarInicio)
  const [fim, setFim] = useState(d.preferencias.naoIncomodarFim)
  const [erro, setErro] = useState<string | null>(null)
  async function guardar() {
    if (!!ini !== !!fim) { setErro('Indica o início e o fim (ou deixa ambos vazios para desligar).'); return }
    setErro(null)
    if (await f.executar('pref', 'tarefas.preferencias', { naoIncomodarInicio: ini, naoIncomodarFim: fim })) f.avisos.mostrar('Preferências guardadas.')
  }
  return (
    <section className="card" aria-label="Não incomodar">
      <h2 className="t-card">Não incomodar</h2>
      <p className="t-meta">Janela horária sem notificações. Deixa vazio para desligar.</p>
      {erro && <Notice tipo="error">{erro}</Notice>}
      <div className="fields">
        <div className="field"><label htmlFor="ni-ini">Início</label><input id="ni-ini" className="input" type="time" value={ini} onChange={(e) => setIni(e.target.value)} /></div>
        <div className="field"><label htmlFor="ni-fim">Fim</label><input id="ni-fim" className="input" type="time" value={fim} onChange={(e) => setFim(e.target.value)} /></div>
      </div>
      <div><Botao pequeno carregando={f.ocupado === 'pref'} disabled={f.ocupado !== null} onClick={() => void guardar()}>Guardar</Botao></div>
    </section>
  )
}

function Resumo({ d }: { d: Def }) {
  const max = Math.max(1, ...d.resumo.pessoas.map((p) => p.feitas))
  return (
    <section className="card" aria-label="Resumo por pessoa">
      <h2 className="t-card">Resumo <span className="t-meta">últimos 7 dias</span></h2>
      {d.resumo.pessoas.length === 0 ? <p className="t-body2">Sem dados ainda.</p> : d.resumo.pessoas.map((p) => (
        <div key={p.nome}>
          <div className="quick" style={{ justifyContent: 'space-between' }}><span className="t-body">{p.nome}</span><span className="t-meta">{p.feitas} tarefa{p.feitas === 1 ? '' : 's'}</span></div>
          <progress className="meter" max={max} value={p.feitas} aria-label={`${p.nome}: ${p.feitas} tarefas`} />
        </div>
      ))}
      {d.resumo.desequilibrio && <Notice tipo="warning" role="status">{d.resumo.desequilibrio} tem feito bastante mais do que os outros esta semana.</Notice>}
    </section>
  )
}

function Sistema({ d, f }: { d: Def; f: Ferramentas }) {
  const [erro, setErro] = useState<string | null>(null)
  const s = d.saude
  async function gerar() {
    const r = await f.executar('gerar', 'tarefas.gerar', {}) as { criadas?: number } | null
    if (r) f.avisos.mostrar(`Tarefas atualizadas (${r.criadas ?? 0} nova${r.criadas === 1 ? '' : 's'}).`)
  }
  async function exportar() {
    setErro(null)
    try {
      const h = await api.get<HistoricoTarefas>('/tasks/history')
      if (h.linhas.length === 0) { f.avisos.mostrar('Sem histórico para exportar.'); return }
      const url = URL.createObjectURL(new Blob([csvHistorico(h.linhas)], { type: 'text/csv;charset=utf-8;' }))
      const a = document.createElement('a')
      a.href = url; a.download = `tarefas-historico-${isoLocal(new Date())}.csv`; a.click()
      URL.revokeObjectURL(url)
      f.avisos.mostrar('Histórico exportado.')
    } catch (e) { setErro(mensagemDeErro(e)) }
  }
  const c = s?.contagens ?? {}
  return (
    <section className="card" aria-label="Sistema">
      <h2 className="t-card">Sistema</h2>
      {erro && <Notice tipo="error">{erro}</Notice>}
      {s === null ? <p className="t-body2">Não foi possível verificar o estado do Pi.</p>
        : !s.ultimaExecucao ? <Notice tipo="warning">A reconciliação dos avisos no Pi ainda não correu nenhuma vez.</Notice>
        : (
          <>
            <p className="t-body2"><span className={`pill ${s.saudavel ? 'pill-ok' : 'pill-soon'}`}>{s.saudavel ? 'Em dia' : 'Atrasada'}</span> Última reconciliação dos avisos no Pi: há {s.minutosDesde} min.</p>
            <p className="t-meta">Mensagens ntfy: {c.sem_alteracao ?? 0} agendadas em dia · {c.agendado ?? 0} novas · {c.reagendado ?? 0} reagendadas · {c.cancelado ?? 0} canceladas · {c.fora_do_horizonte ?? 0} para depois (fora dos 3 dias)</p>
          </>
        )}
      <div className="quick">
        <Botao pequeno variante="secondary" carregando={f.ocupado === 'gerar'} disabled={f.ocupado !== null} onClick={() => void gerar()}>Atualizar tarefas agora</Botao>
        <Botao pequeno variante="secondary" onClick={() => void exportar()}>Exportar histórico (CSV)</Botao>
      </div>
      <p className="t-meta">As notificações por pessoa (utilizador e palavra-passe do ntfy) configuram-se na app dedicada das Tarefas; o Pulse terá as suas próprias (ADR-032).</p>
    </section>
  )
}

function Auditoria({ d }: { d: Def }) {
  return (
    <section className="card" aria-label="Últimas ações">
      <h2 className="t-card">Últimas ações</h2>
      {d.auditoria.length === 0 ? <p className="t-body2">Ainda não há registos.</p>
        : <ul className="rows">{d.auditoria.map((r, k) => <li key={k}><span className="row-main t-meta">{quandoAuditoria(r.ts)} · {r.tarefa || r.acao} · {r.pessoa}</span></li>)}</ul>}
    </section>
  )
}

function Admin({ p, f }: { p: PainelAdmin; f: Ferramentas }) {
  const [admins, setAdmins] = useState<string[]>(p.admins.filter((e) => !p.raiz.includes(e)))
  const [notifs, setNotifs] = useState<Record<string, string[]>>(() => Object.fromEntries(p.notificacoes.map((n) => [n.id, n.destinatarios])))
  const [confirmar, setConfirmar] = useState(false)
  const alterna = (l: string[], v: string) => (l.includes(v) ? l.filter((x) => x !== v) : [...l, v])
  async function guardar() {
    if (await f.executar('admin', 'tarefas.admin', { admins, notificacoes: notifs }, true)) { setConfirmar(false); f.avisos.mostrar('Guardado. Os avisos agendados ajustam-se em poucos minutos.') }
  }
  return (
    <section className="card" aria-label="Administração">
      <h2 className="t-card">Administração</h2>
      <fieldset className="stack">
        <legend className="t-body">Administradores</legend>
        <p className="t-meta">Só se pode escolher pessoas com e-mail registado.</p>
        {p.pessoas.map((x) => (
          <label className="switch" key={x.nome}>
            <input type="checkbox" checked={x.fixo || admins.includes(x.email)} disabled={x.fixo || !x.email} onChange={() => setAdmins(alterna(admins, x.email))} />
            <span>{x.nome} <span className="t-meta">{x.fixo ? 'administrador fixo' : x.email || 'sem e-mail'}</span></span>
          </label>
        ))}
      </fieldset>
      {p.notificacoes.map((n) => (
        <fieldset className="stack" key={n.id}>
          <legend className="t-body">Notificações: {n.nome}{n.padrao && <span className="t-meta"> (predefinição)</span>}</legend>
          <p className="t-meta">{n.descricao}</p>
          {p.pessoas.map((x) => (
            <label className="switch" key={x.nome}>
              <input type="checkbox" checked={(notifs[n.id] ?? []).includes(x.nome)} onChange={() => setNotifs({ ...notifs, [n.id]: alterna(notifs[n.id] ?? [], x.nome) })} />
              <span>{x.nome}</span>
            </label>
          ))}
        </fieldset>
      ))}
      {confirmar ? (
        <div className="quick" role="group" aria-label="Confirmar alterações">
          <span className="t-meta">Mudar quem administra e quem recebe os avisos gerais?</span>
          <Botao pequeno carregando={f.ocupado === 'admin'} disabled={f.ocupado !== null} onClick={() => void guardar()}>Confirmar</Botao>
          <Botao pequeno variante="secondary" onClick={() => setConfirmar(false)}>Cancelar</Botao>
        </div>
      ) : <div><Botao pequeno onClick={() => setConfirmar(true)}>Guardar administração</Botao></div>}
    </section>
  )
}

export function ConfigTab({ atualizar }: { atualizar: () => void }) {
  const [estado, recarregar] = useAsync(() => api.get<Def>('/tasks/settings'))
  const { ocupado, erro, executar, limparErro } = useAcao(() => { recarregar(); atualizar() })
  const avisos = useAvisos()
  if (estado.fase === 'a-carregar') return <BrandLoading texto="A carregar a configuração…" />
  if (estado.fase === 'erro') return <div className="state"><Notice tipo="error">{mensagemDeErro(estado.erro)}</Notice><Botao variante="secondary" pequeno onClick={recarregar}>Tentar de novo</Botao></div>
  const d = estado.dados
  const f: Ferramentas = { executar, ocupado, avisos }
  return (
    <div className="stack">
      {erro && <Notice tipo="error">{erro} <button type="button" className="link-btn" onClick={limparErro}>Fechar</button></Notice>}
      <Pessoas d={d} f={f} />
      <NaoIncomodar key={`${d.preferencias.naoIncomodarInicio}|${d.preferencias.naoIncomodarFim}`} d={d} f={f} />
      <Resumo d={d} />
      <Sistema d={d} f={f} />
      <Auditoria d={d} />
      {d.souAdmin && d.admin && <Admin key={JSON.stringify(d.admin)} p={d.admin} f={f} />}
    </div>
  )
}
