/** Com o teclado virtual aberto o campo em foco tem de ficar à vista: a barra de baixo esconde-se e o campo vai para o centro. */
const CAMPOS = 'input, textarea, select, [contenteditable="true"]'

export function vigiarTeclado(): void {
  const vv = window.visualViewport
  const atualizar = () => {
    const aberto = !!vv && window.innerHeight - vv.height > 150 && !!document.activeElement?.matches(CAMPOS)
    document.documentElement.toggleAttribute('data-teclado', aberto)
  }
  vv?.addEventListener('resize', atualizar)
  document.addEventListener('focusin', (e) => {
    const alvo = e.target as HTMLElement
    if (!alvo.matches?.(CAMPOS)) return
    atualizar()
    // dá tempo ao teclado para abrir antes de centrar o campo
    window.setTimeout(() => alvo.scrollIntoView?.({ block: 'center', behavior: 'smooth' }), 300)
  })
  document.addEventListener('focusout', () => window.setTimeout(atualizar, 100))
}
