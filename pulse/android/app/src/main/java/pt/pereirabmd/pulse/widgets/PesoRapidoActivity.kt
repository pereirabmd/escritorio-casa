package pt.pereirabmd.pulse.widgets

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*
import androidx.compose.ui.text.input.KeyboardType
import kotlinx.coroutines.launch
import org.json.JSONObject
import pt.pereirabmd.pulse.data.*
import pt.pereirabmd.pulse.ui.*
import pt.pereirabmd.pulse.util.*

/** O botão «Registar» do widget do peso: um diálogo pequeno sobre o ecrã inicial para escrever o peso de hoje (a mesma ação `peso.registar`). */
class PesoRapidoActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val store = SessionStore(applicationContext)
        val sugestao = Widgets.lerCache(applicationContext)?.peso?.dados?.sugestao
        setContent {
            PulseTheme(store.tema) {
                val scope = rememberCoroutineScope()
                var texto by remember { mutableStateOf(decimalTexto(sugestao)) }
                var erro by remember { mutableStateOf<String?>(null) }
                var a by remember { mutableStateOf(false) }
                val valor = lerDecimal(texto)?.takeIf { it in 1.0..1000.0 }
                val c = Pulse.cores
                AlertDialog(
                    onDismissRequest = { if (!a) finish() }, containerColor = c.surface,
                    title = { Text("Peso de hoje", color = c.text) },
                    text = {
                        OutlinedTextField(texto, { texto = it; erro = null }, label = { Text("Quilogramas") }, singleLine = true, isError = erro != null || (texto.isNotEmpty() && valor == null),
                            supportingText = { Text(erro ?: if (texto.isNotEmpty() && valor == null) "Entre 1 e 1000." else "") },
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal))
                    },
                    confirmButton = {
                        TextButton(enabled = valor != null && !a, onClick = {
                            a = true
                            scope.launch {
                                try {
                                    Api.token = Api.token ?: store.token
                                    if (Api.token == null) throw ApiError(401, "nao_autenticado", "abre o Pulse para entrares")
                                    Api.post("/actions/peso.registar", JSONObject().put("params", JSONObject().put("peso", valor).put("cid", novoCid())))
                                    Widgets.atualizarTodos(applicationContext)
                                    finish()
                                } catch (e: Exception) {
                                    if (e is kotlinx.coroutines.CancellationException) throw e
                                    erro = mensagemDeErro(e); a = false
                                }
                            }
                        }) { Text(if (a) "A registar…" else "Registar", color = c.primary) }
                    },
                    dismissButton = { TextButton(onClick = { finish() }, enabled = !a) { Text("Cancelar", color = c.text2) } },
                )
            }
        }
    }
}
