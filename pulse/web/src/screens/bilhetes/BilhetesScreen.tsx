import { useId, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, mensagemDeErro } from '../../api/client'
import type { BilhetesModulo } from '../../api/types'
import { useAvisos } from '../../components/Avisos'
import { Icon } from '../../components/Icon'
import { BrandLoading, Botao, Notice } from '../../components/ui'
import { useAcao } from '../../lib/useAcao'
import { useAsync } from '../../lib/useAsync'
import { BilhetesTab } from './BilhetesTab'
import { CpTab } from './CpTab'
import { HistoricoTab } from './HistoricoTab'
import { PedidosTab } from './PedidosTab'
import { RegistoTab } from './RegistoTab'
import { SemanaTab } from './SemanaTab'

const ABAS = [{ id: 'semana', nome: 'Semana' }, { id: 'bilhetes', nome: 'Bilhetes' }, { id: 'pedidos', nome: 'Pedidos' }, { id: 'cp', nome: 'Na CP' }, { id: 'registo', nome: 'Registo' }, { id: 'historico', nome: 'Histórico' }] as const
type Aba = (typeof ABAS)[number]['id']

export function BilhetesScreen() {
  const [params] = useSearchParams()
  const [aba, setAba] = useState<Aba>(ABAS.find((a) => a.id === params.get('aba'))?.id ?? 'semana')
  const [semana, setSemana] = useState<string | null>(null)          // null = a próxima semana (o servidor sabe qual é)
  const [utilizador, setUtilizador] = useState<number | null>(null)   // null = a própria conta; o administrador pode ver e marcar por outra pessoa (ADR-069)
  const [estado, recarregar] = useAsync(() => {
    const q = new URLSearchParams({ ...(semana ? { semana } : {}), ...(utilizador ? { utilizador: String(utilizador) } : {}) }).toString()
    return api.get<BilhetesModulo>(`/tickets${q ? `?${q}` : ''}`)
  }, `${semana}|${utilizador}`)
  const { ocupado, erro, executar: executarBase, limparErro } = useAcao(recarregar)
  const avisos = useAvisos()
  const base = useId()
  // marcar a semana e o passe fazem-se **para a pessoa escolhida** (a compra usa os dados dela); o «Desfazer» passa pelo mesmo caminho
  const executar: typeof executarBase = (chave, nome, params, confirmado) =>
    executarBase(chave, nome, utilizador && (nome === 'bilhetes.semana' || nome === 'bilhetes.passe') && !('utilizador' in params) ? { ...params, utilizador } : params, confirmado)
  const f = { executar, ocupado, avisos }

  return (
    <>
      <header className="hero">
        <Link to="/mais" className="back"><Icon nome="voltar" tamanho={20} />Mais</Link>
        <h1 className="t-page">Bilhetes CP</h1>
      </header>

      {estado.fase === 'a-carregar' && <BrandLoading texto="A carregar os bilhetes…" />}
      {estado.fase === 'erro' && (
        <div className="state">
          <Notice tipo="error">{mensagemDeErro(estado.erro)}</Notice>
          <Botao variante="secondary" pequeno onClick={recarregar}>Tentar de novo</Botao>
        </div>
      )}
      {estado.fase === 'pronto' && (
        <>
          {(estado.dados.pessoas?.length ?? 0) > 1 && (
            <div className="stack">
              <div className="chips" role="group" aria-label="Ver e marcar bilhetes de">
                {estado.dados.pessoas!.map((p) => (
                  <button key={p.id} type="button" className="chip" aria-pressed={estado.dados.utilizador?.id === p.id}
                    onClick={() => { setUtilizador(p.eu ? null : p.id); setSemana(null) }}>{p.eu ? `${p.nome} (eu)` : p.nome}</button>
                ))}
              </div>
              {estado.dados.utilizador && !estado.dados.utilizador.eu && <p className="t-meta">A marcar para <b>{estado.dados.utilizador.nome}</b>: a compra faz-se com os dados dela, e recebes os avisos tu e ela.</p>}
            </div>
          )}
          <div className="segmented tabs" role="tablist" aria-label="Secções dos Bilhetes CP">
            {ABAS.filter((a) => a.id !== 'historico' || (estado.dados.pessoas?.length ?? 0) > 0).map((a) => <button key={a.id} role="tab" id={`${base}-${a.id}`} aria-selected={aba === a.id} aria-controls={`${base}-p`} onClick={() => setAba(a.id)}>{a.nome}</button>)}
          </div>
          {erro && <Notice tipo="error">{erro} <button type="button" className="link-btn" onClick={limparErro}>Fechar</button></Notice>}
          <div role="tabpanel" id={`${base}-p`} aria-labelledby={`${base}-${aba}`} className="tabpanel">
            {aba === 'semana' && <SemanaTab dados={estado.dados} irParaSemana={setSemana} f={f} />}
            {aba === 'bilhetes' && <BilhetesTab dados={estado.dados} />}
            {aba === 'pedidos' && <PedidosTab dados={estado.dados} f={f} />}
            {aba === 'cp' && <CpTab utilizador={utilizador} nome={estado.dados.utilizador?.nome ?? ''} favoritos={estado.dados.favoritos} aoMudar={recarregar} />}
            {aba === 'registo' && <RegistoTab dados={estado.dados} />}
            {aba === 'historico' && <HistoricoTab />}
          </div>
        </>
      )}
    </>
  )
}
