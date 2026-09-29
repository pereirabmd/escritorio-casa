import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth/AuthContext'
import { AvisosProvider } from './components/Avisos'
import { Shell } from './components/Shell'
import { Icon } from './components/Icon'
import { BrandLoading, Botao, Notice } from './components/ui'
import { ModuloAtivo, ModulosProvider } from './lib/modulos'
import { ChangePasswordScreen } from './screens/ChangePasswordScreen'
import { LoginScreen } from './screens/LoginScreen'
import { MoreScreen } from './screens/MoreScreen'
import { ComprasScreen } from './screens/compras/ComprasScreen'
import { BilhetesScreen } from './screens/bilhetes/BilhetesScreen'
import { FinancasScreen } from './screens/financas/FinancasScreen'
import { PesoScreen } from './screens/peso/PesoScreen'
import { RtoScreen } from './screens/rto/RtoScreen'
import { TarefasScreen } from './screens/tarefas/TarefasScreen'
import { SettingsScreen } from './screens/SettingsScreen'
import { TodayScreen } from './screens/TodayScreen'

/** Decide o que se mostra: arranque, início de sessão, mudança obrigatória de palavra-passe ou a aplicação. */
function Porta() {
  const { estado, tentarDeNovo } = useAuth()
  if (estado.fase === 'a-carregar') return <BrandLoading full texto="A iniciar o Pulse…" />
  if (estado.fase === 'servidor-indisponivel') {
    return (
      <main className="auth"><div className="auth-panel">
        <Icon nome="ligacao" tamanho={32} />
        <h1 className="t-section">Sem ligação ao servidor</h1>
        <Notice tipo="warning">Não foi possível contactar o Pulse. Verifica a ligação e tenta de novo.</Notice>
        <Botao grande onClick={tentarDeNovo}>Tentar de novo</Botao>
      </div></main>
    )
  }
  if (estado.fase === 'anonimo') return <LoginScreen />
  if (estado.utilizador.mudarPassword) return <ChangePasswordScreen obrigatorio />
  return (
    <ModulosProvider>
      <Routes>
        <Route element={<Shell />}>
          <Route path="/hoje" element={<TodayScreen />} />
          <Route path="/mais" element={<MoreScreen />} />
          <Route path="/peso" element={<ModuloAtivo id="peso" nome="Peso"><PesoScreen /></ModuloAtivo>} />
          <Route path="/rto" element={<ModuloAtivo id="rto" nome="RTO"><RtoScreen /></ModuloAtivo>} />
          <Route path="/tarefas" element={<ModuloAtivo id="tarefas" nome="Tarefas"><TarefasScreen /></ModuloAtivo>} />
          <Route path="/financas" element={<ModuloAtivo id="financas" nome="Finanças"><FinancasScreen /></ModuloAtivo>} />
          <Route path="/compras" element={<ModuloAtivo id="compras" nome="Compras"><ComprasScreen /></ModuloAtivo>} />
          <Route path="/bilhetes" element={<ModuloAtivo id="bilhetes" nome="Bilhetes CP"><BilhetesScreen /></ModuloAtivo>} />
          <Route path="/definicoes" element={<SettingsScreen />} />
          <Route path="/definicoes/password" element={<ChangePasswordScreen />} />
          <Route path="*" element={<Navigate to="/hoje" replace />} />
        </Route>
      </Routes>
    </ModulosProvider>
  )
}

export function App() {
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, '')}>
      <AuthProvider><AvisosProvider><Porta /></AvisosProvider></AuthProvider>
    </BrowserRouter>
  )
}
