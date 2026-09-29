package pt.pereirabmd.pulse.util

import java.time.DayOfWeek
import java.time.LocalDate

/** Regras de apresentação do RTO (espelho de `web/src/lib/rto.ts`); as contas (totais, saldos) vêm do servidor. */
val MESES_NOME = listOf("Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro")
val DIAS_SEMANA_LETRA = listOf("S", "T", "Q", "Q", "S", "S", "D")          // segunda a domingo

fun nomeMes(mes: Int) = MESES_NOME[((mes % 12) + 12) % 12]

/** Semanas (segunda a domingo) de um mês (`mes` 0..11), com `null` nas posições fora do mês. */
fun semanasDoMes(ano: Int, mes: Int): List<List<String?>> {
    val primeiro = LocalDate.of(ano, mes + 1, 1)
    val vazias = primeiro.dayOfWeek.value - 1                                  // 0 = segunda
    val celulas = MutableList<String?>(vazias) { null } + (1..primeiro.lengthOfMonth()).map { primeiro.withDayOfMonth(it).toString() }
    val cheias = celulas + List((7 - celulas.size % 7) % 7) { null }
    return cheias.chunked(7)
}

/** [início, fim] de uma nota, ou `null` se não tem datas. */
fun intervaloNota(inicio: String?, fim: String?): Pair<String, String>? {
    val ini = inicio?.ifEmpty { null } ?: fim?.ifEmpty { null } ?: return null
    val f = fim?.ifEmpty { null } ?: ini
    return if (f >= ini) ini to f else null
}

/** No modo normal só se marcam dias úteis de hoje em diante (regra da app dedicada); o modo administrador levanta a restrição. */
fun diaBloqueado(data: String, hoje: String): Boolean {
    val dow = LocalDate.parse(data).dayOfWeek
    return dow == DayOfWeek.SATURDAY || dow == DayOfWeek.SUNDAY || data < hoje
}

/** Um toque num dia: vazio → Escritório (T) → Casa (C) → vazio. */
fun proximaMarca(atual: String?): String = when (atual) { "T" -> "C"; "C" -> ""; else -> "T" }

/** O que a célula mostra: T/C manda; senão feriado (com A por cima), senão a letra da nota (F/A). Devolve (texto, classe). */
fun marcaDaCelula(marca: String, feriado: Boolean, letraNota: String): Pair<String, String> {
    val letra = if (marca.isEmpty()) letraNota else ""
    return when {
        marca.isNotEmpty() -> marca to marca
        feriado && letra == "A" -> "Af" to "A"
        feriado -> "f" to "holiday"
        letra.isNotEmpty() -> letra to letra
        else -> "" to ""
    }
}

fun textoHoje(estado: String) = when (estado) {
    "escritorio" -> "Escritório"; "casa" -> "Casa"; "ferias" -> "Férias"; "feriado" -> "Feriado"
    "fim_de_semana" -> "Fim de semana"; "astreinte" -> "Astreinte"; else -> "Ainda por definir"
}

fun textoProximaMudanca(tipo: String, dias: Int, nome: String?): String {
    val quando = if (dias == 1) "amanhã" else "daqui a $dias dias"
    return if (tipo == "feriado") "Feriado ${if (dias == 1) "amanhã" else "a $dias dias"} — ${nome.orEmpty()}" else "Férias a começar $quando"
}
