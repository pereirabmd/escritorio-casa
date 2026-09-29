import type { FinancasModulo } from '../../api/types'
import { Notice } from '../../components/ui'
import { fmtDataIso, fmtEuro, plural } from '../../lib/format'
import type { Ferramentas } from './tipos'
import { LinhaConta } from './LancamentosTab'

interface Props { dados: FinancasModulo; modo: 'mes' | '30d'; trocarModo: (m: 'mes' | '30d') => void; f: Ferramentas }

export function ResumoTab({ dados, modo, trocarModo, f }: Props) {
  const { resumo: r, janela, atrasadas } = dados
  const maximo = Math.max(...r.porCategoria.map((c) => c.total), 1)
  return (
    <div className="stack">
      <div className="chips" role="group" aria-label="Período">
        <button type="button" className="chip" aria-pressed={modo === 'mes'} onClick={() => trocarModo('mes')}>Mês</button>
        <button type="button" className="chip" aria-pressed={modo === '30d'} onClick={() => trocarModo('30d')}>Próximos 30 dias</button>
      </div>
      <p className="t-meta">{fmtDataIso(janela.de)} – {fmtDataIso(janela.ate)}</p>

      {atrasadas.itens.length > 0 && (
        <Notice tipo="warning">{plural(atrasadas.itens.length, 'despesa vencida e por pagar', 'despesas vencidas e por pagar')} · {fmtEuro(atrasadas.total)}</Notice>
      )}

      <section className="card" aria-label="Ativo menos passivo">
        <h2 className="t-card">Ativo − passivo</h2>
        <div className="split"><span>Rendimento</span><span className="pill pill-ok">{fmtEuro(r.rendimento)}</span></div>
        <div className="split"><span>Despesas por pagar</span><span>− {fmtEuro(r.porPagar)}</span></div>
        <div className="split"><strong>Saldo do período</strong><strong className={r.saldo < 0 ? 'link-danger' : undefined}>{fmtEuro(r.saldo)}</strong></div>
        {r.saldo < 0 && <p className="t-meta">Défice de {fmtEuro(-r.saldo)}: será preciso cobrir com liquidez ou crédito.</p>}
        {r.emAtraso > 0 && <p className="t-meta">Com as vencidas de antes do período ({fmtEuro(r.emAtraso)}): <strong>{fmtEuro(r.saldoComAtraso)}</strong></p>}
      </section>

      {atrasadas.itens.length > 0 && (
        <section className="card" aria-label="Vencidos e não pagos">
          <h2 className="t-card">Vencidos e não pagos</h2>
          <ul className="rows">{atrasadas.itens.map((l) => <LinhaConta key={l.id} l={l} f={f} />)}</ul>
        </section>
      )}

      <section className="card" aria-label="Despesas por categoria">
        <h2 className="t-card">Despesas por categoria</h2>
        {r.porCategoria.length === 0 ? <p className="t-body2">Sem despesas neste período.</p> : (
          <ul className="rows">
            {r.porCategoria.map((c) => (
              <li key={c.categoriaId}>
                <div className="row-main">
                  <div className="split"><span className="t-body">{c.nome}</span><span className="t-body">{fmtEuro(c.total)}</span></div>
                  <div className="barra" aria-hidden="true"><i style={{ width: `${Math.max(2, (c.total / maximo) * 100)}%`, background: c.cor ?? 'var(--accent)' }} /></div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

