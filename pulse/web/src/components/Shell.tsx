import { NavLink, Outlet } from 'react-router-dom'
import { Icon } from './Icon'

const LOGO = `${import.meta.env.BASE_URL}pulse-icon-192.png`

/** Barra inferior no telemóvel, coluna lateral no ecrã largo. */
export function Shell() {
  return (
    <div className="shell">
      <nav className="nav" aria-label="Principal">
        <div className="nav-brand"><img src={LOGO} alt="" width={32} height={32} />Pulse</div>
        <NavLink to="/hoje"><Icon nome="hoje" />Hoje</NavLink>
        <NavLink to="/mais"><Icon nome="mais" />Mais</NavLink>
        <NavLink to="/definicoes" className="nav-desktop-only"><Icon nome="definicoes" />Definições</NavLink>
      </nav>
      <main className="main"><Outlet /></main>
    </div>
  )
}
