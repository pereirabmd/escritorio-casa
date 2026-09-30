import { useState } from 'react'
import { api, mensagemDeErro } from '../api/client'
import type { ModuloInfo, Pessoa } from '../api/types'
import { useAvisos } from './Avisos'
import { Botao, Esqueleto, Notice } from './ui'
import { useAsync } from '../lib/useAsync'

/** Só para administradores (ADR-063): quem tem conta, o que cada pessoa vê, criar contas novas e repor a palavra-passe provisória. */
export function PessoasAdmin() {
  const [estado, recarregar] = useAsync(async () => ({
    pessoas: (await api.get<{ pessoas: Pessoa[] }>('/admin/users')).pessoas,
    modulos: (await api.get<{ modulos: ModuloInfo[] }>('/modules')).modulos.filter((m) => m.disponivel),
  }))
  const avisos = useAvisos()
  const [erro, setErro] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState<string | null>(null)
  const [nova, setNova] = useState(false)
  const [form, setForm] = useState({ email: '', nome: '', password: '' })
  const [repor, setRepor] = useState<{ id: number; password: string } | null>(null)

  async function correr(chave: string, f: () => Promise<unknown>, ok?: string) {
    setOcupado(chave); setErro(null)
    try { await f(); recarregar(); if (ok) avisos.mostrar(ok) } catch (e) { setErro(mensagemDeErro(e)) } finally { setOcupado(null) }
  }
  const modulos = (p: Pessoa, id: string) => (p.modulos.includes(id) ? p.modulos.filter((m) => m !== id) : [...p.modulos, id])

  return (
    <section className="section" aria-label="Pessoas">
      <h2 className="t-card muted">Pessoas</h2>
      <p className="t-body2">Cada pessoa só vê os módulos que lhe deres e os seus próprios dados (Peso, RTO). Uma conta nova começa com a palavra-passe provisória que indicares e muda-a no primeiro acesso.</p>
      {erro && <Notice tipo="error">{erro}</Notice>}
      {estado.fase === 'a-carregar' && <Esqueleto linhas={3} />}
      {estado.fase === 'erro' && <Notice tipo="error">{mensagemDeErro(estado.erro)} <button type="button" className="link-btn" onClick={recarregar}>Tentar de novo</button></Notice>}
      {estado.fase === 'pronto' && (
        <>
          {estado.dados.pessoas.map((p) => (
            <div className="card" key={p.id} aria-label={p.nome || p.email}>
              <div className="card-head"><h3 className="t-body grow">{p.nome || p.email}{p.admin ? ' · Administrador' : ''}</h3>{!p.ativo && <span className="pill">Desativada</span>}</div>
              <p className="t-meta">{p.email}{p.mudarPassword ? ' · ainda não mudou a palavra-passe' : ''}</p>
              <div className="chips" role="group" aria-label={`Módulos de ${p.nome || p.email}`}>
                {estado.dados.modulos.map((m) => (
                  <button key={m.id} type="button" className="chip" aria-pressed={p.modulos.includes(m.id)} disabled={ocupado !== null}
                    onClick={() => void correr(`${p.id}-${m.id}`, () => api.put(`/admin/users/${p.id}/modules`, { modulos: modulos(p, m.id) }))}>{m.nome}</button>
                ))}
              </div>
              <div className="quick">
                {repor?.id === p.id ? (
                  <>
                    <input className="input input-sm" type="password" autoComplete="new-password" aria-label="Palavra-passe provisória" placeholder="Nova palavra-passe provisória" value={repor.password} onChange={(e) => setRepor({ id: p.id, password: e.target.value })} />
                    <Botao pequeno disabled={repor.password.length < 8 || ocupado !== null} onClick={() => void correr(`rp-${p.id}`, async () => { await api.post(`/admin/users/${p.id}/password`, { password: repor.password }); setRepor(null) }, 'Palavra-passe provisória definida; as sessões dessa pessoa terminaram.')}>Guardar</Botao>
                    <Botao variante="secondary" pequeno onClick={() => setRepor(null)}>Cancelar</Botao>
                  </>
                ) : (
                  <>
                    <button type="button" className="link-btn" onClick={() => setRepor({ id: p.id, password: '' })}>Repor palavra-passe</button>
                    <button type="button" className="link-btn" disabled={ocupado !== null} onClick={() => void correr(`at-${p.id}`, () => api.put(`/admin/users/${p.id}/active`, { ativo: !p.ativo }), p.ativo ? 'Conta desativada.' : 'Conta ativada.')}>{p.ativo ? 'Desativar' : 'Ativar'}</button>
                  </>
                )}
              </div>
            </div>
          ))}
          {nova ? (
            <form className="card stack" aria-label="Nova pessoa" onSubmit={(e) => { e.preventDefault(); void correr('nova', async () => { await api.post('/admin/users', { ...form, modulos: ['compras'] }); setNova(false); setForm({ email: '', nome: '', password: '' }) }, 'Conta criada, com o módulo Compras. Dá-lhe os outros acima.') }}>
              <label className="t-meta" htmlFor="pn-nome">Nome</label>
              <input id="pn-nome" className="input" autoComplete="off" value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} />
              <label className="t-meta" htmlFor="pn-email">E-mail</label>
              <input id="pn-email" className="input" type="email" autoComplete="off" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
              <label className="t-meta" htmlFor="pn-pw">Palavra-passe provisória (mínimo 8)</label>
              <input id="pn-pw" className="input" type="password" autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
              <div className="quick">
                <Botao type="submit" disabled={!form.email.includes('@') || form.password.length < 8 || ocupado !== null} carregando={ocupado === 'nova'}>Criar conta</Botao>
                <Botao variante="secondary" onClick={() => setNova(false)}>Cancelar</Botao>
              </div>
            </form>
          ) : <div><Botao variante="secondary" pequeno onClick={() => setNova(true)}>Adicionar pessoa</Botao></div>}
        </>
      )}
    </section>
  )
}
