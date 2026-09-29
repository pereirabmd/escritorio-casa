import { useState, type FormEvent } from 'react'
import { api, mensagemDeErro } from '../../api/client'
import type { LembreteFin } from '../../api/types'
import { BrandLoading, Botao, Notice } from '../../components/ui'
import { fmtDataIso } from '../../lib/format'
import { useAsync } from '../../lib/useAsync'
import type { Ferramentas } from './tipos'

function Linha({ l, f, atualizar }: { l: LembreteFin; f: Ferramentas; atualizar: () => void }) {
  const { executar, ocupado, avisos } = f
  const [apagar, setApagar] = useState(false)
  async function alternar() {
    if (await executar(`lem-${l.id}`, 'financas.lembrete_editar', { lembrete: l.id, ativo: !l.ativo })) { atualizar(); avisos.mostrar(l.ativo ? 'Lembrete pausado.' : 'Lembrete reativado.') }
  }
  async function eliminar() {
    if (await executar(`lem-${l.id}`, 'financas.lembrete_eliminar', { lembrete: l.id }, true)) {
      atualizar()
      avisos.mostrar('Lembrete apagado.', () => void executar('desfazer', 'financas.lembrete_criar', { titulo: l.titulo, nota: l.nota, data: l.data, hora: l.hora, repeticao: l.repeticao }).then(atualizar))
    }
  }
  return (
    <li data-estado={l.ativo ? undefined : 'Saltada'}>
      <div className="row-main">
        <div className="t-body">{l.titulo}</div>
        <div className="t-meta">{fmtDataIso(l.data)} às {l.hora} · {l.repeticao === 'mensal' ? 'todos os meses' : 'uma vez'}{l.ativo ? '' : ' · pausado'}{l.nota ? ` · ${l.nota}` : ''}</div>
      </div>
      <button type="button" className="link-btn" disabled={ocupado !== null} aria-label={`${l.ativo ? 'Pausar' : 'Reativar'} ${l.titulo}`} onClick={() => void alternar()}>{l.ativo ? 'Pausar' : 'Reativar'}</button>
      {apagar ? (
        <div className="quick" role="group" aria-label={`Apagar ${l.titulo}`}>
          <Botao variante="danger" pequeno carregando={ocupado === `lem-${l.id}`} disabled={ocupado !== null} onClick={() => void eliminar()}>Apagar</Botao>
          <Botao variante="secondary" pequeno onClick={() => setApagar(false)}>Cancelar</Botao>
        </div>
      ) : <button type="button" className="link-btn link-danger" aria-label={`Apagar ${l.titulo}`} onClick={() => setApagar(true)}>Apagar</button>}
    </li>
  )
}

export function LembretesTab(f: Ferramentas) {
  const [estado, recarregar] = useAsync(() => api.get<{ lembretes: LembreteFin[] }>('/finance/reminders'))
  const [titulo, setTitulo] = useState('')
  const [nota, setNota] = useState('')
  const [data, setData] = useState('')
  const [hora, setHora] = useState('09:00')
  const [repeticao, setRepeticao] = useState<'unica' | 'mensal'>('unica')
  const ok = titulo.trim() !== '' && data !== '' && /^\d{2}:\d{2}$/.test(hora)

  async function criar(ev: FormEvent) {
    ev.preventDefault()
    if (!ok) return
    if (await f.executar('novo-lem', 'financas.lembrete_criar', { titulo: titulo.trim(), nota: nota.trim(), data, hora, repeticao })) {
      setTitulo(''); setNota(''); recarregar(); f.avisos.mostrar('Lembrete agendado.')
    }
  }
  return (
    <div className="stack">
      <form className="card stack" onSubmit={criar} noValidate aria-label="Novo lembrete">
        <h2 className="t-card">Novo lembrete</h2>
        <p className="t-meta">Chega como notificação (ntfy), depois da hora marcada.</p>
        <div className="field"><label htmlFor="lem-t">Título</label><input id="lem-t" className="input" maxLength={100} value={titulo} onChange={(e) => setTitulo(e.target.value)} /></div>
        <div className="field"><label htmlFor="lem-n">Nota (opcional)</label><input id="lem-n" className="input" maxLength={300} value={nota} onChange={(e) => setNota(e.target.value)} /></div>
        <div className="quick">
          <div className="field"><label htmlFor="lem-d">Data</label><input id="lem-d" type="date" className="input" value={data} onChange={(e) => setData(e.target.value)} /></div>
          <div className="field"><label htmlFor="lem-h">Hora</label><input id="lem-h" type="time" className="input" value={hora} onChange={(e) => setHora(e.target.value)} /></div>
        </div>
        <div className="chips" role="group" aria-label="Repetição">
          <button type="button" className="chip" aria-pressed={repeticao === 'unica'} onClick={() => setRepeticao('unica')}>Uma vez</button>
          <button type="button" className="chip" aria-pressed={repeticao === 'mensal'} onClick={() => setRepeticao('mensal')}>Todos os meses</button>
        </div>
        <div><Botao type="submit" pequeno carregando={f.ocupado === 'novo-lem'} disabled={!ok || f.ocupado !== null}>Agendar</Botao></div>
      </form>
      {estado.fase === 'a-carregar' && <BrandLoading texto="A carregar os lembretes…" />}
      {estado.fase === 'erro' && <Notice tipo="error">{mensagemDeErro(estado.erro)} <button type="button" className="link-btn" onClick={recarregar}>Tentar de novo</button></Notice>}
      {estado.fase === 'pronto' && (
        <section className="card" aria-label="Lembretes"><h2 className="t-card">Lembretes <span className="t-meta">{estado.dados.lembretes.length}</span></h2>
          {estado.dados.lembretes.length === 0 ? <p className="t-body2">Sem lembretes agendados.</p>
            : <ul className="rows">{estado.dados.lembretes.map((l) => <Linha key={l.id} l={l} f={f} atualizar={recarregar} />)}</ul>}</section>
      )}
    </div>
  )
}
