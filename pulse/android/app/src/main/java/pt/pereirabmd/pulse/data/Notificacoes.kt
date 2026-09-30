package pt.pereirabmd.pulse.data

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.google.firebase.messaging.FirebaseMessaging
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import org.json.JSONObject
import pt.pereirabmd.pulse.MainActivity
import pt.pereirabmd.pulse.R
import kotlin.coroutines.resume

/**
 * Notificações por FCM (ADR-032/045). O servidor guarda cada aviso como evento e envia-o com prioridade alta para o canal
 * `pulse_<módulo>`; aqui ficam os canais, o registo deste telemóvel (`POST /devices`) e a apresentação com a app aberta.
 */
object Notificacoes {
    /** Um canal por módulo (o utilizador pode silenciar cada um nas definições do Android); `pulse_geral` é o de reserva. */
    private val CANAIS = listOf("geral" to "Geral", "teste" to "Teste", "bilhetes" to "Bilhetes CP", "tarefas" to "Tarefas", "financas" to "Finanças",
        "peso" to "Peso", "rto" to "RTO", "compras" to "Compras")

    fun criarCanais(ctx: Context) {
        val gestor = ctx.getSystemService(NotificationManager::class.java)
        CANAIS.forEach { (id, nome) ->
            gestor.createNotificationChannel(NotificationChannel("pulse_$id", nome, NotificationManager.IMPORTANCE_HIGH))
        }
    }

    /** Antes do Android 13 não há permissão a pedir: as notificações estão sempre permitidas (o utilizador pode desligá-las no sistema). */
    fun permitidas(ctx: Context): Boolean =
        (Build.VERSION.SDK_INT < 33 || ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED) &&
            NotificationManagerCompat.from(ctx).areNotificationsEnabled()

    /** O token FCM deste telemóvel (`null` se o Google não o der, por exemplo sem rede). */
    private suspend fun token(): String? = suspendCancellableCoroutine { k ->
        FirebaseMessaging.getInstance().token.addOnCompleteListener { k.resume(if (it.isSuccessful) it.result else null) }
    }

    /** Regista (ou renova) este telemóvel no servidor para a conta com sessão iniciada. Devolve `true` se ficou registado. */
    suspend fun registar(ctx: Context, novoToken: String? = null): Boolean {
        val store = SessionStore(ctx.applicationContext)
        if (store.token == null) return false
        Api.token = Api.token ?: store.token
        val t = novoToken ?: token() ?: return false
        return try {
            val r = Api.post("/devices", JSONObject().put("token", t).put("nome", "${Build.MANUFACTURER} ${Build.MODEL}".take(80)).put("plataforma", "android"))
            store.dispositivoId = r.optInt("id", 0)
            true
        } catch (e: Exception) { false }
    }

    /** Ao terminar a sessão este telemóvel deixa de receber os avisos da conta. */
    suspend fun remover(ctx: Context) {
        val store = SessionStore(ctx.applicationContext)
        val id = store.dispositivoId
        if (id == 0) return
        try { Api.delete("/devices/$id") } catch (_: Exception) { /* sem rede: o servidor desativa o token quando o Google o recusar */ }
        store.dispositivoId = 0
    }

    /** Mostra o aviso quando a app está aberta (em segundo plano o Android mostra-o sozinho, no canal que o servidor indicou). */
    fun mostrar(ctx: Context, titulo: String, corpo: String, modulo: String) {
        if (!permitidas(ctx)) return
        val abrir = PendingIntent.getActivity(ctx, 0, Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val canal = if (CANAIS.any { it.first == modulo }) modulo else "geral"
        val n = NotificationCompat.Builder(ctx, "pulse_$canal").setSmallIcon(R.drawable.ic_stat_pulse).setContentTitle(titulo).setContentText(corpo)
            .setStyle(NotificationCompat.BigTextStyle().bigText(corpo)).setPriority(NotificationCompat.PRIORITY_HIGH).setAutoCancel(true).setContentIntent(abrir).build()
        try { NotificationManagerCompat.from(ctx).notify((System.currentTimeMillis() % Int.MAX_VALUE).toInt(), n) } catch (_: SecurityException) { /* sem permissão */ }
    }
}

class PulseMessagingService : FirebaseMessagingService() {
    private val scope = CoroutineScope(Dispatchers.IO)

    /** O Google renovou o token: volta a registar (só se houver sessão). */
    override fun onNewToken(token: String) { scope.launch { Notificacoes.registar(applicationContext, token) } }

    override fun onMessageReceived(m: RemoteMessage) {
        val n = m.notification ?: return
        Notificacoes.mostrar(applicationContext, n.title.orEmpty(), n.body.orEmpty(), m.data["modulo"].orEmpty())
    }
}
