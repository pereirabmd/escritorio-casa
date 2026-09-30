package pt.pereirabmd.pulse.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.zIndex
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import pt.pereirabmd.pulse.data.*

private val NOMES_CARTAO = mapOf("calendario" to "Calendário", "tarefas" to "Tarefas", "email" to "Email", "bilhetes" to "Bilhetes CP", "rto" to "RTO", "peso" to "Peso", "compras" to "Compras", "financas" to "Finanças")
private val ALTURA_LINHA = 52.dp
private val ESPACO = 8.dp

/** Definições › Ordem do Hoje: arrastar a pega (ou as ações «Mover para cima/baixo») muda a ordem dos cartões; fica no servidor, por utilizador (ADR-054). */
@Composable
fun OrdemHojeSecao() {
    val c = carga { Api.get("/dashboard/order") }
    Secao("Ordem do Hoje") {
        Texto2("Arrasta para escolher a ordem dos cartões no Hoje. É só para ti e vale na app e na Web.")
        when (val e = c.estado) {
            Estado.ACarregar -> Texto2("A carregar…")
            is Estado.Erro -> { Aviso(TipoAviso.ERRO, e.mensagem); Botao("Tentar de novo", c.recarregar, variante = Variante.SECUNDARIO, pequeno = true) }
            is Estado.Pronto -> ListaOrdem(e.dados.optJSONArray("ordem")?.let { a -> (0 until a.length()).map { a.getString(it) } } ?: CARTOES_ORIGEM)
        }
    }
}

@Composable
private fun ListaOrdem(inicial: List<String>) {
    val avisos = LocalAvisos.current
    val scope = rememberCoroutineScope()
    val ordem = remember { mutableStateListOf<String>().apply { addAll(inicial) } }
    var arrastando by remember { mutableStateOf<String?>(null) }
    var delta by remember { mutableFloatStateOf(0f) }
    val passo = with(LocalDensity.current) { (ALTURA_LINHA + ESPACO).toPx() }
    val cores = Pulse.cores

    fun guardar() {
        scope.launch {
            try { Api.put("/dashboard/order", JSONObject().put("ordem", JSONArray(ordem.toList()))) }
            catch (e: Exception) { avisos.mostrar("Não foi possível guardar a ordem: ${mensagemDeErro(e)}") }
        }
    }
    fun mover(id: String, para: Int) {
        val de = ordem.indexOf(id)
        if (de >= 0 && para in ordem.indices && para != de) ordem.add(para, ordem.removeAt(de))
    }

    Column(verticalArrangement = Arrangement.spacedBy(ESPACO)) {
        ordem.toList().forEach { id ->
            val arrasta = arrastando == id
            Row(
                Modifier.fillMaxWidth().height(ALTURA_LINHA).then(if (arrasta) Modifier.zIndex(1f).graphicsLayer { translationY = delta } else Modifier)
                    .clip(RoundedCornerShape(Pulse.rM)).background(cores.surface).border(1.dp, cores.line, RoundedCornerShape(Pulse.rM)).padding(horizontal = 12.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                val nome = NOMES_CARTAO[id] ?: id
                Canvas(Modifier.size(32.dp).semantics {
                    contentDescription = "Mover $nome"
                    customActions = listOf(
                        CustomAccessibilityAction("Mover para cima") { mover(id, ordem.indexOf(id) - 1); guardar(); true },
                        CustomAccessibilityAction("Mover para baixo") { mover(id, ordem.indexOf(id) + 1); guardar(); true })
                }.pointerInput(id) {
                    detectDragGestures(
                        onDragStart = { arrastando = id; delta = 0f },
                        onDragEnd = { arrastando = null; delta = 0f; guardar() },
                        onDragCancel = { arrastando = null; delta = 0f; guardar() },
                    ) { change, quanto ->
                        change.consume()
                        delta += quanto.y
                        // cada linha tem altura fixa: passar meia linha troca com a vizinha e desconta esse passo ao deslocamento
                        val i = ordem.indexOf(id)
                        if (delta > passo / 2 && i < ordem.lastIndex) { mover(id, i + 1); delta -= passo }
                        else if (delta < -passo / 2 && i > 0) { mover(id, i - 1); delta += passo }
                    }
                }) {
                    for (x in listOf(12.dp, 20.dp)) for (y in listOf(9.dp, 16.dp, 23.dp)) drawCircle(cores.text2, radius = 1.8.dp.toPx(), center = Offset(x.toPx(), y.toPx()))
                }
                Texto(nome)
            }
        }
    }
}
