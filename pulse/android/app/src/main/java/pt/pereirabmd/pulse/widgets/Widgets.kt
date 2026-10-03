package pt.pereirabmd.pulse.widgets

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.widget.RemoteViews
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import org.json.JSONObject
import pt.pereirabmd.pulse.MainActivity
import pt.pereirabmd.pulse.R
import pt.pereirabmd.pulse.data.*
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Os dados dos widgets: o Hoje e o tempo, pela rede (com o token guardado) ou, sem rede, o último que a app guardou, marcado «desatualizado». */
object Widgets {
    class Dados(val hoje: Hoje, val tempo: JSONObject?, val quando: Long, val desatualizado: Boolean)

    private fun guardar(store: SessionStore, hoje: JSONObject, tempo: JSONObject?) {
        store.widgetCache = JSONObject().put("hoje", hoje).put("tempo", tempo ?: JSONObject.NULL).put("ts", System.currentTimeMillis()).toString()
    }

    /** `null` = sem sessão iniciada (o widget convida a abrir o Pulse). */
    suspend fun carregar(ctx: Context): Dados? {
        val store = SessionStore(ctx.applicationContext)
        Api.token = Api.token ?: store.token ?: return null
        return try {
            val j = Api.get("/dashboard/today")
            val t = runCatching { Api.get(Localizacao.caminho(Localizacao.guardada(store))) }.getOrNull()
            guardar(store, j, t)
            Dados(parseHoje(j), t, System.currentTimeMillis(), false)
        } catch (e: Exception) {
            if (e is kotlinx.coroutines.CancellationException) throw e
            val c = store.widgetCache?.let { runCatching { JSONObject(it) }.getOrNull() } ?: return null
            Dados(parseHoje(c.getJSONObject("hoje")), c.optJSONObject("tempo"), c.optLong("ts"), true)
        }
    }

    /** A app acabou de carregar o Hoje: guarda-o e atualiza os widgets sem mais pedidos. */
    fun aoCarregarHoje(ctx: Context, hojeJson: JSONObject, tempoJson: JSONObject?) {
        val store = SessionStore(ctx.applicationContext)
        guardar(store, hojeJson, tempoJson ?: store.widgetCache?.let { runCatching { JSONObject(it).optJSONObject("tempo") }.getOrNull() })
        desenharTodos(ctx, Dados(parseHoje(hojeJson), tempoJson, System.currentTimeMillis(), false))
    }

    fun atualizarTodos(ctx: Context, pendente: (() -> Unit)? = null) {
        CoroutineScope(Dispatchers.IO).launch {
            try { desenharTodos(ctx, carregar(ctx)) } catch (_: Exception) { desenharTodos(ctx, null) } finally { pendente?.invoke() }
        }
    }

    fun desenharTodos(ctx: Context, d: Dados?) {
        val gestor = AppWidgetManager.getInstance(ctx)
        for (id in gestor.getAppWidgetIds(ComponentName(ctx, WidgetHoje::class.java))) gestor.updateAppWidget(id, desenharHoje(ctx, d))
        for (id in gestor.getAppWidgetIds(ComponentName(ctx, WidgetComboio::class.java))) gestor.updateAppWidget(id, desenharComboio(ctx, d))
    }

    private fun abrir(ctx: Context, link: String): PendingIntent =
        PendingIntent.getActivity(ctx, link.hashCode(), Intent(ctx, MainActivity::class.java).setAction(Intent.ACTION_VIEW).setData(Uri.parse(link))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)

    private fun iconeTempo(nome: String): Int = when (nome) {
        "sol" -> R.drawable.ic_tempo_sol; "lua" -> R.drawable.ic_tempo_lua; "pouco_nublado" -> R.drawable.ic_tempo_pouco_nublado; "nevoeiro" -> R.drawable.ic_tempo_nevoeiro
        "chuva" -> R.drawable.ic_tempo_chuva; "aguaceiros" -> R.drawable.ic_tempo_aguaceiros; "neve" -> R.drawable.ic_tempo_neve; "trovoada" -> R.drawable.ic_tempo_trovoada
        else -> R.drawable.ic_tempo_nublado
    }

    private fun hora(ts: Long) = SimpleDateFormat("HH:mm", Locale("pt", "PT")).format(Date(ts))

    fun desenharHoje(ctx: Context, d: Dados?): RemoteViews {
        val v = RemoteViews(ctx.packageName, R.layout.widget_hoje)
        v.setOnClickPendingIntent(R.id.w_raiz, abrir(ctx, "pulse://hoje"))
        if (d == null) {
            for (id in listOf(R.id.w_comboio, R.id.w_tarefas, R.id.w_rto, R.id.w_peso)) v.setTextViewText(id, "—")
            v.setViewVisibility(R.id.w_tempo, android.view.View.GONE)
            v.setTextViewText(R.id.w_rodape, "Abre o Pulse para entrar e ver o teu dia.")
            return v
        }
        val l = linhasDoWidget(d.hoje)
        v.setTextViewText(R.id.w_comboio, l.comboio); v.setTextViewText(R.id.w_tarefas, l.tarefas); v.setTextViewText(R.id.w_rto, l.rto); v.setTextViewText(R.id.w_peso, l.peso)
        v.setOnClickPendingIntent(R.id.w_linha_comboio, abrir(ctx, "pulse://bilhetes/semana"))
        v.setOnClickPendingIntent(R.id.w_linha_tarefas, abrir(ctx, "pulse://tarefas"))
        v.setOnClickPendingIntent(R.id.w_linha_rto, abrir(ctx, "pulse://rto"))
        v.setOnClickPendingIntent(R.id.w_linha_peso, abrir(ctx, "pulse://peso"))
        val t = tempoDoWidget(d.tempo)
        if (t == null) v.setViewVisibility(R.id.w_tempo, android.view.View.GONE) else {
            v.setViewVisibility(R.id.w_tempo, android.view.View.VISIBLE)
            v.setImageViewResource(R.id.w_tempo_icone, iconeTempo(t.icone)); v.setTextViewText(R.id.w_tempo_temp, t.temp); v.setTextViewText(R.id.w_tempo_maxmin, t.maxMin)
            v.setOnClickPendingIntent(R.id.w_tempo, abrir(ctx, "pulse://tempo"))
        }
        v.setTextViewText(R.id.w_rodape, (if (d.desatualizado) "Desatualizado · " else "Atualizado às ") + hora(d.quando))
        return v
    }

    fun desenharComboio(ctx: Context, d: Dados?): RemoteViews {
        val v = RemoteViews(ctx.packageName, R.layout.widget_comboio)
        v.setOnClickPendingIntent(R.id.w_raiz, abrir(ctx, "pulse://bilhetes/semana"))
        if (d == null) { v.setTextViewText(R.id.w_linha1, "Abre o Pulse"); v.setTextViewText(R.id.w_linha2, "para entrar e ver o próximo comboio."); return v }
        val l = linhasDoWidget(d.hoje)
        v.setTextViewText(R.id.w_linha1, l.comboio)
        v.setTextViewText(R.id.w_linha2, l.comboioDetalhe.ifEmpty { if (d.desatualizado) "Desatualizado às ${hora(d.quando)}" else "" })
        return v
    }
}

abstract class WidgetBase : AppWidgetProvider() {
    override fun onUpdate(context: Context, gestor: AppWidgetManager, ids: IntArray) {
        val pendente = goAsync()
        Widgets.atualizarTodos(context) { pendente.finish() }
    }
}

class WidgetHoje : WidgetBase()
class WidgetComboio : WidgetBase()
