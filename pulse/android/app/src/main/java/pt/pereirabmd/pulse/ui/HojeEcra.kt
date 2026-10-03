package pt.pereirabmd.pulse.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.runtime.*
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.draw.clip
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import pt.pereirabmd.pulse.data.*
import pt.pereirabmd.pulse.util.*
import java.util.Calendar
import kotlinx.coroutines.launch

val CARTOES_ORIGEM = listOf("calendario", "tarefas", "email", "bilhetes", "rto", "peso", "compras", "financas")

private sealed interface EstadoHoje {
    data object ACarregar : EstadoHoje
    data class Erro(val mensagem: String) : EstadoHoje
    data class Pronto(val hoje: Hoje) : EstadoHoje
}

private val DIA = listOf("S", "T", "Q", "Q", "S", "S", "D")

@Composable
private fun Abrir(rota: String) { val abrir = LocalAbrir.current; LinkBtn("Abrir", { abrir(rota.trimStart('/')) }) }

/** O tempo de hoje, em pequeno, à direita da saudação; tocar abre o ecrã Tempo (ADR-092). Se a previsão falhar o cartão simplesmente não aparece. */
@Composable
private fun CartaoTempo() {
    val pos = LocalPosicao.current
    val abrir = LocalAbrir.current
    val c = carga("tempo|$pos") { Api.get(Localizacao.caminho(pos)) }
    val p = (c.estado as? Estado.Pronto)?.dados ?: return
    val cores = Pulse.cores
    val hoje = p.obj("hoje"); val agora = p.obj("agora")
    val max = hoje?.real("max"); val min = hoje?.real("min"); val chuva = hoje?.inteiroOuNull("chuva") ?: 0
    val descr = "Tempo: ${agora?.txtOu("descricao").orEmpty()}, ${graus(agora?.real("temp"))}, máxima ${graus(max)}, mínima ${graus(min)}" + (if (chuva > 0) ", chuva $chuva%" else "") + ". Abrir a previsão"
    Column(Modifier.clip(RoundedCornerShape(Pulse.rL)).background(cores.surface).border(1.dp, cores.line, RoundedCornerShape(Pulse.rL))
        .clickable(onClickLabel = "Abrir a previsão do tempo") { abrir("tempo") }.padding(10.dp).widthIn(min = 84.dp).semantics { contentDescription = descr },
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Icon(iconeTempo(agora?.txtOu("icone").orEmpty()), cores.primary, 28.dp)
        Texto(graus(agora?.real("temp")), Pulse.card)
        Meta("${graus(max)} / ${graus(min)}" + if (chuva > 0) " · $chuva%" else "")
    }
}

/** O toque no cartão: leva ao módulo (`rota`), ou a uma aba/mensagem dele (`email/<conta>:<id>`). */
@Composable
private fun tocar(rota: String): () -> Unit { val abrir = LocalAbrir.current; return { abrir(rota.trimStart('/')) } }

/** Um módulo que não está `ok` mostra o motivo no próprio cartão; o resto do Hoje continua a funcionar. */
@Composable
private fun <T> Estado(m: Modulo<T>, conteudo: @Composable ColumnScope.(T) -> Unit) {
    val d = m.dados
    if (m.ok && d != null) { Column(verticalArrangement = Arrangement.spacedBy(8.dp)) { conteudo(d) }; return }
    val texto = when (m.estado) {
        "indisponivel" -> "Indisponível de momento. Tentamos de novo quando atualizares."
        "erro" -> "Não foi possível carregar esta informação."
        else -> "Sem dados."
    }
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
        Icon(Icone.ALERTA, Pulse.cores.text2, 18.dp); Texto2(texto)
    }
}

@Composable
private fun LigarGoogle(icone: Icone, titulo: String, texto: String) {
    val abrir = LocalAbrir.current
    Cartao(icone, titulo) {
        Texto2(texto)
        LinkBtn("Ligar conta Google", { abrir("google") })
    }
}

