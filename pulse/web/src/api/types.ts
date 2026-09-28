export interface Utilizador { id: number; email: string; nome: string; admin: boolean; mudarPassword: boolean }
export interface Sessao { id: number; criada: number; ultimoUso: number; expira: number; dispositivo: string; ip: string; cliente: 'web' | 'android'; atual: boolean }

export type EstadoModulo = 'ok' | 'indisponivel' | 'sem_acesso' | 'erro' | 'nao_ligado'
export interface Modulo<T> { estado: EstadoModulo; dados?: T | null; erro?: { codigo: string; mensagem: string } }

export interface TarefaHoje { id: string; tarefaId: string; nome: string; categoria: string; icone: string; prioridade: 'Alta' | 'Media' | 'Baixa'; hora: string; pessoa: string; estado: string }
export interface TarefasDados { hoje: TarefaHoje[]; atrasadas: number; feitasHoje: number; totalHoje: number; pessoa: string | null }
export interface Viagem { id: number; data: string; origem: string; destino: string; comboio: number; hora: string; compra: { carruagem: string; lugar: string; referencia: string } | null }
export interface BilhetesDados { proximo: Viagem | null; passe: { dataExpira: string | null; diasRestantes: number | null } | null }
export interface DiaRto { data: string; diaSemana: number; marca: 'T' | 'C' | ''; hoje: boolean }
export interface RtoDados { semana: { inicio: string; fim: string }; dias: DiaRto[]; contagem: { T: number; C: number } }
export interface PesoDados { ultimo: { quando: string; peso: number } | null; registadoHoje: boolean; sugestao: number | null }
export interface Conta { id: number; descricao: string; valor: number; categoria: string; dataVencimento: string; diasAte: number; vencida: boolean }
export interface FinancasDados { proximas: Conta[]; vencidas: number; total: number; valorTotal: number }

export interface Hoje {
  estado: 'ok' | 'degradado'
  geradoEm: string
  data: string
  resumo: string | null
  modulos: {
    tarefas: Modulo<TarefasDados>
    bilhetes: Modulo<BilhetesDados>
    rto: Modulo<RtoDados>
    peso: Modulo<PesoDados>
    financas: Modulo<FinancasDados>
    calendario: Modulo<null>
    email: Modulo<null>
  }
}
