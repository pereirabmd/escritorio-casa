package pt.pereirabmd.pulse.captura

import androidx.activity.ComponentActivity
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.SnackbarHostState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasSetTextAction
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import org.json.JSONObject
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import pt.pereirabmd.pulse.data.Api
import pt.pereirabmd.pulse.data.SessionStore
import pt.pereirabmd.pulse.data.Tema
import pt.pereirabmd.pulse.data.Utilizador
import pt.pereirabmd.pulse.ui.*
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

/**
 * Capturas de ecrãs sem emulador (ADR-081): renderiza os ecrãs **reais** da app (Compose, com Robolectric) contra o servidor de demonstração
 * (`pulse/scripts/capturas/servidor_demo.py`) e grava PNG em `app/build/capturas/`. Só corre com `PULSE_CAPTURAS=1` e `-PservidorDemo`:
 *   `PULSE_CAPTURAS=1 gradle :app:testDebugUnitTest -PservidorDemo --rerun --tests '*Captura*'`.
 * `PULSE_CAPTURAS_ESCURO=1` captura no tema escuro (em vez do claro); `PULSE_CAPTURAS_SO=rto,peso` limita aos ecrãs pedidos.
 */
private val TOKEN_DEMO: String by lazy {
    val c = URL("http://127.0.0.1:18897/api/v1/auth/login").openConnection() as HttpURLConnection
    c.requestMethod = "POST"; c.doOutput = true
    c.setRequestProperty("Content-Type", "application/json"); c.setRequestProperty("X-Pulse-Client", "android")
    c.outputStream.use { it.write("""{"email":"pereirabmd@gmail.com","password":"DemoPulse1234","cliente":"android"}""".toByteArray()) }
    JSONObject(c.inputStream.bufferedReader().readText()).getString("token")
}

@RunWith(AndroidJUnit4::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
abstract class CapturaBase {
    @get:Rule val regra = createAndroidComposeRule<ComponentActivity>()
    protected val so = System.getenv("PULSE_CAPTURAS_SO")?.split(",")?.map { it.trim() }

    @Before fun entrar() {
        assumeTrue(System.getenv("PULSE_CAPTURAS") != null)
        folhasEmLinha = true                         // as folhas (diálogos) desenham-se no ecrã, para entrarem na imagem
        Api.token = TOKEN_DEMO                       // o login faz-se uma só vez (o servidor limita-os a 10 por minuto)
    }

    protected fun esperar() {
        regra.waitUntil(30_000) { regra.onAllNodes(hasText("A carregar", substring = true)).fetchSemanticsNodes().isEmpty() }
        Thread.sleep(400); regra.waitForIdle()
    }

    protected fun fotografar(nome: String, tema: Tema) {
        regra.waitForIdle()
        val vista = regra.activity.window.decorView
        val dm = regra.activity.resources.displayMetrics
        vista.measure(android.view.View.MeasureSpec.makeMeasureSpec(dm.widthPixels, android.view.View.MeasureSpec.EXACTLY), android.view.View.MeasureSpec.makeMeasureSpec(dm.heightPixels, android.view.View.MeasureSpec.EXACTLY))
        vista.layout(0, 0, dm.widthPixels, dm.heightPixels)
        val img = android.graphics.Bitmap.createBitmap(dm.widthPixels, dm.heightPixels, android.graphics.Bitmap.Config.ARGB_8888)
        vista.draw(android.graphics.Canvas(img))
        val f = File("build/capturas/$nome${if (tema == Tema.ESCURO) "-escuro" else ""}.png").apply { parentFile.mkdirs() }
        f.outputStream().use { img.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it) }
    }

    /** Um ecrã (e, se houver, cada um dos seus separadores) no tema pedido. */
    protected fun ecra(nome: String, abas: List<String> = emptyList(), antes: () -> Unit = {}, conteudo: @Composable () -> Unit) {
        if (so != null && nome !in so) return
        val tema = if (System.getenv("PULSE_CAPTURAS_ESCURO") != null) Tema.ESCURO else Tema.CLARO       // um tema por execução (o Compose só aceita um `setContent` por teste)
        val temas = listOf(tema)
        for (tema in temas) {
            regra.setContent {
                val scope = rememberCoroutineScope()
                val avisos = Avisos(SnackbarHostState(), scope)
                PulseTheme(tema) {
                    CompositionLocalProvider(LocalAvisos provides avisos, LocalUtilizador provides Utilizador(1, "pereirabmd@gmail.com", "Bruno", true, false)) {
                        Box(Modifier.fillMaxSize()) { conteudo() }
                    }
                }
            }
            esperar(); antes(); fotografar(nome, tema)
            for (aba in abas) {
                regra.onAllNodes(hasText(aba, substring = true) and hasClickAction()).onFirst().performClick()
                esperar(); fotografar("$nome-${aba.lowercase().replace(Regex("[^a-z]"), "")}", tema)
            }
        }
    }

}

