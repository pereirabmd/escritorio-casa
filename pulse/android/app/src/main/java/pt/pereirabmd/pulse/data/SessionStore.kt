package pt.pereirabmd.pulse.data

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import java.security.MessageDigest
import java.security.SecureRandom
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.PBEKeySpec

/** PIN de 6 dígitos guardado só como PBKDF2 com sal (nunca em claro). */
object Pin {
    const val TAMANHO = 6
    private const val ITERACOES = 120_000

    fun novoSal(): ByteArray = ByteArray(16).also { SecureRandom().nextBytes(it) }

    fun hash(pin: String, sal: ByteArray): ByteArray =
        SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(PBEKeySpec(pin.toCharArray(), sal, ITERACOES, 256)).encoded

    fun confere(pin: String, sal: ByteArray, esperado: ByteArray): Boolean = MessageDigest.isEqual(hash(pin, sal), esperado)

    fun valido(pin: String) = pin.length == TAMANHO && pin.all { it.isDigit() }
}

/** Tema escolhido em Definições (paridade com a Web: Sistema / Claro / Escuro). */
enum class Tema(val id: String, val nome: String) { SISTEMA("sistema", "Sistema"), CLARO("claro", "Claro"), ESCURO("escuro", "Escuro") }

/**
 * Tudo o que fica no telemóvel (cifrado no Keystore): o token da sessão, o PIN (só o hash), a biometria e o tema.
 * O token nunca sai daqui a não ser para o cabeçalho `Authorization`.
 */
class SessionStore(context: Context) {
    private val prefs: SharedPreferences = EncryptedSharedPreferences.create(
        context, "pulse_seguro", MasterKey.Builder(context).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV, EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
    )

    var token: String?
        get() = prefs.getString("token", null)
        set(v) = prefs.edit().apply { if (v == null) remove("token") else putString("token", v) }.apply()

    val temPin: Boolean get() = prefs.contains("pin_hash")
    var biometria: Boolean
        get() = prefs.getBoolean("biometria", true)
        set(v) = prefs.edit().putBoolean("biometria", v).apply()
    /** O utilizador disse «Agora não» à oferta de PIN: não voltamos a insistir (só em Definições). */
    var pinRecusado: Boolean
        get() = prefs.getBoolean("pin_recusado", false)
        set(v) = prefs.edit().putBoolean("pin_recusado", v).apply()
    var falhas: Int
        get() = prefs.getInt("pin_falhas", 0)
        set(v) = prefs.edit().putInt("pin_falhas", v).apply()
    var tema: Tema
        get() = Tema.entries.firstOrNull { it.id == prefs.getString("tema", "sistema") } ?: Tema.SISTEMA
        set(v) = prefs.edit().putString("tema", v.id).apply()

    fun definirPin(pin: String) {
        val sal = Pin.novoSal()
        prefs.edit().putString("pin_sal", hex(sal)).putString("pin_hash", hex(Pin.hash(pin, sal))).putInt("pin_falhas", 0).apply()
    }

    fun verificarPin(pin: String): Boolean {
        val sal = prefs.getString("pin_sal", null)?.let(::desHex) ?: return false
        val h = prefs.getString("pin_hash", null)?.let(::desHex) ?: return false
        return Pin.confere(pin, sal, h)
    }

    fun removerPin() = prefs.edit().remove("pin_sal").remove("pin_hash").putInt("pin_falhas", 0).apply()

    /** Terminar sessão: apaga o token e o PIN (o tema fica). */
    fun limparSessao() = prefs.edit().remove("token").remove("pin_sal").remove("pin_hash").remove("pin_recusado").putInt("pin_falhas", 0).apply()

    private fun hex(b: ByteArray) = b.joinToString("") { "%02x".format(it) }
    private fun desHex(s: String) = ByteArray(s.length / 2) { s.substring(it * 2, it * 2 + 2).toInt(16).toByte() }
}
