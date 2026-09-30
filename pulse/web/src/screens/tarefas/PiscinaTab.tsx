import { api, mensagemDeErro } from '../../api/client'
import type { PiscinaCartao, PiscinaDados } from '../../api/types'
import { useAvisos } from '../../components/Avisos'
import { Botao, BrandLoading, Notice } from '../../components/ui'
import { fmtDataIso } from '../../lib/format'
import { useAcao } from '../../lib/useAcao'
import { useAsync } from '../../lib/useAsync'

interface Anterior { ultimaData: string | null; proximaData: string | null; usarIntervaloLongo: boolean; notificacaoEnviada: boolean }

/** Sugerida para hoje ou já passada da data: sobe para o topo e ganha destaque. */
const emDestaque = (c: PiscinaCartao) => c.estado === 'atrasada' || c.destacar === true
const dias = (n: number) => `${n} dia${n === 1 ? '' : 's'}`

function Estado({ c }: { c: PiscinaCartao }) {
  if (c.tipo === 'log') return <>{c.ultima ? `Última vez: ${fmtDataIso(c.ultima)}` : 'Ainda não registada'}</>
  const sugerido = c.proxima ? (c.sugeridoHoje ? 'sugerido para hoje' : `sugerido: ${fmtDataIso(c.proxima)}`) : ''
  if (!c.ultima) return <>Ainda não registada{sugerido && ` · ${sugerido}`}{c.destacar && <> <span className="pill pill-soon">{sugerido}</span></>}</>
  return (
    <>
      Última vez: {fmtDataIso(c.ultima)} (há {dias(c.diasDesde ?? 0)})
      {c.estado === 'atrasada' ? <> <span className="pill pill-soon">por fazer há {dias(c.diasDesde ?? 0)}</span></>
        : c.destacar ? <> <span className="pill pill-soon">{sugerido}</span></>
        : sugerido && ` · ${sugerido}`}
    </>
  )
}

export function PiscinaTab({ atualizar }: { atualizar: () => void }) {
  const [estado, recarregar] = useAsync(() => api.get<PiscinaDados>('/tasks/pool'))
  const { ocupado, erro, executar, limparErro } = useAcao(() => { recarregar(); atualizar() })
  const avisos = useAvisos()

  if (estado.fase === 'a-carregar') return <BrandLoading texto="A carregar a piscina…" />
  if (estado.fase === 'erro') return <div className="state"><Notice tipo="error">{mensagemDeErro(estado.erro)}</Notice><Botao variante="secondary" pequeno onClick={recarregar}>Tentar de novo</Botao></div>
  const d = estado.dados

  async function registar(c: PiscinaCartao) {
    const r = await executar(c.id, 'tarefas.piscina_registar', { item: c.id }) as { anterior?: Anterior } | null
    if (r) avisos.mostrar(`${c.nome} registada.`, r.anterior ? () => void executar(c.id, 'tarefas.piscina_repor', { item: c.id, ...r.anterior }) : undefined)
  }

  const Cartao = ({ c }: { c: PiscinaCartao }) => (
    <li className="piscina-item" data-destaque={emDestaque(c)}>
      <div className="row-main">
        <div className="t-body">{c.nome}{c.nota && <span className="t-meta"> ({c.nota})</span>}</div>
        <div className="t-meta"><Estado c={c} /></div>
        {c.notaLonga && <p className="t-meta nota-longa">{c.notaLonga}</p>}
      </div>
      <Botao variante="secondary" pequeno carregando={ocupado === c.id} disabled={ocupado !== null} aria-label={`${c.tipo === 'log' ? 'Registar agora' : 'Marcar feita hoje'}: ${c.nome}`} onClick={() => void registar(c)}>
        {c.tipo === 'log' ? 'Registar agora' : 'Marcar feita hoje'}
      </Botao>
    </li>
  )

  return (
    <div className="stack">
      {erro && <Notice tipo="error">{erro} <button type="button" className="link-btn" onClick={limparErro}>Fechar</button></Notice>}
      <section className="card" aria-label="Manutenção periódica">
        <h2 className="t-card">Manutenção <span className="t-meta">{d.estacao === 'quente' ? 'meses quentes' : 'meses frios'}</span></h2>
        <ul className="rows">{[...d.periodicas].sort((a, b) => Number(emDestaque(b)) - Number(emDestaque(a))).map((c) => <Cartao key={c.id} c={c} />)}</ul>
      </section>
      <section className="card" aria-label="Outras ações">
        <h2 className="t-card">Outras ações</h2>
        <p className="t-meta">Quando for preciso; só se regista a última vez.</p>
        <ul className="rows">{d.outras.map((c) => <Cartao key={c.id} c={c} />)}</ul>
      </section>
    </div>
  )
}
