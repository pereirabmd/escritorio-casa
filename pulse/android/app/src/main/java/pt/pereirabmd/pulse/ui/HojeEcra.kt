package pt.pereirabmd.pulse.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import pt.pereirabmd.pulse.data.*
import pt.pereirabmd.pulse.util.*
import java.util.Calendar

private sealed interface EstadoHoje {
    data object ACarregar : EstadoHoje
    data class Erro(val mensagem: String) : EstadoHoje
    data class Pronto(val hoje: Hoje) : EstadoHoje
}

private val DIA = listOf("S", "T", "Q", "Q", "S", "S", "D")

@Composable
private fun Abrir(rota: String) { val ctx = LocalContext.current; LinkBtn("Abrir", { abrirNaWeb(ctx, rota) }) }

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
    val ctx = LocalContext.current
    Cartao(icone, titulo) {
        Texto2(texto)
        LinkBtn("Ligar conta Google", { abrirNaWeb(ctx, "/definicoes") })
    }
}

@Composable
private fun Problemas(emails: List<String>) {
    if (emails.isEmpty()) return
    val ctx = LocalContext.current
    Meta("A conta ${emails.joinToString(", ")} pede nova autorização.")
    LinkBtn("Volta a ligá-la", { abrirNaWeb(ctx, "/definicoes") })
}

@Composable private fun Mais(n: Int) = Meta("e mais $n")

@Composable
private fun CartaoCalendario(m: Modulo<CalendarioDados>) {
    if (m.estado == "nao_ligado") return LigarGoogle(Icone.CALENDARIO, "Calendário de hoje", "Liga uma conta Google para veres aqui os eventos de hoje.")
    Cartao(Icone.CALENDARIO, "Calendário de hoje", extra = { Abrir("/calendario") }) {
        Estado(m) { d ->
            if (d.eventos.isEmpty()) Texto2("Sem eventos hoje.")
            else d.eventos.forEach { e ->
                Linha(inicio = { Meta(if (e.diaInteiro) "Dia todo" else e.inicio, Modifier.widthIn(min = 52.dp)) }) {
                    Texto(e.titulo); if (e.local.isNotEmpty()) Meta(e.local)
                }
            }
            if (d.total > d.eventos.size) Mais(d.total - d.eventos.size)
            Problemas(d.comProblemas)
        }
    }
}

@Composable
private fun CartaoTarefas(m: Modulo<TarefasDados>) {
    Cartao(Icone.TAREFAS, "Tarefas de hoje", extra = {
        m.dados?.takeIf { it.totalHoje > 0 }?.let { Meta("${it.feitasHoje} de ${it.totalHoje}") }; Abrir("/tarefas")
    }) {
        Estado(m) { d ->
            if (d.hoje.isEmpty()) Texto2(if (d.totalHoje > 0) "Tudo feito por hoje." else "Sem tarefas para hoje.")
            else d.hoje.take(5).forEach { t -> Linha { Texto(t.nome); Meta(listOf(t.categoria, t.hora).filter { it.isNotEmpty() }.joinToString(" · ")) } }
            if (d.hoje.size > 5) Mais(d.hoje.size - 5)
            if (d.atrasadas > 0) Meta(plural(d.atrasadas, "tarefa por concluir de dias anteriores", "tarefas por concluir de dias anteriores"))
        }
    }
}

@Composable
private fun CartaoEmail(m: Modulo<EmailDados>) {
    if (m.estado == "nao_ligado") return LigarGoogle(Icone.EMAIL, "Emails importantes", "Liga uma conta Google para veres aqui os emails importantes por ler.")
    Cartao(Icone.EMAIL, "Emails importantes", extra = { m.dados?.takeIf { it.porLer > 0 }?.let { Meta("${it.porLer} por ler") }; Abrir("/email") }) {
        Estado(m) { d ->
            if (d.mensagens.isEmpty()) Texto2("Nada importante por ler.")
            else d.mensagens.forEach { x -> Linha { Texto(x.de, Pulse.body.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold)); Texto2(x.assunto) } }
            if (d.porLer > d.mensagens.size) Mais(d.porLer - d.mensagens.size)
            Problemas(d.comProblemas)
        }
    }
}

@Composable
private fun CartaoBilhetes(m: Modulo<BilhetesDados>) {
    Cartao(Icone.BILHETE, "Próximo comboio", extra = { Abrir("/bilhetes") }) {
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
private fun CartaoRto(m: Modulo<RtoDados>) {
    val c = Pulse.cores
    Cartao(Icone.RTO, "RTO desta semana", extra = { m.dados?.let { Meta("${it.escritorio} escritório · ${it.casa} casa") }; Abrir("/rto") }) {
        Estado(m) { d ->
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                d.dias.forEach { dia ->
                    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Meta(DIA[(dia.diaSemana - 1).coerceIn(0, 6)])
                        Texto(dia.data.takeLast(2).toInt().toString(), Pulse.card, if (dia.hoje) c.primary else c.text)
                        Texto(dia.marca.ifEmpty { "·" }, Pulse.meta, when (dia.marca) { "T" -> c.primary; "C" -> c.success; else -> c.text2 })
                    }
                }
            }
        }
    }
}

