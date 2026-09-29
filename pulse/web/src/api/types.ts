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

export interface InstanciaTarefa { id: string; tarefaId: string; nome: string; categoria: string; prioridade: 'Alta' | 'Media' | 'Baixa'; hora: string; pessoa: string; estado: string; data: string; dataConclusao: string }
export interface TarefaCatalogo {
  id: string; nome: string; categoria: string; recorrencia: string; diasSemana: string; diaMes: number | null; horaNotificacao: string
  pessoaPadrao: string; ativa: boolean; prioridade: 'Alta' | 'Media' | 'Baixa'; rotacaoPessoas: string; dependeDe: string; resumo: string; hora: string
}
export interface TarefasModulo {
  data: string; pessoa: string | null; pessoas: string[]; categorias: string[]; horaPadrao: string
  hoje: InstanciaTarefa[]; feitas: InstanciaTarefa[]; atrasadas: InstanciaTarefa[]; amanha: InstanciaTarefa[]; tarefas: TarefaCatalogo[]
}

export interface CalendarioDia { data: string; feriado: string | null; itens: InstanciaTarefa[] }
export interface CalendarioTarefas { de: string; ate: string; hoje: string; horaPadrao: string; dias: CalendarioDia[] }

export interface HorarioAula { disciplina: string; sala: string }
export interface HorarioBloco { ini: string; fim: string; aulas: HorarioAula[]; dividida: boolean; ultima: boolean }
export interface HorarioDia { dia: number; nome: string; entra: string; sai: string; aviso: string; totalAulas: number; slots: HorarioBloco[] }
export interface HorarioDados {
  disponivel: boolean; anoLetivo: string | null; diaHoje: number; avisos: { ativos: boolean; minutos: number } | null
  alunos: { nome: string; dias: HorarioDia[] }[]
}

export interface PiscinaCartao {
  id: string; nome: string; nota: string; notaLonga: string; tipo: 'periodica' | 'log'; ultima: string; proxima: string
  estado: 'nunca' | 'ok' | 'hoje' | 'atrasada' | 'registo'; diasDesde: number | null; sugeridoHoje?: boolean; destacar?: boolean
}
export interface PiscinaDados { estacao: 'quente' | 'fria'; periodicas: PiscinaCartao[]; outras: PiscinaCartao[] }

export interface PainelAdmin {
  raiz: string[]; admins: string[]
  pessoas: { num: number; nome: string; email: string; admin: boolean; fixo: boolean }[]
  notificacoes: { id: string; nome: string; descricao: string; destinatarios: string[]; padrao: boolean }[]
}
export interface DefinicoesTarefas {
  pessoas: { nome: string; email: string }[]; pessoaAtual: string | null; categorias: string[]
  preferencias: { horaPadrao: string; naoIncomodarInicio: string; naoIncomodarFim: string; horarioAvisos: boolean; horarioAvisoMinutos: number }
  resumo: { pessoas: { nome: string; feitas: number }[]; desequilibrio: string | null }
  auditoria: { ts: string; acao: string; tarefa: string; pessoa: string }[]
  souAdmin: boolean; admin: PainelAdmin | null
  saude: { ok?: boolean; saudavel?: boolean; ultimaExecucao?: string | null; minutosDesde?: number | null; contagens?: Record<string, number> } | null
}
export interface HistoricoTarefas { linhas: { tarefa: string; categoria: string; data: string; pessoa: string; estado: string; dataConclusao: string }[] }
