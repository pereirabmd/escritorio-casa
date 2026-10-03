import { Link } from 'react-router-dom'
import { api, mensagemDeErro } from '../api/client'
import { Icon } from '../components/Icon'
import { BrandLoading, Botao, Notice } from '../components/ui'
import { useLocalizacao } from '../lib/localizacao'
import { graus, iconeTempo, type Previsao } from '../lib/tempo'
import { useAsync } from '../lib/useAsync'

export const caminhoTempo = (pos: { lat: number; lon: number } | null) => (pos ? `/weather?lat=${pos.lat}&lon=${pos.lon}` : '/weather')

/** O ecrã do tempo (ADR-092): agora, próximas 24 horas e 5 dias, para onde o aparelho está (ou Aveiro, se não deu a localização). Dados da Open-Meteo. */
export function TempoScreen() {
  const { pos, estado: estadoLoc, pedir } = useLocalizacao()
  const [estado, recarregar] = useAsync(() => api.get<Previsao>(caminhoTempo(pos)), pos ? `${pos.lat},${pos.lon}` : 'omissao')
  return (
    <>
      <header className="hero">
        <Link to="/hoje" className="back"><Icon nome="voltar" tamanho={20} />Hoje</Link>
        <h1 className="t-page">Tempo</h1>
      </header>
      {estado.fase === 'a-carregar' && <BrandLoading texto="A consultar a previsão…" />}
      {estado.fase === 'erro' && (
        <div className="state">
          <Notice tipo="error">{mensagemDeErro(estado.erro)}</Notice>
          <Botao variante="secondary" pequeno onClick={recarregar}>Tentar de novo</Botao>
        </div>
      )}
      {estado.fase === 'pronto' && <Corpo p={estado.dados} semLocal={estadoLoc !== 'ok'} negada={estadoLoc === 'negada'} pedir={pedir} />}
    </>
  )
}

function Corpo({ p, semLocal, negada, pedir }: { p: Previsao; semLocal: boolean; negada: boolean; pedir: () => void }) {
  return (
    <div className="stack">
      {p.localizacao === 'omissao' && (
        <Notice tipo="info">
          Local por omissão: Aveiro. {negada ? 'A permissão de localização foi recusada: dá-a nas definições do browser.' : 'Dá a localização para veres o tempo onde estás.'}
          {semLocal && !negada && <> <button type="button" className="link-btn" onClick={pedir}>Usar a minha localização</button></>}
        </Notice>
      )}
      <section className="card tempo-agora" aria-label="Agora">
        <Icon nome={iconeTempo(p.agora.icone)} tamanho={44} />
        <div>
          <div className="t-metric">{graus(p.agora.temp)}</div>
          <div className="t-body">{p.agora.descricao}</div>
          <div className="t-meta">{p.hoje ? `Máx ${graus(p.hoje.max)} · Mín ${graus(p.hoje.min)}` : ''}{p.agora.vento != null ? ` · vento ${p.agora.vento} km/h` : ''}</div>
          {p.hoje && p.hoje.nascer && <div className="t-meta">Nascer do sol {p.hoje.nascer} · pôr do sol {p.hoje.poer}</div>}
        </div>
      </section>
      <section className="card" aria-label="Próximas 24 horas">
        <h2 className="t-card">Próximas 24 horas</h2>
        <ul className="tempo-horas">
          {p.horas.map((h) => (
            <li key={`${h.dia}-${h.hora}`}>
              <span className="t-meta">{h.hora}</span>
              <Icon nome={iconeTempo(h.icone)} tamanho={22} />
              <span className="t-body">{graus(h.temp)}</span>
              <span className="t-meta">{h.chuva != null && h.chuva > 0 ? `${h.chuva}%` : ' '}</span>
            </li>
          ))}
        </ul>
      </section>
      <section className="card" aria-label="Próximos dias">
        <h2 className="t-card">Próximos dias</h2>
        <ul className="rows">
          {p.dias.map((d, i) => (
            <li key={d.data}>
              <div className="row-main">
                <div className="t-body">{i === 0 ? 'Hoje' : d.diaSemana}</div>
                <div className="t-meta">{d.descricao}{d.chuva != null && d.chuva > 0 ? ` · chuva ${d.chuva}%` : ''}</div>
              </div>
              <Icon nome={iconeTempo(d.icone)} tamanho={24} />
              <span className="row-end t-body">{graus(d.max)} <span className="t-meta">{graus(d.min)}</span></span>
            </li>
          ))}
        </ul>
      </section>
      <p className="t-meta">Previsão da Open-Meteo, atualizada às {p.atualizadoEm.slice(11, 16)}.</p>
    </div>
  )
}
