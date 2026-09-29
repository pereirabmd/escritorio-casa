package pt.pereirabmd.pulse.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import pt.pereirabmd.pulse.util.Ponto
import pt.pereirabmd.pulse.util.fmtDataIso
import pt.pereirabmd.pulse.util.fmtDec

/** Gráfico de linha (sem bibliotecas): série, média móvel, linha do peso alvo e eixos. Espelho do `LineChart` da Web. */
@Composable
fun GraficoLinha(pontos: List<Ponto>, media: List<Ponto>?, alvo: Double?, resumoAcessivel: String, modifier: Modifier = Modifier) {
    val c = Pulse.cores
    val medidor = rememberTextMeasurer()
    if (pontos.isEmpty()) { Texto2("Sem registos neste período."); return }
    Canvas(modifier.fillMaxWidth().height(240.dp).semantics { contentDescription = resumoAcessivel }) {
        val w = size.width; val h = size.height
        val esq = 44.dp.toPx(); val dir = 10.dp.toPx(); val topo = 10.dp.toPx(); val base = 26.dp.toPx()
        val t0 = pontos.minOf { it.t }; val t1 = pontos.maxOf { it.t }
        var v0 = pontos.minOf { it.v }; var v1 = pontos.maxOf { it.v }
        if (v1 - v0 < 1) { v0 -= 0.5; v1 += 0.5 }
        val margem = (v1 - v0) * 0.12; v0 -= margem; v1 += margem
        val alvoVisivel = alvo != null && alvo in v0..v1        // um alvo longe da série não achata o gráfico
        fun x(t: Long) = esq + if (t1 == t0) (w - esq - dir) / 2 else ((t - t0).toFloat() / (t1 - t0)) * (w - esq - dir)
        fun y(v: Double) = topo + (1 - ((v - v0) / (v1 - v0)).toFloat()) * (h - topo - base)
        fun linha(ps: List<Ponto>) = Path().apply { ps.forEachIndexed { i, p -> if (i == 0) moveTo(x(p.t), y(p.v)) else lineTo(x(p.t), y(p.v)) } }
        val estiloTxt = androidx.compose.ui.text.TextStyle(fontSize = 10.sp, color = c.text2)
        for (i in 0..3) {
            val v = v0 + (v1 - v0) * i / 3
            drawLine(c.line, Offset(esq, y(v)), Offset(w - dir, y(v)), 1.dp.toPx())
            val r = medidor.measure(fmtDec(v, 1), estiloTxt)
            drawText(r, topLeft = Offset(esq - 8.dp.toPx() - r.size.width, y(v) - r.size.height / 2f))
        }
        if (alvoVisivel && alvo != null) drawLine(c.success, Offset(esq, y(alvo)), Offset(w - dir, y(alvo)), 1.5.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(10f, 8f)))
        if (media != null && media.size > 1) drawPath(linha(media), c.accent, style = Stroke(2.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
        drawPath(linha(pontos), c.primary, style = Stroke(2.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
        if (pontos.size <= 60) pontos.forEach { drawCircle(c.primary, 3.dp.toPx(), Offset(x(it.t), y(it.v))) }
        fun iso(t: Long) = java.time.Instant.ofEpochMilli(t).atZone(java.time.ZoneId.systemDefault()).toLocalDate().toString()
        val a = medidor.measure(fmtDataIso(iso(t0)), estiloTxt)
        drawText(a, topLeft = Offset(esq, h - a.size.height.toFloat()))
        if (t1 != t0) { val b = medidor.measure(fmtDataIso(iso(t1)), estiloTxt); drawText(b, topLeft = Offset(w - dir - b.size.width, h - b.size.height.toFloat())) }
    }
}
