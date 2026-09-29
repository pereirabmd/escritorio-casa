package pt.pereirabmd.pulse.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

private enum class Destino { HOJE, MAIS, DEFINICOES, PASSWORD, PIN }

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

@Composable
private fun Principal(sessao: Sessao, f: Fase.Autenticado) {
    var destino by remember { mutableStateOf(Destino.HOJE) }
    BackHandler(destino == Destino.PASSWORD || destino == Destino.PIN) { destino = Destino.DEFINICOES }
    BackHandler(destino == Destino.DEFINICOES) { destino = Destino.MAIS }
    BackHandler(destino == Destino.MAIS) { destino = Destino.HOJE }
    val c = Pulse.cores
    Scaffold(
        containerColor = c.bg,
        bottomBar = {
            if (destino == Destino.HOJE || destino == Destino.MAIS) NavigationBar(containerColor = c.surface, tonalElevation = 0.dp) {
                val cor = NavigationBarItemDefaults.colors(selectedIconColor = c.primary, selectedTextColor = c.primary, indicatorColor = c.surface2, unselectedTextColor = c.text2, unselectedIconColor = c.text2)
                NavigationBarItem(destino == Destino.HOJE, { destino = Destino.HOJE }, { Icon(Icone.HOJE, if (destino == Destino.HOJE) c.primary else c.text2) }, label = { Text("Hoje") }, colors = cor)
                NavigationBarItem(destino == Destino.MAIS, { destino = Destino.MAIS }, { Icon(Icone.MAIS, if (destino == Destino.MAIS) c.primary else c.text2) }, label = { Text("Mais") }, colors = cor)
            }
        },
    ) { pad ->
        Box(Modifier.padding(pad).consumeWindowInsets(pad).fillMaxSize()) {
            when (destino) {
                Destino.HOJE -> Column(Modifier.statusBarsPadding()) {
                    EcraHoje(sessao, f.utilizador) { sessao.atualizacao?.let { AvisoAtualizacao(it) } }
                }
                Destino.MAIS -> Box(Modifier.statusBarsPadding()) { EcraMais { destino = Destino.DEFINICOES } }
                Destino.DEFINICOES -> Box(Modifier.statusBarsPadding()) {
                    EcraDefinicoes(sessao, f.utilizador, { destino = Destino.MAIS }, { destino = Destino.PASSWORD }, { destino = Destino.PIN })
                }
                Destino.PASSWORD -> EcraMudarPassword(sessao, f.utilizador.email, obrigatorio = false, aoConcluir = {}, aoVoltar = { destino = Destino.DEFINICOES })
                Destino.PIN -> EcraDefinirPin({ sessao.definirPin(it); destino = Destino.DEFINICOES }, { destino = Destino.DEFINICOES })
            }
        }
    }
}
