import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, mensagemDeErro } from '../../api/client'
import type { CaixaGoogle, MensagemDetalhe, MensagemGoogle } from '../../api/types'
import { useAvisos } from '../../components/Avisos'
import { Icon } from '../../components/Icon'
import { BrandLoading, Botao, Notice } from '../../components/ui'
import { useAcao } from '../../lib/useAcao'
import { useAsync } from '../../lib/useAsync'

const FILTROS = [{ id: 'importantes', nome: 'Importantes' }, { id: 'entrada', nome: 'Caixa de entrada' }, { id: 'por_ler', nome: 'Por ler' }] as const
type Filtro = (typeof FILTROS)[number]['id']

/** «há 5 min», «hoje 09:30», «ontem», «28/09». */
export function quandoMensagem(iso: string, agora: Date = new Date()): string {
  if (!iso) return ''
  const d = new Date(iso)
  const min = Math.round((agora.getTime() - d.getTime()) / 60000)
  if (min >= 0 && min < 60) return min <= 1 ? 'agora' : `há ${min} min`
  const mesmoDia = d.toDateString() === agora.toDateString()
  const hora = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  if (mesmoDia) return `hoje ${hora}`
  const ontem = new Date(agora.getTime() - 86400000)
  if (d.toDateString() === ontem.toDateString()) return 'ontem'
  return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}`
}

function Detalhe({ m, executar, ocupado, avisos, aoMudar }: { m: MensagemGoogle; executar: ReturnType<typeof useAcao>['executar']; ocupado: string | null; avisos: ReturnType<typeof useAvisos>; aoMudar: () => void }) {
  const [estado] = useAsync(() => api.get<MensagemDetalhe>(`/mail/${m.conta}/${m.id}`), `${m.conta}|${m.id}`)
  const ident = { conta: m.conta, mensagem: m.id }

  async function lida(valor: boolean) {
    if (await executar(`l-${m.id}`, 'email.lida', { ...ident, lida: valor })) aoMudar()
  }
  async function arquivar() {
    if (await executar(`a-${m.id}`, 'email.arquivar', { ...ident, arquivado: true })) {
      avisos.mostrar('Mensagem arquivada.', () => void executar('desfazer', 'email.arquivar', { ...ident, arquivado: false }).then(aoMudar))
      aoMudar()
    }
  }
  async function estrela() {
    if (await executar(`e-${m.id}`, 'email.estrela', { ...ident, estrela: !m.estrela })) aoMudar()
  }
  return (
    <div className="stack" role="region" aria-label={`Mensagem: ${m.assunto}`}>
      {estado.fase === 'a-carregar' && <BrandLoading texto="A abrir a mensagem…" />}
      {estado.fase === 'erro' && <Notice tipo="error">{mensagemDeErro(estado.erro)}</Notice>}
      {estado.fase === 'pronto' && (
        <>
          <div className="t-meta">De {estado.dados.de} &lt;{estado.dados.deEmail}&gt;{estado.dados.para ? ` · Para ${estado.dados.para}` : ''}</div>
          {/* o conteúdo de um email não é de confiança: mostra-se sempre como texto simples, nunca como HTML */}
          <pre className="mail-corpo">{estado.dados.corpo || '(sem texto)'}</pre>
          {estado.dados.temAnexos && <p className="t-meta">Esta mensagem tem anexos, que o Pulse não mostra. Abre-a no Gmail para os ver.</p>}
        </>
      )}
      <div className="quick" role="group" aria-label="Ações da mensagem">
        <Botao variante="secondary" pequeno disabled={ocupado !== null} onClick={() => void lida(!m.lida)}>{m.lida ? 'Marcar como por ler' : 'Marcar como lida'}</Botao>
        <Botao variante="secondary" pequeno disabled={ocupado !== null} onClick={() => void arquivar()}>Arquivar</Botao>
        <a className="btn btn-secondary btn-sm" href={m.link} target="_blank" rel="noopener noreferrer">Abrir no Gmail</a>
        <Botao variante="secondary" pequeno aria-pressed={m.estrela} disabled={ocupado !== null} onClick={() => void estrela()}>{m.estrela ? 'Tirar estrela' : 'Pôr estrela'}</Botao>
      </div>
    </div>
  )
}

export function EmailScreen() {
  const [filtro, setFiltro] = useState<Filtro>('importantes')
  const [conta, setConta] = useState<number | null>(null)
  const [params] = useSearchParams()
  const [aberta, setAberta] = useState<string | null>(() => params.get('mensagem'))          // «conta:id»: o toque numa mensagem do Hoje abre-a aqui
  const [estado, recarregar] = useAsync(() => api.get<CaixaGoogle>(`/mail?filtro=${filtro}${conta ? `&conta=${conta}` : ''}`), `${filtro}|${conta}`)
  const { ocupado, erro, executar, limparErro } = useAcao(() => undefined)
  const avisos = useAvisos()
  const chave = (m: MensagemGoogle) => `${m.conta}:${m.id}`
  useEffect(() => { if (aberta && estado.fase === 'pronto') document.querySelector('li.open')?.scrollIntoView?.({ block: 'center' }) }, [estado.fase]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <header className="hero">
        <Link to="/mais" className="back"><Icon nome="voltar" tamanho={20} />Mais</Link>
        <h1 className="t-page">Email</h1>
      </header>

      {estado.fase === 'a-carregar' && <BrandLoading texto="A carregar o email…" />}
      {estado.fase === 'erro' && (
        <div className="state">
          <Notice tipo="error">{mensagemDeErro(estado.erro)}</Notice>
          <Botao variante="secondary" pequeno onClick={recarregar}>Tentar de novo</Botao>
        </div>
      )}
      {estado.fase === 'pronto' && !estado.dados.ligado && (
        <div className="stack">
          <Notice tipo="info">{estado.dados.configurado ? 'Liga uma conta Google com o Gmail para veres aqui as tuas mensagens.' : 'A integração com a Google ainda não está configurada neste servidor.'}</Notice>
          <div><Link to="/definicoes" className="btn btn-secondary btn-sm">Ir às Definições</Link></div>
        </div>
      )}
      {estado.fase === 'pronto' && estado.dados.ligado && (
        <div className="stack">
          <div className="chips" role="group" aria-label="Filtro">
            {FILTROS.map((f) => <button key={f.id} type="button" className="chip" aria-pressed={filtro === f.id} onClick={() => { setFiltro(f.id); setAberta(null) }}>{f.nome}</button>)}
          </div>
          {(estado.dados.contas.length > 1 || conta !== null) && (
            <div className="chips" role="group" aria-label="Conta">
              <button type="button" className="chip" aria-pressed={conta === null} onClick={() => { setConta(null); setAberta(null) }}>Todas</button>
              {estado.dados.contas.map((c) => <button key={c.id} type="button" className="chip" aria-pressed={conta === c.id} onClick={() => { setConta(c.id); setAberta(null) }}>{c.email}</button>)}
            </div>
          )}
          {estado.dados.contas.filter((c) => c.estado !== 'ok').map((c) => (
            <Notice key={c.id} tipo="warning">{c.estado === 'reautorizar' ? <>A conta {c.email} pede nova autorização. <Link to="/definicoes" className="link-btn">Volta a ligá-la</Link>.</> : <>Não foi possível ler a conta {c.email}: {c.erro}</>}</Notice>
          ))}
          {erro && <Notice tipo="error">{erro} <button type="button" className="link-btn" onClick={limparErro}>Fechar</button></Notice>}
          {estado.dados.mensagens.length === 0 ? <p className="t-body2">{filtro === 'por_ler' ? 'Nada por ler.' : 'Sem mensagens.'}</p> : (
            <section className="card" aria-label="Mensagens">
              <ul className="rows">
                {estado.dados.mensagens.map((m) => {
                  const k = chave(m), aberto = aberta === k
                  return (
                    <li key={k} className={aberto ? 'open' : undefined} data-lida={m.lida}>
                      <button type="button" className="mail-linha" aria-expanded={aberto} aria-label={`${m.lida ? '' : 'Por ler: '}${m.assunto}, de ${m.de}`} onClick={() => setAberta(aberto ? null : k)}>
                        <span className="row-main">
                          <span className={`t-body${m.lida ? '' : ' mail-nova'}`}>{m.de}{m.estrela && <span aria-hidden="true"> ★</span>}</span>
                          <span className={`t-body2${m.lida ? '' : ' mail-nova'}`}>{m.assunto}</span>
                          <span className="t-meta">{m.resumo}</span>
                        </span>
                        <span className="t-meta">{quandoMensagem(m.data)}{estado.dados.contas.length > 1 ? ` · ${m.contaEmail}` : ''}</span>
                      </button>
                      {aberto && <Detalhe m={m} executar={executar} ocupado={ocupado} avisos={avisos} aoMudar={recarregar} />}
                    </li>
                  )
                })}
              </ul>
            </section>
          )}
          <div><Botao variante="secondary" pequeno onClick={recarregar}>Atualizar</Botao></div>
        </div>
      )}
    </>
  )
}
