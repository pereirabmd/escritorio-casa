package pt.pereirabmd.pulse.widgets

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.widget.Toast
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import org.json.JSONObject
import pt.pereirabmd.pulse.MainActivity
import pt.pereirabmd.pulse.data.*

/** O toque nos widgets de lista: o visto marca a tarefa como feita / a compra como comprada (as mesmas ações do Pulse, com a sessão guardada, sem abrir a app); o nome abre o módulo. */
class WidgetAcaoReceiver : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        intent.getStringExtra(EXTRA_ABRIR)?.let {
            ctx.startActivity(Intent(ctx, MainActivity::class.java).setAction(Intent.ACTION_VIEW).setData(Uri.parse(it)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP))
            return
        }
        val chave = intent.getStringExtra(EXTRA_CHAVE) ?: return
        val pendente = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val store = SessionStore(ctx.applicationContext)
                Api.token = Api.token ?: store.token
                if (Api.token == null) throw ApiError(401, "nao_autenticado", "sem sessão")
                val (acao, params) = when {
                    chave.startsWith("t:") -> "tarefas.concluir" to JSONObject().put("instancia", chave.drop(2))
                    chave.startsWith("c:") -> "compras.comprado" to JSONObject().put("item", chave.drop(2).toInt()).put("comprado", true)
                    else -> return@launch
                }
                Api.post("/actions/$acao", JSONObject().put("params", params))
                Widgets.ocultar(ctx, chave)
                Widgets.reler(ctx)
                Widgets.atualizarTodos(ctx)                       // dados novos do servidor (o Hoje já sem este item)
            } catch (e: Exception) {
                if (e is kotlinx.coroutines.CancellationException) throw e
                CoroutineScope(Dispatchers.Main).launch { Toast.makeText(ctx, "Não consegui: ${(e as? ApiError)?.message ?: "sem ligação"}", Toast.LENGTH_LONG).show() }
            } finally { pendente.finish() }
        }
    }

    companion object {
        const val ACAO_ITEM = "pt.pereirabmd.pulse.WIDGET_ITEM"
        const val EXTRA_CHAVE = "widget_chave"
        const val EXTRA_ABRIR = "widget_abrir"
    }
}
