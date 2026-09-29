package pt.pereirabmd.pulse.data

import org.json.JSONArray
import org.json.JSONObject

/** Leitura tolerante do JSON do servidor: um campo em falta ou `null` nunca rebenta o ecrã. */
fun JSONObject.txt(k: String): String? = if (isNull(k)) null else optString(k)
fun JSONObject.txtOu(k: String, por: String = ""): String = txt(k) ?: por
fun JSONObject.inteiro(k: String, por: Int = 0): Int = if (isNull(k)) por else optInt(k, por)
fun JSONObject.real(k: String): Double? = if (isNull(k)) null else optDouble(k)
fun JSONObject.bool(k: String): Boolean = !isNull(k) && optBoolean(k)
fun JSONObject.obj(k: String): JSONObject? = if (isNull(k)) null else optJSONObject(k)
fun <T> JSONObject.lista(k: String, f: (JSONObject) -> T): List<T> {
    val a: JSONArray = optJSONArray(k) ?: return emptyList()
    return (0 until a.length()).mapNotNull { a.optJSONObject(it)?.let(f) }
}

/** Estado de um módulo no agregado do Hoje: `ok`, `indisponivel`, `sem_acesso`, `erro`, `nao_ligado` ou `desativado`. */
data class Modulo<T>(val estado: String, val dados: T?) {
    val ok get() = estado == "ok" && dados != null
    /** Sem acesso ou desativado pelo administrador: o cartão nem aparece. */
    val escondido get() = estado == "sem_acesso" || estado == "desativado"
}

data class Tarefa(val id: String, val nome: String, val categoria: String, val hora: String)
data class TarefasDados(val hoje: List<Tarefa>, val atrasadas: Int, val feitasHoje: Int, val totalHoje: Int)
data class Compra(val carruagem: String, val lugar: String)
data class Viagem(val data: String, val hora: String, val origem: String, val destino: String, val comboio: Int, val emCurso: Boolean, val fimEstimado: String?, val compra: Compra?)
data class Passe(val dataExpira: String?, val diasRestantes: Int?)
data class BilhetesDados(val proximo: Viagem?, val passe: Passe?)
data class DiaRto(val data: String, val diaSemana: Int, val marca: String, val hoje: Boolean)
data class RtoDados(val dias: List<DiaRto>, val escritorio: Int, val casa: Int)
data class PesoDados(val ultimoQuando: String?, val ultimoPeso: Double?, val registadoHoje: Boolean)
data class ContaFin(val id: Int, val descricao: String, val valor: Double, val categoria: String, val diasAte: Int, val vencida: Boolean)
data class FinancasDados(val proximas: List<ContaFin>, val vencidas: Int, val total: Int, val valorTotal: Double)
data class ItemCompras(val nome: String, val quantidade: Int?, val nota: String)
data class ComprasDados(val pendentes: Int, val itens: List<ItemCompras>)
data class Evento(val titulo: String, val diaInteiro: Boolean, val inicio: String, val local: String)
data class CalendarioDados(val eventos: List<Evento>, val total: Int, val comProblemas: List<String>)
data class Mensagem(val de: String, val assunto: String)
data class EmailDados(val porLer: Int, val mensagens: List<Mensagem>, val comProblemas: List<String>)

data class Hoje(
    val degradado: Boolean, val data: String,
    val tarefas: Modulo<TarefasDados>, val bilhetes: Modulo<BilhetesDados>, val rto: Modulo<RtoDados>, val peso: Modulo<PesoDados>,
    val financas: Modulo<FinancasDados>, val compras: Modulo<ComprasDados>?, val calendario: Modulo<CalendarioDados>, val email: Modulo<EmailDados>,
) {
    /** Os módulos que falharam (não conta `sem_acesso`, `nao_ligado` nem `desativado`), pelo nome que o utilizador conhece. */
    fun falhados(): List<String> = buildList {
        fun ver(nome: String, m: Modulo<*>?) { if (m != null && (m.estado == "indisponivel" || m.estado == "erro")) add(nome) }
        ver("Calendário", calendario); ver("Tarefas", tarefas); ver("Email", email); ver("Bilhetes CP", bilhetes)
        ver("RTO", rto); ver("Peso", peso); ver("Compras", compras); ver("Finanças", financas)
    }
}

