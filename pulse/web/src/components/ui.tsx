import { useId, useState, type InputHTMLAttributes, type ReactNode } from 'react'
import { Icon, type IconName } from './Icon'

const LOADING_SRC = `${import.meta.env.BASE_URL}pulse-loading.webp`

/** Loading de marca (asset oficial): arranque e ecrãs inteiros. */
export function BrandLoading({ texto = 'A carregar…', full = false }: { texto?: string; full?: boolean }) {
  return (
    <div className={`brand-loading${full ? ' full' : ''}`} role="status" aria-live="polite">
      <img src={LOADING_SRC} alt="" width={96} height={96} />
      <span>{texto}</span>
    </div>
  )
}

export function Spinner() {
  return <span className="spinner" aria-hidden="true" />
}

export function Notice({ tipo, children, role }: { tipo: 'error' | 'warning' | 'info'; children: ReactNode; role?: 'alert' | 'status' }) {
  const icone: IconName = tipo === 'info' ? 'info' : 'alerta'
  return (
    <div className={`notice notice-${tipo}`} role={role ?? (tipo === 'error' ? 'alert' : 'status')}>
      <Icon nome={icone} tamanho={20} />
      <div>{children}</div>
    </div>
  )
}

interface CampoProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'id'> { rotulo: string; erro?: string | null }

export function Campo({ rotulo, erro, ...resto }: CampoProps) {
  const id = useId()
  return (
    <div className="field">
      <label htmlFor={id}>{rotulo}</label>
      <input id={id} className="input" aria-invalid={erro ? true : undefined} aria-describedby={erro ? `${id}-e` : undefined} {...resto} />
      {erro && <span id={`${id}-e`} className="field-error">{erro}</span>}
    </div>
  )
}

export function CampoPassword({ rotulo, erro, ...resto }: CampoProps) {
  const id = useId()
  const [ver, setVer] = useState(false)
  return (
    <div className="field">
      <label htmlFor={id}>{rotulo}</label>
      <div className="input-wrap">
        <input id={id} className="input" type={ver ? 'text' : 'password'} aria-invalid={erro ? true : undefined} aria-describedby={erro ? `${id}-e` : undefined} {...resto} />
        <button type="button" className="input-toggle" onClick={() => setVer((v) => !v)} aria-label={ver ? 'Ocultar palavra-passe' : 'Mostrar palavra-passe'} aria-pressed={ver}>
          <Icon nome={ver ? 'olho-off' : 'olho'} tamanho={20} />
        </button>
      </div>
      {erro && <span id={`${id}-e`} className="field-error">{erro}</span>}
    </div>
  )
}

export function Botao({ children, carregando, variante = 'primary', grande, pequeno, ...resto }: {
  children: ReactNode; carregando?: boolean; variante?: 'primary' | 'secondary' | 'danger'; grande?: boolean; pequeno?: boolean
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button {...resto} disabled={resto.disabled || carregando} className={`btn btn-${variante}${grande ? ' btn-lg' : ''}${pequeno ? ' btn-sm' : ''}`}>
      {carregando && <Spinner />}
      {children}
    </button>
  )
}

export function Esqueleto({ linhas = 3 }: { linhas?: number }) {
  return (
    <ul aria-hidden="true" className="rows">
      {Array.from({ length: linhas }, (_, i) => (
        <li key={i}><div className="skeleton skel-line" data-w={i % 3} /></li>
      ))}
    </ul>
  )
}