@Composable
private fun Problemas(emails: List<String>) {
    if (emails.isEmpty()) return
    val abrir = LocalAbrir.current
    Meta("A conta ${emails.joinToString(", ")} pede nova autorização.")
    LinkBtn("Volta a ligá-la", { abrir("google") })
}

@Composable private fun Mais(n: Int) = Meta("e mais $n")

@Composable
private fun CartaoCalendario(m: Modulo<CalendarioDados>) {
    if (m.estado == "nao_ligado") return LigarGoogle(Icone.CALENDARIO, "Próximos eventos", "Liga uma conta Google para veres aqui os próximos eventos.")
    Cartao(Icone.CALENDARIO, "Próximos eventos", aoTocar = tocar("/calendario"), extra = { Abrir("/calendario") }) {
        Estado(m) { d ->
            if (d.eventos.isEmpty()) Texto2("Sem eventos marcados.")
            else d.eventos.forEach { e ->
                Linha(inicio = { Column(Modifier.widthIn(min = 72.dp)) { Meta(quandoEvento(e.data)); Meta(if (e.diaInteiro) "Dia todo" else e.inicio) } }) {
                    Texto(e.titulo); if (e.local.isNotEmpty()) Meta(e.local)
                }
            }
            Problemas(d.comProblemas)
        }
    }
}

@Composable
private fun CartaoTarefas(m: Modulo<TarefasDados>, acoes: Acoes, hoje: String, otimista: ((Hoje) -> Hoje) -> Unit, recarregarTudo: () -> Unit) {
    val avisos = LocalAvisos.current
    var adiar by remember { mutableStateOf<Tarefa?>(null) }
    Cartao(Icone.TAREFAS, "Tarefas de hoje", aoTocar = tocar("/tarefas"), extra = {
        m.dados?.takeIf { it.totalHoje > 0 }?.let { Meta("${it.feitasHoje} de ${it.totalHoje}") }; Abrir("/tarefas")
    }) {
        Estado(m) { d ->
            if (d.hoje.isEmpty()) Texto2(if (d.totalHoje > 0) "Tudo feito por hoje." else "Sem tarefas para hoje.")
            else d.hoje.take(5).forEach { t ->
                Linha(inicio = { Visto(false, {
                    // a tarefa sai logo da lista; se o servidor recusar, o Hoje volta a pedir tudo e ela regressa
                    otimista { h -> h.tarefas.dados?.let { d -> h.copy(tarefas = h.tarefas.copy(dados = d.copy(hoje = d.hoje.filter { x -> x.id != t.id }, feitasHoje = d.feitasHoje + 1))) } ?: h }
                    acoes.executar(t.id, "tarefas.concluir", jo("instancia" to t.id), aoFalhar = recarregarTudo) { r ->
                        val tambem = r.strs("tambem")
                        avisos.mostrar("Tarefa concluída.") { acoes.executar(t.id, "tarefas.reabrir", jo("instancia" to t.id, "tambem" to ja(tambem))) }
                    }
                }, "Concluir ${t.nome}", acoes.ocupado == t.id, acoes.ocupado == null) }, fim = { LinkBtn("Adiar", { adiar = t }) }) {
                    Texto(t.nome); Meta(listOf(t.categoria, t.hora).filter { it.isNotEmpty() }.joinToString(" · "))
                }
            }
            if (d.hoje.size > 5) Mais(d.hoje.size - 5)
            if (d.atrasadas > 0) Meta(plural(d.atrasadas, "tarefa por concluir de dias anteriores", "tarefas por concluir de dias anteriores"))
            if (d.piscina.isNotEmpty()) {
                Texto("Piscina", Pulse.body.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold))
                d.piscina.forEach { p ->
                    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).background(Pulse.cores.warningBg).padding(horizontal = 8.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Visto(false, {
                            acoes.executar("pisc-${p.id}", "tarefas.piscina_registar", jo("item" to p.id)) { r ->
                                val a = r.obj("anterior")
                                avisos.mostrar("${p.nome} registada.", a?.let { x -> { acoes.executar("pisc-${p.id}", "tarefas.piscina_repor", jo("item" to p.id, "ultimaData" to x.txt("ultimaData"), "proximaData" to x.txt("proximaData"),
                                    "usarIntervaloLongo" to x.bool("usarIntervaloLongo"), "notificacaoEnviada" to x.bool("notificacaoEnviada"))) } })
                            }
                        }, "Marcar feita hoje: ${p.nome}", acoes.ocupado == "pisc-${p.id}", acoes.ocupado == null)
                        Column(Modifier.weight(1f)) {
                            Texto(p.nome + if (p.nota.isNotEmpty()) " (${p.nota})" else "")
                            Meta(if (p.estado == "atrasada") "Atrasada${p.diasDesde?.let { " · há ${plural(it, "dia", "dias")}" } ?: ""}" else if (p.ultima.isNotEmpty()) "Para hoje" else "Ainda não registada · sugerida para hoje")
                        }
                    }
                }
            }
            d.horario?.let { Texto2("${it.aluno} sai às ${it.sai} · aviso às ${it.aviso}") }
        }
    }
    adiar?.let { t -> FolhaAdiar(jo("id" to t.id, "nome" to t.nome), hoje, acoes, avisos) { adiar = null } }
}

