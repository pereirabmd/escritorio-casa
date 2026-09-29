import { useId, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, mensagemDeErro } from '../../api/client'
import type { TarefasModulo } from '../../api/types'
import { useAvisos } from '../../components/Avisos'
import { Icon } from '../../components/Icon'
import { BrandLoading, Botao, Notice } from '../../components/ui'
import { useAcao } from '../../lib/useAcao'
import { useAsync } from '../../lib/useAsync'
import { CalendarioTab } from './CalendarioTab'
import { CatalogoTab } from './CatalogoTab'
import { ConfigTab } from './ConfigTab'
import { HojeTab } from './HojeTab'
import { HorarioTab } from './HorarioTab'
import { PiscinaTab } from './PiscinaTab'

const ABAS = [{ id: 'hoje', nome: 'Hoje' }, { id: 'calendario', nome: 'Calendário' }, { id: 'tarefas', nome: 'Tarefas' }, { id: 'horario', nome: 'Horário' },
  { id: 'piscina', nome: 'Piscina' }, { id: 'config', nome: 'Config' }] as const
type Aba = (typeof ABAS)[number]['id']

export function TarefasScreen() {
  const [estado, recarregar] = useAsync(() => api.get<TarefasModulo>('/tasks'))
  const { ocupado, erro, executar, limparErro } = useAcao(recarregar)
  const avisos = useAvisos()
  const [params] = useSearchParams()
  const [aba, setAba] = useState<Aba>(ABAS.find((a) => a.id === params.get('aba'))?.id ?? 'hoje')
  const base = useId()
  const f = { executar, ocupado, avisos }

  return (
    <>
      <header className="hero">
        <Link to="/mais" className="back"><Icon nome="voltar" tamanho={20} />Mais</Link>
        <h1 className="t-page">Tarefas</h1>
      </header>

      {estado.fase === 'a-carregar' && <BrandLoading texto="A carregar as tarefas…" />}
      {estado.fase === 'erro' && (
        <div className="state">
          <Notice tipo="error">{mensagemDeErro(estado.erro)}</Notice>
          <Botao variante="secondary" pequeno onClick={recarregar}>Tentar de novo</Botao>
        </div>
      )}
      {estado.fase === 'pronto' && (
        <>
          <div className="segmented scroll" role="tablist" aria-label="Secções das Tarefas">
            {ABAS.map((a) => <button key={a.id} role="tab" id={`${base}-${a.id}`} aria-selected={aba === a.id} aria-controls={`${base}-p`} onClick={() => setAba(a.id)}>{a.nome}</button>)}
          </div>
          {erro && <Notice tipo="error">{erro} <button type="button" className="link-btn" onClick={limparErro}>Fechar</button></Notice>}
          <div role="tabpanel" id={`${base}-p`} aria-labelledby={`${base}-${aba}`} className="tabpanel">
            {aba === 'hoje' && <HojeTab dados={estado.dados} f={f} />}
            {aba === 'calendario' && <CalendarioTab principal={estado.dados} atualizar={recarregar} />}
            {aba === 'tarefas' && <CatalogoTab dados={estado.dados} f={f} />}
            {aba === 'horario' && <HorarioTab />}
            {aba === 'piscina' && <PiscinaTab atualizar={recarregar} />}
            {aba === 'config' && <ConfigTab atualizar={recarregar} />}
          </div>
        </>
      )}
    </>
  )
}
