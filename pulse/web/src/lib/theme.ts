export type Tema = 'sistema' | 'claro' | 'escuro'
const CHAVE = 'pulse.tema'

export function lerTema(): Tema {
  try {
    const v = localStorage.getItem(CHAVE)
    return v === 'claro' || v === 'escuro' ? v : 'sistema'
  } catch {
    return 'sistema'
  }
}

export function aplicarTema(t: Tema): void {
  const raiz = document.documentElement
  if (t === 'sistema') raiz.removeAttribute('data-theme')
  else raiz.setAttribute('data-theme', t === 'claro' ? 'light' : 'dark')
}

export function guardarTema(t: Tema): void {
  try {
    if (t === 'sistema') localStorage.removeItem(CHAVE)
    else localStorage.setItem(CHAVE, t)
  } catch {
    /* sem armazenamento (modo privado): a escolha vale só nesta sessão */
  }
  aplicarTema(t)
}
