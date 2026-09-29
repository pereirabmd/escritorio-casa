package pt.pereirabmd.pulse.data

import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import pt.pereirabmd.pulse.BuildConfig
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

class ApiError(val status: Int, val codigo: String, mensagem: String) : Exception(mensagem)

/**
 * Cliente da API do Pulse (`/api/v1`). Android usa `Authorization: Bearer` (ADR-037); o token vive só no `SessionStore`.
 * Um 401 `nao_autenticado` diz à app que a sessão terminou.
 */
object Api {
    @Volatile var token: String? = null
    @Volatile var aoPerderSessao: (() -> Unit)? = null

    private const val BASE_PATH = "/api/v1"

    suspend fun get(caminho: String) = pedir("GET", caminho, null)
    suspend fun post(caminho: String, corpo: JSONObject = JSONObject()) = pedir("POST", caminho, corpo)
    suspend fun put(caminho: String, corpo: JSONObject = JSONObject()) = pedir("PUT", caminho, corpo)
    suspend fun delete(caminho: String) = pedir("DELETE", caminho, null)

    private suspend fun pedir(metodo: String, caminho: String, corpo: JSONObject?): JSONObject = withContext(Dispatchers.IO) {
        val ligacao = try {
            (URL(BuildConfig.SERVER + BASE_PATH + caminho).openConnection() as HttpURLConnection).apply {
                requestMethod = metodo
                connectTimeout = 10_000
                readTimeout = 20_000
                setRequestProperty("Accept", "application/json")
                setRequestProperty("X-Pulse-Client", "android")
                token?.let { setRequestProperty("Authorization", "Bearer $it") }
                if (corpo != null) {
                    doOutput = true
                    setRequestProperty("Content-Type", "application/json")
                    outputStream.use { it.write(corpo.toString().toByteArray()) }
                }
            }
        } catch (e: IOException) {
            throw ApiError(0, "rede", MSG_REDE)
        }
        try {
            val estado = try { ligacao.responseCode } catch (e: IOException) { throw ApiError(0, "rede", MSG_REDE) }
            val texto = try { (if (estado in 200..299) ligacao.inputStream else ligacao.errorStream)?.bufferedReader()?.use { it.readText() } ?: "" } catch (e: IOException) { "" }
            val json = try { if (texto.isBlank()) JSONObject() else JSONObject(texto) } catch (e: Exception) { JSONObject() }
            if (estado !in 200..299) {
                val erro = json.optJSONObject("erro")
                val e = ApiError(estado, erro?.optString("codigo").orEmpty().ifEmpty { "erro" }, erro?.optString("mensagem").orEmpty().ifEmpty { "Ocorreu um erro. Tenta de novo." })
                // só «nao_autenticado» é sessão perdida: um 401 de credenciais erradas não é
                if (estado == 401 && e.codigo == "nao_autenticado" && caminho != "/auth/me") aoPerderSessao?.invoke()
                Log.w("PulseApi", "$metodo $caminho -> $estado ${e.codigo}")
                throw e
            }
            json
        } finally {
            ligacao.disconnect()
        }
    }

    const val MSG_REDE = "Sem ligação ao servidor. Verifica a ligação e tenta de novo."
}

/** Mensagens em pt-PT para os códigos de erro que o utilizador pode provocar (espelho de `mensagemDeErro` da Web). */
fun mensagemDeErro(e: Throwable): String {
    if (e !is ApiError) return "Ocorreu um erro inesperado. Tenta de novo."
    return when (e.codigo) {
        "credenciais_invalidas" -> "E-mail ou palavra-passe incorretos."
        "conta_bloqueada", "demasiadas_tentativas" -> "Demasiadas tentativas. Aguarda alguns minutos e tenta de novo."
        "password_atual_errada" -> "A palavra-passe atual não está certa."
        "password_fraca" -> "A palavra-passe nova é demasiado fraca. Segue as regras indicadas."
        "password_igual" -> "A palavra-passe nova tem de ser diferente da atual."
        "pedido_invalido", "parametros_invalidos" -> "Verifica os valores e tenta de novo."
        "modulo_indisponivel" -> "Este módulo não está disponível de momento. Tenta de novo daqui a pouco."
        "modulo_desativado" -> "Este módulo foi desativado pelo administrador."
        "rede" -> e.message ?: Api.MSG_REDE
        else -> if (e.status >= 500) "O servidor não conseguiu responder. Tenta de novo daqui a pouco." else e.message ?: "Ocorreu um erro. Tenta de novo."
    }
}
