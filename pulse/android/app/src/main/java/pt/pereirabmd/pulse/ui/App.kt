package pt.pereirabmd.pulse.ui

import android.Manifest
import android.os.Build
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.ui.platform.LocalContext
import pt.pereirabmd.pulse.data.Notificacoes
import pt.pereirabmd.pulse.data.Localizacao
import android.provider.Settings
import kotlinx.coroutines.launch
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.Alignment
import androidx.compose.ui.draw.clip
import androidx.compose.foundation.clickable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight


/** Decide o que se mostra: arranque, início de sessão, mudança obrigatória de palavra-passe, bloqueio, oferta de PIN ou a aplicação. */
@Composable
fun PulseApp(sessao: Sessao) {
    PulseTheme(sessao.tema) {
        Box(Modifier.fillMaxSize().background()) {
            when (val f = sessao.fase) {
                Fase.ACarregar -> EcraArranque()
                Fase.SemLigacao -> EcraSemLigacao { sessao.iniciar() }
                Fase.Anonimo -> EcraLogin(sessao)
                is Fase.Autenticado -> when {
                    sessao.bloqueado -> EcraBloqueio(sessao) { sessao.sair() }
                    f.utilizador.mudarPassword -> EcraMudarPassword(sessao, f.utilizador.email, obrigatorio = true, aoConcluir = {})
                    sessao.ofertaPin -> EcraDefinirPin({ sessao.definirPin(it) }, { sessao.recusarPin() })
                    else -> Principal(sessao, f)
                }
            }
        }
    }
}

private sealed interface Destino {
    data object Hoje : Destino
    data object Mais : Destino
    data object Definicoes : Destino
    data object Password : Destino
    data object Pin : Destino
    data class Modulo(val id: String) : Destino
}