@Composable
private fun CartaoEmail(m: Modulo<EmailDados>) {
    val abrirMensagem = LocalAbrir.current
    if (m.estado == "nao_ligado") return LigarGoogle(Icone.EMAIL, "Emails importantes", "Liga uma conta Google para veres aqui os emails importantes por ler.")
    Cartao(Icone.EMAIL, "Emails importantes", aoTocar = tocar("/email"), extra = { m.dados?.takeIf { it.porLer > 0 }?.let { Meta("${it.porLer} por ler") }; Abrir("/email") }) {
        Estado(m) { d ->
            if (d.mensagens.isEmpty()) Texto2("Nada importante por ler.")
            else d.mensagens.forEach { x -> Linha(Modifier.clip(RoundedCornerShape(Pulse.rXs)).clickable(onClickLabel = "Abrir a mensagem") { abrirMensagem("email/${x.conta}:${x.id}") }) { Texto(x.de, Pulse.body.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold)); Texto2(x.assunto) } }
            if (d.porLer > d.mensagens.size) Mais(d.porLer - d.mensagens.size)
            Problemas(d.comProblemas)
        }
    }
}

@Composable
private fun CartaoBilhetes(m: Modulo<BilhetesDados>) {
    Cartao(Icone.BILHETE, "Próximo comboio", aoTocar = tocar("/bilhetes"), extra = { Abrir("/bilhetes") }) {
        Estado(m) { d ->
            val v = d.proximo
            if (v == null) Texto2("Sem viagens agendadas.")
            else {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Texto(v.hora, Pulse.section); Texto(v.origem); Icon(Icone.SETA, Pulse.cores.text2, 16.dp); Texto(v.destino)
                }
                Texto2("${fmtDiaMes(v.data)} · Comboio ${v.comboio}")
                if (v.emCurso) Pilula("Em viagem · chega por volta das ${v.fimEstimado.orEmpty()}", Pulse.cores.warning, Pulse.cores.warningBg)
                if (v.compra != null) Pilula("Comprado · carruagem ${v.compra.carruagem}, lugar ${v.compra.lugar}", Pulse.cores.success) else Pilula("Por comprar")
            }
            val p = d.passe
            if (p != null && p.diasRestantes != null && p.dataExpira != null)
                Meta("Passe válido até ${fmtDataIso(p.dataExpira)} (${plural(maxOf(p.diasRestantes, 0), "dia", "dias")})")
        }
    }
}

