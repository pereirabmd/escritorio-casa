package pt.pereirabmd.pulse.ui

import android.content.Context
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import org.json.JSONObject

/** Os 73 ícones de produto das Compras (`assets/shop-icons.json`, a mesma fonte da Web): SVG linear 24×24, traço 1,6. */
object ShopIcons {
    private var caminhos: Map<String, List<Path>>? = null

    @Synchronized
    fun todos(ctx: Context): Map<String, List<Path>> = caminhos ?: run {
        val j = JSONObject(ctx.assets.open("shop-icons.json").bufferedReader().use { it.readText() })
        j.keys().asSequence().associateWith { k -> val a = j.getJSONArray(k); (0 until a.length()).map { PathParser().parsePathString(a.getString(it)).toPath() } }
            .also { caminhos = it }
    }

    fun nomes(ctx: Context): List<String> = todos(ctx).keys.toList()
}

@Composable
fun ShopIcon(nome: String, cor: Color = Pulse.cores.text, tamanho: Dp = 28.dp, modifier: Modifier = Modifier) {
    val ctx = LocalContext.current
    val caminhos = remember(nome) { ShopIcons.todos(ctx).let { it[nome] ?: it["cesto"] ?: emptyList() } }
    Canvas(modifier.size(tamanho).clearAndSetSemantics { }) {
        scale(size.width / 24f, pivot = Offset.Zero) {
            caminhos.forEach { drawPath(it, cor, style = Stroke(1.6f, cap = StrokeCap.Round, join = StrokeJoin.Round)) }
        }
    }
}
