package pt.pereirabmd.pulse.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import pt.pereirabmd.pulse.data.Api
import pt.pereirabmd.pulse.data.ModuloInfo
import pt.pereirabmd.pulse.data.parseModulos

private data class Entrada(val id: String, val nome: String, val icone: Icone, val rota: String)

private val MODULOS = listOf(
    Entrada("email", "Email", Icone.EMAIL, "/email"), Entrada("calendario", "Calendário", Icone.CALENDARIO, "/calendario"), Entrada("tarefas", "Tarefas", Icone.TAREFAS, "/tarefas"),
    Entrada("bilhetes", "Bilhetes CP", Icone.BILHETE, "/bilhetes"), Entrada("peso", "Peso", Icone.PESO, "/peso"), Entrada("rto", "RTO", Icone.RTO, "/rto"),
    Entrada("financas", "Finanças", Icone.FINANCAS, "/financas"), Entrada("compras", "Compras", Icone.COMPRAS, "/compras"),
)

@Composable
private fun ItemLista(icone: Icone, nome: String, nota: String? = null, aoClicar: () -> Unit) {
    val c = Pulse.cores
    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(Pulse.rM)).background(c.surface).border(1.dp, c.line, RoundedCornerShape(Pulse.rM)).clickable(onClick = aoClicar)
        .heightIn(min = 56.dp).padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Icon(icone, c.primary)
        Texto(nome, modifier = Modifier.weight(1f))
        if (nota != null) Pilula(nota)
        Icon(Icone.SETA, c.text2, 18.dp)
    }
}

/** «Mais»: as aplicações do Pulse. Os módulos ainda sem ecrã nativo abrem a Web do Pulse; o que o administrador desativou não aparece. */
@Composable
fun EcraMais(aoDefinicoes: () -> Unit) {
    val ctx = LocalContext.current
    var ativos by remember { mutableStateOf<List<ModuloInfo>?>(null) }
    LaunchedEffect(Unit) { ativos = try { parseModulos(Api.get("/modules")) } catch (e: Exception) { null } }
    // enquanto a lista não chega (ou falha) mostram-se todos: o servidor recusa o que estiver desativado
    val visiveis = MODULOS.filter { m -> ativos?.firstOrNull { it.id == m.id }?.ativo ?: true }
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Texto("Mais", Pulse.page)
                Texto2("As aplicações completas chegam ao Android por fases. Por agora abrem na Web do Pulse, com a mesma conta.")
            }
        }
        item { Texto("Aplicações", Pulse.card, Pulse.cores.text2) }
        visiveis.forEach { m -> item { ItemLista(m.icone, m.nome, "Na Web") { abrirNaWeb(ctx, m.rota) } } }
        item { Spacer(Modifier.height(4.dp)); Texto("Conta", Pulse.card, Pulse.cores.text2) }
        item { ItemLista(Icone.DEFINICOES, "Definições", aoClicar = aoDefinicoes) }
    }
}
