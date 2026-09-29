import { useRef, useState, type FormEvent } from 'react'
import type { FinancasModulo, LancamentoFin } from '../../api/types'
import { Icon } from '../../components/Icon'
import { Botao, Notice } from '../../components/ui'
import { ESTADO_TXT, lerValor, paraInputValor, somarMeses, tituloMesFin } from '../../lib/financas'
import { fmtDataIso, fmtEuro, plural } from '../../lib/format'
import { novoCid } from '../../lib/useAcao'
import type { Ferramentas } from './tipos'

/** Uma conta com «pagar/anular», editar e apagar. Reaproveitada no Resumo (vencidas). */
export function LinhaConta({ l, f, categorias }: { l: LancamentoFin; f: Ferramentas; categorias?: FinancasModulo['categorias'] }) {
  const { executar, ocupado, avisos } = f
  const [modo, setModo] = useState<'ver' | 'editar' | 'apagar'>('ver')
  const paga = l.estado === 'pago'
  const verbo = l.tipo === 'despesa' ? 'paga' : 'recebido'

  async function alternar() {
    if (paga) {
      if (await executar(`pg-${l.id}`, 'financas.anular_pagamento', { lancamento: l.id })) avisos.mostrar('Pagamento anulado.')
      return
    }
    if (await executar(`pg-${l.id}`, 'financas.pagar', { lancamento: l.id })) {
      avisos.mostrar(`Marcado como ${verbo}.`, () => void executar('desfazer', 'financas.anular_pagamento', { lancamento: l.id }))
    }
  }
  async function apagar() {
    const r = await executar(`del-${l.id}`, 'financas.apagar', { lancamento: l.id }, true)
    if (r) {
      avisos.mostrar('Lançamento apagado.', () => void executar('desfazer', 'financas.criar', {
        tipo: l.tipo, descricao: l.descricao, valor: l.valor, categoriaId: l.categoria_id, dataVencimento: l.data_vencimento,
        dataPagamento: l.data_pagamento, recorrente: l.recorrente, mesReferencia: l.mes_referencia }))
    }
  }

  if (modo === 'editar' && categorias) {
    return <li className="edit"><FormLancamento inicial={l} categorias={categorias} f={f} fechar={() => setModo('ver')} /></li>
  }
  return (
    <li data-estado={l.estado}>
      <button type="button" className="check" data-done={paga} aria-pressed={paga} disabled={ocupado !== null}
        aria-label={`${paga ? 'Anular pagamento' : 'Marcar como ' + verbo}: ${l.descricao}`} onClick={() => void alternar()}>
        <Icon nome="certo" tamanho={16} />
      </button>
      <div className="row-main">
        <div className={`t-body${paga ? ' struck' : ''}`}>{l.descricao}</div>
        <div className="t-meta">
          {l.categoria} · {fmtDataIso(l.data_vencimento)}{l.recorrente ? ' · recorrente' : ''}
          {l.estado === 'vencido' && <> · <span className="pill pill-soon">{ESTADO_TXT.vencido}</span></>}
          {l.estado === 'hoje' && <> · <span className="pill pill-soon">{ESTADO_TXT.hoje}</span></>}
        </div>
      </div>
      <div className={`t-body${l.tipo === 'rendimento' ? ' link-ok' : ''}`}>{l.tipo === 'rendimento' ? '+ ' : ''}{fmtEuro(l.valor)}</div>
      {modo === 'apagar' ? (
        <div className="quick" role="group" aria-label={`Apagar ${l.descricao}`}>
          <Botao variante="danger" pequeno carregando={ocupado === `del-${l.id}`} disabled={ocupado !== null} onClick={() => void apagar()}>Apagar</Botao>
          <Botao variante="secondary" pequeno onClick={() => setModo('ver')}>Cancelar</Botao>
        </div>
      ) : (
        <>
          {categorias && <button type="button" className="link-btn" aria-label={`Editar ${l.descricao}`} onClick={() => setModo('editar')}>Editar</button>}
          <button type="button" className="link-btn link-danger" aria-label={`Apagar ${l.descricao}`} onClick={() => setModo('apagar')}>Apagar</button>
        </>
      )}
    </li>
  )
}

interface FormProps { inicial?: LancamentoFin; categorias: FinancasModulo['categorias']; f: Ferramentas; fechar?: () => void; mesPadrao?: string }

