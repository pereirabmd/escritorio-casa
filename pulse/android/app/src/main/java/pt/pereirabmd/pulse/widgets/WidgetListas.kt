package pt.pereirabmd.pulse.widgets

import android.appwidget.AppWidgetManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.widget.RemoteViews
import android.widget.RemoteViewsService
import pt.pereirabmd.pulse.R

/** Uma linha do widget de lista: o texto, o que mostrar por baixo e o que o visto faz (`chave` «t:<instância>» ou «c:<item>»). */
data class LinhaLista(val chave: String, val texto: String, val meta: String)

fun linhasTarefas(h: pt.pereirabmd.pulse.data.Hoje): List<LinhaLista> =
    h.tarefas.dados?.takeIf { h.tarefas.ok }?.hoje.orEmpty().map { LinhaLista("t:${it.id}", it.nome, listOf(it.categoria, it.hora.take(5)).filter { s -> s.isNotEmpty() }.joinToString(" · ")) }

fun linhasCompras(h: pt.pereirabmd.pulse.data.Hoje): List<LinhaLista> =
    h.compras?.dados?.takeIf { h.compras.ok }?.itens.orEmpty().map { LinhaLista("c:${it.item}", it.nome, listOfNotNull(it.quantidade?.takeIf { q -> q > 1 }?.let { q -> "×$q" }, it.nota.takeIf { n -> n.isNotEmpty() }).joinToString(" · ")) }

/** Tira da cache do Hoje (JSON) a tarefa «t:<instância>» ou a compra «c:<item>» que se marcou no widget, e acerta os contadores (puro, testado na JVM). */
fun removerDaCache(c: org.json.JSONObject, chave: String) {
    val m = c.optJSONObject("hoje")?.optJSONObject("modulos") ?: return
    fun sem(a: org.json.JSONArray, quer: (org.json.JSONObject?) -> Boolean) = org.json.JSONArray().also { n -> for (i in 0 until a.length()) if (!quer(a.optJSONObject(i))) n.put(a.get(i)) }
    when {
        chave.startsWith("t:") -> m.optJSONObject("tarefas")?.optJSONObject("dados")?.let { d ->
            d.optJSONArray("hoje")?.let { a -> d.put("hoje", sem(a) { it?.optString("id") == chave.drop(2) }); d.put("feitasHoje", d.optInt("feitasHoje") + 1) }
        }
        chave.startsWith("c:") -> m.optJSONObject("compras")?.optJSONObject("dados")?.let { d ->
            d.optJSONArray("itens")?.let { a -> d.put("itens", sem(a) { it?.optInt("item").toString() == chave.drop(2) }); d.put("pendentes", maxOf(0, d.optInt("pendentes") - 1)) }
        }
    }
}

/** As linhas do widget de lista, lidas da cache do Hoje (sem rede). */
class ListaFactory(private val ctx: Context, private val linhas: (pt.pereirabmd.pulse.data.Hoje) -> List<LinhaLista>) : RemoteViewsService.RemoteViewsFactory {
    private var itens: List<LinhaLista> = emptyList()
    override fun onCreate() {}
    override fun onDataSetChanged() { itens = Widgets.lerCache(ctx)?.let(linhas).orEmpty() }
    override fun onDestroy() {}
    override fun getCount() = itens.size
    override fun getViewAt(i: Int): RemoteViews {
        val l = itens.getOrNull(i) ?: return RemoteViews(ctx.packageName, R.layout.widget_item)
        val v = RemoteViews(ctx.packageName, R.layout.widget_item)
        v.setTextViewText(R.id.w_item_texto, l.texto)
        v.setTextViewText(R.id.w_item_meta, l.meta)
        v.setViewVisibility(R.id.w_item_meta, if (l.meta.isEmpty()) android.view.View.GONE else android.view.View.VISIBLE)
        // o visto trata o item; o nome abre o módulo
        v.setOnClickFillInIntent(R.id.w_item_visto, Intent().putExtra(WidgetAcaoReceiver.EXTRA_CHAVE, l.chave))
        v.setOnClickFillInIntent(R.id.w_item_corpo, Intent().putExtra(WidgetAcaoReceiver.EXTRA_ABRIR, if (l.chave.startsWith("t:")) "pulse://tarefas" else "pulse://compras"))
        return v
    }
    override fun getLoadingView(): RemoteViews? = null
    override fun getViewTypeCount() = 1
    override fun getItemId(i: Int) = i.toLong()
    override fun hasStableIds() = false
}

class ListaTarefasService : RemoteViewsService() { override fun onGetViewFactory(intent: Intent): RemoteViewsFactory = ListaFactory(applicationContext, ::linhasTarefas) }
class ListaComprasService : RemoteViewsService() { override fun onGetViewFactory(intent: Intent): RemoteViewsFactory = ListaFactory(applicationContext, ::linhasCompras) }
