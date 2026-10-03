package pt.pereirabmd.pulse

import android.content.Intent
import android.os.Bundle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.remember
import androidx.fragment.app.FragmentActivity
import pt.pereirabmd.pulse.data.Notificacoes
import pt.pereirabmd.pulse.data.SessionStore
import pt.pereirabmd.pulse.ui.PulseApp
import pt.pereirabmd.pulse.ui.Sessao

/** FragmentActivity porque o BiometricPrompt precisa dela. */
class MainActivity : FragmentActivity() {
    private var sessao: Sessao? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            val scope = rememberCoroutineScope()
            val s = remember { Sessao(SessionStore(applicationContext), scope).also { it.aoSair = { Notificacoes.remover(applicationContext) }; it.iniciar(); sessao = it; tratar(intent) } }
            PulseApp(s)
        }
    }

    override fun onNewIntent(intent: Intent) { super.onNewIntent(intent); setIntent(intent); tratar(intent) }

    /** O regresso da Google (`pulse://google?resultado=ok|erro&motivo=…`) chega por aqui. */
    private fun tratar(intent: Intent?) {
        intent?.getStringExtra(Notificacoes.EXTRA_LINK)?.takeIf { it.isNotEmpty() }?.let { sessao?.abrirLink(it); intent.removeExtra(Notificacoes.EXTRA_LINK) }
        val uri = intent?.data ?: return
        if (uri.scheme == "pulse" && uri.host == "google") sessao?.regressoGoogle(uri.getQueryParameter("resultado") == "ok", uri.getQueryParameter("motivo").orEmpty())
        // os atalhos do toque longo (pulse://assistente, pulse://peso, pulse://rto/registar…) e os widgets abrem o sítio certo, depois do desbloqueio
        else if (uri.scheme == "pulse") { sessao?.abrirLink(uri.toString()); intent.data = null }
    }

    override fun onStop() { super.onStop(); sessao?.aoIrParaSegundoPlano() }
    override fun onStart() { super.onStart(); sessao?.aoVoltar() }
}
