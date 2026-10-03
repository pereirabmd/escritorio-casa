package pt.pereirabmd.pulse.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

internal sealed interface Forma
internal class Rect(val x: Float, val y: Float, val w: Float, val h: Float, val rx: Float) : Forma
internal class Circulo(val cx: Float, val cy: Float, val r: Float) : Forma
internal class Caminho(val d: String) : Forma

private fun r(x: Float, y: Float, w: Float, h: Float, rx: Float) = Rect(x, y, w, h, rx)
private fun c(x: Float, y: Float, raio: Float) = Circulo(x, y, raio)
private fun p(d: String) = Caminho(d)

/** Os mesmos ícones lineares da Web (`web/src/components/Icon.tsx`): grelha 24, traço 1,75. Sem emojis (CLAUDE.md). */
enum class Icone(internal val formas: List<Forma>) {
    MAIS(listOf(r(4f, 4f, 6.5f, 6.5f, 1.5f), r(13.5f, 4f, 6.5f, 6.5f, 1.5f), r(4f, 13.5f, 6.5f, 6.5f, 1.5f), r(13.5f, 13.5f, 6.5f, 6.5f, 1.5f))),
    HOJE(listOf(c(12f, 12f, 4f), p("M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6 7 7M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4"))),
    TAREFAS(listOf(r(4f, 4f, 16f, 16f, 3.5f), p("m8.5 12.2 2.6 2.6 4.6-5.2"))),
    CALENDARIO(listOf(r(4f, 5.5f, 16f, 14.5f, 3f), p("M4 10h16M8.5 3.5v4M15.5 3.5v4"))),
    EMAIL(listOf(r(3.5f, 5.5f, 17f, 13f, 3f), p("m4.5 8 7.5 5.5L19.5 8"))),
    BILHETE(listOf(r(6f, 3.5f, 12f, 13.5f, 3.5f), p("M6 11h12M9 20.5l1.6-3.5M15 20.5 13.4 17"), c(9.3f, 14f, .6f), c(14.7f, 14f, .6f))),
    PESO(listOf(r(4f, 4.5f, 16f, 15f, 4f), p("M8.5 9.5a4.2 4.2 0 0 1 7 0M12 9.6l1.6-1.3"))),
    RTO(listOf(r(5f, 3.5f, 14f, 17f, 2.5f), p("M9 8h1.5M13.5 8H15M9 12h1.5M13.5 12H15M10 20.5v-4h4v4"))),
    FINANCAS(listOf(p("M4 8.5A2.5 2.5 0 0 1 6.5 6H18a2 2 0 0 1 2 2v9.5a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 17.5z"), p("M4 8.5V7a2 2 0 0 1 2-2h9M15.5 13.5h4.5"))),
    COMPRAS(listOf(p("M5 9h14l-1.3 9.2a2 2 0 0 1-2 1.8H8.3a2 2 0 0 1-2-1.8z"), p("M9 9V7a3 3 0 0 1 6 0v2"))),
    DEFINICOES(listOf(p("M5 7h9M18 7h1M5 17h1M10 17h9"), c(16f, 7f, 2f), c(8f, 17f, 2f))),
    SAIR(listOf(p("M10 4.5H7a2.5 2.5 0 0 0-2.5 2.5v10A2.5 2.5 0 0 0 7 19.5h3M15 8l4 4-4 4M19 12H9.5"))),
    OLHO(listOf(p("M2.8 12S6 6.5 12 6.5 21.2 12 21.2 12 18 17.5 12 17.5 2.8 12 2.8 12z"), c(12f, 12f, 2.7f))),
    OLHO_OFF(listOf(p("M4 4l16 16M9.9 6.7A9 9 0 0 1 12 6.5c6 0 9.2 5.5 9.2 5.5a15 15 0 0 1-2.6 3.2M6.4 8.4A15 15 0 0 0 2.8 12S6 17.5 12 17.5c1.3 0 2.5-.3 3.5-.7M10 10a2.7 2.7 0 0 0 3.9 3.5"))),
    ALERTA(listOf(p("M12 4.2 21 19.5H3z"), p("M12 10v4.2M12 16.9v.1"))),
    INFO(listOf(c(12f, 12f, 8.5f), p("M12 11v5M12 8v.1"))),
    CERTO(listOf(p("m5 12.5 4.5 4.5L19 7.5"))),
    PONTO(listOf(c(12f, 12f, 3f))),
    SETA(listOf(p("M5 12h14M13 6l6 6-6 6"))),
    VOLTAR(listOf(p("M19 12H5M11 6l-6 6 6 6"))),
    CHAVE(listOf(c(8f, 15f, 3.5f), p("m10.5 12.5 8-8M15.5 7.5l2.5 2.5M13 10l2 2"))),
    DISPOSITIVO(listOf(r(7f, 3.5f, 10f, 17f, 2.5f), p("M11 17.5h2"))),
    LIGACAO(listOf(p("M4 9a12 12 0 0 1 16 0M7 12.5a8 8 0 0 1 10 0M10 16a4 4 0 0 1 4 0M12 19.5v.1"))),
    TEMPO_SOL(listOf(c(12f, 12f, 3.8f), p("M12 3.5v2M12 18.5v2M3.5 12h2M18.5 12h2M6 6l1.4 1.4M16.6 16.6 18 18M18 6l-1.4 1.4M7.4 16.6 6 18"))),
    TEMPO_LUA(listOf(p("M19 14.5A7.5 7.5 0 0 1 9.5 5a7.5 7.5 0 1 0 9.5 9.5z"))),
    TEMPO_POUCO_NUBLADO(listOf(c(9f, 8.5f, 2.8f), p("M9 3.2v1M3.7 8.5h1M5.2 4.7l.7.7M12.8 4.7l-.7.7"), p("M9.5 19.5a3.4 3.4 0 0 1-.4-6.7 4.7 4.7 0 0 1 8.9 1 2.9 2.9 0 0 1-.4 5.7z"))),
    TEMPO_NUBLADO(listOf(p("M7 19a4.3 4.3 0 0 1-.6-8.5 6 6 0 0 1 11.3 1.2A3.7 3.7 0 0 1 17 19z"))),
    TEMPO_NEVOEIRO(listOf(p("M4 9h16M6 13h12M4 17h16"))),
    TEMPO_CHUVA(listOf(p("M7.5 15.5a3.8 3.8 0 0 1-.5-7.5 5.3 5.3 0 0 1 10 1.1 3.2 3.2 0 0 1-.5 6.4z"), p("m8.5 18.5-1 2M12.5 18.5l-1 2M16.5 18.5l-1 2"))),
    TEMPO_AGUACEIROS(listOf(p("M7.5 15.5a3.8 3.8 0 0 1-.5-7.5 5.3 5.3 0 0 1 10 1.1 3.2 3.2 0 0 1-.5 6.4z"), p("m9 18.5-.8 1.6M13 18.5l-.8 1.6M17 18.5l-.8 1.6"))),
    TEMPO_NEVE(listOf(p("M7.5 15.5a3.8 3.8 0 0 1-.5-7.5 5.3 5.3 0 0 1 10 1.1 3.2 3.2 0 0 1-.5 6.4z"), p("M8 18.5v.1M12 19.5v.1M16 18.5v.1M10 21v.1M14 21v.1"))),
    TEMPO_TROVOADA(listOf(p("M7.5 15.5a3.8 3.8 0 0 1-.5-7.5 5.3 5.3 0 0 1 10 1.1 3.2 3.2 0 0 1-.5 6.4z"), p("m12.5 15-2.5 3.5h3.5L11.5 22")))
}

