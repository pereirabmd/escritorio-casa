package pt.pereirabmd.pulse.ui

import android.Manifest
import android.os.Build
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.ui.platform.LocalContext
import pt.pereirabmd.pulse.data.Notificacoes
import kotlinx.coroutines.launch
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp


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

private val MODULOS_ABRIVEIS = setOf("tarefas", "bilhetes", "financas", "peso", "rto", "compras", "calendario", "email")

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Principal(sessao: Sessao, f: Fase.Autenticado) {
    var destino by remember { mutableStateOf<Destino>(Destino.Hoje) }
    val scope = rememberCoroutineScope()
    val contexto = LocalContext.current
    // notificações: canais, pedido da permissão (uma só vez; depois só em Definições) e registo deste telemóvel no servidor
    val pedirPermissao = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok -> if (ok) scope.launch { Notificacoes.registar(contexto) } }
    LaunchedEffect(Unit) {
        Notificacoes.criarCanais(contexto)
        if (Notificacoes.permitidas(contexto)) Notificacoes.registar(contexto)
        else if (Build.VERSION.SDK_INT >= 33 && !sessao.store.notificacoesPedidas) { sessao.store.notificacoesPedidas = true; pedirPermissao.launch(Manifest.permission.POST_NOTIFICATIONS) }
    }
    val snackbar = remember { SnackbarHostState() }
    val avisos = remember { Avisos(snackbar, scope) }
    // o regresso da Google leva ao ecrã das contas (mesmo depois de a app ter sido bloqueada enquanto se dava a permissão)
    LaunchedEffect(sessao.resultadoGoogle) { if (sessao.resultadoGoogle != null) destino = Destino.Modulo("google") }
    // o toque numa notificação leva ao módulo (e à aba) certos
    LaunchedEffect(sessao.pedidoAbrir) {
        val link = sessao.pedidoAbrir ?: return@LaunchedEffect
        val caminho = link.removePrefix("pulse://").split('/')
        if (caminho[0] in MODULOS_ABRIVEIS) { sessao.abaPedida = caminho.getOrNull(1); destino = Destino.Modulo(caminho[0]) }
        sessao.pedidoAbrir = null
    }
    BackHandler(destino != Destino.Hoje) {
        destino = when (destino) { Destino.Password, Destino.Pin -> Destino.Definicoes; Destino.Mais -> Destino.Hoje; else -> Destino.Mais }
    }
    val c = Pulse.cores
    CompositionLocalProvider(LocalAvisos provides avisos, LocalUtilizador provides f.utilizador, LocalAbrir provides { id -> destino = Destino.Modulo(id) }) {
        // com o teclado aberto o conteúdo encolhe (o formulário em foco fica à vista) e a barra de baixo esconde-se
        val tecladoAberto = WindowInsets.isImeVisible
        Scaffold(
            modifier = Modifier.imePadding(),
            containerColor = c.bg,
            snackbarHost = { SnackbarHost(snackbar) { d -> Snackbar(d, containerColor = c.text, contentColor = c.bg, actionColor = c.accent) } },
            bottomBar = {
                // sempre visível (o «Hoje» está a um toque de qualquer ecrã), exceto nos formulários de ecrã inteiro
                if (destino != Destino.Password && destino != Destino.Pin && !tecladoAberto) NavigationBar(containerColor = c.surface, tonalElevation = 0.dp) {
                    val cor = NavigationBarItemDefaults.colors(selectedIconColor = c.primary, selectedTextColor = c.primary, indicatorColor = c.surface2, unselectedTextColor = c.text2, unselectedIconColor = c.text2)
                    val emHoje = destino == Destino.Hoje
                    NavigationBarItem(emHoje, { destino = Destino.Hoje }, { LogoPulse(26.dp, if (emHoje) 1f else 0.55f) }, label = { Text("Hoje") }, colors = cor)
                    NavigationBarItem(!emHoje, { destino = Destino.Mais },
                        { Icon(Icone.MAIS, if (!emHoje) c.primary else c.text2) }, label = { Text("Mais") }, colors = cor)
                }
            },
        ) { pad ->
            Box(Modifier.padding(pad).consumeWindowInsets(pad).fillMaxSize()) {
                when (val d = destino) {
                    Destino.Hoje -> Column(Modifier.statusBarsPadding()) { EcraHoje(sessao, f.utilizador) { sessao.atualizacao?.let { AvisoAtualizacao(it) } } }
                    Destino.Mais -> Box(Modifier.statusBarsPadding()) { EcraMais({ destino = Destino.Modulo(it) }) { destino = Destino.Definicoes } }
                    Destino.Definicoes -> Box(Modifier.statusBarsPadding()) {
                        EcraDefinicoes(sessao, f.utilizador, { destino = Destino.Mais }, { destino = Destino.Password }, { destino = Destino.Pin })
                    }
                    Destino.Password -> EcraMudarPassword(sessao, f.utilizador.email, obrigatorio = false, aoConcluir = {}, aoVoltar = { destino = Destino.Definicoes })
                    Destino.Pin -> EcraDefinirPin({ sessao.definirPin(it); destino = Destino.Definicoes }, { destino = Destino.Definicoes })
                    is Destino.Modulo -> EcraDoModulo(d.id, sessao) { destino = Destino.Mais }
                }
            }
        }
    }
}
