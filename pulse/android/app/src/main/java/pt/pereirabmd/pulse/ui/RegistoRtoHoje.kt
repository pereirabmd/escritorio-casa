package pt.pereirabmd.pulse.ui

import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import kotlinx.coroutines.launch
import org.json.JSONObject
import pt.pereirabmd.pulse.data.*
import pt.pereirabmd.pulse.util.*

/** O atalho «Registar RTO» (toque longo no ícone, ADR-092): pergunta onde estás hoje e regista, sem passar pelo módulo. A mesma ação `rto.marcar_dia` do resto da app. */
@Composable
fun RegistoRtoHoje(aoFechar: () -> Unit, aoRegistar: () -> Unit) {
    val avisos = LocalAvisos.current
    val scope = rememberCoroutineScope()
    var a by remember { mutableStateOf(false) }
    fun registar(marca: String, onde: String) {
        a = true
        scope.launch {
            try {
                Api.post("/actions/rto.marcar_dia", JSONObject().put("params", JSONObject().put("data", java.time.LocalDate.now().toString()).put("marca", marca)))
                avisos.mostrar("RTO de hoje: $onde.")
                aoRegistar()
            } catch (e: Exception) {
                if (e is kotlinx.coroutines.CancellationException) throw e
                avisos.mostrar(mensagemDeErro(e))
            }
            aoFechar()
        }
    }
    val c = Pulse.cores
    AlertDialog(
        onDismissRequest = { if (!a) aoFechar() },
        containerColor = c.surface,
        title = { Text("Registar RTO de hoje", color = c.text) },
        text = { Text(if (a) "A registar…" else "Onde estás hoje?", color = c.text2) },
        confirmButton = { TextButton(onClick = { registar("T", "Escritório") }, enabled = !a) { Text("Escritório", color = c.primary) } },
        dismissButton = { Row2(a, aoFechar) { registar("C", "Casa") } },
    )
}

@Composable
private fun Row2(a: Boolean, aoFechar: () -> Unit, casa: () -> Unit) {
    val c = Pulse.cores
    androidx.compose.foundation.layout.Row {
        TextButton(onClick = casa, enabled = !a) { Text("Casa", color = c.primary) }
        TextButton(onClick = aoFechar, enabled = !a) { Text("Cancelar", color = c.text2) }
    }
}
