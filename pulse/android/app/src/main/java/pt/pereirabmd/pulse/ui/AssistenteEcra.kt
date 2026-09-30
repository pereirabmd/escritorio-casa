package pt.pereirabmd.pulse.ui

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import pt.pereirabmd.pulse.data.*
import pt.pereirabmd.pulse.util.ComandoVoz
import pt.pereirabmd.pulse.util.comandoVoz
import pt.pereirabmd.pulse.util.descreverProposta

/**
 * Assistente (ADR-077): abre ao tocar no logotipo e começa logo a ouvir. O que se diz vai (como texto) ao servidor, que escolhe as ações; o que
 * escreve dados fica como **proposta** e só corre depois de confirmar — com um toque ou dizendo «confirma» (ou «cancela»).
 * A conversa é só texto e vive aqui; o servidor não guarda nada entre pedidos.
 */
@Composable
fun AssistenteFolha(aoFechar: () -> Unit, aoAlterado: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val conversa = remember { mutableStateListOf<Pair<String, String>>() }        // (papel, texto): «utilizador» | «assistente»
    var propostas by remember { mutableStateOf<List<JSONObject>>(emptyList()) }
    var ativo by remember { mutableStateOf<Boolean?>(null) }
    var texto by remember { mutableStateOf("") }
    var aOuvir by remember { mutableStateOf(false) }
    var aPensar by remember { mutableStateOf(false) }
    var erro by remember { mutableStateOf<String?>(null) }

    fun confirmar() {
        val lote = propostas; if (lote.isEmpty() || aPensar) return
        aPensar = true; erro = null
        scope.launch {
            try {
                val corpo = jo("propostas" to JSONArray(lote.map { jo("acao" to it.txtOu("acao"), "params" to it.optJSONObject("params")) }))
                val rs = Api.post("/ai/confirm", corpo, 60_000).optJSONArray("resultados") ?: JSONArray()
                val falhas = (0 until rs.length()).map { rs.getJSONObject(it) }.filter { !it.optBoolean("ok") }
                propostas = emptyList()
                conversa.add("assistente" to if (falhas.isEmpty()) "Feito." else "Nem tudo correu bem: " + falhas.joinToString("; ") { it.txtOu("erro") })
                aoAlterado()
            } catch (e: Exception) { if (e is kotlinx.coroutines.CancellationException) throw e; erro = mensagemDeErro(e) } finally { aPensar = false }
        }
    }

    fun enviar(frase: String) {
        val f = frase.trim(); if (f.isEmpty() || aPensar) return
        texto = ""
        when (comandoVoz(f, propostas.isNotEmpty())) {
            ComandoVoz.CONFIRMAR -> { confirmar(); return }
            ComandoVoz.CANCELAR -> { propostas = emptyList(); conversa.add("assistente" to "Cancelado. Não fiz nada."); return }
            ComandoVoz.NENHUM -> {}
        }
        propostas = emptyList()            // um pedido novo substitui o que estava por confirmar
        conversa.add("utilizador" to f); aPensar = true; erro = null
        scope.launch {
            try {
                val msgs = JSONArray(conversa.map { jo("papel" to it.first, "texto" to it.second) })
                val r = Api.post("/ai/command", jo("mensagens" to msgs), 60_000)
                conversa.add("assistente" to r.txtOu("texto"))
                propostas = r.objs("propostas")
            } catch (e: Exception) { if (e is kotlinx.coroutines.CancellationException) throw e; erro = mensagemDeErro(e) } finally { aPensar = false }
        }
    }

    val disponivel = remember { SpeechRecognizer.isRecognitionAvailable(ctx) }
    val reconhecedor = remember { if (disponivel) SpeechRecognizer.createSpeechRecognizer(ctx) else null }
    DisposableEffect(Unit) { onDispose { reconhecedor?.destroy() } }
    val enviarAtual by rememberUpdatedState(::enviar)

    fun ouvir() {
        val r = reconhecedor ?: return
        r.setRecognitionListener(object : RecognitionListener {
            override fun onResults(res: Bundle?) { aOuvir = false; res?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()?.let { enviarAtual(it) } }
            override fun onPartialResults(p: Bundle?) { p?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()?.let { texto = it } }
            override fun onError(codigo: Int) {
                aOuvir = false
                if (codigo != SpeechRecognizer.ERROR_NO_MATCH && codigo != SpeechRecognizer.ERROR_SPEECH_TIMEOUT) erro = "Não consegui ouvir. Podes escrever o pedido."
            }
            override fun onReadyForSpeech(p: Bundle?) {}
            override fun onBeginningOfSpeech() {}
            override fun onRmsChanged(v: Float) {}
            override fun onBufferReceived(b: ByteArray?) {}
            override fun onEndOfSpeech() {}
            override fun onEvent(t: Int, p: Bundle?) {}
        })
        r.startListening(Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            .putExtra(RecognizerIntent.EXTRA_LANGUAGE, "pt-PT").putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true))
        aOuvir = true; erro = null
    }
    val pedirMicrofone = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok -> if (ok) ouvir() else erro = "Sem permissão do microfone. Podes escrever o pedido." }
    fun alternarMicrofone() {
        if (aOuvir) { reconhecedor?.stopListening(); return }
        if (ContextCompat.checkSelfPermission(ctx, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) ouvir() else pedirMicrofone.launch(Manifest.permission.RECORD_AUDIO)
    }

    LaunchedEffect(Unit) {
        ativo = try { Api.get("/ai/status").optBoolean("ativo") } catch (e: Exception) { if (e is kotlinx.coroutines.CancellationException) throw e; false }
        if (ativo == true && disponivel) alternarMicrofone()         // abre a ouvir
    }

    Folha("Assistente", { reconhecedor?.cancel(); aoFechar() }) {
        if (ativo == false) { Texto2("O assistente ainda não está ligado neste servidor."); return@Folha }
        if (conversa.isEmpty()) Texto2("Diz, por exemplo: «adiciona à lista de compras pão e cebolas» ou «o que tenho amanhã?».")
        conversa.forEach { (papel, t) ->
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) { Meta(if (papel == "utilizador") "Tu" else "Pulse"); if (papel == "utilizador") Texto2(t) else Texto(t) }
        }
        if (propostas.isNotEmpty()) Bloco(titulo = "Para confirmar") {
            propostas.forEach { Texto2(descreverProposta(it.txtOu("descricao"), it.optJSONObject("params") ?: JSONObject())) }
            Meta("Toca em «Confirmar» ou diz «confirma»; «cancela» desiste.")
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Botao("Confirmar", ::confirmar, carregando = aPensar, ativo = !aPensar)
                Botao("Cancelar", { propostas = emptyList(); conversa.add("assistente" to "Cancelado. Não fiz nada.") }, Modifier, Variante.SECUNDARIO, ativo = !aPensar)
            }
        }
        if (aPensar && propostas.isEmpty()) Meta("A pensar…")
        erro?.let { e -> Aviso(TipoAviso.ERRO) { Texto(e, Pulse.body2); LinkBtn("Fechar", { erro = null }) } }
        Campo(if (aOuvir) "A ouvir…" else "Escreve ou fala", texto, { texto = it.take(600) }, aoConcluir = { enviar(texto) })
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            Botao("Enviar", { enviar(texto) }, ativo = texto.isNotBlank() && !aPensar)
            if (disponivel) Botao(if (aOuvir) "Parar" else "Falar", ::alternarMicrofone, Modifier, Variante.SECUNDARIO, ativo = !aPensar)
        }
    }
}