@Composable
private fun CartaoRto(m: Modulo<RtoDados>, acoes: Acoes, hoje: String, atualizar: () -> Unit) {
    val c = Pulse.cores; val avisos = LocalAvisos.current; val scope = rememberCoroutineScope()
    var otim by remember(m) { mutableStateOf(emptyMap<String, String>()) }        // a marca aparece logo; o servidor confirma em segundo plano
    var pendentes by remember { mutableIntStateOf(0) }
    Cartao(Icone.RTO, "RTO desta semana", aoTocar = tocar("/rto"), extra = { m.dados?.let { Meta("${it.escritorio} escritório · ${it.casa} casa") }; Abrir("/rto") }) {
        Estado(m) { d ->
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                d.dias.forEach { dia ->
                    val marca = otim[dia.data] ?: dia.marca
                    Column(Modifier.clip(RoundedCornerShape(8.dp)).clickable {
                        if (diaBloqueado(dia.data, hoje)) avisos.mostrar("Fim de semana ou dia passado: para alterar, usa o modo administrador no ecrã do RTO.")
                        else {
                            val nova = proximaMarca(marca)
                            otim = otim + (dia.data to nova); pendentes++
                            scope.launch {
                                try { Api.post("/actions/rto.marcar_dia", jo("params" to jo("data" to dia.data, "marca" to nova))) }
                                catch (e: Exception) { if (e is kotlinx.coroutines.CancellationException) throw e; otim = otim - dia.data; acoes.erro = mensagemDeErro(e) }
                                finally { pendentes--; if (pendentes == 0) atualizar() }
                            }
                        }
                    }.padding(horizontal = 6.dp, vertical = 4.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Meta(DIA[(dia.diaSemana - 1).coerceIn(0, 6)])
                        Texto(dia.data.takeLast(2).toInt().toString(), Pulse.card, if (dia.hoje) c.primary else c.text)
                        Texto(marca.ifEmpty { "·" }, Pulse.meta, when (marca) { "T" -> c.primary; "C" -> c.success; else -> c.text2 })
                    }
                }
            }
            Meta("Toca num dia: T · Escritório → C · Casa → vazio")
        }
    }
}

@Composable
private fun CartaoPeso(m: Modulo<PesoDados>, acoes: Acoes, sugestao: Double?, otimista: ((Hoje) -> Hoje) -> Unit, recarregarTudo: () -> Unit) {
    val avisos = LocalAvisos.current
    var texto by remember(sugestao) { mutableStateOf(decimalTexto(sugestao)) }
    var cid by remember { mutableStateOf(novoCid()) }
    val valor = lerDecimal(texto)?.takeIf { it in 1.0..1000.0 }
    Cartao(Icone.PESO, "Peso", aoTocar = tocar("/peso"), extra = { Abrir("/peso") }) {
        Estado(m) { d ->
            // uma só caixa: editável enquanto falta o registo de hoje; depois passa a mostrar o peso de hoje, sem editar
            if (d.registadoHoje && d.ultimoPeso != null) {
                Texto(fmtPeso(d.ultimoPeso), Pulse.metric)
                Texto2("Registo de hoje feito.")
            } else {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.Bottom) {
                    Campo("Peso de hoje (kg)", texto, { texto = it }, Modifier.weight(1f), teclado = TecladoNumero, erro = if (texto.isNotEmpty() && valor == null) "Entre 1 e 1000." else null)
                    Botao("Registar", {
                        // o cartão passa logo a «registo de hoje feito»; se o servidor recusar, o Hoje volta a pedir tudo e o campo regressa
                        otimista { h -> h.peso.dados?.let { d -> h.copy(peso = h.peso.copy(dados = d.copy(registadoHoje = true, ultimoPeso = valor, ultimoQuando = "${h.data} 00:00:00"))) } ?: h }
                        acoes.executar("peso", "peso.registar", jo("peso" to valor, "cid" to cid), aoFalhar = recarregarTudo) { cid = novoCid(); avisos.mostrar("Peso registado.") }
                    },
                        pequeno = true, ativo = valor != null && acoes.ocupado == null, carregando = acoes.ocupado == "peso")
                }
                Meta(if (d.ultimoPeso != null) "Último registo: ${fmtPeso(d.ultimoPeso)} a ${fmtDataIso(d.ultimoQuando.orEmpty())}. Ainda não registaste hoje." else "Ainda sem registos de peso.")
            }
        }
        m.dados?.let { MinimapaPeso(it.ultimos7) }
    }
}

