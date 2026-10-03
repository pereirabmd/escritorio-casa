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
        // dados novos do servidor: o que se marcou como feito/comprado a partir do widget já lá vem tratado, por isso as «ocultas» recomeçam vazias
        store.widgetCache = JSONObject().put("hoje", hoje).put("tempo", tempo ?: JSONObject.NULL).put("ts", System.currentTimeMillis()).toString()
    }

    /** O último Hoje guardado, sem rede (as listas dos widgets leem daqui), já sem o que se marcou nos widgets depois. */
    fun lerCache(ctx: Context): Hoje? {
        val c = SessionStore(ctx.applicationContext).widgetCache?.let { runCatching { JSONObject(it) }.getOrNull() } ?: return null
        return runCatching { parseHoje(c.getJSONObject("hoje")) }.getOrNull()
    }

    /** Marca (só na cache dos widgets, até haver dados novos) uma tarefa ou compra como tratada, para a lista a esconder já. */
    fun ocultar(ctx: Context, chave: String) {
        val store = SessionStore(ctx.applicationContext)
        val c = store.widgetCache?.let { runCatching { JSONObject(it) }.getOrNull() } ?: return
        removerDaCache(c, chave)
        store.widgetCache = c.toString()
    }

    /** Pede aos widgets de lista que releiam a cache (depois de marcar um visto). */
    fun reler(ctx: Context) {
        val gestor = AppWidgetManager.getInstance(ctx)
        for (cls in listOf(WidgetTarefas::class.java, WidgetCompras::class.java)) {
            val ids = gestor.getAppWidgetIds(ComponentName(ctx, cls))
            gestor.notifyAppWidgetViewDataChanged(ids, R.id.w_lista)
        }
        lerCache(ctx)?.let { h -> val d = Dados(h, null, System.currentTimeMillis(), false); desenharPeso(ctx, d) }
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
        for (id in gestor.getAppWidgetIds(ComponentName(ctx, WidgetTarefas::class.java))) gestor.updateAppWidget(id, desenharLista(ctx, id, "Tarefas de hoje", ListaTarefasService::class.java, "pulse://tarefas", d, TipoLista.TAREFAS))
        for (id in gestor.getAppWidgetIds(ComponentName(ctx, WidgetCompras::class.java))) gestor.updateAppWidget(id, desenharLista(ctx, id, "Lista de compras", ListaComprasService::class.java, "pulse://compras", d, TipoLista.COMPRAS))
        for (id in gestor.getAppWidgetIds(ComponentName(ctx, WidgetVoz::class.java))) gestor.updateAppWidget(id, desenharVoz(ctx))
        desenharPeso(ctx, d)
        for (cls in listOf(WidgetTarefas::class.java, WidgetCompras::class.java)) gestor.notifyAppWidgetViewDataChanged(gestor.getAppWidgetIds(ComponentName(ctx, cls)), R.id.w_lista)
    }

    enum class TipoLista { TAREFAS, COMPRAS }

    /** Os widgets de lista: título, a lista (um serviço de itens) e, vazia, uma frase. Tocar no visto trata o item; tocar no nome abre o módulo. */
    fun desenharLista(ctx: Context, id: Int, titulo: String, servico: Class<*>, linkModulo: String, d: Dados?, tipo: TipoLista): RemoteViews {
        val v = RemoteViews(ctx.packageName, R.layout.widget_lista)
        v.setTextViewText(R.id.w_titulo, titulo)
        v.setOnClickPendingIntent(R.id.w_titulo, abrir(ctx, linkModulo))
        v.setRemoteAdapter(R.id.w_lista, Intent(ctx, servico).apply { putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, id); data = Uri.parse(toUri(Intent.URI_INTENT_SCHEME)) })
        v.setEmptyView(R.id.w_lista, R.id.w_vazio)
        v.setTextViewText(R.id.w_vazio, if (d == null) "Abre o Pulse para entrar." else if (tipo == TipoLista.TAREFAS) "Nada por fazer hoje." else "Nada por comprar.")
        val modelo = Intent(ctx, WidgetAcaoReceiver::class.java).setAction(WidgetAcaoReceiver.ACAO_ITEM)
        val flags = PendingIntent.FLAG_UPDATE_CURRENT or (if (android.os.Build.VERSION.SDK_INT >= 31) PendingIntent.FLAG_MUTABLE else 0)
        v.setPendingIntentTemplate(R.id.w_lista, PendingIntent.getBroadcast(ctx, 4000 + tipo.ordinal, modelo, flags))
        return v
    }

    fun desenharVoz(ctx: Context): RemoteViews {
        val v = RemoteViews(ctx.packageName, R.layout.widget_voz)
        v.setOnClickPendingIntent(R.id.w_raiz, abrir(ctx, "pulse://assistente"))
        return v
    }

    /** Peso rápido: o último peso, o minigráfico dos 7 dias e o botão que abre o diálogo para registar. */
    fun desenharPeso(ctx: Context, d: Dados?) {
        val gestor = AppWidgetManager.getInstance(ctx)
        val ids = gestor.getAppWidgetIds(ComponentName(ctx, WidgetPeso::class.java))
        if (ids.isEmpty()) return
        for (id in ids) {
            val v = RemoteViews(ctx.packageName, R.layout.widget_peso)
            val p = d?.hoje?.peso?.dados
            v.setTextViewText(R.id.w_peso_valor, if (p?.ultimoPeso != null) pt.pereirabmd.pulse.util.fmtPeso(p.ultimoPeso) else "—")
            v.setTextViewText(R.id.w_peso_estado, when { d == null -> "Abre o Pulse para entrar"; p == null -> "indisponível"; p.registadoHoje -> "Registo de hoje feito" else -> "Ainda não registaste hoje" })
            val bmp = if (p != null) minigraficoPeso(ctx, p.ultimos7) else null
            if (bmp != null) { v.setImageViewBitmap(R.id.w_peso_grafico, bmp); v.setViewVisibility(R.id.w_peso_grafico, android.view.View.VISIBLE) } else v.setViewVisibility(R.id.w_peso_grafico, android.view.View.GONE)
            v.setOnClickPendingIntent(R.id.w_peso_botao, PendingIntent.getActivity(ctx, 5000, Intent(ctx, PesoRapidoActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT))
            v.setOnClickPendingIntent(R.id.w_peso_texto, abrir(ctx, "pulse://peso"))
            gestor.updateAppWidget(id, v)
        }
    }

    /** O minigráfico de 7 dias (linha + pontos) desenhado num bitmap, com as cores do tema atual. `null` com menos de 2 registos. */
    fun minigraficoPeso(ctx: Context, pontos: List<Pair<String, Double>>): android.graphics.Bitmap? {
        if (pontos.size < 2) return null
        val w = 360; val h = 96; val pad = 10f
        val bmp = android.graphics.Bitmap.createBitmap(w, h, android.graphics.Bitmap.Config.ARGB_8888)
        val c = android.graphics.Canvas(bmp)
        val cor = ctx.getColor(R.color.widget_primary); val fundo = ctx.getColor(R.color.widget_surface)
        val linha = android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG).apply { color = cor; style = android.graphics.Paint.Style.STROKE; strokeWidth = 5f; strokeCap = android.graphics.Paint.Cap.ROUND; strokeJoin = android.graphics.Paint.Join.ROUND }
        val hoje = java.time.LocalDate.now()
        fun dia(iso: String) = runCatching { java.time.temporal.ChronoUnit.DAYS.between(java.time.LocalDate.parse(iso), hoje).toInt() }.getOrDefault(6).coerceIn(0, 6)
        var v0 = pontos.minOf { it.second }; var v1 = pontos.maxOf { it.second }
        if (v1 - v0 < 0.4) { v0 -= 0.2; v1 += 0.2 }
        fun x(iso: String) = pad + ((6 - dia(iso)) / 6f) * (w - 2 * pad)
        fun y(v: Double) = pad + (1 - ((v - v0) / (v1 - v0)).toFloat()) * (h - 2 * pad)
        val path = android.graphics.Path()
        pontos.forEachIndexed { i, p -> if (i == 0) path.moveTo(x(p.first), y(p.second)) else path.lineTo(x(p.first), y(p.second)) }
        c.drawPath(path, linha)
        val ponto = android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG)
        pontos.forEach { p ->
            ponto.style = android.graphics.Paint.Style.FILL; ponto.color = fundo; c.drawCircle(x(p.first), y(p.second), 8f, ponto)
            ponto.style = android.graphics.Paint.Style.STROKE; ponto.color = cor; ponto.strokeWidth = 4f; c.drawCircle(x(p.first), y(p.second), 8f, ponto)
        }
        return bmp
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

class WidgetTarefas : WidgetBase()
class WidgetCompras : WidgetBase()
class WidgetPeso : WidgetBase()
class WidgetVoz : WidgetBase()
