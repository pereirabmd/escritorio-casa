import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, mensagemDeErro } from '../api/client'
import { useAuth, useUtilizador } from '../auth/AuthContext'
import { Icon } from '../components/Icon'
import { Botao, CampoPassword, Notice } from '../components/ui'
import { regras, todasOk } from '../lib/passwordRules'

/** Primeiro acesso (`obrigatorio`): ecrã único, sem navegação. Depois: o mesmo formulário em Definições → Conta. */
export function ChangePasswordScreen({ obrigatorio = false }: { obrigatorio?: boolean }) {
  const utilizador = useUtilizador()
  const { passwordMudada, sair } = useAuth()
  const [atual, setAtual] = useState('')
  const [nova, setNova] = useState('')
  const [confirmacao, setConfirmacao] = useState('')
  const [erro, setErro] = useState<string | null>(null)
  const [aEnviar, setAEnviar] = useState(false)
  const [feito, setFeito] = useState(false)

  const rs = regras(nova, atual, utilizador.email)
  const diferente = confirmacao.length > 0 && confirmacao !== nova
  const pronto = atual.length > 0 && todasOk(rs) && confirmacao === nova

  async function submeter(ev: FormEvent) {
    ev.preventDefault()
    if (!pronto) return
    setErro(null)
    setAEnviar(true)
    try {
      await api.post('/auth/password', { atual, nova })
      setAtual(''); setNova(''); setConfirmacao('')
      if (obrigatorio) passwordMudada()
      else setFeito(true)
    } catch (e) {
      setErro(mensagemDeErro(e))
    } finally {
      setAEnviar(false)
    }
  }

  const formulario = (
    <form onSubmit={submeter} noValidate>
      {/* o campo de utilizador ajuda os gestores de passwords a associar a mudança à conta certa */}
      <input type="text" name="username" autoComplete="username" value={utilizador.email} readOnly hidden />
      {erro && <Notice tipo="error">{erro}</Notice>}
      <CampoPassword rotulo="Palavra-passe atual" name="atual" autoComplete="current-password" value={atual} onChange={(e) => setAtual(e.target.value)} />
      <CampoPassword rotulo="Palavra-passe nova" name="nova" autoComplete="new-password" value={nova} onChange={(e) => setNova(e.target.value)} />
      <ul className="rules" aria-label="Regras da palavra-passe nova">
        {rs.map((r) => (
          <li key={r.id} data-ok={r.ok}>
            <Icon nome={r.ok ? 'certo' : 'ponto'} tamanho={16} />
            <span>{r.texto}<span className="sr-only">{r.ok ? ' — cumprido' : ' — por cumprir'}</span></span>
          </li>
        ))}
      </ul>
      <CampoPassword rotulo="Confirmar palavra-passe nova" name="confirmacao" autoComplete="new-password" value={confirmacao} onChange={(e) => setConfirmacao(e.target.value)} erro={diferente ? 'As palavras-passe não coincidem.' : null} />
      <Botao type="submit" grande carregando={aEnviar} disabled={!pronto}>Mudar palavra-passe</Botao>
    </form>
  )

  if (obrigatorio) {
    return (
      <main className="auth">
        <div className="auth-panel">
          <div className="auth-brand">
            <img src={`${import.meta.env.BASE_URL}pulse-icon-192.png`} alt="" width={56} height={56} />
            <h1 className="t-page">Define a tua palavra-passe</h1>
            <p className="t-body2">A palavra-passe que recebeste é provisória. Escolhe uma nova para continuar.</p>
          </div>
          {formulario}
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => void sair()}>Terminar sessão</button>
        </div>
      </main>
    )
  }

  return (
    <div className="section narrow">
      <Link to="/definicoes" className="back"><Icon nome="voltar" tamanho={20} />Definições</Link>
      <h1 className="t-page">Mudar palavra-passe</h1>
      {feito ? (
        <Notice tipo="info" role="status">Palavra-passe mudada. Terminámos as outras sessões; esta continua ativa.</Notice>
      ) : formulario}
    </div>
  )
}
