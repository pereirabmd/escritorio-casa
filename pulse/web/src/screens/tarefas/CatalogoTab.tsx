import { useRef, useState, type FormEvent } from 'react'
import type { TarefaCatalogo, TarefasModulo } from '../../api/types'
import { Botao, Notice } from '../../components/ui'
import { COM_DATA, COM_DIAS, DIAS, DIAS_NOME, RECORRENCIAS } from '../../lib/tarefas'
import { novoCid } from '../../lib/useAcao'
import type { Ferramentas } from './tipos'

interface Form {
  id: string | null; nome: string; categoria: string; recorrencia: string; dias: string[]; data: string; diaMes: string; hora: string
  pessoa: string; prioridade: string; rotacao: string[]; dependeDe: string
}

const CHAVE_CAT = 'pulse.tarefas.ultimaCategoria'
const lerCat = () => { try { return localStorage.getItem(CHAVE_CAT) || '' } catch { return '' } }
const guardarCat = (c: string) => { try { localStorage.setItem(CHAVE_CAT, c) } catch { /* sem armazenamento */ } }

function vazio(d: TarefasModulo): Form {
  const ultima = lerCat()
  return { id: null, nome: '', categoria: d.categorias.includes(ultima) ? ultima : d.categorias[0] ?? '', recorrencia: 'Diaria', dias: [], data: '', diaMes: '1', hora: '08:00',
    pessoa: d.pessoas[0] ?? '', prioridade: 'Media', rotacao: [], dependeDe: '' }
}

function deTarefa(t: TarefaCatalogo, copia = false): Form {
  const ehData = COM_DATA.includes(t.recorrencia)
  return { id: copia ? null : t.id, nome: copia ? `${t.nome} (cópia)` : t.nome, categoria: t.categoria, recorrencia: t.recorrencia, dias: ehData ? [] : t.diasSemana.split(',').filter(Boolean),
    data: ehData ? t.diasSemana : '', diaMes: String(t.diaMes ?? 1), hora: t.horaNotificacao || '08:00', pessoa: t.pessoaPadrao, prioridade: t.prioridade || 'Media',
    rotacao: t.rotacaoPessoas.split(',').filter(Boolean), dependeDe: t.dependeDe }
}

const alterna = (lista: string[], v: string) => (lista.includes(v) ? lista.filter((x) => x !== v) : [...lista, v])