/** Ecrãs de altura normal (telemóvel). */
@Config(sdk = [34], qualifiers = "w411dp-h891dp-xxhdpi")
class CapturaEcras : CapturaBase() {
    @Test fun rto() = ecra("rto", listOf("Ano", "Notas")) { RtoEcra {} }
    @Test fun peso() = ecra("peso", listOf("Gráfico", "Registos", "Configuração")) { PesoEcra {} }
    @Test fun financas() = ecra("financas", listOf("Lançamentos", "Relatórios", "Categorias", "Lembretes")) { FinancasEcra {} }
    @Test fun bilhetes() = ecra("bilhetes", listOf("Bilhetes", "Pedidos", "Na CP", "Registo")) { BilhetesEcra {} }
    @Test fun trocaFormulario() = ecra("bilhetes-troca", antes = {
        regra.onAllNodes(hasText("Na CP") and hasClickAction()).onFirst().performClick(); esperar()
        regra.onNode(hasText("Trocar por outro comboio") and hasClickAction()).performClick(); esperar()
    }) { BilhetesEcra {} }
    @Test fun compras() = ecra("compras", listOf("Catálogo")) { ComprasEcra {} }
    @Test fun tarefas() = ecra("tarefas", listOf("Calendário", "Tarefas", "Horário", "Piscina", "Config")) { TarefasEcra({}, null) {} }
    @Test fun calendario() = ecra("calendario") { CalendarioGoogleEcra {} }
    @Test fun email() = ecra("email") { EmailEcra {} }
    @Test fun mais() = ecra("mais") { EcraMais({}, {}) }
    @Test fun assistente() = ecra("assistente", antes = {
        regra.onNode(hasSetTextAction()).performTextInput("adiciona pão e cebolas à lista de compras")
        regra.onNode(hasText("Enviar") and hasClickAction()).performClick()
        regra.waitUntil(30_000) { regra.onAllNodes(hasText("A pensar", substring = true)).fetchSemanticsNodes().isEmpty() }; esperar()
    }) { AssistenteFolha({}, {}) }
    @Test fun novaLista() = ecra("compras-nova-lista", antes = { regra.onAllNodes(hasText("Nova lista", substring = true) and hasClickAction()).onFirst().performClick(); esperar() }) { ComprasEcra {} }
}

/** Ecrãs compridos (a página rola): capturados numa janela alta para se ver tudo. */
@Config(sdk = [34], qualifiers = "w411dp-h2300dp-xxhdpi")
class CapturaEcrasLongos : CapturaBase() {
    private fun sessao(): Sessao {
        val store = SessionStore(regra.activity.getSharedPreferences("demo", android.content.Context.MODE_PRIVATE))
        store.token = TOKEN_DEMO                      // a `Sessao` põe o token do armazenamento no `Api`
        return Sessao(store, CoroutineScope(Dispatchers.Main))
    }
    private val utilizador = Utilizador(1, "pereirabmd@gmail.com", "Bruno", true, false)

    @Test fun bilhetesEditor() = ecra("bilhetes-editor", antes = { regra.onNode(hasText("Configurar semana") and hasClickAction()).performClick(); esperar() }) { BilhetesEcra {} }
    @Test fun hoje() = ecra("hoje") { EcraHoje(sessao(), utilizador) {} }
    @Test fun definicoes() = ecra("definicoes") { EcraDefinicoes(sessao(), utilizador, {}, {}, {}) }
    @Test fun google() = ecra("google") { GoogleContasEcra(sessao()) {} }
    @Test fun tarefasPiscina() = ecra("tarefas-piscina-longo", antes = { regra.onAllNodes(hasText("Piscina") and hasClickAction()).onFirst().performClick(); esperar() }) { TarefasEcra({}, null) {} }
    @Test fun comprasLista() = ecra("compras-longo") { ComprasEcra {} }
}
