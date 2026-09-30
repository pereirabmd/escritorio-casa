package pt.pereirabmd.pulse.ui

import android.content.Context
import android.content.Intent
import android.net.Uri

/** Partilha um ficheiro de texto (ex.: CSV) pelo menu de partilha do Android. */
fun partilharFicheiro(ctx: Context, nome: String, conteudo: String, tipo: String = "text/csv") {
    val dir = java.io.File(ctx.cacheDir, "exports").apply { mkdirs() }
    val f = java.io.File(dir, nome).apply { writeText(conteudo) }
    val uri = androidx.core.content.FileProvider.getUriForFile(ctx, "${ctx.packageName}.files", f)
    val envio = Intent(Intent.ACTION_SEND).setType(tipo).putExtra(Intent.EXTRA_STREAM, uri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    ctx.startActivity(Intent.createChooser(envio, "Exportar").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
}

/** Abre a aplicação de calendário do telemóvel com o evento já preenchido (sem sincronização automática). */
fun adicionarAoCalendario(ctx: Context, titulo: String, dataIso: String, hora: String, notas: String) {
    val (h, m) = hora.split(':').let { (it.getOrNull(0)?.toIntOrNull() ?: 8) to (it.getOrNull(1)?.toIntOrNull() ?: 0) }
    val ini = java.time.LocalDate.parse(dataIso).atTime(h, m).atZone(java.time.ZoneId.systemDefault()).toInstant().toEpochMilli()
    ctx.startActivity(Intent(Intent.ACTION_INSERT).setData(android.provider.CalendarContract.Events.CONTENT_URI)
        .putExtra(android.provider.CalendarContract.Events.TITLE, titulo).putExtra(android.provider.CalendarContract.Events.DESCRIPTION, notas)
        .putExtra(android.provider.CalendarContract.EXTRA_EVENT_BEGIN_TIME, ini).putExtra(android.provider.CalendarContract.EXTRA_EVENT_END_TIME, ini + 30 * 60_000)
        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
}

/** Abre um endereço http(s) fora da app (o Gmail abre as ligações mail.google.com na própria aplicação, na conta certa). */
fun abrirEndereco(ctx: Context, url: String) {
    if (!url.startsWith("https://")) return
    runCatching { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
}

/** «2026-10-02» → «Hoje» / «Amanhã» / «sex, 2 out» (o Hoje mostra os próximos eventos, de qualquer dia). */
fun diaCurto(iso: String, hoje: java.time.LocalDate = java.time.LocalDate.now()): String {
    val d = runCatching { java.time.LocalDate.parse(iso.take(10)) }.getOrNull() ?: return ""
    return when (java.time.temporal.ChronoUnit.DAYS.between(hoje, d)) {
        0L -> "Hoje"
        1L -> "Amanhã"
        else -> "${listOf("seg", "ter", "qua", "qui", "sex", "sáb", "dom")[d.dayOfWeek.value - 1]}, ${d.dayOfMonth} ${listOf("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")[d.monthValue - 1]}"
    }
}
