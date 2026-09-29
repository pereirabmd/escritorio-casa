import { useEffect, useId, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, mensagemDeErro } from '../../api/client'
import type { FinancasModulo } from '../../api/types'
import { useAvisos } from '../../components/Avisos'
import { Icon } from '../../components/Icon'
import { BrandLoading, Botao, Notice } from '../../components/ui'
import { somarMeses } from '../../lib/financas'
import { useAcao } from '../../lib/useAcao'
import { useAsync } from '../../lib/useAsync'
import { CategoriasTab } from './CategoriasTab'
import { LancamentosTab } from './LancamentosTab'
import { LembretesTab } from './LembretesTab'
import { RelatoriosTab } from './RelatoriosTab'
import { ResumoTab } from './ResumoTab'

const ABAS = [{ id: 'resumo', nome: 'Resumo' }, { id: 'lancamentos', nome: 'Lançamentos' }, { id: 'relatorios', nome: 'Relatórios' },
  { id: 'categorias', nome: 'Categorias' }, { id: 'lembretes', nome: 'Lembretes' }] as const
type Aba = (typeof ABAS)[number]['id']

export function FinancasScreen() {
  const [params] = useSearchParams()
  const [aba, setAba] = useState<Aba>(ABAS.find((a) => a.id === params.get('aba'))?.id ?? 'resumo')
  const [mes, setMes] = useState<string | null>(null)                    // null = o mês de hoje (o servidor sabe qual é)
  const [modo, setModo] = useState<'mes' | '30d'>('mes')
  const [estado, recarregar] = useAsync(() => api.get<FinancasModulo>(`/finance?${mes ? `mes=${mes}&` : ''}janela=${modo}`), `${mes}|${modo}`)
  const { ocupado, erro, executar, limparErro } = useAcao(recarregar)
  const avisos = useAvisos()
  const base = useId()
  const mesAtual = estado.fase === 'pronto' ? estado.dados.mes : null
  const hojeMes = estado.fase === 'pronto' ? estado.dados.hoje.slice(0, 7) : null

  // Ao abrir um mês (até ao seguinte) copia-se-lhe os recorrentes do mês anterior, uma só vez (idempotente no servidor).
  useEffect(() => {
    if (!mesAtual || !hojeMes || mesAtual > somarMeses(hojeMes, 1)) return
    api.post<{ resultado?: { criados?: number } }>('/actions/financas.preparar_mes', { params: { mes: mesAtual } })
      .then((r) => { if ((r.resultado?.criados ?? 0) > 0) recarregar() }, () => undefined)
    // só quando muda o mês à vista
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mesAtual, hojeMes])

  const f = { executar, ocupado, avisos }
  return (
    <>
      <header className="hero">
        <Link to="/mais" className="back"><Icon nome="voltar" tamanho={20} />Mais</Link>
        <h1 className="t-page">Finanças</h1>
      </header>

      {estado.fase === 'a-carregar' && <BrandLoading texto="A carregar as finanças…" />}
      {estado.fase === 'erro' && (
        <div className="state">
          <Notice tipo="error">{mensagemDeErro(estado.erro)}</Notice>
          <Botao variante="secondary" pequeno onClick={recarregar}>Tentar de novo</Botao>
        </div>
      )}
      {estado.fase === 'pronto' && (
        <>
          <div className="segmented scroll" role="tablist" aria-label="Secções das Finanças">
            {ABAS.map((a) => <button key={a.id} role="tab" id={`${base}-${a.id}`} aria-selected={aba === a.id} aria-controls={`${base}-p`} onClick={() => setAba(a.id)}>{a.nome}</button>)}
          </div>
          {erro && <Notice tipo="error">{erro} <button type="button" className="link-btn" onClick={limparErro}>Fechar</button></Notice>}
          <div role="tabpanel" id={`${base}-p`} aria-labelledby={`${base}-${aba}`} className="tabpanel">
            {aba === 'resumo' && <ResumoTab dados={estado.dados} modo={modo} trocarModo={setModo} f={f} />}
            {aba === 'lancamentos' && <LancamentosTab dados={estado.dados} irParaMes={setMes} f={f} />}
            {aba === 'relatorios' && <RelatoriosTab mes={estado.dados.mes} />}
            {aba === 'categorias' && <CategoriasTab categorias={estado.dados.categorias} {...f} />}
            {aba === 'lembretes' && <LembretesTab {...f} />}
          </div>
        </>
      )}
    </>
  )
}
