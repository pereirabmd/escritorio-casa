import { useState, type FormEvent } from 'react'
import { mensagemDeErro } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { Botao, Campo, CampoPassword, Notice } from '../components/ui'

export function LoginScreen() {
  const { entrar } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [erro, setErro] = useState<string | null>(null)
  const [aEnviar, setAEnviar] = useState(false)

  async function submeter(ev: FormEvent) {
    ev.preventDefault()
    setErro(null)
    setAEnviar(true)
    try {
      await entrar(email.trim(), password)
    } catch (e) {
      setErro(mensagemDeErro(e))
      setPassword('')
    } finally {
      setAEnviar(false)
    }
  }

  return (
    <main className="auth">
      <div className="auth-panel">
        <div className="auth-brand">
          <img src={`${import.meta.env.BASE_URL}pulse-icon-192.png`} alt="" width={56} height={56} />
          <h1 className="t-page">Iniciar sessão</h1>
          <p className="t-body2">Entra na tua conta Pulse.</p>
        </div>
        <form onSubmit={submeter} noValidate>
          {erro && <Notice tipo="error">{erro}</Notice>}
          <Campo rotulo="E-mail" type="email" name="email" autoComplete="username" inputMode="email" autoCapitalize="none" spellCheck={false} required value={email} onChange={(e) => setEmail(e.target.value)} />
          <CampoPassword rotulo="Palavra-passe" name="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          <Botao type="submit" grande carregando={aEnviar} disabled={!email.trim() || !password}>Iniciar sessão</Botao>
        </form>
        <p className="t-meta">Não tens conta? As contas são criadas pelo administrador. Se te esqueceste da palavra-passe, pede-lhe que a reponha.</p>
      </div>
    </main>
  )
}