/** Os últimos 7 dias do peso, em pequeno: uma linha e um ponto por dia com registo; os dias sem registo ficam em branco. */
@Composable
private fun MinimapaPeso(pontos: List<Pair<String, Double>>) {
    if (pontos.size < 2) { Meta("Com 2 registos nos últimos 7 dias aparece aqui o gráfico."); return }
    val c = Pulse.cores
    val hoje = java.time.LocalDate.now()
    fun dia(iso: String): Int = runCatching { java.time.temporal.ChronoUnit.DAYS.between(java.time.LocalDate.parse(iso), hoje).toInt() }.getOrDefault(6).coerceIn(0, 6)
    val primeiro = pontos.first().second; val ultimo = pontos.last().second; val dif = ultimo - primeiro
    var v0 = pontos.minOf { it.second }; var v1 = pontos.maxOf { it.second }
    if (v1 - v0 < 0.4) { v0 -= 0.2; v1 += 0.2 }
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
        androidx.compose.foundation.Canvas(Modifier.weight(1f).height(48.dp).semantics { this.contentDescription = "Peso nos últimos 7 dias: de ${fmtPeso(primeiro)} a ${fmtPeso(ultimo)}, ${pontos.size} registos" }) {
            val pad = 6.dp.toPx()
            fun x(iso: String) = pad + ((6 - dia(iso)) / 6f) * (size.width - 2 * pad)
            fun y(v: Double) = pad + (1 - ((v - v0) / (v1 - v0)).toFloat()) * (size.height - 2 * pad)
            val path = androidx.compose.ui.graphics.Path().apply { pontos.forEachIndexed { i, p -> if (i == 0) moveTo(x(p.first), y(p.second)) else lineTo(x(p.first), y(p.second)) } }
            drawPath(path, c.primary, style = androidx.compose.ui.graphics.drawscope.Stroke(width = 2.25.dp.toPx(), cap = androidx.compose.ui.graphics.StrokeCap.Round, join = androidx.compose.ui.graphics.StrokeJoin.Round))
            pontos.forEach { p -> drawCircle(c.surface, 3.5.dp.toPx(), androidx.compose.ui.geometry.Offset(x(p.first), y(p.second))); drawCircle(c.primary, 3.5.dp.toPx(), androidx.compose.ui.geometry.Offset(x(p.first), y(p.second)), style = androidx.compose.ui.graphics.drawscope.Stroke(1.75.dp.toPx())) }
        }
        Meta("7 dias: " + if (dif == 0.0) "igual" else (if (dif > 0) "+" else "−") + "%.1f".format(java.util.Locale("pt", "PT"), kotlin.math.abs(dif)) + " kg")
    }
}

@Composable
private fun CartaoCompras(m: Modulo<ComprasDados>, acoes: Acoes) {
    val avisos = LocalAvisos.current
    Cartao(Icone.COMPRAS, "Lista de compras", aoTocar = tocar("/compras"), extra = { m.dados?.takeIf { it.pendentes > 0 }?.let { Meta("${it.pendentes} por comprar") }; Abrir("/compras") }) {
        Estado(m) { d ->
            if (d.itens.isEmpty()) Texto2("Nada por comprar.")
            else d.itens.forEach { i ->
                Linha(inicio = { Visto(false, {
                    acoes.executar("compra-${i.item}", "compras.comprado", jo("item" to i.item, "comprado" to true)) {
                        avisos.mostrar("${i.nome} comprado.") { acoes.executar("desfazer", "compras.comprado", jo("item" to i.item, "comprado" to false)) }
                    }
                }, "Marcar como comprado: ${i.nome}", acoes.ocupado == "compra-${i.item}", acoes.ocupado == null) }) {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) { Texto(i.nome); if (i.quantidade != null) Pilula("${i.quantidade}×") }; if (i.nota.isNotEmpty()) Meta(i.nota)
                }
            }
            if (d.pendentes > d.itens.size) Mais(d.pendentes - d.itens.size)
        }
    }
}