private val MODULOS_ABRIVEIS = setOf("tarefas", "bilhetes", "financas", "peso", "rto", "compras", "calendario", "email", "tempo")

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Principal(sessao: Sessao, f: Fase.Autenticado) {
    var destino by remember { mutableStateOf<Destino>(Destino.Hoje) }
    var assistente by remember { mutableStateOf(false) }
    var registoRto by remember { mutableStateOf(false) }       // o diálogo «Registar RTO de hoje» (atalho do toque longo)
    var recarga by remember { mutableIntStateOf(0) }          // sobe depois de o assistente alterar dados: o ecrã aberto volta a pedi-los
    val scope = rememberCoroutineScope()
    val contexto = LocalContext.current
    // notificações: canais, pedido da permissão (uma só vez; depois só em Definições) e registo deste telemóvel no servidor
    val pedirPermissao = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok -> if (ok) scope.launch { Notificacoes.registar(contexto) } }
    LaunchedEffect(Unit) {
        Notificacoes.criarCanais(contexto)
        if (Notificacoes.permitidas(contexto)) Notificacoes.registar(contexto)
        else if (Build.VERSION.SDK_INT >= 33 && !sessao.store.notificacoesPedidas) { sessao.store.notificacoesPedidas = true; pedirPermissao.launch(Manifest.permission.POST_NOTIFICATIONS) }
    }
    // tempo (ADR-092): a localização aproximada do aparelho; pede-se a permissão uma só vez no arranque e depois pelo ecrã Tempo
    var posicao by remember { mutableStateOf(Localizacao.guardada(sessao.store)) }
    val pedirLocalizacao = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok ->
        if (ok) scope.launch { Localizacao.obter(contexto)?.let { posicao = it; Localizacao.guardar(sessao.store, it) } }
        else if (!androidx.core.app.ActivityCompat.shouldShowRequestPermissionRationale(contexto as android.app.Activity, Manifest.permission.ACCESS_COARSE_LOCATION)
            && sessao.store.localizacaoPedida) {
            // recusada «para sempre»: só nas definições do sistema
            contexto.startActivity(android.content.Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, android.net.Uri.parse("package:${contexto.packageName}")).addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK))
        }
    }
    LaunchedEffect(Unit) {
        if (Localizacao.permitida(contexto)) Localizacao.obter(contexto)?.let { posicao = it; Localizacao.guardar(sessao.store, it) }
        else if (!sessao.store.localizacaoPedida) { sessao.store.localizacaoPedida = true; pedirLocalizacao.launch(Manifest.permission.ACCESS_COARSE_LOCATION) }
    }
    val snackbar = remember { SnackbarHostState() }
    val avisos = remember { Avisos(snackbar, scope) }
    // o regresso da Google leva ao ecrã das contas (mesmo depois de a app ter sido bloqueada enquanto se dava a permissão)
    LaunchedEffect(sessao.resultadoGoogle) { if (sessao.resultadoGoogle != null) destino = Destino.Modulo("google") }
    // o toque numa notificação leva ao módulo (e à aba) certos
    LaunchedEffect(sessao.pedidoAbrir) {
        val link = sessao.pedidoAbrir ?: return@LaunchedEffect
        val caminho = link.removePrefix("pulse://").substringBefore('?').split('/')
        if (caminho[0] == "hoje") destino = Destino.Hoje
        else if (caminho[0] == "assistente") assistente = true                                     // atalho «Assistente»: abre a ouvir
        else if (caminho[0] == "rto" && caminho.getOrNull(1) == "registar") registoRto = true  // atalho «Registar RTO»: pergunta Casa ou Escritório e regista hoje
        else if (caminho[0] in MODULOS_ABRIVEIS) { sessao.abaPedida = caminho.getOrNull(1); destino = Destino.Modulo(caminho[0]) }
        sessao.pedidoAbrir = null
    }
    BackHandler(destino != Destino.Hoje) {
        destino = when (destino) { Destino.Password, Destino.Pin -> Destino.Definicoes; Destino.Mais -> Destino.Hoje; Destino.Modulo("tempo") -> Destino.Hoje; else -> Destino.Mais }
    }
    val c = Pulse.cores
    CompositionLocalProvider(LocalAvisos provides avisos, LocalUtilizador provides f.utilizador, LocalPosicao provides posicao, LocalPedirLocalizacao provides { pedirLocalizacao.launch(Manifest.permission.ACCESS_COARSE_LOCATION) }, LocalAbrir provides { rota -> val c = rota.split('/', limit = 2); sessao.abaPedida = c.getOrNull(1); destino = Destino.Modulo(c[0]) }) {
        // com o teclado aberto o conteúdo encolhe (o formulário em foco fica à vista) e a barra de baixo esconde-se
        val tecladoAberto = WindowInsets.isImeVisible
        Scaffold(
            modifier = Modifier.imePadding(),
            containerColor = c.bg,
            snackbarHost = { SnackbarHost(snackbar) { d -> Snackbar(d, containerColor = c.text, contentColor = c.bg, actionColor = c.accent) } },
            bottomBar = {
                // sempre visível (o «Hoje» está a um toque de qualquer ecrã), exceto nos formulários de ecrã inteiro
                if (destino != Destino.Password && destino != Destino.Pin && !tecladoAberto) {
                    // «Hoje» à esquerda e «Mais» à direita, do mesmo tamanho e discretos; o logotipo ao centro, maior; tocar nele abre o assistente de voz (ADR-067/075/077)
                    val emHoje = destino == Destino.Hoje
                    val corHoje = if (emHoje) c.primary else c.text2.copy(alpha = 0.65f)
                    val corMais = if (!emHoje) c.primary else c.text2.copy(alpha = 0.65f)
                    Column(Modifier.fillMaxWidth().background(c.surface)) {
                        HorizontalDivider(color = c.line)
                        Box(Modifier.fillMaxWidth().navigationBarsPadding().height(60.dp)) {
                            Row(Modifier.align(Alignment.CenterStart).padding(start = 8.dp).clip(RoundedCornerShape(10.dp)).clickable(role = Role.Tab) { destino = Destino.Hoje }
                                .semantics { selected = emHoje }.padding(horizontal = 10.dp, vertical = 10.dp),
                                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                                Icon(Icone.HOJE, corHoje, tamanho = 16.dp)
                                Text("Hoje", style = Pulse.meta, color = corHoje)
                            }
                            LogoPulse(40.dp, 1f, Modifier.align(Alignment.Center).clip(RoundedCornerShape(20.dp)).clickable(role = Role.Button, onClickLabel = "Abrir o assistente") { assistente = true })
                            Row(Modifier.align(Alignment.CenterEnd).padding(end = 8.dp).clip(RoundedCornerShape(10.dp)).clickable(role = Role.Tab) { destino = Destino.Mais }
                                .semantics { selected = !emHoje }.padding(horizontal = 10.dp, vertical = 10.dp),
                                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                                Icon(Icone.MAIS, corMais, tamanho = 16.dp)
                                Text("Mais", style = Pulse.meta, color = corMais)
                            }
                        }
                    }
                }
            },
        ) { pad ->
            Box(Modifier.padding(pad).consumeWindowInsets(pad).fillMaxSize()) {
                key(recarga) { when (val d = destino) {
                    Destino.Hoje -> Column(Modifier.statusBarsPadding()) { EcraHoje(sessao, f.utilizador) { sessao.atualizacao?.let { AvisoAtualizacao(it) } } }
                    Destino.Mais -> Box(Modifier.statusBarsPadding()) { EcraMais({ destino = Destino.Modulo(it) }) { destino = Destino.Definicoes } }
                    Destino.Definicoes -> Box(Modifier.statusBarsPadding()) {
                        EcraDefinicoes(sessao, f.utilizador, { destino = Destino.Mais }, { destino = Destino.Password }, { destino = Destino.Pin })
                    }
                    Destino.Password -> EcraMudarPassword(sessao, f.utilizador.email, obrigatorio = false, aoConcluir = {}, aoVoltar = { destino = Destino.Definicoes })
                    Destino.Pin -> EcraDefinirPin({ sessao.definirPin(it); destino = Destino.Definicoes }, { destino = Destino.Definicoes })
                    is Destino.Modulo -> EcraDoModulo(d.id, sessao) { destino = Destino.Mais }
                } }
                if (assistente) AssistenteFolha({ assistente = false }, { recarga++ })
                if (registoRto) RegistoRtoHoje({ registoRto = false }) { recarga++ }
            }
        }
    }
}
