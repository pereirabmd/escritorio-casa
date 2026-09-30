package pt.pereirabmd.pulse.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import org.json.JSONObject
import pt.pereirabmd.pulse.data.*
import pt.pereirabmd.pulse.util.*
import java.time.LocalDate

private val ABAS = listOf("Hoje", "Calendário", "Tarefas", "Horário", "Piscina", "Config")

/** Tarefas (ADR-042/043): Hoje, Calendário, Tarefas, Horário, Piscina e Config. Ocorrências, atrasos e rotações vêm do servidor. */
@Composable
fun TarefasEcra(aoVoltar: () -> Unit) {
    var aba by remember { mutableIntStateOf(0) }
    val c = carga { Api.get("/tasks") }
    val acoes = rememberAcoes { c.recarregar() }
    EcraModulo("Tarefas", aoVoltar) {
        Ao(c, "A carregar as tarefas…") { d ->
            Abas(ABAS, aba) { aba = it }
            Rolar {
                ErroAcao(acoes)
                when (aba) {
                    0 -> HojeTab(d, acoes)
                    1 -> CalendarioTab(d, c.recarregar)
                    2 -> CatalogoTab(d, acoes)
                    3 -> HorarioTab()
                    4 -> PiscinaTab(c.recarregar)
                    else -> ConfigTab(c.recarregar)
                }
            }
        }
    }
}

/** Uma ocorrência com as ações (concluir, adiar, saltar, pôr no calendário do telemóvel). */
@Composable
fun TarefaLinha(i: JSONObject, hoje: String, horaPadrao: String, acoes: Acoes) {
    val avisos = LocalAvisos.current; val ctx = LocalContext.current
    var adiar by remember { mutableStateOf(false) }
    val id = i.txtOu("id"); val estado = i.txtOu("estado"); val feita = estado == "Feita"; val saltada = estado == "Saltada"
    val c = Pulse.cores
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Visto(feita, {
                if (feita) acoes.executar(id, "tarefas.reabrir", jo("instancia" to id)) { avisos.mostrar("Tarefa reaberta.") }
                else acoes.executar(id, "tarefas.concluir", jo("instancia" to id)) { r ->
                    val tambem = r.strs("tambem"); val extra = tambem.size
                    avisos.mostrar("Tarefa concluída${if (extra > 0) " · +$extra atrasada${if (extra > 1) "s" else ""} anterior${if (extra > 1) "es" else ""}" else ""}.") {
                        acoes.executar(id, "tarefas.reabrir", jo("instancia" to id, "tambem" to ja(tambem)))
                    }
                }
            }, (if (feita) "Marcar como não concluída: " else "Marcar como concluída: ") + i.txtOu("nome"), acoes.ocupado == id, acoes.ocupado == null)
            Column(Modifier.weight(1f)) {
                Text(i.txtOu("nome"), style = Pulse.body.let { if (feita || saltada) it.copy(textDecoration = TextDecoration.LineThrough) else it }, color = if (feita || saltada) c.text2 else c.text)
                Meta(if (feita) "Concluída por ${i.txtOu("pessoa")}${i.txtOu("dataConclusao").let { if (it.isNotEmpty()) " · ${quando(it, hoje)}" else "" }}"
                     else listOf(i.txtOu("pessoa"), i.txtOu("hora")).filter { it.isNotEmpty() }.joinToString(" · ") + (if (estado == "Atrasada") " · Atrasada" else "") + (if (saltada) " · Saltada" else ""))
            }
        }
        if (!feita && !saltada) Row(Modifier.padding(start = 50.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            LinkBtn("Calendário", { adicionarAoCalendario(ctx, i.txtOu("nome"), i.txtOu("data").ifEmpty { hoje }, i.txtOu("hora").ifEmpty { horaPadrao.ifEmpty { "08:00" } }, "Tarefa de casa — ${i.txtOu("pessoa")}") })
            LinkBtn("Adiar", { adiar = true })
            LinkBtn("Saltar", {
                acoes.executar(id, "tarefas.saltar", jo("instancia" to id)) { avisos.mostrar("Tarefa saltada.") { acoes.executar(id, "tarefas.reabrir", jo("instancia" to id)) } }
            })
        }
    }
    if (adiar) FolhaAdiar(i, hoje, acoes, avisos) { adiar = false }
}

