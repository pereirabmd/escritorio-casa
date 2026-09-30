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
import androidx.compose.foundation.layout.Arrangement

@Composable
fun Secao(titulo: String, conteudo: @Composable ColumnScope.() -> Unit) {
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
    val abrir = LocalAbrir.current
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
            Botao("Contas Google", { abrir("google") }, variante = Variante.SECUNDARIO, pequeno = true)
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
        NotificacoesSecao(sessao)
        OrdemHojeSecao()
        SessoesSecao()
        if (utilizador.admin) AdministracaoSecao()
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

private fun dispositivo(cliente: String, ua: String): String {
    if (cliente == "android") return "Aplicação Android"
    val nav = when { "Firefox/" in ua -> "Firefox"; "Edg/" in ua -> "Edge"; "Chrome/" in ua -> "Chrome"; "Safari/" in ua -> "Safari"; else -> "Browser" }
    val so = when { "Android" in ua -> "Android"; "iPhone" in ua || "iPad" in ua -> "iOS"; "Windows" in ua -> "Windows"; "Mac OS" in ua -> "macOS"; "Linux" in ua -> "Linux"; else -> "" }
    return if (so.isNotEmpty()) "$nav em $so" else nav
}

private fun quandoSessao(s: Long): String {
    val z = java.time.Instant.ofEpochSecond(s).atZone(java.time.ZoneId.systemDefault())
    return "%02d/%02d/%04d %02d:%02d".format(z.dayOfMonth, z.monthValue, z.year, z.hour, z.minute)
}

/** Sessões e dispositivos: as que estão abertas nesta conta, com «Terminar» nas outras (como na Web). */
@Composable
private fun SessoesSecao() {
    val c = carga { Api.get("/auth/sessions") }
    val scope = rememberCoroutineScope()
    var erro by remember { mutableStateOf<String?>(null) }
    Secao("Sessões e dispositivos") {
        erro?.let { Aviso(TipoAviso.ERRO, it) }
        when (val e = c.estado) {
            Estado.ACarregar -> Texto2("A carregar…")
            is Estado.Erro -> { Aviso(TipoAviso.ERRO, e.mensagem); Botao("Tentar de novo", c.recarregar, variante = Variante.SECUNDARIO, pequeno = true) }
            is Estado.Pronto -> e.dados.objs("sessoes").forEach { s ->
                val nome = dispositivo(s.txtOu("cliente"), s.txtOu("dispositivo"))
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Icon(Icone.DISPOSITIVO, Pulse.cores.primary)
                    Column(Modifier.weight(1f)) {
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) { Texto(nome); if (s.bool("atual")) Pilula("Esta sessão", Pulse.cores.success) }
                        Meta("Último uso: ${quandoSessao(s.optLong("ultimoUso"))}")
                    }
                    if (!s.bool("atual")) LinkBtn("Terminar", {
                        erro = null
                        scope.launch { try { Api.delete("/auth/sessions/${s.getInt("id")}"); c.recarregar() } catch (x: Exception) { erro = mensagemDeErro(x) } }
                    })
                }
            }
        }
    }
}

/** Só para administradores: ativar ou desativar módulos para todos os utilizadores. */
@Composable
private fun AdministracaoSecao() {
    val c = carga { Api.get("/modules") }
    val scope = rememberCoroutineScope()
    var erro by remember { mutableStateOf<String?>(null) }
    var ocupado by remember { mutableStateOf<String?>(null) }
    Secao("Administração") {
        Texto2("Módulos: um módulo desativado desaparece do Hoje e de Mais para todos os utilizadores, e o servidor recusa os pedidos que lhe chegarem.")
        erro?.let { Aviso(TipoAviso.ERRO, it) }
        when (val e = c.estado) {
            Estado.ACarregar -> Texto2("A carregar…")
            is Estado.Erro -> Aviso(TipoAviso.ERRO, e.mensagem)
            is Estado.Pronto -> e.dados.objs("modulos").forEach { m ->
                val id = m.txtOu("id")
                Interruptor(m.txtOu("nome"), m.optBoolean("ativo", true), { ativo ->
                    if (ocupado == null) { ocupado = id; erro = null
                        scope.launch { try { Api.put("/admin/modules", jo("modulos" to jo(id to ativo))); c.recarregar() } catch (x: Exception) { erro = mensagemDeErro(x) } finally { ocupado = null } } }
                }, if (m.optBoolean("ativo", true)) "Ativo" else "Desativado")
            }
        }
    }
}

/** Definições › Notificações: estado da permissão e do registo deste telemóvel, e o teste de ponta a ponta (servidor → FCM → telemóvel). */
@Composable
private fun NotificacoesSecao(sessao: Sessao) {
    val ctx = LocalContext.current
    val avisos = LocalAvisos.current
    val scope = rememberCoroutineScope()
    var permitidas by remember { mutableStateOf(Notificacoes.permitidas(ctx)) }
    var aEnviar by remember { mutableStateOf(false) }
    val pedir = androidx.activity.compose.rememberLauncherForActivityResult(androidx.activity.result.contract.ActivityResultContracts.RequestPermission()) { ok ->
        permitidas = Notificacoes.permitidas(ctx)
        if (ok) scope.launch { Notificacoes.registar(ctx) }
    }
    Secao("Notificações") {
        if (permitidas) {
            Texto2("Permitidas neste telemóvel. Cada módulo tem o seu canal nas definições de notificações do Android.")
            Botao("Enviar notificação de teste", {
                aEnviar = true
                scope.launch {
                    try {
                        val falha = Notificacoes.registar(ctx)            // garante o registo (e renova o token) antes do teste
                        if (falha != null) avisos.mostrar("Não foi possível registar este telemóvel: $falha")
                        else { Api.post("/notifications/test"); avisos.mostrar("Teste enviado. Deve aparecer em poucos segundos.") }
                    } catch (e: Exception) { avisos.mostrar(mensagemDeErro(e)) }
                    aEnviar = false
                }
            }, variante = Variante.SECUNDARIO, pequeno = true, carregando = aEnviar)
        } else {
            Texto2("Desligadas neste telemóvel: não vais receber avisos do Pulse.")
            Botao("Ativar notificações", {
                if (android.os.Build.VERSION.SDK_INT >= 33 && !sessao.store.notificacoesPedidas) { sessao.store.notificacoesPedidas = true; pedir.launch(android.Manifest.permission.POST_NOTIFICATIONS) }
                else ctx.startActivity(android.content.Intent(android.provider.Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(android.provider.Settings.EXTRA_APP_PACKAGE, ctx.packageName).addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK))
            }, variante = Variante.SECUNDARIO, pequeno = true)
            Meta("Se o botão abrir as definições do sistema, liga as notificações do Pulse e volta aqui.")
        }
    }
}
