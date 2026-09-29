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
import { PedidosTab } from './PedidosTab'
import { RegistoTab } from './RegistoTab'
import { SemanaTab } from './SemanaTab'

const ABAS = [{ id: 'semana', nome: 'Semana' }, { id: 'bilhetes', nome: 'Bilhetes' }, { id: 'pedidos', nome: 'Pedidos' }, { id: 'registo', nome: 'Registo' }] as const
type Aba = (typeof ABAS)[number]['id']

export function BilhetesScreen() {
  const [params] = useSearchParams()
  const [aba, setAba] = useState<Aba>(ABAS.find((a) => a.id === params.get('aba'))?.id ?? 'semana')
  const [semana, setSemana] = useState<string | null>(null)          // null = a próxima semana (o servidor sabe qual é)
  const [estado, recarregar] = useAsync(() => api.get<BilhetesModulo>(`/tickets${semana ? `?semana=${semana}` : ''}`), semana)
  const { ocupado, erro, executar, limparErro } = useAcao(recarregar)
  const avisos = useAvisos()
  const base = useId()
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
          <div className="segmented tabs" role="tablist" aria-label="Secções dos Bilhetes CP">
            {ABAS.map((a) => <button key={a.id} role="tab" id={`${base}-${a.id}`} aria-selected={aba === a.id} aria-controls={`${base}-p`} onClick={() => setAba(a.id)}>{a.nome}</button>)}
          </div>
          {erro && <Notice tipo="error">{erro} <button type="button" className="link-btn" onClick={limparErro}>Fechar</button></Notice>}
          <div role="tabpanel" id={`${base}-p`} aria-labelledby={`${base}-${aba}`} className="tabpanel">
            {aba === 'semana' && <SemanaTab dados={estado.dados} irParaSemana={setSemana} f={f} />}
            {aba === 'bilhetes' && <BilhetesTab dados={estado.dados} />}
            {aba === 'pedidos' && <PedidosTab dados={estado.dados} f={f} />}
            {aba === 'registo' && <RegistoTab dados={estado.dados} />}
          </div>
        </>
      )}
    </>
  )
}
