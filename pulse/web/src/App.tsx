import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth/AuthContext'
import { Shell } from './components/Shell'
import { Icon } from './components/Icon'
import { BrandLoading, Botao, Notice } from './components/ui'
import { ChangePasswordScreen } from './screens/ChangePasswordScreen'
import { LoginScreen } from './screens/LoginScreen'
import { MoreScreen } from './screens/MoreScreen'
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
    <Routes>
      <Route element={<Shell />}>
        <Route path="/hoje" element={<TodayScreen />} />
        <Route path="/mais" element={<MoreScreen />} />
        <Route path="/definicoes" element={<SettingsScreen />} />
        <Route path="/definicoes/password" element={<ChangePasswordScreen />} />
        <Route path="*" element={<Navigate to="/hoje" replace />} />
      </Route>
    </Routes>
  )
}

export function App() {
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, '')}>
      <AuthProvider><Porta /></AuthProvider>
    </BrowserRouter>
  )
}
