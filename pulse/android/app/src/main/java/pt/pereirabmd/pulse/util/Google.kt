package pt.pereirabmd.pulse.util

import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneId

/** Motivos de erro do regresso da Google, em pt-PT (espelho de `MOTIVOS_GOOGLE` da Web). */
val MOTIVOS_GOOGLE = mapOf(
    "recusado" to "Não deste as permissões à Google. Podes tentar de novo quando quiseres.", "estado_invalido" to "O pedido de ligação expirou. Tenta de novo.",
    "sem_permissoes" to "A conta não deu as permissões pedidas.", "sem_refresh_token" to "A Google não deu acesso duradouro. Remove a app em myaccount.google.com/permissions e liga de novo.",
    "google_recusou" to "A Google recusou o pedido. Tenta de novo.", "google_desligado" to "A integração com a Google não está configurada neste servidor.", "invalido" to "O regresso da Google foi inválido.",
)

private fun instanteZona(iso: String): java.time.ZonedDateTime? = try { OffsetDateTime.parse(iso).atZoneSameInstant(ZoneId.systemDefault()) } catch (_: Exception) {
    try { LocalDateTime.parse(iso.take(19)).atZone(ZoneId.systemDefault()) } catch (_: Exception) { null }
}

/** «há 5 min», «hoje 09:30», «ontem», «28/09» (espelho de `quandoMensagem` da Web). */
fun quandoMensagem(iso: String, agora: java.time.ZonedDateTime = java.time.ZonedDateTime.now()): String {
    if (iso.isEmpty()) return ""
    val d = instanteZona(iso) ?: return ""
    val min = java.time.Duration.between(d, agora).toMinutes()
    if (min in 0..59) return if (min <= 1) "agora" else "há $min min"
    val hora = "%02d:%02d".format(d.hour, d.minute)
    if (d.toLocalDate() == agora.toLocalDate()) return "hoje $hora"
    if (d.toLocalDate() == agora.toLocalDate().minusDays(1)) return "ontem"
    return "%02d/%02d".format(d.dayOfMonth, d.monthValue)
}
