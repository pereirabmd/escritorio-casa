/** Nível de atividade: a config pode ter valores antigos (1-4) ou intermédios; os ecrãs só mostram 1,2 / 1,45 / 1,7. */
export function normalizarAtividade(raw: number | undefined | null): number {
  if (!raw || Number.isNaN(raw)) return 1.2
  const escala: Record<number, number> = { 1: 1.2, 2: 1.45, 3: 1.7, 4: 1.7 }
  if (Number.isInteger(raw) && escala[raw]) return escala[raw]
  if (raw >= 1.2 && raw <= 1.725) return [1.2, 1.45, 1.7].reduce((a, b) => (Math.abs(b - raw) < Math.abs(a - raw) ? b : a), 1.2)
  return 1.2
}
