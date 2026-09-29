package pt.pereirabmd.pulse.ui

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import org.json.JSONObject
import pt.pereirabmd.pulse.data.*

sealed interface Fase {
    data object ACarregar : Fase
    data object SemLigacao : Fase
    data object Anonimo : Fase
    data class Autenticado(val utilizador: Utilizador) : Fase
}

/** Quanto tempo a app pode estar em segundo plano antes de pedir de novo o PIN/biometria. */
const val BLOQUEIO_MS = 60_000L
const val MAX_FALHAS_PIN = 5

/**
 * Estado da sessão (espelho do `AuthContext` da Web) mais o que é só do Android: bloqueio por PIN/biometria (ADR-009).
 * O PIN protege a app neste telemóvel; a sessão em si é o token do servidor.
 */
class Sessao(val store: SessionStore, private val scope: CoroutineScope, private val agora: () -> Long = System::currentTimeMillis) {
    var fase: Fase by mutableStateOf(Fase.ACarregar); private set
    var bloqueado by mutableStateOf(store.temPin); private set
    var ofertaPin by mutableStateOf(false); private set
    var tema by mutableStateOf(store.tema); private set
    var temPin by mutableStateOf(store.temPin); private set
    var biometria by mutableStateOf(store.biometria); private set
    var atualizacao: Atualizacao? by mutableStateOf(null); private set
    /** O que a Google disse ao regressar ao `pulse://google` («ok» ou o motivo do erro); o ecrã de contas mostra-o e limpa-o. */
    var resultadoGoogle: Pair<Boolean, String>? by mutableStateOf(null)
    private var saiuEm = 0L

    init {
        Api.token = store.token
        Api.aoPerderSessao = { scope.launch { terminarLocal() } }
    }

    fun iniciar() {
        if (store.token == null) { fase = Fase.Anonimo; verificarAtualizacao(); return }
        fase = Fase.ACarregar
        scope.launch {
            fase = consultar()
            verificarAtualizacao()
        }
    }

    /** Pergunta ao servidor quem sou. 401 = sem sessão; qualquer outra falha (rede, 5xx) não quer dizer que a sessão acabou. */
    private suspend fun consultar(): Fase = try {
        Fase.Autenticado(parseUtilizador(Api.get("/auth/me").getJSONObject("utilizador")))
    } catch (e: ApiError) {
        if (e.status == 401) { store.limparSessao(); Api.token = null; temPin = false; bloqueado = false; Fase.Anonimo } else Fase.SemLigacao
    }

    suspend fun entrar(email: String, password: String) {
        val r = Api.post("/auth/login", JSONObject().put("email", email).put("password", password).put("cliente", "android"))
        val token = r.getString("token")
        store.token = token; Api.token = token
        fase = Fase.Autenticado(parseUtilizador(r.getJSONObject("utilizador")))
        ofertaPin = !store.temPin && !store.pinRecusado
    }

    fun passwordMudada() { (fase as? Fase.Autenticado)?.let { fase = Fase.Autenticado(it.utilizador.copy(mudarPassword = false)) } }

    fun sair() {
        scope.launch {
            try { Api.post("/auth/logout") } catch (_: ApiError) { /* sem ligação: a sessão apaga-se aqui na mesma */ }
            terminarLocal()
        }
    }

    private fun terminarLocal() {
        store.limparSessao(); Api.token = null
        temPin = false; bloqueado = false; ofertaPin = false
        fase = Fase.Anonimo
    }

    // --- PIN e biometria ---
    fun definirPin(pin: String) { store.definirPin(pin); store.pinRecusado = false; temPin = true; ofertaPin = false }
    fun recusarPin() { store.pinRecusado = true; ofertaPin = false }
    fun oferecerPin() { ofertaPin = true }
    fun removerPin() { store.removerPin(); temPin = false; bloqueado = false }
    fun ativarBiometria(v: Boolean) { store.biometria = v; biometria = v }

    /** Devolve `true` se desbloqueou. À 5.ª falha a sessão termina (o PIN deixa de proteger algo que qualquer um pode adivinhar). */
    fun tentarPin(pin: String): Boolean {
        if (store.verificarPin(pin)) { store.falhas = 0; bloqueado = false; return true }
        store.falhas += 1
        if (store.falhas >= MAX_FALHAS_PIN) terminarLocal()
        return false
    }
    fun tentativasRestantes() = (MAX_FALHAS_PIN - store.falhas).coerceAtLeast(0)
    fun desbloquearComBiometria() { store.falhas = 0; bloqueado = false }

    fun aoIrParaSegundoPlano() { saiuEm = agora() }
    fun aoVoltar() { if (temPin && saiuEm > 0 && agora() - saiuEm > BLOQUEIO_MS) bloqueado = true }

    fun regressoGoogle(ok: Boolean, motivo: String) { resultadoGoogle = ok to motivo }
    fun limparResultadoGoogle() { resultadoGoogle = null }

    fun escolherTema(t: Tema) { store.tema = t; tema = t }

    fun verificarAtualizacao() { scope.launch { verificarAtualizacaoAgora() } }
    suspend fun verificarAtualizacaoAgora() { atualizacao = Updater.verificar() }
    fun atualizacaoInstalada() { atualizacao = null }
}
