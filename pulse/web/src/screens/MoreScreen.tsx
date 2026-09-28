import { Link } from 'react-router-dom'
import { Icon, type IconName } from '../components/Icon'

const MODULOS: { nome: string; icone: IconName }[] = [
  { nome: 'Email', icone: 'email' }, { nome: 'Calendário', icone: 'calendario' }, { nome: 'Tarefas', icone: 'tarefas' },
  { nome: 'Bilhetes CP', icone: 'bilhete' }, { nome: 'Peso', icone: 'peso' }, { nome: 'RTO', icone: 'rto' },
  { nome: 'Finanças', icone: 'financas' }, { nome: 'Compras', icone: 'compras' },
]

export function MoreScreen() {
  return (
    <>
      <header className="hero"><h1 className="t-page">Mais</h1><p className="t-body2">As aplicações completas chegam por fases. O que já está pronto aparece no ecrã Hoje.</p></header>
      <section className="section" aria-label="Aplicações">
        <h2 className="t-card muted">Aplicações</h2>
        <div className="list">
          {MODULOS.map((m) => (
            <div key={m.nome} className="list-item" aria-disabled="true">
              <Icon nome={m.icone} /><span className="row-main">{m.nome}</span><span className="pill">Em breve</span>
            </div>
          ))}
        </div>
      </section>
      <section className="section" aria-label="Conta e definições">
        <h2 className="t-card muted">Conta</h2>
        <div className="list"><Link to="/definicoes" className="list-item"><Icon nome="definicoes" /><span className="row-main">Definições</span><Icon nome="seta" tamanho={18} /></Link></div>
      </section>
    </>
  )
}