@Composable
private fun CartaoFinancas(m: Modulo<FinancasDados>, acoes: Acoes) {
    val avisos = LocalAvisos.current
    Cartao(Icone.FINANCAS, "Contas a pagar", aoTocar = tocar("/financas"), extra = { m.dados?.takeIf { it.total > 0 }?.let { Meta("${fmtEuro(it.valorTotal)} em ${it.total}") }; Abrir("/financas") }) {
        Estado(m) { d ->
            if (d.proximas.isEmpty()) Texto2("Sem contas pendentes nos próximos 30 dias.")
            else d.proximas.forEach { c ->
                Linha(fim = {
                    Column(horizontalAlignment = Alignment.End) { Texto(fmtEuro(c.valor)); Meta(if (c.vencida) "Venceu ${fmtDias(c.diasAte)}" else "Vence ${fmtDias(c.diasAte)}") }
                    LinkBtn("Pagar", {
                        acoes.executar("conta-${c.id}", "financas.pagar", jo("lancamento" to c.id)) {
                            avisos.mostrar("${c.descricao} marcada como paga.") { acoes.executar("desfazer", "financas.anular_pagamento", jo("lancamento" to c.id)) }
                        }
                    })
                }) { Texto(c.descricao); Meta(c.categoria) }
            }
        }
    }
}

private fun resumo(h: Hoje): String = buildList {
    val t = h.tarefas.dados
    if (h.tarefas.ok && t != null) add(if (t.hoje.isNotEmpty()) plural(t.hoje.size, "tarefa para hoje", "tarefas para hoje") else "Sem tarefas por fazer hoje")
    val v = h.bilhetes.dados?.proximo
    if (h.bilhetes.ok && v != null) add("próximo comboio ${fmtDiaMes(v.data)} às ${v.hora}")
}.joinToString(" · ")

/** O último Hoje carregado, só da conta que o carregou (nunca se mostra o de outra pessoa). */
internal object UltimoHoje {
    private var utilizador = -1
    private var hoje: Hoje? = null
    fun de(id: Int): Hoje? = hoje.takeIf { utilizador == id }
    fun guardar(id: Int, h: Hoje) { utilizador = id; hoje = h }
}