@Composable
fun FolhaAdiar(i: JSONObject, hoje: String, acoes: Acoes, avisos: Avisos, aoFechar: () -> Unit) {
    var data by remember { mutableStateOf("") }
    val id = i.txtOu("id")
    Folha("Adiar ${i.txtOu("nome")}", aoFechar) {
        Botao("Amanhã", { acoes.executar(id, "tarefas.adiar", jo("instancia" to id)) { aoFechar(); avisos.mostrar("Tarefa adiada para amanhã.") } }, variante = Variante.SECUNDARIO, grande = true, ativo = acoes.ocupado == null)
        CampoData("Ou escolhe uma data", data, { data = it }, minimo = hoje)
        ErroAcao(acoes)
        Botao("Adiar para essa data", { acoes.executar(id, "tarefas.adiar", jo("instancia" to id, "data" to data)) { aoFechar(); avisos.mostrar("Tarefa adiada para ${fmtDataIso(data)}.") } },
            grande = true, ativo = data.isNotEmpty() && data >= hoje && acoes.ocupado == null, carregando = acoes.ocupado == id)
    }
}

@Composable
private fun ColumnScope.HojeTab(d: JSONObject, acoes: Acoes) {
    val ctx = LocalContext.current
    val pessoa = d.txt("pessoa"); val pessoas = d.strs("pessoas"); val hoje = d.getString("data"); val horaPadrao = d.txtOu("horaPadrao")
    var filtro by remember { mutableStateOf(UiPrefs.ler(ctx, "tarefas.filtro", "todas").let { if (it == "todas" || (it == "minhas" && pessoa != null) || it in pessoas) it else "todas" }) }
    var rapida by remember { mutableStateOf(false) }
    fun ok(i: JSONObject) = passaFiltro(i.txtOu("pessoa"), filtro, pessoa)
    val hojeL = d.objs("hoje").filter(::ok); val feitas = d.objs("feitas").filter(::ok)
    val total = hojeL.size + feitas.size
    Filtros(listOf("todas" to "Todas") + (if (pessoa != null) listOf("minhas" to "Minhas") else emptyList()) + pessoas.map { it to it }, filtro) { filtro = it; UiPrefs.guardar(ctx, "tarefas.filtro", it) }
    if (total > 0) Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
        Texto2("${feitas.size} de $total concluídas"); if (hojeL.isEmpty()) Pilula("Tudo feito por hoje", Pulse.cores.success)
    }
    @Composable fun lista(titulo: String, itens: List<JSONObject>, vazio: String) = Bloco(titulo = titulo) {
        if (itens.isEmpty()) Texto2(vazio) else itens.forEach { TarefaLinha(it, hoje, horaPadrao, acoes) }
    }
    lista("Hoje", hojeL + feitas, "Sem tarefas para hoje.")
    lista("Atrasadas", d.objs("atrasadas").filter(::ok), "Nenhuma tarefa atrasada.")
    lista("Amanhã", d.objs("amanha").filter(::ok), "Nada agendado para amanhã.")
    Botao("Adicionar tarefa a hoje", { rapida = true }, variante = Variante.SECUNDARIO, pequeno = true)
    if (rapida) FolhaRapida(d, acoes) { rapida = false }
}

@Composable
private fun FolhaRapida(d: JSONObject, acoes: Acoes, aoFechar: () -> Unit) {
    val avisos = LocalAvisos.current
    var nome by remember { mutableStateOf("") }
    val pessoas = d.strs("pessoas")
    var pessoa by remember { mutableStateOf(d.txt("pessoa") ?: pessoas.firstOrNull() ?: "") }
    val cid = remember { novoCid() }
    Folha("Tarefa para hoje", aoFechar) {
        Campo("Nome", nome, { nome = it.take(200) })
        if (pessoas.isNotEmpty()) Seletor("Pessoa", pessoas.map { it to it }, pessoa, { pessoa = it })
        ErroAcao(acoes)
        Botao("Adicionar", {
            val cats = d.strs("categorias"); val cat = if ("Outros" in cats) "Outros" else cats.firstOrNull() ?: "Outros"
            acoes.executar("rapida", "tarefas.criar", jo("nome" to nome.trim(), "categoria" to cat, "recorrencia" to "Pontual", "data" to d.getString("data"), "pessoa" to pessoa, "cid" to cid)) {
                aoFechar(); avisos.mostrar("Tarefa adicionada a hoje.")
            }
        }, grande = true, ativo = nome.isNotBlank() && acoes.ocupado == null, carregando = acoes.ocupado == "rapida")
    }
}

