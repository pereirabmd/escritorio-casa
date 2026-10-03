package pt.pereirabmd.pulse.widgets

import org.json.JSONObject
import pt.pereirabmd.pulse.data.Hoje
import pt.pereirabmd.pulse.data.inteiroOuNull
import pt.pereirabmd.pulse.data.obj
import pt.pereirabmd.pulse.data.real
import pt.pereirabmd.pulse.data.txtOu
import pt.pereirabmd.pulse.util.graus

/** O que os widgets escrevem (funções puras, testadas na JVM). `null` = o módulo não está disponível (a linha mostra «—»). */
data class LinhasWidget(val comboio: String, val comboioDetalhe: String, val tarefas: String, val rto: String, val peso: String)

private fun hhmm(s: String) = s.take(5)

fun linhasDoWidget(h: Hoje): LinhasWidget {
    val comboio = h.bilhetes.dados?.proximo
    val c = h.bilhetes.takeIf { it.ok }?.let {
        if (comboio == null) "sem viagens marcadas" else {
            val quando = if (comboio.data == h.data) "hoje" else "${comboio.data.substring(8, 10)}/${comboio.data.substring(5, 7)}"
            "$quando ${hhmm(comboio.hora)} · comboio ${comboio.comboio}"
        }
    } ?: "—"
    val detalhe = comboio?.let { v -> "${v.origem} → ${v.destino}" + (v.compra?.let { " · carruagem ${it.carruagem}, lugar ${it.lugar}" } ?: " · por comprar") } ?: ""
    val t = h.tarefas.dados?.takeIf { h.tarefas.ok }?.let {
        when {
            it.totalHoje == 0 && it.atrasadas == 0 -> "nada para hoje"
            else -> (if (it.totalHoje > 0) "${it.feitasHoje} de ${it.totalHoje} feitas" else "") + (if (it.atrasadas > 0) (if (it.totalHoje > 0) " · " else "") + "${it.atrasadas} atrasada${if (it.atrasadas > 1) "s" else ""}" else "")
        }
    } ?: "—"
    val r = h.rto.dados?.takeIf { h.rto.ok }?.let { d ->
        when (d.dias.firstOrNull { it.hoje }?.marca) { "T" -> "Escritório"; "C" -> "Casa"; null -> "—"; else -> "por marcar" }
    } ?: "—"
    val p = h.peso.dados?.takeIf { h.peso.ok }?.let { if (it.registadoHoje) "registado hoje" else "por registar" } ?: "—"
    return LinhasWidget(c, detalhe, t, r, p)
}

/** O tempo para o widget: ícone, temperatura e «máx/mín». */
data class TempoWidget(val icone: String, val temp: String, val maxMin: String)

fun tempoDoWidget(t: JSONObject?): TempoWidget? {
    val agora = t?.obj("agora") ?: return null
    val hoje = t.obj("hoje")
    return TempoWidget(agora.txtOu("icone"), graus(agora.real("temp")), "${graus(hoje?.real("max"))}/${graus(hoje?.real("min"))}" + (hoje?.inteiroOuNull("chuva")?.takeIf { it > 0 }?.let { " · $it%" } ?: ""))
}
