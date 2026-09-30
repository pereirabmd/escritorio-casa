import { useState, type FormEvent } from 'react'
import type { ComprasModulo, ItemCompras, SugestaoCompras } from '../../api/types'
import { Icon } from '../../components/Icon'
import { ShopIcon } from '../../components/ShopIcon'
import { Botao } from '../../components/ui'
import { useFechadas } from '../../lib/recolher'
import type { Ferramentas } from './tipos'

const paraRestaurar = (i: ItemCompras) => ({ produto: i.produto, quantidade: i.quantidade, nota: i.nota, estado: i.estado })

function Linha({ i, dados, f, partilhada }: { i: ItemCompras; dados: ComprasModulo; f: Ferramentas; partilhada: boolean }) {
  const { executar, ocupado, avisos } = f
  const [aberto, setAberto] = useState(false)
  const [quantidade, setQuantidade] = useState(i.quantidade === null ? '' : String(i.quantidade))
  const [nota, setNota] = useState(i.nota)
  const feito = i.estado === 'comprado'
  const n = Number(quantidade)
  const quantidadeOk = quantidade === '' || (/^\d{1,3}$/.test(quantidade) && n >= 1)
  const outras = dados.listas.filter((l) => l.id !== i.lista)

  async function marcar() {
    if (await executar(`c-${i.id}`, 'compras.comprado', { item: i.id, comprado: !feito }) && !feito) avisos.mostrar(`${i.nome} comprado.`, () => void executar('desfazer', 'compras.comprado', { item: i.id, comprado: false }))
  }
  async function guardar(ev: FormEvent) {
    ev.preventDefault()
    if (!quantidadeOk) return
    if (await executar(`d-${i.id}`, 'compras.detalhes', { item: i.id, quantidade: quantidade === '' ? null : n, nota: nota.trim() })) { setAberto(false); avisos.mostrar('Detalhes guardados.') }
  }
  async function remover() {
    const r = await executar(`r-${i.id}`, 'compras.remover', { item: i.id })
    if (r) avisos.mostrar(`${i.nome} removido.`, () => void executar('desfazer', 'compras.restaurar', { lista: i.lista, itens: [paraRestaurar(r as unknown as ItemCompras)] }))
  }
  async function mover(lista: number) {
    if (await executar(`m-${i.id}`, 'compras.mover', { item: i.id, lista })) avisos.mostrar(`${i.nome} passou para ${dados.listas.find((l) => l.id === lista)?.nome ?? 'a outra lista'}.`)
  }

  return (
    <li className={aberto ? 'open' : undefined} data-estado={feito ? 'Saltada' : undefined}>
      <button type="button" className="check" data-done={feito} aria-pressed={feito} disabled={ocupado !== null}
        aria-label={`${feito ? 'Voltar a pôr por comprar' : 'Marcar como comprado'}: ${i.nome}`} onClick={() => void marcar()}>
        <Icon nome="certo" tamanho={16} />
      </button>
      <span className="item-icon"><ShopIcon nome={i.icone} tamanho={24} /></span>
      <div className="row-main">
        <div className={`t-body${feito ? ' struck' : ''}`}>{i.nome}{i.quantidade !== null && <span className="pill"> {i.quantidade}×</span>}</div>
        {(i.nota || (partilhada && i.adicionadoPor)) && <div className="t-meta">{[i.nota, partilhada && i.adicionadoPor ? `por ${i.adicionadoPor.split('@')[0]}` : ''].filter(Boolean).join(' · ')}</div>}
      </div>
      <button type="button" className="link-btn" aria-expanded={aberto} aria-label={`Detalhes de ${i.nome}`} onClick={() => setAberto((v) => !v)}>Detalhes</button>
      {aberto && (
        <form className="adiar stack" onSubmit={guardar} noValidate aria-label={`Detalhes de ${i.nome}`}>
          <div className="quick">
            <div className="field"><label htmlFor={`q-${i.id}`}>Quantidade (opcional)</label>
              <input id={`q-${i.id}`} className="input input-sm peso-input" inputMode="numeric" value={quantidade} onChange={(e) => setQuantidade(e.target.value)} aria-invalid={!quantidadeOk ? true : undefined} /></div>
            <div className="field grow-input"><label htmlFor={`n-${i.id}`}>Nota</label>
              <input id={`n-${i.id}`} className="input input-sm" maxLength={80} placeholder="ex.: 1 L, marca X" value={nota} onChange={(e) => setNota(e.target.value)} /></div>
          </div>
          <div className="quick">
            <Botao type="submit" pequeno carregando={ocupado === `d-${i.id}`} disabled={!quantidadeOk || ocupado !== null}>Guardar</Botao>
            {outras.length > 0 && (
              <select className="input input-sm" aria-label={`Passar ${i.nome} para outra lista`} value="" onChange={(e) => void mover(Number(e.target.value))} disabled={ocupado !== null}>
                <option value="">Passar para…</option>{outras.map((l) => <option key={l.id} value={l.id}>{l.nome}</option>)}
              </select>
            )}
            <button type="button" className="link-btn link-danger" disabled={ocupado !== null} aria-label={`Remover ${i.nome} da lista`} onClick={() => void remover()}>Remover</button>
          </div>
        </form>
      )}
    </li>
  )
}

