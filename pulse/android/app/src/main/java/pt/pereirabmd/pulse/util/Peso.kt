package pt.pereirabmd.pulse.util

/** Um ponto de uma série no tempo (`t` em milissegundos, `v` o valor). */
data class Ponto(val t: Long, val v: Double)

/** Média móvel de `dias` dias (como na app dedicada): média dos registos da janela que termina em cada ponto. */
fun mediaMovel(pontos: List<Ponto>, dias: Int = 7): List<Ponto> {
    val janela = (dias - 1) * 86_400_000L
    return pontos.map { p ->
        val dentro = pontos.filter { it.t >= p.t - janela && it.t <= p.t }
        Ponto(p.t, dentro.sumOf { it.v } / dentro.size)
    }
}

/** Nível de atividade: a config pode ter valores antigos (1-4) ou intermédios; os ecrãs só mostram 1,2 / 1,45 / 1,7. */
fun normalizarAtividade(raw: Double?): Double {
    if (raw == null || raw.isNaN() || raw == 0.0) return 1.2
    val escala = mapOf(1 to 1.2, 2 to 1.45, 3 to 1.7, 4 to 1.7)
    if (raw % 1.0 == 0.0 && escala.containsKey(raw.toInt())) return escala.getValue(raw.toInt())
    if (raw in 1.2..1.725) return listOf(1.2, 1.45, 1.7).reduce { a, b -> if (Math.abs(b - raw) < Math.abs(a - raw)) b else a }
    return 1.2
}

/** «2026-09-30 07:30:00» -> milissegundos (hora local do telemóvel, como a Web). */
fun instante(quando: String): Long = try {
    java.time.LocalDateTime.parse(quando.replace(' ', 'T').take(19)).atZone(java.time.ZoneId.systemDefault()).toInstant().toEpochMilli()
} catch (_: Exception) { 0L }
