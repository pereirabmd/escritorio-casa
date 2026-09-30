import { useEffect, useState, type FormEvent } from 'react'
import { api } from '../../api/client'
import type { BilhetesModulo, ViagemBilhetes } from '../../api/types'
import { Icon } from '../../components/Icon'
import { Botao, Notice } from '../../components/ui'
import { diaCurto, diaMes, diasParaEditor, ESTADO_VIAGEM, intervaloSemana, linhaVazia, somarDias, validarDias, viagensParaEnviar, type DiaEditor } from '../../lib/bilhetes'
import { fmtDias, plural } from '../../lib/format'
import type { Ferramentas } from './tipos'

function Passe({ dados, f }: { dados: BilhetesModulo; f: Ferramentas }) {
  const p = dados.passe
  const [editar, setEditar] = useState(false)
  const [data, setData] = useState(p.dataUltimaCompra ?? dados.hoje)
  const dias = p.diasRestantes
  const texto = p.estado === 'sem_data' ? 'Indica a data do último carregamento para receberes o aviso antes de expirar.'
    : dias! < 0 ? `Expirou a ${diaMes(p.dataExpira!)}` : dias === 0 ? 'Expira hoje' : `Válido até ${diaMes(p.dataExpira!)} (${fmtDias(dias!)})`

  async function guardar(ev: FormEvent) {
    ev.preventDefault()
    if (!data || data > somarDias(dados.hoje, 1)) return
    if (await f.executar('passe', 'bilhetes.passe', { dataUltimaCompra: data })) { setEditar(false); f.avisos.mostrar('Passe atualizado.') }
  }
  return (
    <section className="card" aria-label="Passe Verde">
      <div className="split"><h2 className="t-card">Passe Verde</h2>{dias !== null && <span className="t-meta">{plural(Math.max(dias, 0), 'dia', 'dias')}</span>}</div>
      {p.percentagem !== null && <progress className="meter" max={100} value={p.percentagem} aria-label={texto} />}
      <p className={p.estado === 'expirado' || p.estado === 'a_expirar' ? 't-body2 link-danger' : 't-body2'}>{texto}{p.estado === 'a_expirar' ? ' Renova na App CP e atualiza a data aqui.' : ''}</p>
      {editar ? (
        <form className="quick" onSubmit={guardar} aria-label="Atualizar passe">
          <label className="sr-only" htmlFor="passe-data">Data do último carregamento</label>
          <input id="passe-data" type="date" className="input input-sm" max={somarDias(dados.hoje, 1)} value={data} onChange={(e) => setData(e.target.value)} />
          <Botao type="submit" pequeno carregando={f.ocupado === 'passe'} disabled={!data || data > somarDias(dados.hoje, 1) || f.ocupado !== null}>Guardar</Botao>
          <Botao type="button" variante="secondary" pequeno onClick={() => setEditar(false)}>Cancelar</Botao>
        </form>
      ) : <div><Botao variante="secondary" pequeno onClick={() => setEditar(true)}>Atualizar carregamento</Botao></div>}
    </section>
  )
}

function Estado({ v }: { v: ViagemBilhetes }) {
  const e = ESTADO_VIAGEM[v.estado]
  return <span className={`pill ${e.classe}`.trim()}>{e.texto}{v.estado === 'em_curso' ? ` · chega por volta das ${v.fimEstimado}` : ''}</span>
}

function Proxima({ v }: { v: ViagemBilhetes }) {
  return (
    <section className="card" aria-label="Próximo comboio">
      <h2 className="t-card">{v.estado === 'em_curso' ? 'Em viagem' : 'Próximo comboio'}</h2>
      <div className="trip"><span className="t-section">{v.hora}</span><span className="t-body">{v.origem}</span><span className="arrow"><span className="sr-only">para</span><Icon nome="seta" tamanho={16} /></span><span className="t-body">{v.destino}</span></div>
      <div className="trip t-body2"><span>{diaCurto(v.data)}</span><span>Comboio {v.comboio}</span><Estado v={v} /></div>
      {v.compra && <div className="t-body2">Carruagem {v.compra.carruagem}, lugar {v.compra.lugar}{v.compra.referencia ? ` · ref. ${v.compra.referencia}` : ''}</div>}
    </section>
  )
}

interface ResultadoCp { estado: 'desligado' | 'confirmado' | 'preenchido' | 'aviso' | 'sem_informacao'; mensagem: string; sugestaoHora?: string }

