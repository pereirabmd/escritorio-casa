package pt.pereirabmd.pulse.util

import java.util.Calendar
import java.util.Locale

/** Formatos pt-PT do Design System (espelho de `web/src/lib/format.ts`): 28/09/2026, «28 de setembro», 1 245,50 €, 104,8 kg. */
private val MESES = listOf("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")
private val DIAS_SEMANA = listOf("domingo", "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado")
private const val NBSP = ' '

private fun decimal(v: Double, casas: Int, agrupar: Boolean): String {
    val txt = String.format(Locale.US, "%.${casas}f", Math.abs(v))
    val (inteiro, frac) = txt.split('.').let { it[0] to it.getOrElse(1) { "" } }
    val g = if (agrupar) inteiro.reversed().chunked(3).joinToString(NBSP.toString()).reversed() else inteiro
    val sinal = if (v < 0 && txt.any { it in '1'..'9' }) "-" else ""
    return sinal + g + if (frac.isEmpty()) "" else ",$frac"
}

fun fmtEuro(v: Double): String = decimal(v, 2, true) + NBSP + "€"
fun fmtPeso(v: Double): String = decimal(v, 1, false) + NBSP + "kg"

/** 2026-09-28 -> 28/09/2026 */
fun fmtDataIso(iso: String): String {
    val p = iso.take(10).split('-')
    return if (p.size == 3) "${p[2]}/${p[1]}/${p[0]}" else iso
}

/** 2026-09-28 -> 28 de setembro */
fun fmtDiaMes(iso: String): String {
    val p = iso.take(10).split('-')
    if (p.size != 3) return iso
    return "${p[2].toInt()} de ${MESES[p[1].toInt() - 1]}"
}

/** «Segunda-feira, 28 de setembro» */
fun fmtDataLonga(c: Calendar): String {
    val dia = DIAS_SEMANA[c.get(Calendar.DAY_OF_WEEK) - 1]
    return "${dia.replaceFirstChar { it.uppercase() }}, ${c.get(Calendar.DAY_OF_MONTH)} de ${MESES[c.get(Calendar.MONTH)]}"
}

fun saudacao(hora: Int): String = when {
    hora < 5 -> "Boa noite"
    hora < 13 -> "Bom dia"
    hora < 20 -> "Boa tarde"
    else -> "Boa noite"
}

/** «hoje», «amanhã», «em 5 dias», «há 3 dias». */
fun fmtDias(dias: Int): String = when {
    dias == 0 -> "hoje"
    dias == 1 -> "amanhã"
    dias == -1 -> "ontem"
    dias > 0 -> "em $dias dias"
    else -> "há ${-dias} dias"
}

fun plural(n: Int, um: String, varios: String) = if (n == 1) "$n $um" else "$n $varios"