data class Utilizador(val id: Int, val email: String, val nome: String, val admin: Boolean, val mudarPassword: Boolean)

fun parseUtilizador(j: JSONObject) = Utilizador(j.inteiro("id"), j.txtOu("email"), j.txtOu("nome"), j.bool("admin"), j.bool("mudarPassword"))

private fun <T> modulo(j: JSONObject?, f: (JSONObject) -> T): Modulo<T> {
    if (j == null) return Modulo("erro", null)
    val estado = j.txtOu("estado", "erro")
    val d = j.obj("dados")
    return Modulo(estado, if (d != null && estado == "ok") f(d) else null)
}

private fun problemas(d: JSONObject) = d.lista("comProblemas") { it.txtOu("email") }

fun parseHoje(j: JSONObject): Hoje {
    val m = j.optJSONObject("modulos") ?: JSONObject()
    return Hoje(
        degradado = j.txt("estado") == "degradado", data = j.txtOu("data"),
        tarefas = modulo(m.obj("tarefas")) { d ->
            TarefasDados(d.lista("hoje") { Tarefa(it.txtOu("id"), it.txtOu("nome"), it.txtOu("categoria"), it.txtOu("hora")) },
                d.inteiro("atrasadas"), d.inteiro("feitasHoje"), d.inteiro("totalHoje"))
        },
        bilhetes = modulo(m.obj("bilhetes")) { d ->
            BilhetesDados(
                d.obj("proximo")?.let { v -> Viagem(v.txtOu("data"), v.txtOu("hora"), v.txtOu("origem"), v.txtOu("destino"), v.inteiro("comboio"), v.bool("emCurso"), v.txt("fimEstimado"),
                    v.obj("compra")?.let { c -> Compra(c.txtOu("carruagem"), c.txtOu("lugar")) }) },
                d.obj("passe")?.let { p -> Passe(p.txt("dataExpira"), if (p.isNull("diasRestantes")) null else p.optInt("diasRestantes")) })
        },
        rto = modulo(m.obj("rto")) { d ->
            RtoDados(d.lista("dias") { DiaRto(it.txtOu("data"), it.inteiro("diaSemana", 1), it.txtOu("marca"), it.bool("hoje")) },
                d.obj("contagem")?.inteiro("T") ?: 0, d.obj("contagem")?.inteiro("C") ?: 0)
        },
        peso = modulo(m.obj("peso")) { d -> PesoDados(d.obj("ultimo")?.txt("quando"), d.obj("ultimo")?.real("peso"), d.bool("registadoHoje")) },
        financas = modulo(m.obj("financas")) { d ->
            FinancasDados(d.lista("proximas") { ContaFin(it.inteiro("id"), it.txtOu("descricao"), it.real("valor") ?: 0.0, it.txtOu("categoria"), it.inteiro("diasAte"), it.bool("vencida")) },
                d.inteiro("vencidas"), d.inteiro("total"), d.real("valorTotal") ?: 0.0)
        },
        compras = m.obj("compras")?.let { c ->
            modulo(c) { d -> ComprasDados(d.inteiro("pendentes"), d.lista("itens") { ItemCompras(it.txtOu("nome"), if (it.isNull("quantidade")) null else it.optInt("quantidade"), it.txtOu("nota")) }) }
        },
        calendario = modulo(m.obj("calendario")) { d ->
            CalendarioDados(d.lista("eventos") { Evento(it.txtOu("titulo"), it.bool("diaInteiro"), it.txtOu("inicio"), it.txtOu("local")) }, d.inteiro("total"), problemas(d))
        },
        email = modulo(m.obj("email")) { d ->
            EmailDados(d.inteiro("porLer"), d.lista("mensagens") { Mensagem(it.txtOu("de"), it.txtOu("assunto")) }, problemas(d))
        },
    )
}

data class ModuloInfo(val id: String, val nome: String, val ativo: Boolean)

fun parseModulos(j: JSONObject): List<ModuloInfo> = j.lista("modulos") { ModuloInfo(it.txtOu("id"), it.txtOu("nome"), it.optBoolean("ativo", true)) }
