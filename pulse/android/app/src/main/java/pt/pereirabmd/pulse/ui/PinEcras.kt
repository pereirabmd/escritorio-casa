package pt.pereirabmd.pulse.ui

import android.content.Context
import android.content.ContextWrapper
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import pt.pereirabmd.pulse.R
import pt.pereirabmd.pulse.data.Pin

private tailrec fun Context.activity(): FragmentActivity? = when (this) {
    is FragmentActivity -> this
    is ContextWrapper -> baseContext.activity()
    else -> null
}

fun biometriaDisponivel(ctx: Context) = BiometricManager.from(ctx).canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_STRONG) == BiometricManager.BIOMETRIC_SUCCESS

fun pedirBiometria(ctx: Context, aoSucesso: () -> Unit) {
    val act = ctx.activity() ?: return
    val prompt = BiometricPrompt(act, ContextCompat.getMainExecutor(act), object : BiometricPrompt.AuthenticationCallback() {
        override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) = aoSucesso()
    })
    prompt.authenticate(BiometricPrompt.PromptInfo.Builder().setTitle("Desbloquear o Pulse").setSubtitle("Confirma que és tu")
        .setNegativeButtonText("Usar PIN").setAllowedAuthenticators(BiometricManager.Authenticators.BIOMETRIC_STRONG).build())
}

/** Teclado numérico: 6 pontos, 12 teclas grandes e um botão opcional de biometria. */
@Composable
private fun TecladoPin(pin: String, aoDigitar: (String) -> Unit, aoBiometria: (() -> Unit)?) {
    val c = Pulse.cores
    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(20.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(14.dp), modifier = Modifier.semantics { contentDescription = "${pin.length} de ${Pin.TAMANHO} dígitos" }) {
            repeat(Pin.TAMANHO) { i ->
                Box(Modifier.size(14.dp).clip(CircleShape).background(if (i < pin.length) c.primary else c.line))
            }
        }
        val teclas = listOf("1", "2", "3", "4", "5", "6", "7", "8", "9", if (aoBiometria != null) "bio" else "", "0", "apagar")
        teclas.chunked(3).forEach { linha ->
            Row(horizontalArrangement = Arrangement.spacedBy(20.dp)) {
                linha.forEach { t ->
                    Box(Modifier.size(72.dp).clip(CircleShape).then(if (t.isEmpty()) Modifier else Modifier.background(if (t.length == 1) c.surface else c.bg).clickable {
                        when (t) {
                            "apagar" -> if (pin.isNotEmpty()) aoDigitar(pin.dropLast(1))
                            "bio" -> aoBiometria?.invoke()
                            else -> if (pin.length < Pin.TAMANHO) aoDigitar(pin + t)
                        }
                    }).semantics { if (t == "apagar") contentDescription = "Apagar" else if (t == "bio") contentDescription = "Usar biometria" },
                        contentAlignment = Alignment.Center) {
                        when (t) {
                            "apagar" -> Icon(Icone.VOLTAR, c.text, 26.dp)
                            "bio" -> Icon(Icone.CHAVE, c.primary, 26.dp)
                            "" -> {}
                            else -> Text(t, style = Pulse.section, color = c.text)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun PainelPin(titulo: String, sub: String, erro: String?, conteudo: @Composable ColumnScope.() -> Unit) {
    Column(Modifier.fillMaxSize().background().statusBarsPadding().navigationBarsPadding().padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(20.dp, Alignment.CenterVertically)) {
        Image(painterResource(R.drawable.pulse_icon), null, Modifier.size(56.dp))
        Texto(titulo, Pulse.section)
        Texto2(sub)
        if (erro != null) Aviso(TipoAviso.ERRO, erro, Modifier.widthIn(max = 360.dp))
        conteudo()
    }
}

/** Ecrã de bloqueio: PIN (sempre possível) e biometria (se ativada e disponível). */
@Composable
fun EcraBloqueio(sessao: Sessao, aoSairDaConta: () -> Unit) {
    val ctx = LocalContext.current
    var pin by remember { mutableStateOf("") }
    var erro by remember { mutableStateOf<String?>(null) }
    val bio = sessao.biometria && remember { biometriaDisponivel(ctx) }
    LaunchedEffect(Unit) { if (bio) pedirBiometria(ctx) { sessao.desbloquearComBiometria() } }
    PainelPin("Pulse bloqueado", "Escreve o teu PIN para continuar.", erro) {
        TecladoPin(pin, { novo ->
            pin = novo
            if (novo.length == Pin.TAMANHO) {
                if (!sessao.tentarPin(novo)) {
                    val r = sessao.tentativasRestantes()
                    erro = if (r > 0) "PIN errado. Restam $r tentativas." else null
                    pin = ""
                }
            }
        }, if (bio) ({ pedirBiometria(ctx) { sessao.desbloquearComBiometria() } }) else null)
        LinkBtn("Terminar sessão", aoSairDaConta)
    }
}

/** Definir o PIN: escreve duas vezes. `Agora não` só na oferta inicial. */
@Composable
fun EcraDefinirPin(aoDefinir: (String) -> Unit, aoRecusar: (() -> Unit)?) {
    var primeiro by remember { mutableStateOf<String?>(null) }
    var pin by remember { mutableStateOf("") }
    var erro by remember { mutableStateOf<String?>(null) }
    PainelPin(if (primeiro == null) "Proteger o Pulse com um PIN" else "Confirma o PIN",
        if (primeiro == null) "Escolhe ${Pin.TAMANHO} dígitos. O PIN fica só neste telemóvel." else "Escreve o mesmo PIN outra vez.", erro) {
        TecladoPin(pin, { novo ->
            pin = novo
            if (novo.length == Pin.TAMANHO) {
                if (primeiro == null) { primeiro = novo; pin = ""; erro = null }
                else if (primeiro == novo) aoDefinir(novo)
                else { erro = "Os PIN não coincidem. Começa de novo."; primeiro = null; pin = "" }
            }
        }, null)
        if (aoRecusar != null) LinkBtn("Agora não", aoRecusar)
    }
}