@Composable
private fun CartaoPeso(m: Modulo<PesoDados>) {
    Cartao(Icone.PESO, "Peso", extra = { Abrir("/peso") }) {
        Estado(m) { d ->
            if (d.ultimoPeso != null) {
                Texto(fmtPeso(d.ultimoPeso), Pulse.metric)
                Texto2(if (d.registadoHoje) "Registo de hoje feito." else "Último registo a ${fmtDataIso(d.ultimoQuando.orEmpty())}. Ainda não registaste hoje.")
            } else Texto2("Ainda sem registos de peso.")
        }
    }
}

@Composable
private fun CartaoCompras(m: Modulo<ComprasDados>) {
    Cartao(Icone.COMPRAS, "Lista de compras", extra = { m.dados?.takeIf { it.pendentes > 0 }?.let { Meta("${it.pendentes} por comprar") }; Abrir("/compras") }) {
        Estado(m) { d ->
            if (d.itens.isEmpty()) Texto2("Nada por comprar.")
            else d.itens.forEach { i ->
                Linha { Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) { Texto(i.nome); if (i.quantidade != null) Pilula("${i.quantidade}×") }; if (i.nota.isNotEmpty()) Meta(i.nota) }
            }
            if (d.pendentes > d.itens.size) Mais(d.pendentes - d.itens.size)
        }
    }
}

@Composable
private fun CartaoFinancas(m: Modulo<FinancasDados>) {
    Cartao(Icone.FINANCAS, "Contas a pagar", extra = { m.dados?.takeIf { it.total > 0 }?.let { Meta("${fmtEuro(it.valorTotal)} em ${it.total}") } }) {
        Estado(m) { d ->
            if (d.proximas.isEmpty()) Texto2("Sem contas pendentes nos próximos 30 dias.")
            else d.proximas.forEach { c ->
                Linha(fim = { Column(horizontalAlignment = Alignment.End) {
                    Texto(fmtEuro(c.valor)); Meta(if (c.vencida) "Venceu ${fmtDias(c.diasAte)}" else "Vence ${fmtDias(c.diasAte)}")
                } }) { Texto(c.descricao); Meta(c.categoria) }
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

@Composable
fun EcraHoje(sessao: Sessao, utilizador: Utilizador, cabecalho: @Composable () -> Unit) {
    var estado by remember { mutableStateOf<EstadoHoje>(EstadoHoje.ACarregar) }
    var versao by remember { mutableIntStateOf(0) }
    LaunchedEffect(versao) {
        if (estado is EstadoHoje.Erro) estado = EstadoHoje.ACarregar
        estado = try { EstadoHoje.Pronto(parseHoje(Api.get("/dashboard/today"))) } catch (e: Exception) { EstadoHoje.Erro(mensagemDeErro(e)) }
    }
    val agora = Calendar.getInstance()
    val nome = utilizador.nome.trim().substringBefore(' ')
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Texto2(fmtDataLonga(agora))
                Texto(saudacao(agora.get(Calendar.HOUR_OF_DAY)) + if (nome.isNotEmpty()) ", $nome" else "", Pulse.page)
                (estado as? EstadoHoje.Pronto)?.let { Texto2(resumo(it.hoje)) }
            }
        }
        item { cabecalho() }
        when (val e = estado) {
            EstadoHoje.ACarregar -> item { BrandLoading("A preparar o teu dia…") }
            is EstadoHoje.Erro -> item { EstadoErro(e.mensagem) { versao++ } }
            is EstadoHoje.Pronto -> {
                val h = e.hoje
                if (h.degradado) item { Aviso(TipoAviso.AVISO, "Alguns módulos não responderam (${h.falhados().joinToString(", ")}). O resto está atualizado.") }
                if (!h.calendario.escondido) item { CartaoCalendario(h.calendario) }
                if (!h.tarefas.escondido) item { CartaoTarefas(h.tarefas) }
                if (!h.email.escondido) item { CartaoEmail(h.email) }
                if (!h.bilhetes.escondido) item { CartaoBilhetes(h.bilhetes) }
                if (!h.rto.escondido) item { CartaoRto(h.rto) }
                if (!h.peso.escondido) item { CartaoPeso(h.peso) }
                h.compras?.let { if (!it.escondido) item { CartaoCompras(it) } }
                if (!h.financas.escondido) item { CartaoFinancas(h.financas) }
                item { Botao("Atualizar", { versao++ }, variante = Variante.SECUNDARIO, pequeno = true) }
            }
        }
    }
}