@Composable
fun EcraHoje(sessao: Sessao, utilizador: Utilizador, cabecalho: @Composable () -> Unit) {
    // ao voltar ao Hoje (do «Mais», por exemplo) mostra-se logo o último e atualiza-se em segundo plano, em vez de recomeçar do zero (o Google demora ~3 s)
    val contextoWidget = LocalContext.current.applicationContext
    var estado by remember { mutableStateOf<EstadoHoje>(UltimoHoje.de(utilizador.id)?.let { EstadoHoje.Pronto(it) } ?: EstadoHoje.ACarregar) }
    LaunchedEffect(estado) { (estado as? EstadoHoje.Pronto)?.let { UltimoHoje.guardar(utilizador.id, it.hoje) } }
    var versao by remember { mutableIntStateOf(0) }
    val scope = rememberCoroutineScope()
    // depois de uma ação só o módulo dela volta a ser pedido (o resto não mudou e a Google é lenta); se falhar, pede-se tudo
    fun atualizar(modulos: Set<String>) {
        scope.launch {
            try {
                val novo = parseHoje(Api.get("/dashboard/today?modulos=${modulos.joinToString(",")}"))
                (estado as? EstadoHoje.Pronto)?.let { estado = EstadoHoje.Pronto(it.hoje.fundir(novo, modulos)) }
            } catch (e: Exception) { if (e is kotlinx.coroutines.CancellationException) throw e; versao++ }
        }
    }
    fun otimista(alterar: (Hoje) -> Hoje) { (estado as? EstadoHoje.Pronto)?.let { estado = EstadoHoje.Pronto(alterar(it.hoje)) } }
    val acoes = rememberAcoes { nome -> atualizar(setOf(nome.substringBefore('.'))) }
    LaunchedEffect(versao) {
        if (estado is EstadoHoje.Erro) estado = EstadoHoje.ACarregar
        estado = try {
            val json = Api.get("/dashboard/today")
            EstadoHoje.Pronto(parseHoje(json)).also { runCatching { pt.pereirabmd.pulse.widgets.Widgets.aoCarregarHoje(contextoWidget, json, null) } }      // os widgets mostram o mesmo Hoje, sem novo pedido
        } catch (e: Exception) {
            if (e is kotlinx.coroutines.CancellationException) throw e
            if (estado is EstadoHoje.Pronto) estado else EstadoHoje.Erro(mensagemDeErro(e))          // com o último Hoje à vista, uma falha não o apaga
        }
    }
    val agora = Calendar.getInstance()
    val nome = utilizador.nome.trim().substringBefore(' ')
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.Top) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Texto2(fmtDataLonga(agora))
                    Texto(saudacao(agora.get(Calendar.HOUR_OF_DAY)) + if (nome.isNotEmpty()) ", $nome" else "", Pulse.page)
                    (estado as? EstadoHoje.Pronto)?.let { Texto2(resumo(it.hoje)) }
                }
                CartaoTempo()
            }
        }
        item { cabecalho() }
        when (val e = estado) {
            EstadoHoje.ACarregar -> item { BrandLoading("A preparar o teu dia…") }
            is EstadoHoje.Erro -> item { EstadoErro(e.mensagem) { versao++ } }
            is EstadoHoje.Pronto -> {
                val h = e.hoje
                item { ErroAcao(acoes) }
                if (h.degradado) item { Aviso(TipoAviso.AVISO, "Alguns módulos não responderam (${h.falhados().joinToString(", ")}). O resto está atualizado.") }
                val cartoes = mutableMapOf<String, @Composable () -> Unit>()
                if (!h.calendario.escondido) cartoes["calendario"] = { CartaoCalendario(h.calendario) }
                if (!h.tarefas.escondido) cartoes["tarefas"] = { CartaoTarefas(h.tarefas, acoes, h.data, ::otimista) { versao++ } }
                if (!h.email.escondido) cartoes["email"] = { CartaoEmail(h.email) }
                if (!h.bilhetes.escondido) cartoes["bilhetes"] = { CartaoBilhetes(h.bilhetes) }
                if (!h.rto.escondido) cartoes["rto"] = { CartaoRto(h.rto, acoes, h.data) { atualizar(setOf("rto")) } }
                if (!h.peso.escondido) cartoes["peso"] = { CartaoPeso(h.peso, acoes, h.peso.dados?.sugestao, ::otimista) { versao++ } }
                h.compras?.let { c -> if (!c.escondido) cartoes["compras"] = { CartaoCompras(c, acoes) } }
                if (!h.financas.escondido) cartoes["financas"] = { CartaoFinancas(h.financas, acoes) }
                // pela ordem escolhida nas Definições (ADR-054); os cartões que ela não menciona entram no fim
                val ordem = h.ordem + CARTOES_ORIGEM.filter { it !in h.ordem }
                items(ordem.filter { it in cartoes }, key = { it }) { id -> cartoes[id]?.invoke() }
                item { Botao("Atualizar", { versao++ }, variante = Variante.SECUNDARIO, pequeno = true) }
            }
        }
    }
}
