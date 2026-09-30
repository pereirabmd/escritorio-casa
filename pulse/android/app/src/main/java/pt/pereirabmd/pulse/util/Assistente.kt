package pt.pereirabmd.pulse.util

import java.text.Normalizer

/** O que uma frase dita significa quando há propostas à espera de confirmação (ADR-077). */
enum class ComandoVoz { CONFIRMAR, CANCELAR, NENHUM }

private val CONFIRMAR = setOf("confirma", "confirmo", "confirmar", "sim", "ok", "pode ser", "faz", "faz isso", "avanca", "avanca com isso", "esta bem")
private val CANCELAR = setOf("cancela", "cancelar", "nao", "deixa", "esquece", "para", "nao faz", "nao quero")

/**
 * Só conta a frase **inteira** («confirma», «sim», «cancela»…): «sim, e acrescenta leite» é um pedido novo, não uma confirmação.
 * Sem propostas pendentes não há nada a confirmar, por isso devolve sempre `NENHUM`.
 */
fun comandoVoz(texto: String, haPropostas: Boolean): ComandoVoz {
    if (!haPropostas) return ComandoVoz.NENHUM
    val t = Normalizer.normalize(texto, Normalizer.Form.NFD).replace(Regex("\\p{Mn}+"), "").lowercase().replace(Regex("[^a-z ]"), " ").trim().replace(Regex("\\s+"), " ")
    return when (t) { in CONFIRMAR -> ComandoVoz.CONFIRMAR; in CANCELAR -> ComandoVoz.CANCELAR; else -> ComandoVoz.NENHUM }
}