function Sugestoes({ dados, f }: { dados: ComprasModulo; f: Ferramentas }) {
  const { executar, ocupado, avisos } = f
  const { acabar, frequentes } = dados.sugestoes
  if (acabar.length + frequentes.length === 0) return null

  async function adicionar(s: SugestaoCompras) {
    if (await executar(`s-${s.produto}`, 'compras.adicionar', { lista: dados.lista.id, produto: s.produto })) avisos.mostrar(`${s.nome} na lista.`)
  }
  async function naoSugerir(s: SugestaoCompras) {
    if (await executar(`i-${s.produto}`, 'compras.sugestao_ignorar', { produto: s.produto, valor: true }))
      avisos.mostrar(`Deixámos de sugerir ${s.nome}.`, () => void executar('desfazer', 'compras.sugestao_ignorar', { produto: s.produto, valor: false }))
  }
  const linha = (s: SugestaoCompras, texto: string) => (
    <li key={s.produto}>
      <span className="item-icon"><ShopIcon nome={s.icone} tamanho={24} /></span>
      <div className="row-main"><div className="t-body">{s.nome}</div><div className="t-meta">{texto}</div></div>
      <button type="button" className="link-btn" disabled={ocupado !== null} aria-label={`Adicionar ${s.nome} à lista`} onClick={() => void adicionar(s)}>Adicionar</button>
      <button type="button" className="link-btn" disabled={ocupado !== null} aria-label={`Não sugerir ${s.nome}`} onClick={() => void naoSugerir(s)}>Não sugerir</button>
    </li>
  )
  const vezes = (n: number) => `${n} ${n === 1 ? 'vez' : 'vezes'}`
  return (
    <section className="card stack" aria-label="Sugestões">
      <h2 className="t-card">Sugestões</h2>
      <p className="t-meta">Calculadas do que costumas comprar. Ignora à vontade: nada é adicionado sozinho.</p>
      {acabar.length > 0 && (
        <div>
          <h3 className="t-body">Talvez esteja a acabar</h3>
          <ul className="rows">{acabar.map((s) => linha(s, `Costumas comprar de ${s.intervaloDias} em ${s.intervaloDias} dias · última compra há ${s.diasDesde} dias`))}</ul>
        </div>
      )}
      {frequentes.length > 0 && (
        <div>
          <h3 className="t-body">Costumas comprar</h3>
          <ul className="rows">{frequentes.map((s) => linha(s, `${vezes(s.compras)} nos últimos 90 dias · última há ${s.diasDesde} ${s.diasDesde === 1 ? 'dia' : 'dias'}`))}</ul>
        </div>
      )}
    </section>
  )
}

interface Props { dados: ComprasModulo; f: Ferramentas; abrirCatalogo: () => void; gerir: boolean; setGerir: (v: boolean) => void; aoApagarLista: () => void }

