package pt.pereirabmd.pulse.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
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

/** Definições › O meu Hoje: arrastar a pega (ou as ações «Mover para cima/baixo») muda a ordem dos cartões e o interruptor mostra/esconde cada um;
 *  fica no servidor, por pessoa (ADR-054/063). Só aparecem os cartões dos módulos a que a pessoa tem acesso. */
@Composable
fun OrdemHojeSecao() {
    val c = carga { Api.get("/dashboard/order") }
    Secao("O meu Hoje") {
        Texto2("Escolhe que cartões aparecem no teu Hoje e por que ordem (arrasta). É só para ti e vale na app e na Web.")
        when (val e = c.estado) {
            Estado.ACarregar -> Texto2("A carregar…")
            is Estado.Erro -> { Aviso(TipoAviso.ERRO, e.mensagem); Botao("Tentar de novo", c.recarregar, variante = Variante.SECUNDARIO, pequeno = true) }
            is Estado.Pronto -> {
                val ordem = e.dados.strs("ordem").ifEmpty { CARTOES_ORIGEM }
                val disponiveis = e.dados.strs("disponiveis").ifEmpty { ordem }
                if (disponiveis.isEmpty()) Texto2("Ainda não tens nenhum módulo. Pede ao administrador.")
                else ListaOrdem(ordem, disponiveis, e.dados.strs("ocultos"))
            }
        }
    }
}

@Composable
private fun ListaOrdem(completa: List<String>, disponiveis: List<String>, ocultosIniciais: List<String>) {
    val inicial = completa.filter { it in disponiveis }
    val ocultos = remember { mutableStateListOf<String>().apply { addAll(ocultosIniciais) } }
    val avisos = LocalAvisos.current
    val scope = rememberCoroutineScope()
    val ordem = remember { mutableStateListOf<String>().apply { addAll(inicial) } }
    var arrastando by remember { mutableStateOf<String?>(null) }
    var delta by remember { mutableFloatStateOf(0f) }
    val passo = with(LocalDensity.current) { (ALTURA_LINHA + ESPACO).toPx() }
    val cores = Pulse.cores

    fun guardar() {
        scope.launch {
            try { Api.put("/dashboard/order", JSONObject().put("ordem", JSONArray(ordem.toList() + completa.filter { it !in ordem })).put("ocultos", JSONArray(ocultos.toList()))) }
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
                val visivel = id !in ocultos
                Box(Modifier.weight(1f)) { Texto(nome, cor = if (visivel) cores.text else cores.text2) }
                Switch(visivel, { quer -> if (quer) ocultos.remove(id) else ocultos.add(id); guardar() }, modifier = Modifier.semantics { contentDescription = "$nome no Hoje: ${if (visivel) "visível" else "escondido"}" },
                    colors = SwitchDefaults.colors(checkedTrackColor = cores.primary))
            }
        }
    }
}