@Composable
fun Icon(icone: Icone, cor: Color = Pulse.cores.text, tamanho: Dp = 24.dp, modifier: Modifier = Modifier) {
    val caminhos = androidx.compose.runtime.remember(icone) { icone.formas.map { f -> (f as? Caminho)?.let { PathParser().parsePathString(it.d).toPath() } } }
    Canvas(modifier.size(tamanho).clearAndSetSemantics { }) {
        scale(size.width / 24f, pivot = Offset.Zero) {
            val traco = Stroke(width = 1.75f, cap = StrokeCap.Round, join = StrokeJoin.Round)
            icone.formas.forEachIndexed { i, f ->
                when (f) {
                    is Rect -> drawRoundRect(cor, Offset(f.x, f.y), Size(f.w, f.h), CornerRadius(f.rx), style = traco)
                    is Circulo -> drawCircle(cor, f.r, Offset(f.cx, f.cy), style = traco)
                    is Caminho -> caminhos[i]?.let { drawPath(it, cor, style = traco) }
                }
            }
        }
    }
}

/** O ícone do tempo para o `icone` que o servidor devolve (sol, lua, pouco_nublado, nublado, nevoeiro, chuva, aguaceiros, neve, trovoada). */
fun iconeTempo(nome: String): Icone = when (nome) {
    "sol" -> Icone.TEMPO_SOL; "lua" -> Icone.TEMPO_LUA; "pouco_nublado" -> Icone.TEMPO_POUCO_NUBLADO; "nevoeiro" -> Icone.TEMPO_NEVOEIRO
    "chuva" -> Icone.TEMPO_CHUVA; "aguaceiros" -> Icone.TEMPO_AGUACEIROS; "neve" -> Icone.TEMPO_NEVE; "trovoada" -> Icone.TEMPO_TROVOADA
    else -> Icone.TEMPO_NUBLADO
}