function GerirLista({ dados, f, aoApagarLista }: { dados: ComprasModulo; f: Ferramentas; aoApagarLista: () => void }) {
  const { executar, ocupado, avisos } = f
  const l = dados.lista
  const [nome, setNome] = useState(l.nome)
  const [apagar, setApagar] = useState(false)
  async function renomear(ev: FormEvent) {
    ev.preventDefault()
    if (nome.trim() && nome.trim() !== l.nome && await executar('lista-nome', 'compras.lista_editar', { lista: l.id, nome: nome.trim() })) avisos.mostrar('Lista renomeada.')
  }
  async function eliminar() {
    if (await executar('lista-apagar', 'compras.lista_apagar', { lista: l.id }, true)) { aoApagarLista(); avisos.mostrar('Lista apagada.') }
  }
  return (
    <section className="card stack" aria-label={`Gerir a lista ${l.nome}`}>
      <form className="quick" onSubmit={renomear}>
        <label className="sr-only" htmlFor="lista-nome">Nome da lista</label>
        <input id="lista-nome" className="input input-sm grow-input" maxLength={60} value={nome} onChange={(e) => setNome(e.target.value)} />
        <Botao type="submit" pequeno variante="secondary" carregando={ocupado === 'lista-nome'} disabled={!nome.trim() || nome.trim() === l.nome || ocupado !== null}>Renomear</Botao>
      </form>
      {apagar ? (
        <div className="quick" role="group" aria-label="Confirmar apagar lista">
          <span className="t-meta">Apagar «{l.nome}» e os seus {l.total} itens?</span>
          <Botao variante="danger" pequeno carregando={ocupado === 'lista-apagar'} disabled={ocupado !== null} onClick={() => void eliminar()}>Apagar lista</Botao>
          <Botao variante="secondary" pequeno onClick={() => setApagar(false)}>Cancelar</Botao>
        </div>
      ) : <div><button type="button" className="link-btn link-danger" onClick={() => setApagar(true)}>Apagar esta lista</button></div>}
    </section>
  )
}

function UltimaChamada({ dados, f }: { dados: ComprasModulo; f: Ferramentas }) {
  const { executar, ocupado, avisos } = f
  const [aberto, setAberto] = useState(false)
  const [mensagem, setMensagem] = useState('')
  const u = dados.ultimaChamada
  if (u) {
    const hora = new Date(u.criado * 1000).toLocaleTimeString('pt-PT', { hour: '2-digit', minute: '2-digit' })
    return (
      <section className="card stack" aria-label="Última chamada">
        <h2 className="t-card">Última chamada</h2>
        <p className="t-body2">{u.por || 'Alguém'} avisou toda a gente às {hora}{u.mensagem ? `: ${u.mensagem}` : '.'}</p>
      </section>
    )
  }
  async function enviar(ev: FormEvent) {
    ev.preventDefault()
    if (await executar('ultima-chamada', 'compras.ultima_chamada', { lista: dados.lista.id, mensagem: mensagem.trim() }, true)) {
      setAberto(false); setMensagem(''); avisos.mostrar('Última chamada enviada a toda a gente.')
    }
  }
  if (!aberto) return <div><Botao pequeno variante="secondary" onClick={() => setAberto(true)}>Última chamada</Botao></div>
  return (
    <form className="card stack" aria-label="Confirmar última chamada" onSubmit={(ev) => void enviar(ev)}>
      <h2 className="t-card">Última chamada</h2>
      <p className="t-body2">Avisa toda a gente de que vais fechar a lista e ir às compras. Só se pode fazer uma vez.</p>
      <label className="t-meta">Mensagem (opcional)
        <input className="input" value={mensagem} maxLength={120} placeholder="Saio às 18h" onChange={(e) => setMensagem(e.target.value)} /></label>
      <div className="quick">
        <Botao type="submit" pequeno carregando={ocupado === 'ultima-chamada'} disabled={ocupado !== null}>Avisar toda a gente</Botao>
        <Botao type="button" variante="secondary" pequeno onClick={() => setAberto(false)}>Cancelar</Botao>
      </div>
    </form>
  )
}

