export interface Utilizador { id: number; email: string; nome: string; admin: boolean; mudarPassword: boolean }
export interface Sessao { id: number; criada: number; ultimoUso: number; expira: number; dispositivo: string; ip: string; cliente: 'web' | 'android'; atual: boolean }

export type EstadoModulo = 'ok' | 'indisponivel' | 'sem_acesso' | 'erro' | 'nao_ligado' | 'desativado'
export interface ModuloInfo { id: string; nome: string; disponivel: boolean; ativo: boolean }
export interface Modulo<T> { estado: EstadoModulo; dados?: T | null; erro?: { codigo: string; mensagem: string } }

export interface TarefaHoje { id: string; tarefaId: string; nome: string; categoria: string; icone: string; prioridade: 'Alta' | 'Media' | 'Baixa'; hora: string; pessoa: string; estado: string }
export interface TarefasDados { hoje: TarefaHoje[]; atrasadas: number; feitasHoje: number; totalHoje: number; pessoa: string | null }
export interface Viagem { id: number; data: string; origem: string; destino: string; comboio: number; hora: string; fimEstimado?: string; emCurso?: boolean; compra: { carruagem: string; lugar: string; referencia: string } | null }
export interface BilhetesDados { proximo: Viagem | null; passe: { dataExpira: string | null; diasRestantes: number | null } | null }
export interface DiaRto { data: string; diaSemana: number; marca: 'T' | 'C' | ''; hoje: boolean }
export interface RtoDados { semana: { inicio: string; fim: string }; dias: DiaRto[]; contagem: { T: number; C: number } }
export interface PesoDados { ultimo: { quando: string; peso: number } | null; registadoHoje: boolean; sugestao: number | null }
export interface Conta { id: number; descricao: string; valor: number; categoria: string; dataVencimento: string; diasAte: number; vencida: boolean }
export interface FinancasDados { proximas: Conta[]; vencidas: number; total: number; valorTotal: number }

export interface CalendarioHoje { eventos: EventoGoogle[]; total: number; contas: number; comProblemas: EstadoContaGoogle[] }
export interface EmailHoje { porLer: number; mensagens: MensagemGoogle[]; contas: number; comProblemas: EstadoContaGoogle[] }
export interface ComprasHoje { lista: { id: number; nome: string }; pendentes: number; itens: { item: number; produto: number; nome: string; categoria: string; icone: string; quantidade: number | null; nota: string }[] }

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
    compras?: Modulo<ComprasHoje>
    calendario: Modulo<CalendarioHoje>
    email: Modulo<EmailHoje>
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

// --- Finanças (GET /finance, /finance/reports, /finance/reminders) ---
export interface CategoriaFin { id: number; nome: string; cor: string | null }
export interface LancamentoFin {
  id: number; tipo: 'despesa' | 'rendimento'; descricao: string; valor: number; categoria_id: number; categoria: string
  data_vencimento: string; data_pagamento: string | null; recorrente: boolean; mes_referencia: string; estado: 'pago' | 'vencido' | 'hoje' | 'pendente'
}
export interface FinancasModulo {
  mes: string; hoje: string; categorias: CategoriaFin[]
  totaisMes: { rendimento: number; despesas: number; porPagar: number }
  lancamentos: LancamentoFin[]
  atrasadas: { total: number; itens: LancamentoFin[] }
  janela: { modo: 'mes' | '30d'; de: string; ate: string }
  resumo: { rendimento: number; porPagar: number; saldo: number; emAtraso: number; saldoComAtraso: number; porCategoria: { categoriaId: number; nome: string; cor: string | null; total: number }[] }
}
export interface RelatorioFin {
  de: string; ate: string; meses: { mes: string; rendimento: number; despesas: number; saldo: number }[]
  categorias: { categoriaId: number; nome: string; cor: string | null; total: number; meses: Record<string, number> }[]
  totais: { rendimento: number; despesas: number }
}
export interface LembreteFin { id: number; titulo: string; nota: string; data: string; hora: string; repeticao: 'unica' | 'mensal'; ativo: boolean; ultimo_aviso: string | null }

