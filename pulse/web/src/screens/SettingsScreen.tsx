import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, mensagemDeErro } from '../api/client'
import type { ContaGoogle, ServicoGoogle, Sessao } from '../api/types'
import { useAuth, useUtilizador } from '../auth/AuthContext'
import { Icon } from '../components/Icon'
import { Botao, Esqueleto, Notice } from '../components/ui'
import { irPara } from '../lib/navegacao'
import { useModulos } from '../lib/modulos'
import { useAsync } from '../lib/useAsync'
import { aplicarTema, guardarTema, lerTema, type Tema } from '../lib/theme'
import { VERSAO } from '../version'

const TEMAS: { id: Tema; nome: string }[] = [{ id: 'sistema', nome: 'Sistema' }, { id: 'claro', nome: 'Claro' }, { id: 'escuro', nome: 'Escuro' }]

const quando = (s: number) => new Date(s * 1000).toLocaleString('pt-PT', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })

function dispositivo(s: Sessao): string {
  if (s.cliente === 'android') return 'Aplicação Android'
  const ua = s.dispositivo
  const nav = /Firefox\//.test(ua) ? 'Firefox' : /Edg\//.test(ua) ? 'Edge' : /Chrome\//.test(ua) ? 'Chrome' : /Safari\//.test(ua) ? 'Safari' : 'Browser'
  const so = /Android/.test(ua) ? 'Android' : /iPhone|iPad/.test(ua) ? 'iOS' : /Windows/.test(ua) ? 'Windows' : /Mac OS/.test(ua) ? 'macOS' : /Linux/.test(ua) ? 'Linux' : ''
  return so ? `${nav} em ${so}` : nav
}