@Composable
private fun ColumnScope.CalendarioTab(principal: JSONObject, atualizar: () -> Unit) {
    val hoje = principal.getString("data"); val horaPadrao = principal.txtOu("horaPadrao")
    var vista by remember { mutableStateOf("mes") }
    var ancora by remember { mutableStateOf(hoje) }
    var escolhido by remember { mutableStateOf(hoje) }
    val (de, ate) = if (vista == "mes") intervaloMes(ancora) else intervaloSemanaDomingo(ancora)
    val c = carga("$de|$ate") { Api.get("/tasks/calendar?de=$de&ate=$ate") }
    val acoes = rememberAcoes { c.recarregar(); atualizar() }
    val dias = (c.dados?.objs("dias") ?: emptyList()).associateBy { it.txtOu("data") }
    val mesAtual = ancora.take(7)

    fun mover(n: Int) {
        val d = LocalDate.parse(ancora)
        val nova = if (vista == "mes") d.withDayOfMonth(1).plusMonths(n.toLong()).toString() else d.plusDays(7L * n).toString()
        ancora = nova
        val dentro = if (vista == "mes") hoje.take(7) == nova.take(7) else intervaloSemanaDomingo(nova).let { hoje >= it.first && hoje <= it.second }
        escolhido = if (dentro) hoje else if (vista == "mes") nova else intervaloSemanaDomingo(nova).first
    }
    val ferDaVista = dias.values.filter { it.txt("feriado") != null && (vista == "semana" || it.txtOu("data").startsWith(mesAtual)) }

    ErroAcao(acoes)
    Bloco(titulo = if (vista == "mes") tituloMes(ancora) else tituloSemana(de, ate), extra = {
        LinkBtn("‹", { mover(-1) }); LinkBtn("›", { mover(1) })
    }) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Filtros(listOf("mes" to "Mês", "semana" to "Semana"), vista) { vista = it; ancora = escolhido }
            LinkBtn("Hoje", { ancora = hoje; escolhido = hoje })
        }
        if (c.estado is Estado.Erro) Aviso(TipoAviso.ERRO) { Texto((c.estado as Estado.Erro).mensagem, Pulse.body2); LinkBtn("Tentar de novo", c.recarregar) }
        Row(Modifier.fillMaxWidth()) { DIAS_CURTO.forEach { Meta(it, Modifier.weight(1f).wrapContentWidth(Alignment.CenterHorizontally)) } }
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            listaDatas(de, ate).chunked(7).forEach { semana ->
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    semana.forEach { d ->
                        val info = dias[d]; val itens = info?.objs("itens") ?: emptyList()
                        val cores = itens.map { it.txtOu("categoria") }.distinct().take(3)
                        val fora = vista == "mes" && !d.startsWith(mesAtual)
                        val fds = diaDaSemana(LocalDate.parse(d)).let { it == 0 || it == 6 }
                        Column(Modifier.weight(1f).height(48.dp).clip(RoundedCornerShape(8.dp))
                            .background(if (info?.txt("feriado") != null) Pulse.cores.warningBg else if (d == escolhido) Pulse.cores.surface2 else Color.Transparent)
                            .border(if (d == hoje) 2.dp else if (d == escolhido) 1.dp else 0.dp, if (d == hoje) Pulse.cores.primary else Pulse.cores.text2, RoundedCornerShape(8.dp))
                            .clickable { escolhido = d }, horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                            Text(d.takeLast(2).toInt().toString(), style = Pulse.body2, color = if (fora) Pulse.cores.text2.copy(alpha = .5f) else if (fds) Pulse.cores.text2 else Pulse.cores.text)
                            Row(horizontalArrangement = Arrangement.spacedBy(2.dp), modifier = Modifier.height(6.dp)) { cores.forEach { Box(Modifier.size(5.dp).clip(CircleShape).background(Color(corCategoria(it)))) } }
                        }
                    }
                }
            }
        }
        if (ferDaVista.isNotEmpty()) Meta(ferDaVista.joinToString(" · ") { "${it.txtOu("data").takeLast(2).toInt()} — ${it.txtOu("feriado")}" })
    }
    val dia = dias[escolhido]
    Bloco(titulo = fmtDataLonga(java.util.Calendar.getInstance().apply { time = java.sql.Date.valueOf(escolhido) }) + (dia?.txt("feriado")?.let { " · $it" } ?: "")) {
        val itens = dia?.objs("itens") ?: emptyList()
        if (c.estado is Estado.Pronto && dias.isNotEmpty() && itens.isEmpty()) Texto2("Sem tarefas neste dia.")
        else itens.forEach { TarefaLinha(it, hoje, horaPadrao, acoes) }
        Botao("Atualizar", c.recarregar, variante = Variante.SECUNDARIO, pequeno = true)
    }
}
