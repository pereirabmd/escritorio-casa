package pt.pereirabmd.pulse.ui

import androidx.activity.compose.BackHandler
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

@Composable
private fun Principal(sessao: Sessao, f: Fase.Autenticado) {
    var destino by remember { mutableStateOf<Destino>(Destino.Hoje) }
    val scope = rememberCoroutineScope()
    val snackbar = remember { SnackbarHostState() }
    val avisos = remember { Avisos(snackbar, scope) }
    // o regresso da Google leva ao ecrã das contas (mesmo depois de a app ter sido bloqueada enquanto se dava a permissão)
    LaunchedEffect(sessao.resultadoGoogle) { if (sessao.resultadoGoogle != null) destino = Destino.Modulo("google") }
    BackHandler(destino != Destino.Hoje) {
        destino = when (destino) { Destino.Password, Destino.Pin -> Destino.Definicoes; Destino.Mais -> Destino.Hoje; else -> Destino.Mais }
    }
    val c = Pulse.cores
    CompositionLocalProvider(LocalAvisos provides avisos, LocalUtilizador provides f.utilizador, LocalAbrir provides { id -> destino = Destino.Modulo(id) }) {
        Scaffold(
            containerColor = c.bg,
            snackbarHost = { SnackbarHost(snackbar) { d -> Snackbar(d, containerColor = c.text, contentColor = c.bg, actionColor = c.accent) } },
            bottomBar = {
                if (destino == Destino.Hoje || destino == Destino.Mais) NavigationBar(containerColor = c.surface, tonalElevation = 0.dp) {
                    val cor = NavigationBarItemDefaults.colors(selectedIconColor = c.primary, selectedTextColor = c.primary, indicatorColor = c.surface2, unselectedTextColor = c.text2, unselectedIconColor = c.text2)
                    NavigationBarItem(destino == Destino.Hoje, { destino = Destino.Hoje }, { Icon(Icone.HOJE, if (destino == Destino.Hoje) c.primary else c.text2) }, label = { Text("Hoje") }, colors = cor)
                    NavigationBarItem(destino == Destino.Mais, { destino = Destino.Mais }, { Icon(Icone.MAIS, if (destino == Destino.Mais) c.primary else c.text2) }, label = { Text("Mais") }, colors = cor)
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
