import { useId, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, mensagemDeErro } from '../../api/client'
import type { RtoModulo } from '../../api/types'
import { useAvisos } from '../../components/Avisos'
import { Icon } from '../../components/Icon'
import { BrandLoading, Botao, Notice } from '../../components/ui'
import { useAcao } from '../../lib/useAcao'
import { useAsync } from '../../lib/useAsync'
import { AnoTab } from './AnoTab'
import { CalendarioTab } from './CalendarioTab'
import { NotasTab } from './NotasTab'

const ABAS = [{ id: 'calendario', nome: 'Calendário' }, { id: 'ano', nome: 'Ano' }, { id: 'notas', nome: 'Notas' }] as const
type Aba = (typeof ABAS)[number]['id']

export function RtoScreen() {
  const hoje = new Date()
  const [ano, setAno] = useState(hoje.getFullYear())
  const [mes, setMes] = useState(hoje.getMonth())
  const [estado, recarregar] = useAsync(() => api.get<RtoModulo>(`/rto?ano=${ano}`), ano)
  const { ocupado, erro, executar, limparErro } = useAcao(recarregar)
  const avisos = useAvisos()
  const [params] = useSearchParams()
  const [aba, setAba] = useState<Aba>(ABAS.find((a) => a.id === params.get('aba'))?.id ?? 'calendario')
  const [admin, setAdmin] = useState(false)          // modo administrador (partilhado pelo calendário e pelas notas)
  const base = useId()
  const irPara = (a: number, m: number) => { setAno(a); setMes(m) }

  return (
    <>
      <header className="hero">
        <Link to="/mais" className="back"><Icon nome="voltar" tamanho={20} />Mais</Link>
        <h1 className="t-page">RTO</h1>
      </header>

      {estado.fase === 'a-carregar' && <BrandLoading texto="A carregar o RTO…" />}
      {estado.fase === 'erro' && (
        <div className="state">
          <Notice tipo="error">{mensagemDeErro(estado.erro)}</Notice>
          <Botao variante="secondary" pequeno onClick={recarregar}>Tentar de novo</Botao>
        </div>
      )}
      {estado.fase === 'pronto' && (
        <>
          <div className="segmented" role="tablist" aria-label="Secções do RTO">
            {ABAS.map((a) => <button key={a.id} role="tab" id={`${base}-${a.id}`} aria-selected={aba === a.id} aria-controls={`${base}-p`} onClick={() => setAba(a.id)}>{a.nome}</button>)}
          </div>
          {admin && (
            <Notice tipo="warning" role="status">
              Modo administrador ativo: podes alterar fins de semana, dias e notas já passados, sem restrições.{' '}
              <button type="button" className="link-btn" onClick={() => setAdmin(false)}>Desativar</button>
            </Notice>
          )}
          {erro && <Notice tipo="error">{erro} <button type="button" className="link-btn" onClick={limparErro}>Fechar</button></Notice>}
          <div role="tabpanel" id={`${base}-p`} aria-labelledby={`${base}-${aba}`} className="tabpanel">
            {aba === 'calendario' && <CalendarioTab dados={estado.dados} executar={executar} ocupado={ocupado} avisos={avisos} mes={mes} ano={ano} irPara={irPara} admin={admin} setAdmin={setAdmin} />}
            {aba === 'ano' && <AnoTab dados={estado.dados} abrirMes={(m) => { setMes(m); setAba('calendario') }} />}
            {aba === 'notas' && <NotasTab dados={estado.dados} executar={executar} ocupado={ocupado} avisos={avisos} admin={admin} />}
          </div>
        </>
      )}
    </>
  )
}
