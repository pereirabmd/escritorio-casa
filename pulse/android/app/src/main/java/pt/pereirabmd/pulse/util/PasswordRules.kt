package pt.pereirabmd.pulse.util

/** Regras mostradas enquanto se escreve (espelho de `web/src/lib/passwordRules.ts`). A validação final é do servidor. */
data class Regra(val id: String, val texto: String, val ok: Boolean)

private val FRACAS = setOf("1234567890", "password12", "qwertyuiop", "1234qwer12", "passw0rd12")

fun regrasPassword(nova: String, atual: String, email: String): List<Regra> {
    val n = nova.lowercase()
    val previsivel = n in FRACAS || n == email.lowercase() || n == email.substringBefore('@').lowercase()
    return listOf(
        Regra("tamanho", "Pelo menos 10 caracteres", nova.length >= 10),
        Regra("variedade", "Não demasiado repetitiva", nova.toSet().size >= 5),
        Regra("previsivel", "Nada previsível (como o e-mail ou 1234567890)", nova.isNotEmpty() && !previsivel),
        Regra("diferente", "Diferente da palavra-passe atual", nova.isNotEmpty() && nova != atual),
    )
}

fun todasOk(rs: List<Regra>) = rs.all { it.ok }
