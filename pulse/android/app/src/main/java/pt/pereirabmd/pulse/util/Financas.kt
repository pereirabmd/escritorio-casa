package pt.pereirabmd.pulse.util

private val MESES = listOf("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")

/** 2026-09 -> «setembro de 2026» */
fun tituloMesFin(mes: String) = "${MESES[mes.substring(5, 7).toInt() - 1]} de ${mes.substring(0, 4)}"

/** Soma (ou subtrai) meses a «AAAA-MM». */
fun somarMeses(mes: String, n: Int): String {
    val i = mes.substring(0, 4).toInt() * 12 + mes.substring(5, 7).toInt() - 1 + n
    return "%04d-%02d".format(i / 12, i % 12 + 1)
}

/** «12,5», «12.5» ou «1 234,50» -> 12.5; vazio, zero, negativo ou inválido -> null. */
fun lerValor(texto: String): Double? {
    val n = texto.trim().replace(Regex("\\s"), "").replace(',', '.').toDoubleOrNull() ?: return null
    return if (n > 0 && n <= 1_000_000_000) Math.round(n * 100) / 100.0 else null
}

fun valorParaCampo(v: Double) = (if (v % 1.0 == 0.0) v.toLong().toString() else v.toString()).replace('.', ',')

val ESTADO_TXT = mapOf("pago" to "Pago", "vencido" to "Vencido", "hoje" to "Vence hoje", "pendente" to "Por pagar")