function Sessoes() {
  const [estado, recarregar] = useAsync(() => api.get<{ sessoes: Sessao[] }>('/auth/sessions'))
  const [erro, setErro] = useState<string | null>(null)

  async function terminar(id: number) {
    setErro(null)
    try {
      await api.del(`/auth/sessions/${id}`)
      recarregar()
    } catch (e) {
      setErro(mensagemDeErro(e))
    }
  }

  return (
    <section className="section" aria-label="Sessões e dispositivos">
      <h2 className="t-card muted">Sessões e dispositivos</h2>
      {erro && <Notice tipo="error">{erro}</Notice>}
      {estado.fase === 'a-carregar' && <div className="list"><div className="list-item"><Esqueleto linhas={2} /></div></div>}
      {estado.fase === 'erro' && <Notice tipo="error">{mensagemDeErro(estado.erro)} <button className="btn btn-secondary btn-sm" onClick={recarregar}>Tentar de novo</button></Notice>}
      {estado.fase === 'pronto' && (
        <div className="list">
          {estado.dados.sessoes.map((s) => (
            <div className="list-item" key={s.id}>
              <Icon nome="dispositivo" />
              <div className="row-main"><div className="t-body">{dispositivo(s)}{s.atual && <> <span className="pill pill-ok">Esta sessão</span></>}</div><div className="t-meta">Último uso: {quando(s.ultimoUso)}</div></div>
              {!s.atual && <Botao variante="secondary" pequeno onClick={() => void terminar(s.id)} aria-label={`Terminar sessão em ${dispositivo(s)}`}>Terminar</Botao>}
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

const MOTIVOS_GOOGLE: Record<string, string> = {
  recusado: 'Não deste as permissões à Google. Podes tentar de novo quando quiseres.', estado_invalido: 'O pedido de ligação expirou. Tenta de novo.',
  sem_permissoes: 'A conta não deu as permissões pedidas.', sem_refresh_token: 'A Google não deu acesso duradouro. Remove a app em myaccount.google.com/permissions e liga de novo.',
  google_recusou: 'A Google recusou o pedido. Tenta de novo.', google_desligado: 'A integração com a Google não está configurada neste servidor.', invalido: 'O regresso da Google foi inválido.',
}

/** Ligar Gmail e Calendar: o servidor guarda o acesso; a Web nunca vê tokens. */
function ContasGoogle() {
  const [estado, recarregar] = useAsync(() => api.get<{ configurado: boolean; contas: ContaGoogle[] }>('/google/accounts'))
  const [params] = useSearchParams()
  const [servicos, setServicos] = useState<ServicoGoogle[]>(['gmail', 'calendar'])
  const [ocupado, setOcupado] = useState<string | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [remover, setRemover] = useState<number | null>(null)
  const resultado = params.get('google')

  async function ligar() {
    setOcupado('ligar'); setErro(null)
    try {
      irPara((await api.post<{ url: string }>('/google/connect', { servicos })).url)
    } catch (e) {
      setErro(mensagemDeErro(e)); setOcupado(null)
    }
  }
  async function apagar(id: number) {
    setOcupado(`rm-${id}`); setErro(null)
    try {
      await api.del(`/google/accounts/${id}`)
      setRemover(null); recarregar()
    } catch (e) {
      setErro(mensagemDeErro(e))
    } finally {
      setOcupado(null)
    }
  }
  const alternar = (s: ServicoGoogle) => setServicos((atual) => (atual.includes(s) ? atual.filter((x) => x !== s) : [...atual, s]))

  return (
    <section className="section" aria-label="Contas Google">
      <h2 className="t-card muted">Contas Google</h2>
      <p className="t-body2">Liga contas para ver o Gmail e o Calendar no Pulse. O acesso fica guardado (cifrado) no servidor e podes removê-lo quando quiseres. O Pulse nunca envia nem apaga emails.</p>
      {resultado === 'ok' && <Notice tipo="info">Conta Google ligada.</Notice>}
      {resultado === 'erro' && <Notice tipo="error">{MOTIVOS_GOOGLE[params.get('motivo') ?? ''] ?? 'Não foi possível ligar a conta Google.'}</Notice>}
      {erro && <Notice tipo="error">{erro}</Notice>}
      {estado.fase === 'a-carregar' && <div className="list"><div className="list-item"><Esqueleto linhas={2} /></div></div>}
      {estado.fase === 'erro' && <Notice tipo="error">{mensagemDeErro(estado.erro)} <button className="btn btn-secondary btn-sm" onClick={recarregar}>Tentar de novo</button></Notice>}
      {estado.fase === 'pronto' && (
        <>
          {estado.dados.contas.length > 0 && (
            <div className="list">
              {estado.dados.contas.map((c) => (
                <div className="list-item" key={c.id}>
                  <div className="row-main">
                    <div className="t-body">{c.email}{c.estado === 'reautorizar' && <> <span className="pill pill-soon">Volta a ligar</span></>}</div>
                    <div className="t-meta">{c.servicos.map((x) => (x === 'gmail' ? 'Gmail' : 'Calendário')).join(' · ')}</div>
                  </div>
                  {remover === c.id ? (
                    <span role="group" aria-label={`Remover ${c.email}`} className="quick">
                      <Botao variante="danger" pequeno carregando={ocupado === `rm-${c.id}`} disabled={ocupado !== null} onClick={() => void apagar(c.id)}>Remover</Botao>
                      <Botao variante="secondary" pequeno onClick={() => setRemover(null)}>Cancelar</Botao>
                    </span>
                  ) : <Botao variante="secondary" pequeno onClick={() => setRemover(c.id)} aria-label={`Remover a conta ${c.email}`}>Remover</Botao>}
                </div>
              ))}
            </div>
          )}
          {!estado.dados.configurado ? <Notice tipo="warning">A integração com a Google ainda não está configurada neste servidor (ver <code>pulse/docs/GOOGLE_SETUP.md</code>).</Notice> : (
            <div className="stack">
              <div className="chips" role="group" aria-label="O que ligar">
                <button type="button" className="chip" aria-pressed={servicos.includes('gmail')} onClick={() => alternar('gmail')}>Gmail</button>
                <button type="button" className="chip" aria-pressed={servicos.includes('calendar')} onClick={() => alternar('calendar')}>Calendário</button>
              </div>
              <div><Botao pequeno carregando={ocupado === 'ligar'} disabled={servicos.length === 0 || ocupado !== null} onClick={() => void ligar()}>Ligar conta Google</Botao></div>
            </div>
          )}
        </>
      )}
    </section>
  )
}

/** Só para administradores: ativar ou desativar módulos para todos os utilizadores. */
function AdministracaoModulos() {
  const { lista, definir } = useModulos()
  const [ocupado, setOcupado] = useState<string | null>(null)
  const [erro, setErro] = useState<string | null>(null)

  async function alternar(id: string, ativo: boolean) {
    setOcupado(id); setErro(null)
    try {
      definir((await api.put<{ modulos: typeof lista }>('/admin/modules', { modulos: { [id]: ativo } })).modulos)
    } catch (e) {
      setErro(mensagemDeErro(e))
    } finally {
      setOcupado(null)
    }
  }
  return (
    <section className="section" aria-label="Administração">
      <h2 className="t-card muted">Administração</h2>
      <p className="t-body2">Módulos: um módulo desativado desaparece do Hoje e de Mais para todos os utilizadores, e o servidor recusa os pedidos que lhe chegarem.</p>
      {erro && <Notice tipo="error">{erro}</Notice>}
      <div className="list" role="group" aria-label="Módulos">
        {lista.map((m) => (
          <div className="list-item" key={m.id}>
            <span className="row-main">{m.nome}</span>
            {m.disponivel ? (
              <button type="button" role="switch" className="chip" aria-checked={m.ativo} aria-label={`${m.nome}: ${m.ativo ? 'ativo' : 'desativado'}`}
                disabled={ocupado !== null} onClick={() => void alternar(m.id, !m.ativo)}>{m.ativo ? 'Ativo' : 'Desativado'}</button>
            ) : <span className="pill">Em breve</span>}
          </div>
        ))}
      </div>
    </section>
  )
}

export function SettingsScreen() {
  const u = useUtilizador()
  const { sair } = useAuth()
  const [tema, setTema] = useState<Tema>(lerTema)

  return (
    <>
      <header className="hero"><h1 className="t-page">Definições</h1></header>
      <section className="section" aria-label="Conta">
        <h2 className="t-card muted">Conta</h2>
        <div className="list">
          <div className="list-item"><div className="row-main"><div className="t-body">{u.nome || u.email}</div><div className="t-meta">{u.email}{u.admin ? ' · Administrador' : ''}</div></div></div>
          <Link to="/definicoes/password" className="list-item"><Icon nome="chave" /><span className="row-main">Mudar palavra-passe</span><Icon nome="seta" tamanho={18} /></Link>
        </div>
      </section>
      <ContasGoogle />
      {u.admin && <AdministracaoModulos />}
      <Sessoes />
      <section className="section" aria-label="Aparência">
        <h2 className="t-card muted">Aparência</h2>
        <div className="segmented" role="group" aria-label="Tema">
          {TEMAS.map((t) => (
            <button key={t.id} aria-pressed={tema === t.id} onClick={() => { setTema(t.id); guardarTema(t.id); aplicarTema(t.id) }}>{t.nome}</button>
          ))}
        </div>
      </section>
      <section className="section" aria-label="App Android">
        <h2 className="t-card muted">App Android</h2>
        <p className="t-body2">A app nativa do Pulse, instalada fora da Play Store. A app atualiza-se sozinha a partir daqui.</p>
        <div><a className="btn btn-secondary btn-sm" href={`${import.meta.env.BASE_URL}apk/pulse.apk`}>Descarregar o APK</a></div>
      </section>
      <section className="section" aria-label="Sistema">
        <h2 className="t-card muted">Sistema</h2>
        <p className="t-body2">Pulse Web {VERSAO}</p>
        <div><Botao variante="danger" onClick={() => void sair()}><Icon nome="sair" tamanho={20} />Terminar sessão</Botao></div>
      </section>
    </>
  )
}