// --- Bilhetes CP (GET /tickets) ---
export type EstadoViagem = 'comprado' | 'por_comprar' | 'inativa' | 'em_curso' | 'passada'
export interface ViagemBilhetes {
  id: number; data: string; hora: string; origem: string; destino: string; comboio: number; ativo: boolean; estado: EstadoViagem; fimEstimado: string
  compra: { carruagem: string; lugar: string; referencia: string } | null
}
export interface BilheteCp { id: number; data: string; hora: string; origem: string; destino: string; comboio: number; carruagem: string; lugar: string; referencia: string }
export interface PedidoCp {
  id: number; data: string; hora: string; origem: string; destino: string; comboio: number; ativo: boolean; retry: boolean; intervaloMinutos: number | null
  forcar: boolean; estado: string; ultimaTentativa: string | null; referencia: string | null; mensagem: string | null
}
export interface RegistoCp { ts: string; tipo: string; data: string | null; perna: string | null; comboio: number | null; status: number | null; resultado: string | null; referencia: string | null; erro: string | null }
export interface BilhetesModulo {
  hoje: string
  passe: { dataUltimaCompra: string | null; validadeDias: number; dataExpira: string | null; diasRestantes: number | null; estado: 'sem_data' | 'expirado' | 'hoje' | 'a_expirar' | 'ok'; percentagem: number | null }
  proxima: ViagemBilhetes | null; proximas: ViagemBilhetes[]
  semanaSeguinte: { inicio: string; ativas: number }
  semana: { inicio: string; dias: string[]; viagens: ViagemBilhetes[] }
  bilhetes: { proximos: BilheteCp[]; anteriores: BilheteCp[] }
  pedidos: PedidoCp[]; registo: RegistoCp[]
  estacoes: string[]; historico: { comboio: number; origem: string; destino: string; hora: string }[]
}

// --- Compras (GET /shopping) ---
export interface ListaCompras { id: number; nome: string; tipo: 'partilhada' | 'pessoal'; padrao: boolean; pendentes: number; total: number }
export interface ItemCompras { id: number; lista: number; produto: number; nome: string; categoria: string; icone: string; quantidade: number | null; nota: string; estado: 'pendente' | 'comprado'; adicionadoPor: string; compradoEm: number | null }
export interface ProdutoCompras { id: number; nome: string; categoria: string; icone: string; builtin: boolean; criadoPor: number | null; favorito: boolean; oculto: boolean; item: number | null; estado: 'pendente' | 'comprado' | null }
export interface SugestaoCompras { produto: number; nome: string; categoria: string; icone: string; ultima: string; diasDesde: number; compras: number; intervaloDias?: number }
export interface ComprasModulo {
  categorias: { id: string; nome: string; oculta: boolean }[]
  sugestoes: { acabar: SugestaoCompras[]; frequentes: SugestaoCompras[] }
  listas: ListaCompras[]; lista: ListaCompras
  grupos: { categoria: { id: string; nome: string }; itens: ItemCompras[] }[]
  comprados: ItemCompras[]; pendentes: number
  produtos: ProdutoCompras[]
}

// --- Google: contas, Calendar e Gmail (GET /google/accounts, /calendar, /mail) ---
export type ServicoGoogle = 'gmail' | 'calendar'
export interface ContaGoogle { id: number; email: string; nome: string; servicos: ServicoGoogle[]; estado: 'ok' | 'reautorizar' }
export interface EstadoContaGoogle { id: number; email: string; estado: 'ok' | 'reautorizar' | 'erro'; erro?: string; total?: number }
export interface EventoGoogle {
  id: string; conta: number; contaEmail: string; calendario: string; calendarioNome: string; cor: string | null; titulo: string; data: string; dataFim: string
  inicio: string | null; fim: string | null; diaInteiro: boolean; local: string; descricao: string; link: string; podeEditar: boolean
}
export interface AgendaGoogle {
  ligado: boolean; configurado: boolean; de: string; ate: string; contas: EstadoContaGoogle[]
  calendarios: { conta: number; id: string; nome: string; cor: string | null; principal: boolean; podeEditar: boolean }[]
  dias: { data: string; eventos: EventoGoogle[] }[]
}
export interface MensagemGoogle { id: string; conta: number; contaEmail: string; thread: string; de: string; deEmail: string; assunto: string; resumo: string; data: string; lida: boolean; estrela: boolean; importante: boolean; entrada: boolean }
export interface MensagemDetalhe extends MensagemGoogle { para: string; corpo: string; temAnexos: boolean }
export interface CaixaGoogle { ligado: boolean; configurado: boolean; filtro: string; contas: EstadoContaGoogle[]; mensagens: MensagemGoogle[] }
