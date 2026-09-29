package pt.pereirabmd.pulse.data

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import pt.pereirabmd.pulse.BuildConfig
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

data class Atualizacao(val versionCode: Int, val versionName: String, val url: String, val sha256: String?, val notas: String)

/**
 * Atualização interna (ADR-026): o APK vive no Pi, ao lado de um `version.json`. A app compara o `versionCode`, descarrega para a cache,
 * confere o SHA-256 e entrega ao instalador do Android (que só aceita se a assinatura for a mesma, ADR-034).
 */
object Updater {
    private val BASE = BuildConfig.SERVER + "/apk/"

    /** `null` se está atualizada ou se não foi possível saber (sem ligação não é um erro para o utilizador). */
    suspend fun verificar(atual: Int = BuildConfig.VERSION_CODE): Atualizacao? = withContext(Dispatchers.IO) {
        try {
            val c = URL(BASE + "version.json").openConnection() as HttpURLConnection
            c.connectTimeout = 8_000; c.readTimeout = 8_000
            try {
                if (c.responseCode != 200) return@withContext null
                interpretar(JSONObject(c.inputStream.bufferedReader().use { it.readText() }), atual)
            } finally { c.disconnect() }
        } catch (e: Exception) { null }
    }

    fun interpretar(j: JSONObject, atual: Int): Atualizacao? {
        val codigo = j.optInt("versionCode", 0)
        if (codigo <= atual) return null
        val url = resolver(j.optString("url"))
        return Atualizacao(codigo, j.optString("versionName", codigo.toString()), url ?: return null, j.txt("sha256")?.lowercase()?.takeIf { it.isNotEmpty() }, j.optString("notas", ""))
    }

    /** Só se descarrega do próprio servidor do Pulse; um endereço de outro sítio é ignorado. */
    fun resolver(url: String): String? {
        if (url.isBlank()) return null
        val abs = if (url.startsWith("http")) url else BASE + url.trimStart('/')
        return abs.takeIf { it.startsWith(BuildConfig.SERVER + "/") }
    }

    suspend fun descarregar(ctx: Context, a: Atualizacao, progresso: (Float) -> Unit): File = withContext(Dispatchers.IO) {
        val dir = File(ctx.cacheDir, "update").apply { deleteRecursively(); mkdirs() }
        val f = File(dir, "pulse.apk")
        val c = URL(a.url).openConnection() as HttpURLConnection
        c.connectTimeout = 10_000; c.readTimeout = 30_000
        try {
            if (c.responseCode != 200) throw ApiError(c.responseCode, "download", "Não foi possível descarregar a atualização.")
            val total = c.contentLengthLong.takeIf { it > 0 }
            val md = MessageDigest.getInstance("SHA-256")
            var lidos = 0L
            c.inputStream.use { entrada -> f.outputStream().use { saida ->
                val buf = ByteArray(32 * 1024)
                while (true) {
                    val n = entrada.read(buf); if (n < 0) break
                    saida.write(buf, 0, n); md.update(buf, 0, n); lidos += n
                    if (total != null) progresso(lidos.toFloat() / total)
                }
            } }
            val hash = md.digest().joinToString("") { "%02x".format(it) }
            if (a.sha256 != null && a.sha256 != hash) { f.delete(); throw ApiError(0, "download", "A atualização descarregada está corrompida. Tenta de novo.") }
            f
        } finally { c.disconnect() }
    }

    /** Devolve `false` se o Android ainda não deixou o Pulse instalar apps: abre essa definição e o utilizador volta a tocar. */
    fun instalar(ctx: Context, apk: File): Boolean {
        if (!ctx.packageManager.canRequestPackageInstalls()) {
            ctx.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${ctx.packageName}")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            return false
        }
        val uri = FileProvider.getUriForFile(ctx, "${ctx.packageName}.files", apk)
        ctx.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uri, "application/vnd.android.package-archive")
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK))
        return true
    }
}
