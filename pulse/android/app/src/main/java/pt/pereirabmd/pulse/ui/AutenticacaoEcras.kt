package pt.pereirabmd.pulse.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import pt.pereirabmd.pulse.R
import pt.pereirabmd.pulse.data.ApiError
import pt.pereirabmd.pulse.data.Api
import pt.pereirabmd.pulse.data.mensagemDeErro
import pt.pereirabmd.pulse.util.regrasPassword
import pt.pereirabmd.pulse.util.todasOk

@Composable
private fun PainelAuth(conteudo: @Composable ColumnScope.() -> Unit) {
    Column(Modifier.fillMaxSize().background().statusBarsPadding().navigationBarsPadding().imePadding().verticalScroll(rememberScrollState()).padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(16.dp, Alignment.CenterVertically)) {
        Column(Modifier.widthIn(max = 420.dp), verticalArrangement = Arrangement.spacedBy(16.dp), content = conteudo)
    }
}

@Composable
private fun Marca(titulo: String, sub: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
        Image(painterResource(R.drawable.pulse_icon), null, Modifier.size(56.dp))
        Texto(titulo, Pulse.page)
        Texto2(sub)
    }
}

/** Arranque: o splash animado da marca enquanto se confirma a sessão. */
@Composable
fun EcraArranque() {
    Column(Modifier.fillMaxSize().background(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
        MarcaImagem(Marca.SPLASH, 200.dp)
        Spacer(Modifier.height(8.dp))
        Texto2("A iniciar o Pulse…")
    }
}

@Composable
fun EcraSemLigacao(aoTentar: () -> Unit) = PainelAuth {
    Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        MarcaImagem(Marca.ERRO, 96.dp)
        Texto("Sem ligação ao servidor", Pulse.section)
    }
    Aviso(TipoAviso.AVISO, "Não foi possível contactar o Pulse. Verifica a ligação e tenta de novo.")
    Botao("Tentar de novo", aoTentar, grande = true)
}

@Composable
fun EcraLogin(sessao: Sessao) {
    val scope = rememberCoroutineScope()
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var erro by remember { mutableStateOf<String?>(null) }
    var aEnviar by remember { mutableStateOf(false) }
    fun submeter() {
        if (email.isBlank() || password.isEmpty() || aEnviar) return
        erro = null; aEnviar = true
        scope.launch {
            try { sessao.entrar(email.trim(), password) } catch (e: Exception) { erro = mensagemDeErro(e); password = "" } finally { aEnviar = false }
        }
    }
    PainelAuth {
        Marca("Iniciar sessão", "Entra na tua conta Pulse.")
        erro?.let { Aviso(TipoAviso.ERRO, it) }
        Campo("E-mail", email, { email = it }, teclado = KeyboardType.Email)
        Campo("Palavra-passe", password, { password = it }, password = true, aoConcluir = ::submeter)
        Botao("Iniciar sessão", ::submeter, grande = true, ativo = email.isNotBlank() && password.isNotEmpty(), carregando = aEnviar)
        Meta("Não tens conta? As contas são criadas pelo administrador. Se te esqueceste da palavra-passe, pede-lhe que a reponha.")
    }
}

/** Primeiro acesso (`obrigatorio`): ecrã único, sem navegação. Depois: o mesmo formulário em Definições → Conta. */
@Composable
fun EcraMudarPassword(sessao: Sessao, email: String, obrigatorio: Boolean, aoConcluir: () -> Unit, aoVoltar: () -> Unit = {}) {
    val scope = rememberCoroutineScope()
    var atual by remember { mutableStateOf("") }
    var nova by remember { mutableStateOf("") }
    var conf by remember { mutableStateOf("") }
    var erro by remember { mutableStateOf<String?>(null) }
    var aEnviar by remember { mutableStateOf(false) }
    var feito by remember { mutableStateOf(false) }
    val rs = regrasPassword(nova, atual, email)
    val diferente = conf.isNotEmpty() && conf != nova
    val pronto = atual.isNotEmpty() && todasOk(rs) && conf == nova

    fun submeter() {
        if (!pronto || aEnviar) return
        erro = null; aEnviar = true
        scope.launch {
            try {
                Api.post("/auth/password", org.json.JSONObject().put("atual", atual).put("nova", nova))
                atual = ""; nova = ""; conf = ""
                if (obrigatorio) { sessao.passwordMudada(); aoConcluir() } else feito = true
            } catch (e: Exception) { erro = mensagemDeErro(e) } finally { aEnviar = false }
        }
    }
    val corpo: @Composable ColumnScope.() -> Unit = {
        erro?.let { Aviso(TipoAviso.ERRO, it) }
        if (feito) Aviso(TipoAviso.INFO, "Palavra-passe alterada.")
        Campo("Palavra-passe atual", atual, { atual = it }, password = true)
        Campo("Palavra-passe nova", nova, { nova = it }, password = true)
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            rs.forEach { r ->
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(if (r.ok) Icone.CERTO else Icone.PONTO, if (r.ok) Pulse.cores.success else Pulse.cores.text2, 16.dp)
                    Texto(r.texto + if (r.ok) " — cumprido" else " — por cumprir", Pulse.meta.copy(fontSize = androidx.compose.ui.unit.TextUnit(13f, androidx.compose.ui.unit.TextUnitType.Sp)), if (r.ok) Pulse.cores.success else Pulse.cores.text2)
                }
            }
        }
        Campo("Confirmar palavra-passe nova", conf, { conf = it }, password = true, erro = if (diferente) "As palavras-passe não coincidem." else null, aoConcluir = ::submeter)
        Botao("Mudar palavra-passe", ::submeter, grande = true, ativo = pronto, carregando = aEnviar)
    }
    if (obrigatorio) {
        PainelAuth {
            Marca("Define a tua palavra-passe", "A palavra-passe que recebeste é provisória. Escolhe uma nova para continuar.")
            corpo()
            Botao("Terminar sessão", { sessao.sair() }, variante = Variante.SECUNDARIO, pequeno = true)
        }
    } else {
        Column(Modifier.fillMaxSize().background().statusBarsPadding().navigationBarsPadding().imePadding().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            LinkBtn("‹ Definições", aoVoltar)
            Texto("Mudar palavra-passe", Pulse.page)
            corpo()
        }
    }
}
