import { useId, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, mensagemDeErro } from '../../api/client'
import type { PesoModulo } from '../../api/types'
import { useAvisos } from '../../components/Avisos'
import { Icon } from '../../components/Icon'
import { BrandLoading, Botao, Notice } from '../../components/ui'
import { useAcao } from '../../lib/useAcao'
import { useAsync } from '../../lib/useAsync'
import { ConfigTab } from './ConfigTab'
import { GraficoTab } from './GraficoTab'
import { RegistosTab } from './RegistosTab'
import { ResumoTab } from './ResumoTab'

const ABAS = [
  { id: 'resumo', nome: 'Resumo' }, { id: 'grafico', nome: 'Gráfico' }, { id: 'registos', nome: 'Registos' }, { id: 'config', nome: 'Configuração' },
] as const
type Aba = (typeof ABAS)[number]['id']

export function PesoScreen() {
  const [estado, recarregar] = useAsync(() => api.get<PesoModulo>('/weight'))
  const { ocupado, erro, executar, limparErro } = useAcao(recarregar)
  const avisos = useAvisos()
  const [params] = useSearchParams()
  const inicial = ABAS.find((a) => a.id === params.get('aba'))?.id ?? 'resumo'      // ligação direta: /peso?aba=grafico
  const [aba, setAba] = useState<Aba>(inicial)
  const base = useId()

  return (
    <>
      <header className="hero">
        <Link to="/mais" className="back"><Icon nome="voltar" tamanho={20} />Mais</Link>
        <h1 className="t-page">Peso</h1>
      </header>

      {estado.fase === 'a-carregar' && <BrandLoading texto="A carregar o teu peso…" />}
      {estado.fase === 'erro' && (
        <div className="state">
          <Notice tipo="error">{mensagemDeErro(estado.erro)}</Notice>
          <Botao variante="secondary" pequeno onClick={recarregar}>Tentar de novo</Botao>
        </div>
      )}
      {estado.fase === 'pronto' && (
        <>
          <div className="segmented tabs" role="tablist" aria-label="Secções do Peso">
            {ABAS.map((a) => (
              <button key={a.id} role="tab" id={`${base}-${a.id}`} aria-selected={aba === a.id} aria-controls={`${base}-p`} onClick={() => setAba(a.id)}>{a.nome}</button>
            ))}
          </div>
          {erro && <Notice tipo="error">{erro} <button type="button" className="link-btn" onClick={limparErro}>Fechar</button></Notice>}
          <div role="tabpanel" id={`${base}-p`} aria-labelledby={`${base}-${aba}`} className="tabpanel">
            {aba === 'resumo' && <ResumoTab dados={estado.dados} />}
            {aba === 'grafico' && <GraficoTab dados={estado.dados} />}
            {aba === 'registos' && <RegistosTab dados={estado.dados} executar={executar} ocupado={ocupado} avisos={avisos} />}
            {aba === 'config' && <ConfigTab dados={estado.dados} executar={executar} ocupado={ocupado} avisos={avisos} />}
          </div>
        </>
      )}
    </>
  )
}