export function ListaTab({ dados, f, abrirCatalogo, gerir, setGerir, aoApagarLista }: Props) {
  const { executar, ocupado, avisos } = f
  const [limpar, setLimpar] = useState(false)
  const { fechadas, alternar, todas } = useFechadas('pulse.compras.fechadas.lista')
  const ids = dados.grupos.map((g) => g.categoria.id)
  const todasFechadas = ids.length > 0 && ids.every((id) => fechadas.has(id))
  const partilhada = dados.lista.tipo === 'partilhada'

  async function limparComprados() {
    const r = await executar('limpar', 'compras.limpar_comprados', { lista: dados.lista.id }, true)
    if (r) {
      setLimpar(false)
      const removidos = (r.removidos as ItemCompras[]) ?? []
      avisos.mostrar(`${removidos.length} ${removidos.length === 1 ? 'item comprado removido' : 'itens comprados removidos'}.`,
        () => void executar('desfazer', 'compras.restaurar', { lista: dados.lista.id, itens: removidos.map(paraRestaurar) }))
    }
  }

  return (
    <div className="stack">
      {dados.lista.padrao && <UltimaChamada dados={dados} f={f} />}
      {dados.pendentes === 0 && dados.comprados.length === 0 && (
        <section className="card stack" aria-label="Lista vazia">
          <p className="t-body2">A lista «{dados.lista.nome}» está vazia. Escolhe produtos no catálogo com um toque.</p>
          <div><Botao pequeno onClick={abrirCatalogo}>Abrir o catálogo</Botao></div>
        </section>
      )}
      {ids.length > 1 && <div><button type="button" className="link-btn" onClick={() => todas(ids, !todasFechadas)}>{todasFechadas ? 'Expandir todas' : 'Encolher todas'}</button></div>}
      {dados.grupos.map((g) => {
        const aberto = !fechadas.has(g.categoria.id)
        return (
          <section className="card" aria-label={g.categoria.nome} key={g.categoria.id}>
            <h2 className="t-card"><button type="button" className="sec-toggle" aria-expanded={aberto} onClick={() => alternar(g.categoria.id)}>
              <Icon nome="seta" tamanho={16} />{g.categoria.nome} <span className="t-meta">{g.itens.length}</span></button></h2>
            {aberto && <ul className="rows">{g.itens.map((i) => <Linha key={i.id} i={i} dados={dados} f={f} partilhada={partilhada} />)}</ul>}
          </section>
        )
      })}
      {dados.pendentes > 0 && dados.comprados.length === 0 && <p className="t-meta">Toca no círculo de um item quando o comprares.</p>}
      {dados.comprados.length > 0 && (
        <section className="card" aria-label="Comprados">
          <div className="split"><h2 className="t-card">Comprados <span className="t-meta">{dados.comprados.length}</span></h2>
            {!limpar && <Botao pequeno variante="secondary" onClick={() => setLimpar(true)}>Limpar comprados</Botao>}</div>
          {limpar && (
            <div className="quick" role="group" aria-label="Confirmar limpar comprados">
              <span className="t-meta">Apagar {dados.comprados.length} {dados.comprados.length === 1 ? 'item' : 'itens'} da lista?</span>
              <Botao variante="danger" pequeno carregando={ocupado === 'limpar'} disabled={ocupado !== null} onClick={() => void limparComprados()}>Apagar</Botao>
              <Botao variante="secondary" pequeno onClick={() => setLimpar(false)}>Cancelar</Botao>
            </div>
          )}
          <ul className="rows">{dados.comprados.map((i) => <Linha key={i.id} i={i} dados={dados} f={f} partilhada={partilhada} />)}</ul>
        </section>
      )}
      <Sugestoes dados={dados} f={f} />
      {!dados.lista.padrao && (
        <div>
          <button type="button" className="link-btn" aria-expanded={gerir} onClick={() => setGerir(!gerir)}>{gerir ? 'Fechar gestão da lista' : 'Gerir esta lista'}</button>
          {gerir && <GerirLista key={dados.lista.id} dados={dados} f={f} aoApagarLista={aoApagarLista} />}
        </div>
      )}
    </div>
  )
}
