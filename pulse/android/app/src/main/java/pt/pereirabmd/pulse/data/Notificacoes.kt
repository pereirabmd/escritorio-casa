package pt.pereirabmd.pulse.data

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
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

    /** O token FCM deste telemóvel, ou o motivo de o Google não o dar (por exemplo chave da API restrita, sem rede ou sem Play Services). */
    private suspend fun token(): Pair<String?, String?> = suspendCancellableCoroutine { k ->
        try {
            FirebaseMessaging.getInstance().token.addOnCompleteListener {
                k.resume(if (it.isSuccessful && !it.result.isNullOrEmpty()) it.result to null else null to (it.exception?.message ?: "o Google não devolveu o token"))
            }
        } catch (e: Exception) { k.resume(null to (e.message ?: e.javaClass.simpleName)) }
    }

    /** Regista (ou renova) este telemóvel no servidor para a conta com sessão iniciada. Devolve `null` se ficou registado, ou o motivo da falha. */
    suspend fun registar(ctx: Context, novoToken: String? = null): String? {
        val store = SessionStore(ctx.applicationContext)
        if (store.token == null) return "sem sessão iniciada"
        Api.token = Api.token ?: store.token
        val t = novoToken ?: token().let { (tk, erro) -> tk ?: return "sem token do Google: $erro" }
        return try {
            val r = Api.post("/devices", JSONObject().put("token", t).put("nome", "${Build.MANUFACTURER} ${Build.MODEL}".take(80)).put("plataforma", "android"))
            store.dispositivoId = r.optInt("id", 0)
            null
        } catch (e: Exception) { "o servidor recusou o registo: ${(e as? ApiError)?.message ?: e.javaClass.simpleName}" }
    }

    /** Ao terminar a sessão este telemóvel deixa de receber os avisos da conta. */
    suspend fun remover(ctx: Context) {
        val store = SessionStore(ctx.applicationContext)
        val id = store.dispositivoId
        if (id == 0) return
        try { Api.delete("/devices/$id") } catch (_: Exception) { /* sem rede: o servidor desativa o token quando o Google o recusar */ }
        store.dispositivoId = 0
    }

    /** Desenha o aviso (o servidor manda só dados, por isso é sempre a app a mostrá-lo): canal do módulo, toque que abre o sítio certo (`link`) e, nas
     *  tarefas, os botões «Marcar feita» e «Daqui a 1 h» que agem sem abrir a app. */
    fun mostrar(ctx: Context, titulo: String, corpo: String, modulo: String, link: String = "", instancia: String = "") {
        if (!permitidas(ctx)) return
        val id = (System.currentTimeMillis() % Int.MAX_VALUE).toInt()
        val abrir = PendingIntent.getActivity(ctx, id, Intent(ctx, MainActivity::class.java).putExtra(EXTRA_LINK, link)
            .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val canal = if (CANAIS.any { it.first == modulo }) modulo else "geral"
        val b = NotificationCompat.Builder(ctx, "pulse_$canal").setSmallIcon(R.drawable.ic_stat_pulse).setContentTitle(titulo).setContentText(corpo)
            .setStyle(NotificationCompat.BigTextStyle().bigText(corpo)).setPriority(NotificationCompat.PRIORITY_HIGH).setAutoCancel(true).setContentIntent(abrir)
        if (instancia.isNotEmpty()) {
            b.addAction(0, "Marcar feita", acao(ctx, id, AcaoNotificacaoReceiver.CONCLUIR, instancia))
            b.addAction(0, "Daqui a 1 h", acao(ctx, id, AcaoNotificacaoReceiver.LEMBRAR, instancia))
        }
        try { NotificationManagerCompat.from(ctx).notify(id, b.build()) } catch (_: SecurityException) { /* sem permissão */ }
    }

    const val EXTRA_LINK = "pulse_link"

    private fun acao(ctx: Context, id: Int, qual: String, instancia: String): PendingIntent =
        PendingIntent.getBroadcast(ctx, id * 2 + if (qual == AcaoNotificacaoReceiver.CONCLUIR) 0 else 1,
            Intent(ctx, AcaoNotificacaoReceiver::class.java).setAction(qual).putExtra("instancia", instancia).putExtra("notificacao", id),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
}

/** Os botões da notificação: chamam as mesmas ações do Pulse (`tarefas.concluir`, `tarefas.lembrar_mais_tarde`) com a sessão guardada, sem abrir a app. */
class AcaoNotificacaoReceiver : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        val instancia = intent.getStringExtra("instancia") ?: return
        val notificacao = intent.getIntExtra("notificacao", 0)
        val concluir = intent.action == CONCLUIR
        val pendente = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            val gestor = NotificationManagerCompat.from(ctx)
            try {
                val store = SessionStore(ctx.applicationContext)
                Api.token = Api.token ?: store.token
                if (Api.token == null) throw ApiError(401, "nao_autenticado", "sem sessão")
                val params = JSONObject().put("instancia", instancia).also { if (!concluir) it.put("minutos", 60) }
                Api.post("/actions/${if (concluir) "tarefas.concluir" else "tarefas.lembrar_mais_tarde"}", JSONObject().put("params", params))
                gestor.cancel(notificacao)
            } catch (e: Exception) {
                // a notificação fica, a dizer porquê: o utilizador toca nela e resolve dentro da app
                Notificacoes.mostrar(ctx, if (concluir) "Não foi possível marcar como feita" else "Não foi possível adiar o lembrete", mensagemDeErro(e), "tarefas", "pulse://tarefas/hoje")
                gestor.cancel(notificacao)
            } finally { pendente.finish() }
        }
    }

    companion object {
        const val CONCLUIR = "pt.pereirabmd.pulse.CONCLUIR"
        const val LEMBRAR = "pt.pereirabmd.pulse.LEMBRAR"
    }
}

class PulseMessagingService : FirebaseMessagingService() {
    private val scope = CoroutineScope(Dispatchers.IO)

    /** O Google renovou o token: volta a registar (só se houver sessão). */
    override fun onNewToken(token: String) { scope.launch { Notificacoes.registar(applicationContext, token) } }

    override fun onMessageReceived(m: RemoteMessage) {
        // desde o ADR-061 o servidor manda só dados; o bloco `notification` (mensagens antigas ou de teste na consola) continua a servir de reserva
        val titulo = m.data["titulo"] ?: m.notification?.title ?: return
        Notificacoes.mostrar(applicationContext, titulo, m.data["corpo"] ?: m.notification?.body.orEmpty(), m.data["modulo"].orEmpty(),
            m.data["link"].orEmpty(), m.data["instancia"].orEmpty())
    }
}