/** Confere na CP (pelo servidor: as chaves nunca vão para o telemóvel) o comboio, a data, o percurso e a hora. Consultivo: nunca impede de guardar (ADR-068). */
function VerificacaoCp({ data, origem, destino, comboio, hora, aoUsarHora }: { data: string; origem: string; destino: string; comboio: string; hora: string; aoUsarHora: (h: string) => void }) {
  const [res, setRes] = useState<{ chave: string; r: ResultadoCp } | null>(null)
  const n = Number(comboio)
  const pronto = /^\d{1,5}$/.test(comboio.trim()) && n > 0 && !!origem && !!destino && origem !== destino
  const chave = `${data}|${origem}|${destino}|${comboio.trim()}|${hora}`
  useEffect(() => {
    if (!pronto) return
    let vivo = true
    const t = window.setTimeout(() => {
      const q = new URLSearchParams({ comboio: String(n), data, origem, destino, ...(hora ? { hora } : {}) })
      api.get<ResultadoCp>(`/tickets/timetable?${q}`).then((r) => {
        if (!vivo) return
        setRes({ chave, r })
        if (r.estado === 'preenchido' && r.sugestaoHora && !hora) aoUsarHora(r.sugestaoHora)         // hora em falta: preenche-se com a da CP
      }, () => { if (vivo) setRes(null) })
    }, 450)
    return () => { vivo = false; window.clearTimeout(t) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chave, pronto])
  if (!pronto || !res || res.chave !== chave || res.r.estado === 'desligado') return null
  const { estado, mensagem, sugestaoHora } = res.r
  if (estado === 'aviso') {
    return (
      <Notice tipo="warning" role="alert">
        <strong>Verifica na CP:</strong> {mensagem}
        {sugestaoHora && sugestaoHora !== hora && <> <button type="button" className="link-btn" onClick={() => aoUsarHora(sugestaoHora)}>Usar {sugestaoHora}</button></>}
      </Notice>
    )
  }
  return <p className="t-meta" data-cp={estado} role="status">{estado === 'sem_informacao' ? mensagem : `${estado === 'confirmado' ? '✓ ' : ''}${mensagem}`}</p>
}

interface EditorProps { dados: BilhetesModulo; f: Ferramentas; fechar: () => void }

function Editor({ dados, f, fechar }: EditorProps) {
  const { semana, estacoes, historico, hoje } = dados
  const [dias, setDias] = useState<DiaEditor[]>(() => diasParaEditor(semana.dias, semana.viagens, hoje))
  const [erros, setErros] = useState<string[][]>([])
  const mudar = (i: number, alterar: (d: DiaEditor) => DiaEditor) => setDias((atual) => atual.map((d, k) => (k === i ? alterar(d) : d)))
  const [origemPadrao, destinoPadrao] = [estacoes[0] ?? '', estacoes[1] ?? '']

  async function guardar() {
    const e = validarDias(dias)
    setErros(e)
    if (e.some((x) => x.length)) return
    const anteriores = semana.viagens.map((v) => ({ data: v.data, origem: v.origem, destino: v.destino, comboio: v.comboio, hora: v.hora, ativo: v.ativo }))
    const r = await f.executar('semana', 'bilhetes.semana', { inicio: semana.inicio, viagens: viagensParaEnviar(dias) })
    if (r) {
      fechar()
      f.avisos.mostrar('Semana guardada. O Pi vai ler a nova configuração.', () => void f.executar('desfazer', 'bilhetes.semana', { inicio: semana.inicio, viagens: (r.anteriores as typeof anteriores | undefined) ?? anteriores }))
    }
  }

  return (
    <section className="card stack" aria-label="Configurar semana">
      <h2 className="t-card">Configurar {intervaloSemana(semana.inicio)}</h2>
      <p className="t-meta">A compra automática faz-se no dia anterior, à hora da viagem. Os dias que já passaram não se alteram.</p>
      {dias.map((d, i) => (
        <fieldset className="stack" key={d.data} disabled={d.passado} aria-label={diaCurto(d.data)}>
          <div className="split">
            <legend className="t-body">{diaCurto(d.data)}{d.passado ? ' · passou' : ''}</legend>
            {d.viagens.length > 0 && <label className="check-line"><input type="checkbox" checked={d.ativo} onChange={(e) => mudar(i, (x) => ({ ...x, ativo: e.target.checked }))} /> Ativo</label>}
          </div>
          {d.viagens.map((v, k) => {
            const campo = (nome: string) => `${d.data}-${k}-${nome}`
            const atual = (alterar: Partial<typeof v>) => mudar(i, (x) => ({ ...x, viagens: x.viagens.map((y, j) => (j === k ? { ...y, ...alterar } : y)) }))
            const opcoes = (sel: string) => (sel && !estacoes.includes(sel) ? [...estacoes, sel] : estacoes)
            return (
              <div className="stack" key={k} role="group" aria-label={`${diaCurto(d.data)}, viagem ${k + 1}`}>
                {historico.length > 0 && !d.passado && (
                  <select className="input input-sm" aria-label={`Comboios que já usei (viagem ${k + 1} de ${diaCurto(d.data)})`} value=""
                    onChange={(e) => { const h = historico[Number(e.target.value)]; if (h) atual({ origem: h.origem, destino: h.destino, comboio: String(h.comboio), hora: h.hora }) }}>
                    <option value="">Comboios que já usei…</option>
                    {historico.map((h, n) => <option key={n} value={n}>{h.comboio} — {h.origem} → {h.destino} ({h.hora})</option>)}
                  </select>
                )}
                <div className="quick">
                  <label className="sr-only" htmlFor={campo('o')}>Origem</label>
                  <select id={campo('o')} className="input input-sm" value={v.origem} onChange={(e) => atual({ origem: e.target.value })}><option value="">Origem…</option>{opcoes(v.origem).map((s) => <option key={s}>{s}</option>)}</select>
                  <label className="sr-only" htmlFor={campo('d')}>Destino</label>
                  <select id={campo('d')} className="input input-sm" value={v.destino} onChange={(e) => atual({ destino: e.target.value })}><option value="">Destino…</option>{opcoes(v.destino).map((s) => <option key={s}>{s}</option>)}</select>
                </div>
                <div className="quick">
                  <label className="sr-only" htmlFor={campo('c')}>Comboio</label>
                  <input id={campo('c')} className="input input-sm peso-input" inputMode="numeric" placeholder="Comboio" value={v.comboio} onChange={(e) => atual({ comboio: e.target.value })} />
                  <label className="sr-only" htmlFor={campo('h')}>Hora de partida</label>
                  <input id={campo('h')} type="time" className="input input-sm" value={v.hora} onChange={(e) => atual({ hora: e.target.value })} />
                  <button type="button" className="link-btn link-danger" aria-label={`Remover viagem ${k + 1} de ${diaCurto(d.data)}`} onClick={() => mudar(i, (x) => ({ ...x, viagens: x.viagens.filter((_, j) => j !== k) }))}>Remover</button>
                </div>
                {!d.passado && <VerificacaoCp data={d.data} origem={v.origem} destino={v.destino} comboio={v.comboio} hora={v.hora} aoUsarHora={(h) => atual({ hora: h })} />}
              </div>
            )
          })}
          {!d.passado && <div><button type="button" className="link-btn" onClick={() => mudar(i, (x) => ({ ...x, viagens: [...x.viagens, linhaVazia(origemPadrao, destinoPadrao)] }))}>Adicionar viagem a {diaCurto(d.data)}</button></div>}
          {erros[i]?.length > 0 && <Notice tipo="error">{erros[i].map((e) => <div key={e}>{e}</div>)}</Notice>}
        </fieldset>
      ))}
      <div className="quick">
        <Botao pequeno carregando={f.ocupado === 'semana'} disabled={f.ocupado !== null} onClick={() => void guardar()}>Guardar semana</Botao>
        <Botao variante="secondary" pequeno onClick={fechar}>Cancelar</Botao>
      </div>
    </section>
  )
}

interface Props { dados: BilhetesModulo; irParaSemana: (segunda: string) => void; f: Ferramentas }

export function SemanaTab({ dados, irParaSemana, f }: Props) {
  const [editar, setEditar] = useState(false)
  const { semana, semanaSeguinte } = dados
  const ativas = semana.viagens.filter((v) => v.ativo).length
  return (
    <div className="stack">
      {semanaSeguinte.ativas === 0 && <Notice tipo="warning">Falta configurar a semana de {intervaloSemana(semanaSeguinte.inicio)}. <button type="button" className="link-btn" onClick={() => { irParaSemana(semanaSeguinte.inicio); setEditar(true) }}>Configurar</button></Notice>}
      {dados.proxima && <Proxima v={dados.proxima} />}
      <Passe dados={dados} f={f} />

      <div className="cal-head">
        <button type="button" className="icon-round" aria-label="Semana anterior" onClick={() => { setEditar(false); irParaSemana(somarDias(semana.inicio, -7)) }}><Icon nome="voltar" tamanho={20} /></button>
        <h2 className="t-card grow" style={{ textAlign: 'center' }}>{intervaloSemana(semana.inicio)}</h2>
        <button type="button" className="icon-round" aria-label="Semana seguinte" onClick={() => { setEditar(false); irParaSemana(somarDias(semana.inicio, 7)) }}><Icon nome="seta" tamanho={20} /></button>
      </div>

      {editar ? <Editor key={semana.inicio} dados={dados} f={f} fechar={() => setEditar(false)} /> : (
        <section className="card" aria-label="Viagens da semana">
          <div className="split"><h2 className="t-card">Viagens <span className="t-meta">{ativas} ativas</span></h2><Botao pequeno variante="secondary" onClick={() => setEditar(true)}>Configurar semana</Botao></div>
          {semana.viagens.length === 0 ? <p className="t-body2">Sem viagens nesta semana.</p> : (
            <ul className="rows">
              {semana.viagens.map((v) => (
                <li key={v.id} data-estado={v.ativo ? undefined : 'Saltada'}>
                  <div className="row-main">
                    <div className="t-body">{diaCurto(v.data)} · {v.hora} <Estado v={v} /></div>
                    <div className="t-meta">{v.origem} → {v.destino} · comboio {v.comboio}{v.compra ? ` · carruagem ${v.compra.carruagem}, lugar ${v.compra.lugar}` : ''}</div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  )
}