/** Criar (sem `inicial`) ou editar um lançamento. */
function FormLancamento({ inicial, categorias, f, fechar, mesPadrao }: FormProps) {
  const { executar, ocupado, avisos } = f
  const [tipo, setTipo] = useState<'despesa' | 'rendimento'>(inicial?.tipo ?? 'despesa')
  const [descricao, setDescricao] = useState(inicial?.descricao ?? '')
  const [texto, setTexto] = useState(inicial ? paraInputValor(inicial.valor) : '')
  const [categoria, setCategoria] = useState(String(inicial?.categoria_id ?? categorias[0]?.id ?? ''))
  const [venc, setVenc] = useState(inicial?.data_vencimento ?? (mesPadrao ? `${mesPadrao}-01` : ''))
  const [recorrente, setRecorrente] = useState(inicial?.recorrente ?? false)
  const cid = useRef(novoCid())
  const valor = lerValor(texto)
  const ok = descricao.trim() !== '' && valor !== null && categoria !== '' && venc !== ''
  const chave = inicial ? `ed-${inicial.id}` : 'novo'

  async function guardar(ev: FormEvent) {
    ev.preventDefault()
    if (!ok) return
    const base = { tipo, descricao: descricao.trim(), valor, categoriaId: Number(categoria), dataVencimento: venc, recorrente }
    const feito = inicial
      ? await executar(chave, 'financas.editar', { lancamento: inicial.id, ...base, ...(venc.slice(0, 7) !== inicial.data_vencimento.slice(0, 7) ? { mesReferencia: venc.slice(0, 7) } : {}) })
      : await executar(chave, 'financas.criar', { ...base, cid: cid.current })
    if (feito) {
      avisos.mostrar(inicial ? 'Lançamento atualizado.' : 'Lançamento criado.')
      if (!inicial) { cid.current = novoCid(); setDescricao(''); setTexto('') }
      fechar?.()
    }
  }
  const id = inicial ? `l${inicial.id}` : 'ln'
  return (
    <form className={inicial ? 'stack' : 'card stack'} onSubmit={guardar} noValidate aria-label={inicial ? `Editar ${inicial.descricao}` : 'Novo lançamento'}>
      {!inicial && <h2 className="t-card">Novo lançamento</h2>}
      <div className="chips" role="group" aria-label="Tipo">
        <button type="button" className="chip" aria-pressed={tipo === 'despesa'} onClick={() => setTipo('despesa')}>Despesa</button>
        <button type="button" className="chip" aria-pressed={tipo === 'rendimento'} onClick={() => setTipo('rendimento')}>Rendimento</button>
      </div>
      <div className="field"><label htmlFor={`${id}-d`}>Descrição</label><input id={`${id}-d`} className="input" maxLength={100} value={descricao} onChange={(e) => setDescricao(e.target.value)} /></div>
      <div className="field"><label htmlFor={`${id}-v`}>Valor (€)</label>
        <input id={`${id}-v`} className="input" inputMode="decimal" autoComplete="off" value={texto} onChange={(e) => setTexto(e.target.value)} aria-invalid={texto !== '' && valor === null ? true : undefined} /></div>
      <div className="field"><label htmlFor={`${id}-c`}>Categoria</label>
        <select id={`${id}-c`} className="input" value={categoria} onChange={(e) => setCategoria(e.target.value)}>{categorias.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}</select></div>
      <div className="field"><label htmlFor={`${id}-t`}>Vencimento</label><input id={`${id}-t`} type="date" className="input" value={venc} onChange={(e) => setVenc(e.target.value)} /></div>
      <label className="check-line"><input type="checkbox" checked={recorrente} onChange={(e) => setRecorrente(e.target.checked)} /> Recorrente (repete-se todos os meses)</label>
      <div className="quick">
        <Botao type="submit" pequeno carregando={ocupado === chave} disabled={!ok || ocupado !== null}>{inicial ? 'Guardar' : 'Adicionar'}</Botao>
        {fechar && <Botao type="button" pequeno variante="secondary" onClick={fechar}>Cancelar</Botao>}
      </div>
    </form>
  )
}

interface Props { dados: FinancasModulo; irParaMes: (m: string) => void; f: Ferramentas }

export function LancamentosTab({ dados, irParaMes, f }: Props) {
  const [novo, setNovo] = useState(false)
  const porPagar = dados.lancamentos.filter((l) => l.estado !== 'pago'), pagos = dados.lancamentos.filter((l) => l.estado === 'pago')
  const t = dados.totaisMes
  return (
    <div className="stack">
      <div className="cal-head">
        <button type="button" className="icon-round" aria-label="Mês anterior" onClick={() => irParaMes(somarMeses(dados.mes, -1))}><Icon nome="voltar" tamanho={20} /></button>
        <h2 className="t-card grow" style={{ textAlign: 'center' }}>{tituloMesFin(dados.mes)}</h2>
        <button type="button" className="icon-round" aria-label="Mês seguinte" onClick={() => irParaMes(somarMeses(dados.mes, 1))}><Icon nome="seta" tamanho={20} /></button>
      </div>
      <div className="stats" aria-label="Totais do mês">
        <div><div className="t-meta">Rendimento</div><div className="t-body">{fmtEuro(t.rendimento)}</div></div>
        <div><div className="t-meta">Despesas</div><div className="t-body">{fmtEuro(t.despesas)}</div></div>
        <div><div className="t-meta">Por pagar</div><div className="t-body">{fmtEuro(t.porPagar)}</div></div>
      </div>
      {dados.atrasadas.itens.length > 0 && (
        <Notice tipo="warning">{plural(dados.atrasadas.itens.length, 'despesa vencida e por pagar', 'despesas vencidas e por pagar')} · {fmtEuro(dados.atrasadas.total)} (ver no Resumo)</Notice>
      )}
      {novo ? <FormLancamento categorias={dados.categorias} f={f} mesPadrao={dados.mes} fechar={() => setNovo(false)} /> : (
        <div><Botao pequeno onClick={() => setNovo(true)}>Novo lançamento</Botao></div>
      )}
      {dados.lancamentos.length === 0 && <p className="t-body2">Sem lançamentos em {tituloMesFin(dados.mes)}.</p>}
      {porPagar.length > 0 && (
        <section className="card" aria-label="Por pagar ou receber"><h2 className="t-card">Por pagar / receber <span className="t-meta">{porPagar.length}</span></h2>
          <ul className="rows">{porPagar.map((l) => <LinhaConta key={l.id} l={l} f={f} categorias={dados.categorias} />)}</ul></section>
      )}
      {pagos.length > 0 && (
        <section className="card" aria-label="Pagos ou recebidos"><h2 className="t-card">Pagos / recebidos <span className="t-meta">{pagos.length}</span></h2>
          <ul className="rows">{pagos.map((l) => <LinhaConta key={l.id} l={l} f={f} categorias={dados.categorias} />)}</ul></section>
      )}
    </div>
  )
}