export function CatalogoTab({ dados, f }: { dados: TarefasModulo; f: Ferramentas }) {
  const { executar, ocupado, avisos } = f
  const [form, setForm] = useState<Form | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [pesquisa, setPesquisa] = useState('')
  const [apagar, setApagar] = useState<string | null>(null)
  const [mais, setMais] = useState(false)
  const cid = useRef(novoCid())

  const termo = pesquisa.trim().toLowerCase()
  const lista = termo ? dados.tarefas.filter((t) => [t.nome, t.categoria, t.pessoaPadrao].some((x) => x.toLowerCase().includes(termo))) : dados.tarefas
  const abrir = (fm: Form) => { setForm(fm); setErro(null); setMais(fm.prioridade !== 'Media' || fm.rotacao.length > 0 || fm.dependeDe !== ''); document.getElementById('form-tarefa')?.scrollIntoView?.({ block: 'center' }) }
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setForm((x) => (x ? { ...x, [k]: v } : x))

  async function guardar(ev: FormEvent) {
    ev.preventDefault()
    if (!form) return
    if (!form.nome.trim() || !form.categoria) { setErro('Preenche o nome e a categoria.'); return }
    if (COM_DIAS.includes(form.recorrencia) && form.dias.length === 0) { setErro('Escolhe pelo menos um dia da semana.'); return }
    if (COM_DATA.includes(form.recorrencia) && !form.data) { setErro(form.recorrencia === 'Pontual' ? 'Escolhe a data.' : 'Escolhe a data de início.'); return }
    const dm = Number(form.diaMes)
    if (form.recorrencia === 'Mensal' && !(Number.isInteger(dm) && dm >= 1 && dm <= 31)) { setErro('Dia do mês inválido.'); return }
    setErro(null)
    const base = {
      nome: form.nome.trim(), categoria: form.categoria, recorrencia: form.recorrencia, hora: form.hora, pessoa: form.pessoa, prioridade: form.prioridade,
      rotacao: form.rotacao, dependeDe: form.dependeDe, ...(COM_DIAS.includes(form.recorrencia) ? { dias: form.dias } : {}),
      ...(COM_DATA.includes(form.recorrencia) ? { data: form.data } : {}), ...(form.recorrencia === 'Mensal' ? { diaMes: dm } : {}),
    }
    guardarCat(form.categoria)
    const ok = form.id ? await executar('form', 'tarefas.editar', { ...base, tarefa: form.id }) : await executar('form', 'tarefas.criar', { ...base, cid: cid.current })
    if (ok) { avisos.mostrar(form.id ? 'Tarefa atualizada.' : 'Tarefa criada.'); if (!form.id) cid.current = novoCid(); setForm(null) }
  }

  async function eliminar(t: TarefaCatalogo) {
    if (await executar(`del-${t.id}`, 'tarefas.apagar', { tarefa: t.id }, true)) { setApagar(null); avisos.mostrar('Tarefa apagada.') }
  }

  return (
    <div className="stack">
      <div className="quick">
        <input className="input input-sm grow-input" type="search" aria-label="Pesquisar tarefas" placeholder="Pesquisar por nome, categoria ou pessoa" value={pesquisa} onChange={(e) => setPesquisa(e.target.value)} />
        <Botao pequeno onClick={() => abrir(vazio(dados))}>Nova tarefa</Botao>
      </div>

      {form && (
        <form className="card" id="form-tarefa" noValidate onSubmit={guardar} aria-label={form.id ? 'Editar tarefa' : 'Nova tarefa'}>
          <h2 className="t-card">{form.id ? 'Editar tarefa' : form.nome.endsWith('(cópia)') ? 'Duplicar tarefa' : 'Nova tarefa'}</h2>
          {erro && <Notice tipo="error">{erro}</Notice>}
          <div className="field"><label htmlFor="t-nome">Nome</label><input id="t-nome" className="input" maxLength={200} value={form.nome} onChange={(e) => set('nome', e.target.value)} /></div>
          <div className="field"><span className="lbl">Categoria</span>
            <div className="chips" role="group" aria-label="Categoria">{dados.categorias.map((c) => <button key={c} type="button" className="chip" aria-pressed={form.categoria === c} onClick={() => set('categoria', c)}>{c}</button>)}</div></div>
          <div className="fields">
            <div className="field"><label htmlFor="t-rec">Repetição</label>
              <select id="t-rec" className="input" value={form.recorrencia} onChange={(e) => set('recorrencia', e.target.value)}>{RECORRENCIAS.map(([v, n]) => <option key={v} value={v}>{n}</option>)}</select></div>
            <div className="field"><label htmlFor="t-hora">Hora do aviso</label><input id="t-hora" className="input" type="time" value={form.hora} onChange={(e) => set('hora', e.target.value)} /></div>
          </div>
          {COM_DIAS.includes(form.recorrencia) && (
            <div className="field"><span className="lbl">Dias da semana</span>
              <div className="chips" role="group" aria-label="Dias da semana">{DIAS.map((d) => <button key={d} type="button" className="chip" aria-pressed={form.dias.includes(d)} aria-label={DIAS_NOME[d]} onClick={() => set('dias', alterna(form.dias, d))}>{d}</button>)}</div></div>
          )}
          {form.recorrencia === 'Mensal' && <div className="field"><label htmlFor="t-dm">Dia do mês</label><input id="t-dm" className="input" type="number" min={1} max={31} value={form.diaMes} onChange={(e) => set('diaMes', e.target.value)} /></div>}
          {COM_DATA.includes(form.recorrencia) && <div className="field"><label htmlFor="t-data">{form.recorrencia === 'Pontual' ? 'Data' : 'Data de início'}</label><input id="t-data" className="input" type="date" value={form.data} onChange={(e) => set('data', e.target.value)} /></div>}
          <div className="field"><label htmlFor="t-pessoa">Pessoa</label>
            <select id="t-pessoa" className="input" value={form.pessoa} onChange={(e) => set('pessoa', e.target.value)}>{dados.pessoas.map((p) => <option key={p} value={p}>{p}</option>)}</select></div>
          <button type="button" className="link-btn" aria-expanded={mais} onClick={() => setMais((v) => !v)}>{mais ? '− Menos opções' : '+ Mais opções'}</button>
          {mais && (
            <>
              <div className="field"><span className="lbl">Prioridade</span>
                <div className="chips" role="group" aria-label="Prioridade">{[['Alta', 'Alta'], ['Media', 'Média'], ['Baixa', 'Baixa']].map(([v, n]) => <button key={v} type="button" className="chip" aria-pressed={form.prioridade === v} onClick={() => set('prioridade', v)}>{n}</button>)}</div></div>
              <div className="field"><span className="lbl">Rotação entre pessoas</span>
                <div className="chips" role="group" aria-label="Rotação entre pessoas">{dados.pessoas.map((p) => <button key={p} type="button" className="chip" aria-pressed={form.rotacao.includes(p)} onClick={() => set('rotacao', alterna(form.rotacao, p))}>{p}</button>)}</div></div>
              <div className="field"><label htmlFor="t-dep">Só depois de…</label>
                <select id="t-dep" className="input" value={form.dependeDe} onChange={(e) => set('dependeDe', e.target.value)}>
                  <option value="">— Nenhuma dependência —</option>{dados.tarefas.filter((t) => t.id !== form.id).map((t) => <option key={t.id} value={t.id}>{t.nome}</option>)}</select></div>
            </>
          )}
          <div className="quick">
            <Botao type="submit" carregando={ocupado === 'form'} disabled={ocupado !== null}>Guardar</Botao>
            <Botao type="button" variante="secondary" onClick={() => setForm(null)}>Cancelar</Botao>
          </div>
        </form>
      )}

      <section className="card" aria-label="Lista de tarefas">
        <h2 className="t-card">Tarefas <span className="t-meta">{lista.length}</span></h2>
        {dados.tarefas.length === 0 ? <p className="t-body2">Ainda não há tarefas. Cria a primeira em «Nova tarefa».</p>
          : lista.length === 0 ? <p className="t-body2">Nenhuma tarefa corresponde à pesquisa.</p> : (
            <ul className="rows">{lista.map((t) => (
              <li key={t.id}>
                <div className="row-main"><div className="t-body">{t.nome}</div>
                  <div className="t-meta">{[t.categoria, t.resumo, t.hora, t.pessoaPadrao].filter(Boolean).join(' · ')}{t.prioridade === 'Alta' && <> · <span className="pill pill-soon">Prioridade alta</span></>}</div></div>
                {apagar === t.id ? (
                  <div className="quick" role="group" aria-label={`Apagar ${t.nome}`}>
                    <span className="t-meta">Apagar? O histórico mantém-se; as pendentes desaparecem.</span>
                    <Botao variante="danger" pequeno carregando={ocupado === `del-${t.id}`} disabled={ocupado !== null} onClick={() => void eliminar(t)}>Apagar</Botao>
                    <Botao variante="secondary" pequeno onClick={() => setApagar(null)}>Cancelar</Botao>
                  </div>
                ) : (
                  <>
                    <button type="button" className="link-btn" aria-label={`Duplicar ${t.nome}`} onClick={() => abrir(deTarefa(t, true))}>Duplicar</button>
                    <button type="button" className="link-btn" aria-label={`Editar ${t.nome}`} onClick={() => abrir(deTarefa(t))}>Editar</button>
                    <button type="button" className="link-btn link-danger" aria-label={`Apagar ${t.nome}`} onClick={() => setApagar(t.id)}>Apagar</button>
                  </>
                )}
              </li>
            ))}</ul>
          )}
      </section>
    </div>
  )
}
