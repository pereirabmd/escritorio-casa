import { useRef, useState, type FormEvent } from 'react'
import type { PesoModulo, RegistoPeso } from '../../api/types'
import { Botao } from '../../components/ui'
import { fmtDataIso, fmtPeso } from '../../lib/format'
import { lerPeso, novoCid } from '../../lib/useAcao'
import type { Ferramentas } from './tipos'

const hora = (quando: string) => quando.slice(11, 16)
const paraInput = (quando: string) => quando.slice(0, 16).replace(' ', 'T')     // «2026-09-30 07:30:00» -> «2026-09-30T07:30»
const deInput = (v: string) => `${v.replace('T', ' ')}:00`

function Novo({ dados, executar, ocupado, avisos }: Ferramentas) {
  const [texto, setTexto] = useState(() => (dados.resumo.ultimo ? String(dados.resumo.ultimo.peso).replace('.', ',') : ''))
  const [nota, setNota] = useState('')
  const cid = useRef(novoCid())
  const valor = lerPeso(texto)

  async function registar(ev: FormEvent) {
    ev.preventDefault()
    if (valor === null) return
    if (await executar('novo', 'peso.registar', { peso: valor, nota: nota.trim(), cid: cid.current })) {
      cid.current = novoCid(); setNota('')
      avisos.mostrar('Peso registado.')
    }
  }
  return (
    <form className="card" onSubmit={registar} aria-label="Registar peso">
      <h2 className="t-card">Registar peso</h2>
      <div className="quick">
        <label className="sr-only" htmlFor="peso-novo">Peso em quilogramas</label>
        <input id="peso-novo" className="input input-sm peso-input" inputMode="decimal" autoComplete="off" value={texto} onChange={(e) => setTexto(e.target.value)} aria-invalid={texto !== '' && valor === null ? true : undefined} />
        <span className="t-body2">kg</span>
        <label className="sr-only" htmlFor="peso-nota">Nota (opcional)</label>
        <input id="peso-nota" className="input input-sm grow-input" placeholder="Nota (opcional)" maxLength={500} value={nota} onChange={(e) => setNota(e.target.value)} />
        <Botao type="submit" pequeno carregando={ocupado === 'novo'} disabled={valor === null || ocupado !== null}>Registar</Botao>
      </div>
    </form>
  )
}

function Linha({ r, executar, ocupado, avisos }: { r: RegistoPeso } & Omit<Ferramentas, 'dados'>) {
  const [modo, setModo] = useState<'ver' | 'editar' | 'apagar'>('ver')
  const [texto, setTexto] = useState(String(r.peso).replace('.', ','))
  const [quando, setQuando] = useState(paraInput(r.quando))
  const [nota, setNota] = useState(r.nota)
  const valor = lerPeso(texto)
  const data = fmtDataIso(r.quando)

  async function guardar(ev: FormEvent) {
    ev.preventDefault()
    if (valor === null || !quando) return
    if (await executar(`ed-${r.id}`, 'peso.editar', { registo: r.id, quando: deInput(quando), peso: valor, nota: nota.trim() })) {
      setModo('ver'); avisos.mostrar('Registo atualizado.')
    }
  }
  async function apagar() {
    const apagado = await executar(`del-${r.id}`, 'peso.eliminar', { registo: r.id }, true)
    if (apagado) {
      avisos.mostrar('Registo eliminado.', () => void executar('desfazer', 'peso.registar', { peso: r.peso, quando: r.quando, nota: r.nota }))
    }
  }

  if (modo === 'editar') {
    return (
      <li className="edit">
        <form className="quick" onSubmit={guardar} aria-label={`Editar registo de ${data}`}>
          <input type="datetime-local" className="input input-sm" aria-label="Data e hora" value={quando} onChange={(e) => setQuando(e.target.value)} />
          <input className="input input-sm peso-input" inputMode="decimal" aria-label="Peso em quilogramas" value={texto} onChange={(e) => setTexto(e.target.value)} aria-invalid={valor === null ? true : undefined} />
          <input className="input input-sm grow-input" aria-label="Nota" maxLength={500} value={nota} onChange={(e) => setNota(e.target.value)} />
          <Botao type="submit" pequeno carregando={ocupado === `ed-${r.id}`} disabled={valor === null || !quando || ocupado !== null}>Guardar</Botao>
          <Botao type="button" variante="secondary" pequeno onClick={() => setModo('ver')}>Cancelar</Botao>
        </form>
      </li>
    )
  }
  return (
    <li>
      <div className="row-main"><div className="t-body">{fmtPeso(r.peso)}</div><div className="t-meta">{data} · {hora(r.quando)}{r.nota ? ` · ${r.nota}` : ''}</div></div>
      {modo === 'apagar' ? (
        <div className="quick" role="group" aria-label={`Eliminar registo de ${data}`}>
          <span className="t-meta">Eliminar?</span>
          <Botao variante="danger" pequeno carregando={ocupado === `del-${r.id}`} disabled={ocupado !== null} onClick={() => void apagar()}>Eliminar</Botao>
          <Botao variante="secondary" pequeno onClick={() => setModo('ver')}>Cancelar</Botao>
        </div>
      ) : (
        <>
          <button type="button" className="link-btn" aria-label={`Editar registo de ${data}`} onClick={() => setModo('editar')}>Editar</button>
          <button type="button" className="link-btn link-danger" aria-label={`Eliminar registo de ${data}`} onClick={() => setModo('apagar')}>Eliminar</button>
        </>
      )}
    </li>
  )
}

export function RegistosTab(f: Ferramentas) {
  const { dados, ...resto } = f
  const registos: PesoModulo['registos'] = [...dados.registos].reverse()          // o mais recente primeiro
  return (
    <div className="stack">
      <Novo {...f} />
      <section className="card" aria-label="Lista de registos">
        <h2 className="t-card">Registos <span className="t-meta">{registos.length}</span></h2>
        {registos.length === 0 ? <p className="t-body2">Ainda sem registos.</p> : (
          <ul className="rows">{registos.slice(0, 200).map((r) => <Linha key={r.id} r={r} {...resto} />)}</ul>
        )}
        {registos.length > 200 && <p className="t-meta">A mostrar os 200 mais recentes.</p>}
      </section>
    </div>
  )
}
