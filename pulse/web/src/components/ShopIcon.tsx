import icones from '../assets/shop-icons.json'

const CAMINHOS = icones as Record<string, string[]>

/** Ícone de produto (SVG linear, 24×24). A fonte é `assets/shop-icons.json`, a mesma que o Android converterá em VectorDrawable. */
export function ShopIcon({ nome, tamanho = 28 }: { nome: string; tamanho?: number }) {
  const caminhos = CAMINHOS[nome] ?? CAMINHOS.cesto
  return (
    <svg width={tamanho} height={tamanho} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {caminhos.map((d, i) => <path key={i} d={d} />)}
    </svg>
  )
}

export const NOMES_ICONES = Object.keys(CAMINHOS)
