export class ApiError extends Error {
  constructor(public status: number, public codigo: string, message: string) {
    super(message)
  }
}

const BASE = `${import.meta.env.BASE_URL}api/v1`
let aoPerderSessao: (() => void) | null = null

/** Chamado quando um pedido autenticado devolve 401 (sessão terminada ou expirada). */
export function definirAoPerderSessao(fn: (() => void) | null) {
  aoPerderSessao = fn
}

async function pedir<T>(metodo: string, caminho: string, corpo?: unknown): Promise<T> {
  let r: Response
  try {
    r = await fetch(`${BASE}${caminho}`, {
      method: metodo,
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-Pulse-Client': 'web' },
      body: corpo === undefined ? undefined : JSON.stringify(corpo),
    })
  } catch {
    throw new ApiError(0, 'rede', 'Sem ligação ao servidor. Verifica a ligação e tenta de novo.')
  }
  let dados: unknown = null
  try {
    dados = await r.json()
  } catch {
    /* corpo vazio ou não-JSON */
  }
  if (!r.ok) {
    const erro = (dados as { erro?: { codigo?: string; mensagem?: string } } | null)?.erro
    const e = new ApiError(r.status, erro?.codigo ?? 'erro', erro?.mensagem ?? 'Ocorreu um erro. Tenta de novo.')
    // só «nao_autenticado» é sessão perdida: um 401 de «password_atual_errada» ou de credenciais não é
    if (r.status === 401 && e.codigo === 'nao_autenticado' && caminho !== '/auth/me') aoPerderSessao?.()
    throw e
  }
  return dados as T
}

export const api = {
  get: <T>(caminho: string) => pedir<T>('GET', caminho),
  post: <T>(caminho: string, corpo?: unknown) => pedir<T>('POST', caminho, corpo ?? {}),
  del: <T>(caminho: string) => pedir<T>('DELETE', caminho),
}

/** Mensagens em pt-PT para os códigos de erro que o utilizador pode provocar. */
export function mensagemDeErro(e: unknown): string {
  if (!(e instanceof ApiError)) return 'Ocorreu um erro inesperado. Tenta de novo.'
  switch (e.codigo) {
    case 'credenciais_invalidas': return 'E-mail ou palavra-passe incorretos.'
    case 'conta_bloqueada':
    case 'demasiadas_tentativas': return 'Demasiadas tentativas. Aguarda alguns minutos e tenta de novo.'
    case 'password_atual_errada': return 'A palavra-passe atual não está certa.'
    case 'password_fraca': return 'A palavra-passe nova é demasiado fraca. Segue as regras indicadas.'
    case 'password_igual': return 'A palavra-passe nova tem de ser diferente da atual.'
    case 'pedido_invalido': return 'Verifica os dados e tenta de novo.'
    case 'rede': return e.message
    default: return e.status >= 500 ? 'O servidor não conseguiu responder. Tenta de novo daqui a pouco.' : e.message
  }
}
