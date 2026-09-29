import { useState, type FormEvent } from 'react'
import { Botao, Notice } from '../../components/ui'
import { normalizarAtividade } from '../../lib/peso'
import type { Ferramentas } from './tipos'

const DIAS = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']
const ATIVIDADES = [['1.2', 'Pouco ativo'], ['1.45', 'Moderadamente ativo'], ['1.7', 'Muito ativo']]
const num = (t: string) => (t.trim() === '' ? null : Number(t.trim().replace(',', '.')))

export function ConfigTab({ dados, executar, ocupado, avisos }: Ferramentas) {
  const c = dados.config
  const [altura, setAltura] = useState(c.altura?.toString().replace('.', ',') ?? '')
  const [nascimento, setNascimento] = useState(c.nascimento ?? '')
  const [sexo, setSexo] = useState(c.sexo ?? '')
  const [alvo, setAlvo] = useState(c.pesoAlvo?.toString().replace('.', ',') ?? '')
  const [atividade, setAtividade] = useState(String(normalizarAtividade(c.atividade)))
  const [dia, setDia] = useState(String(c.diaControlo ?? 0))
  const [pmin, setPmin] = useState(c.pesoMin?.toString().replace('.', ',') ?? '')
  const [pmax, setPmax] = useState(c.pesoMax?.toString().replace('.', ',') ?? '')
  const [erro, setErro] = useState<string | null>(null)

  async function guardar(ev: FormEvent) {
    ev.preventDefault()
    const v = { altura: num(altura), pesoAlvo: num(alvo), pesoMin: num(pmin), pesoMax: num(pmax) }
    for (const [k, x] of Object.entries(v)) {
      if (x !== null && (!Number.isFinite(x) || x <= 0)) { setErro(`Valor inválido em ${k === 'altura' ? 'Altura' : k === 'pesoAlvo' ? 'Peso alvo' : k === 'pesoMin' ? 'Peso mínimo' : 'Peso máximo'}.`); return }
    }
    if (v.pesoMin !== null && v.pesoMax !== null && v.pesoMin > v.pesoMax) { setErro('O peso mínimo não pode ser maior do que o máximo.'); return }
    setErro(null)
    const ok = await executar('config', 'peso.configurar', { ...v, nascimento: nascimento || null, sexo: sexo || null, atividade: Number(atividade), diaControlo: Number(dia) })
    if (ok) avisos.mostrar('Configuração guardada.')
  }

  return (
    <form className="card narrow" onSubmit={guardar} aria-label="Configuração do Peso">
      {erro && <Notice tipo="error">{erro}</Notice>}
      <h2 className="t-card">Corpo</h2>
      <div className="fields">
        <div className="field"><label htmlFor="cf-altura">Altura (cm)</label><input id="cf-altura" className="input" inputMode="decimal" value={altura} onChange={(e) => setAltura(e.target.value)} /></div>
        <div className="field"><label htmlFor="cf-nasc">Data de nascimento</label><input id="cf-nasc" className="input" type="date" value={nascimento} onChange={(e) => setNascimento(e.target.value)} /></div>
        <div className="field"><label htmlFor="cf-sexo">Sexo</label>
          <select id="cf-sexo" className="input" value={sexo} onChange={(e) => setSexo(e.target.value as '' | 'M' | 'F')}><option value="">—</option><option value="M">Masculino</option><option value="F">Feminino</option></select></div>
        <div className="field"><label htmlFor="cf-ativ">Nível de atividade</label>
          <select id="cf-ativ" className="input" value={atividade} onChange={(e) => setAtividade(e.target.value)}>{ATIVIDADES.map(([v, n]) => <option key={v} value={v}>{n}</option>)}</select></div>
      </div>
      <h2 className="t-card">Objetivo de peso</h2>
      <div className="fields">
        <div className="field"><label htmlFor="cf-alvo">Peso alvo (kg)</label><input id="cf-alvo" className="input" inputMode="decimal" value={alvo} onChange={(e) => setAlvo(e.target.value)} /></div>
        <div className="field"><label htmlFor="cf-min">Peso mínimo de controlo (kg)</label><input id="cf-min" className="input" inputMode="decimal" value={pmin} onChange={(e) => setPmin(e.target.value)} /></div>
        <div className="field"><label htmlFor="cf-max">Peso máximo de controlo (kg)</label><input id="cf-max" className="input" inputMode="decimal" value={pmax} onChange={(e) => setPmax(e.target.value)} /></div>
        <div className="field"><label htmlFor="cf-dia">Dia de controlo</label>
          <select id="cf-dia" className="input" value={dia} onChange={(e) => setDia(e.target.value)}>{DIAS.map((n, i) => <option key={n} value={i}>{n}</option>)}</select></div>
      </div>
      <Botao type="submit" grande carregando={ocupado === 'config'} disabled={ocupado !== null}>Guardar configuração</Botao>
    </form>
  )
}
