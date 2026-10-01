package pt.pereirabmd.pulse.util

import org.json.JSONObject
import java.time.LocalDate

/** Regras de apresentação e edição dos Bilhetes CP (espelho de `web/src/lib/bilhetes.ts`); a lógica de compra vive no servidor e no Pi. */
private val WD = listOf("seg", "ter", "qua", "qui", "sex", "sáb", "dom")

fun somarDias(iso: String, n: Int): String = LocalDate.parse(iso).plusDays(n.toLong()).toString()

/** «seg 05/10» */
fun diaCurto(iso: String): String = "${WD[LocalDate.parse(iso).dayOfWeek.value - 1]} ${iso.substring(8, 10)}/${iso.substring(5, 7)}"
fun diaMes(iso: String) = "${iso.substring(8, 10)}/${iso.substring(5, 7)}"
fun intervaloSemana(segunda: String) = "${diaMes(segunda)} a ${diaMes(somarDias(segunda, 6))}"

val ESTADO_VIAGEM = mapOf("comprado" to "Comprado", "por_comprar" to "Por comprar", "inativa" to "Inativa", "em_curso" to "Em viagem", "passada" to "Concluída")
val ESTADO_PEDIDO = mapOf("PENDENTE" to "Pendente", "A_TENTAR" to "A tentar…", "ESGOTADO" to "Esgotado", "FALHOU" to "Falhou", "AMBIGUO" to "Confirmar na App CP", "CONFIRMADO" to "Comprado", "EXPIRADO" to "Expirou", "DESARMADO" to "Desativada")
val RESULTADO_REGISTO = mapOf("CONFIRMED" to "Comprado", "SALE_CREATED" to "Venda criada", "SOLD_OUT" to "Esgotado", "FAILED" to "Falhou", "AMBIGUOUS" to "Estado incerto",
    "OK" to "OK", "FALHA" to "Falha", "EXCECAO" to "Erro inesperado")
val TIPO_REGISTO = mapOf("COMPRA" to "Compra", "ERRO" to "Erro", "PREFLIGHT" to "Verificação")

/** ok / warn / err / vazio, para a cor do registo. */
fun classeRegisto(resultado: String?, tipo: String): String {
    val res = resultado.orEmpty()
    if (Regex("^(OK|CONFIRMED|SALE_CREATED)$", RegexOption.IGNORE_CASE).matches(res)) return "ok"
    if (Regex("SOLD_OUT", RegexOption.IGNORE_CASE).containsMatchIn(res)) return "warn"
    if (Regex("FAIL|FALHA|AMBIG|EXCECAO|ERRO", RegexOption.IGNORE_CASE).containsMatchIn(res + tipo)) return "err"
    return ""
}

// --- editor da semana ---
data class LinhaEd(val origem: String = "", val destino: String = "", val comboio: String = "", val hora: String = "")
data class DiaEd(val data: String, val ativo: Boolean, val passado: Boolean, val viagens: List<LinhaEd>)

/** Os 7 dias da semana com as viagens já configuradas; o interruptor «ativo» é por dia (como na app dedicada). */
fun diasParaEditor(dias: List<String>, viagens: List<JSONObject>, hoje: String): List<DiaEd> = dias.map { data ->
    val doDia = viagens.filter { it.optString("data") == data }
    DiaEd(data, doDia.isEmpty() || doDia.any { it.optBoolean("ativo") }, data < hoje,
        doDia.map { LinhaEd(it.optString("origem"), it.optString("destino"), it.optInt("comboio").toString(), it.optString("hora")) })
}

private val HORA = Regex("^([01]\\d|2[0-3]):[0-5]\\d$")

/** Uma lista de avisos por dia (vazia = válido). Dias passados não se validam nem se alteram; dias sem viagens não pedem nada. */
fun validarDias(dias: List<DiaEd>): List<List<String>> = dias.map { d ->
    if (d.passado || d.viagens.isEmpty()) return@map emptyList<String>()
    val erros = mutableListOf<String>()
    val vistas = mutableMapOf<String, Int>()
    d.viagens.forEachIndexed { i, v ->
        val n = i + 1
        if (v.origem.isEmpty() || v.destino.isEmpty()) erros += "Viagem $n: escolhe a origem e o destino."
        else if (v.origem.equals(v.destino, ignoreCase = true)) erros += "Viagem $n: a origem e o destino são iguais."
        val comboioOk = Regex("^\\d{1,5}$").matches(v.comboio.trim()) && v.comboio.trim().toInt() >= 1
        if (!comboioOk) erros += "Viagem $n: comboio inválido."
        if (!HORA.matches(v.hora)) erros += "Viagem $n: hora inválida."
        if (comboioOk && HORA.matches(v.hora)) {
            val chave = "${v.comboio.trim().toInt()}|${v.hora}"
            if (vistas.containsKey(chave)) erros += "Viagem $n: repete a viagem ${vistas.getValue(chave) + 1}." else vistas[chave] = i
        }
    }
    erros
}

/** O corpo da ação `bilhetes.semana`: dias passados enviam-se tal como estavam (o servidor substitui a semana toda). */
fun viagensParaEnviar(dias: List<DiaEd>): List<JSONObject> = dias.flatMap { d ->
    d.viagens.map { v -> JSONObject().put("data", d.data).put("origem", v.origem.trim()).put("destino", v.destino.trim()).put("comboio", v.comboio.trim().toInt()).put("hora", v.hora).put("ativo", d.ativo) }
}
