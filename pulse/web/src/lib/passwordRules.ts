// Regras mostradas enquanto se escreve. A validação final é sempre do servidor (`password_fraca`, `password_igual`…).
export interface Regra { id: string; texto: string; ok: boolean }

const FRACAS = new Set(['1234567890', 'password12', 'qwertyuiop', '1234qwer12', 'passw0rd12'])

export function regras(nova: string, atual: string, email: string): Regra[] {
  const previsivel = FRACAS.has(nova.toLowerCase()) || nova.toLowerCase() === email.toLowerCase() || nova.toLowerCase() === email.split('@')[0].toLowerCase()
  return [
    { id: 'tamanho', texto: 'Pelo menos 10 caracteres', ok: nova.length >= 10 },
    { id: 'variedade', texto: 'Não demasiado repetitiva', ok: new Set(nova).size >= 5 },
    { id: 'previsivel', texto: 'Nada previsível (como o e-mail ou 1234567890)', ok: nova.length > 0 && !previsivel },
    { id: 'diferente', texto: 'Diferente da palavra-passe atual', ok: nova.length > 0 && nova !== atual },
  ]
}

export const todasOk = (rs: Regra[]) => rs.every((r) => r.ok)
