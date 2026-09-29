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

export interface RegistoPeso { id: number; quando: string; peso: number; nota: string }
export interface ConfigPeso { altura?: number; nascimento?: string; sexo?: 'M' | 'F'; pesoAlvo?: number; atividade?: number; diaControlo?: number; pesoMin?: number; pesoMax?: number }
export interface AnalisePeso {
  tendencia: { kgSemana: number; dias: number; pontos: number } | null
  mensal: { diff: number } | null
  melhorSemana: { diff: number } | null
  piorSemana: { diff: number } | null
}
export interface ResumoPeso {
  analise: AnalisePeso
  previsao: { estado: 'poucos_registos' | 'sem_alvo' | 'atingido' | 'sem_tendencia' | 'ok'; data?: string; kgSemana?: number }
  ultimo: { id: number; quando: string; peso: number } | null
  anterior?: { quando: string; peso: number; diferenca: number } | null
  sequenciaDias?: number
  novoMinimo?: boolean
  controlo?: 'acima' | 'abaixo' | 'dentro' | null
  progresso?: { pct: number; inicial: number; alvo: number } | null
  totalPerdido?: number
  ritmo?: { kgDia: number; kgSemana: number } | null
  faltam?: { kg: number; atingido: boolean } | null
  imc?: { valor: number; classe: string } | null
  gastoDiario?: number | null
  minimo?: number
  maximo?: number
  registos?: number
}
export interface PesoModulo { registos: RegistoPeso[]; config: ConfigPeso; resumo: ResumoPeso }

export interface NotaRto { id: number; dataInicio: string | null; dataFim: string | null; categoria: string; descricao: string }
export interface TotaisRto {
  T: number; C: number; CCondicional: number; creditosAstreinte: number; decorridos: number; diasAno: number
  quotaAnual: number; quotaProRata: number; saldo: number; saldoCondicional: number; pctQuota: number
}
export interface HojeRto { estado: 'escritorio' | 'casa' | 'ferias' | 'feriado' | 'fim_de_semana' | 'astreinte' | 'por_definir'; nome?: string; astreinte: boolean }
export interface RtoModulo {
  ano: number; quotaAnual: number
  dias: Record<string, 'T' | 'C'>
  notas: NotaRto[]
  feriados: Record<string, string>
  ferias: string[]; astreinte: string[]; suspensao: string[]
  marcasNotas: Record<string, 'F' | 'A'>
  totais: TotaisRto
  mensal: { t: number; c: number }[]
  dezembroAnterior: { t: number; c: number }
  hoje: HojeRto
  proximaMudanca: { tipo: 'feriado' | 'ferias'; dias: number; nome?: string; data: string } | null
}
