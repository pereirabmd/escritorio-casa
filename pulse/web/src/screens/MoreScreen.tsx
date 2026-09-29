import { Link } from 'react-router-dom'
import { Icon, type IconName } from '../components/Icon'
import { useModulos } from '../lib/modulos'

const MODULOS: { id?: string; nome: string; icone: IconName; rota?: string }[] = [
  { nome: 'Email', icone: 'email' }, { nome: 'Calendário', icone: 'calendario' }, { id: 'tarefas', nome: 'Tarefas', icone: 'tarefas', rota: '/tarefas' },
  { id: 'bilhetes', nome: 'Bilhetes CP', icone: 'bilhete', rota: '/bilhetes' }, { id: 'peso', nome: 'Peso', icone: 'peso', rota: '/peso' }, { id: 'rto', nome: 'RTO', icone: 'rto', rota: '/rto' },
  { id: 'financas', nome: 'Finanças', icone: 'financas', rota: '/financas' }, { id: 'compras', nome: 'Compras', icone: 'compras', rota: '/compras' },
]

export function MoreScreen() {
  const { ativo } = useModulos()
  const visiveis = MODULOS.filter((m) => !m.id || ativo(m.id))          // os desativados pelo administrador não aparecem
  return (
    <>
      <header className="hero"><h1 className="t-page">Mais</h1><p className="t-body2">As aplicações completas chegam por fases. O que já está pronto aparece no ecrã Hoje.</p></header>
      <section className="section" aria-label="Aplicações">
        <h2 className="t-card muted">Aplicações</h2>
        <div className="list">
          {visiveis.map((m) => m.rota ? (
            <Link key={m.nome} to={m.rota} className="list-item"><Icon nome={m.icone} /><span className="row-main">{m.nome}</span><Icon nome="seta" tamanho={18} /></Link>
          ) : (
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
