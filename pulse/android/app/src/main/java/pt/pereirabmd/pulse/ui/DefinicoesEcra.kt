package pt.pereirabmd.pulse.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import pt.pereirabmd.pulse.BuildConfig
import pt.pereirabmd.pulse.data.*
import pt.pereirabmd.pulse.data.Updater

@Composable
private fun Secao(titulo: String, conteudo: @Composable ColumnScope.() -> Unit) {
    val c = Pulse.cores
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Texto(titulo, Pulse.card, c.text2)
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(Pulse.rM)).background(c.surface).border(1.dp, c.line, RoundedCornerShape(Pulse.rM)).padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp), content = conteudo)
    }
}

/** Cartão persistente de atualização: fica enquanto houver versão nova (não é um toast). */
@Composable
fun AvisoAtualizacao(a: Atualizacao, modifier: Modifier = Modifier) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var progresso by remember { mutableStateOf<Float?>(null) }
    var erro by remember { mutableStateOf<String?>(null) }
    var pronto by remember { mutableStateOf<java.io.File?>(null) }
    Aviso(TipoAviso.INFO, modifier) {
        Texto("Há uma versão nova do Pulse: ${a.versionName}", Pulse.body2.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold))
        if (a.notas.isNotBlank()) Texto2(a.notas)
        erro?.let { Texto(it, Pulse.body2, Pulse.cores.error) }
        progresso?.let { p -> if (pronto == null) Meta("A descarregar… ${(p * 100).toInt()}%") }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Botao(if (pronto != null) "Instalar" else "Descarregar e instalar", {
                erro = null
                val f = pronto
                if (f != null) { Updater.instalar(ctx, f); return@Botao }
                scope.launch {
                    try {
                        progresso = 0f
                        val ficheiro = Updater.descarregar(ctx, a) { progresso = it }
                        pronto = ficheiro
                        Updater.instalar(ctx, ficheiro)
                    } catch (e: Exception) { erro = (e as? ApiError)?.message ?: "Não foi possível descarregar a atualização. Tenta de novo." ; progresso = null }
                }
            }, pequeno = true, carregando = progresso != null && pronto == null)
        }
    }
}

@Composable
fun EcraDefinicoes(sessao: Sessao, utilizador: Utilizador, aoVoltar: () -> Unit, aoMudarPassword: () -> Unit, aoDefinirPin: () -> Unit) {
    val ctx = LocalContext.current
    val c = Pulse.cores
    val scope = rememberCoroutineScope()
    var aVerificar by remember { mutableStateOf(false) }
    var verificada by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(20.dp)) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            LinkBtn("‹ Mais", aoVoltar)
            Texto("Definições", Pulse.page)
        }
        Secao("Conta") {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Icon(Icone.DISPOSITIVO, c.primary)
                Column(Modifier.weight(1f)) { Texto(utilizador.nome.ifEmpty { utilizador.email }); Meta(utilizador.email + if (utilizador.admin) " · administrador" else "") }
            }
            Botao("Mudar palavra-passe", aoMudarPassword, variante = Variante.SECUNDARIO, pequeno = true)
            Botao("Ligar contas Google (na Web)", { abrirNaWeb(ctx, "/definicoes") }, variante = Variante.SECUNDARIO, pequeno = true)
            Botao("Terminar sessão", { sessao.sair() }, variante = Variante.PERIGO, pequeno = true)
        }
        Secao("Segurança") {
            if (sessao.temPin) {
                Texto2("O Pulse pede o PIN ao abrir e depois de estar 1 minuto em segundo plano.")
                if (biometriaDisponivel(ctx)) Row(verticalAlignment = Alignment.CenterVertically) {
                    Texto("Desbloquear com biometria", modifier = Modifier.weight(1f))
                    Switch(sessao.biometria, { sessao.ativarBiometria(it) }, colors = SwitchDefaults.colors(checkedTrackColor = c.primary))
                }
                Botao("Mudar PIN", aoDefinirPin, variante = Variante.SECUNDARIO, pequeno = true)
                Botao("Remover PIN", { sessao.removerPin() }, variante = Variante.PERIGO, pequeno = true)
            } else {
                Texto2("Sem PIN, qualquer pessoa com o telemóvel desbloqueado abre o Pulse.")
                Botao("Definir PIN", aoDefinirPin, pequeno = true)
            }
        }
        Secao("Aparência") {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Tema.entries.forEach { t ->
                    Botao(t.nome, { sessao.escolherTema(t) }, variante = if (sessao.tema == t) Variante.PRIMARIO else Variante.SECUNDARIO, pequeno = true)
                }
            }
        }
        Secao("Aplicação") {
            Texto("Pulse ${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})")
            val a = sessao.atualizacao
            if (a != null) AvisoAtualizacao(a)
            else {
                if (verificada) Meta("Tens a versão mais recente.")
                Botao("Procurar atualizações", { aVerificar = true; scope.launch { sessao.verificarAtualizacaoAgora(); verificada = true; aVerificar = false } },
                    variante = Variante.SECUNDARIO, pequeno = true, carregando = aVerificar)
            }
        }
    }
}
