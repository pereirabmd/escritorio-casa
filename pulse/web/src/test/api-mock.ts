import { vi } from 'vitest'

type Resposta = [number, unknown] | Error
export type Rotas = Record<string, (corpo: unknown) => Resposta | Promise<Resposta>>

/** Substitui `fetch` por um servidor falso: as chaves são «METODO /caminho» (sem o prefixo /api/v1). */
export function servidorFalso(rotas: Rotas) {
  const pedidos: { metodo: string; caminho: string; corpo: unknown; cabecalhos: Record<string, string> }[] = []
  const fetchFalso = vi.fn(async (url: string, init?: RequestInit) => {
    const caminho = String(url).replace(/^(\/pulse)?\/api\/v1/, '')
    const metodo = init?.method ?? 'GET'
    const corpo = init?.body ? JSON.parse(String(init.body)) : undefined
    pedidos.push({ metodo, caminho, corpo, cabecalhos: init?.headers as Record<string, string> })
    const rota = rotas[`${metodo} ${caminho}`]
    if (!rota) return new Response(JSON.stringify({ erro: { codigo: 'nao_encontrado', mensagem: 'x' } }), { status: 404 })
    const r = await rota(corpo)
    if (r instanceof Error) throw r
    return new Response(JSON.stringify(r[1]), { status: r[0], headers: { 'Content-Type': 'application/json' } })
  })
  vi.stubGlobal('fetch', fetchFalso)
  return { pedidos, fetchFalso }
}

export const UTILIZADOR = { id: 1, email: 'pereirabmd@gmail.com', nome: 'Bruno Pereira', admin: true, mudarPassword: false }

export const HOJE = {
  estado: 'ok', geradoEm: '2026-09-30T10:00:00+01:00', data: '2026-09-30', resumo: null,
  modulos: {
    tarefas: { estado: 'ok', dados: { hoje: [
      { id: 'I1', tarefaId: 'T1', nome: 'Limpar WC', categoria: 'Limpeza', icone: '', prioridade: 'Alta', hora: '09:00', pessoa: 'Bruno', estado: 'Pendente' },
      { id: 'I2', tarefaId: 'T2', nome: 'Levar o lixo', categoria: '', icone: '', prioridade: 'Baixa', hora: '', pessoa: '', estado: 'Pendente' }],
      atrasadas: 1, feitasHoje: 1, totalHoje: 3, pessoa: 'Bruno' } },
    bilhetes: { estado: 'ok', dados: { proximo: { id: 1, data: '2026-10-01', origem: 'Aveiro', destino: 'Lisboa Oriente', comboio: 520, hora: '07:27', compra: { carruagem: '21', lugar: '53', referencia: 'R' } },
      passe: { dataExpira: '2026-10-20', diasRestantes: 20 } } },
    rto: { estado: 'ok', dados: { semana: { inicio: '2026-09-28', fim: '2026-10-04' }, contagem: { T: 2, C: 1 },
      dias: ['2026-09-28', '2026-09-29', '2026-09-30', '2026-10-01', '2026-10-02', '2026-10-03', '2026-10-04'].map((data, i) => ({ data, diaSemana: i + 1, marca: (['T', 'C', 'T', '', '', '', ''] as const)[i], hoje: i === 2 })) } },
    peso: { estado: 'ok', dados: { ultimo: { quando: '2026-09-30 07:30:00', peso: 104.8 }, registadoHoje: true, sugestao: 104.8 } },
    financas: { estado: 'ok', dados: { proximas: [
      { id: 2, descricao: 'Luz', valor: 1245.5, categoria: 'Habitação', dataVencimento: '2026-10-05', diasAte: 5, vencida: false },
      { id: 1, descricao: 'Água', valor: 20, categoria: 'Habitação', dataVencimento: '2026-09-27', diasAte: -3, vencida: true }], vencidas: 1, total: 2, valorTotal: 1265.5 } },
    compras: { estado: 'ok', dados: { lista: { id: 1, nome: 'Casa' }, pendentes: 7, itens: [
      { item: 10, produto: 1, nome: 'Maçã', categoria: 'frutas-legumes', icone: 'fruta', quantidade: 6, nota: '' },
      { item: 11, produto: 2, nome: 'Leite meio-gordo', categoria: 'laticinios', icone: 'leite', quantidade: null, nota: '1 L' }] } },
    calendario: { estado: 'nao_ligado', dados: null }, email: { estado: 'nao_ligado', dados: null },
  },
}
