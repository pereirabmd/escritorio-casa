package pt.pereirabmd.pulse

import android.os.Bundle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.remember
import androidx.fragment.app.FragmentActivity
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
            val s = remember { Sessao(SessionStore(applicationContext), scope).also { it.iniciar(); sessao = it } }
            PulseApp(s)
        }
    }

    override fun onStop() { super.onStop(); sessao?.aoIrParaSegundoPlano() }
    override fun onStart() { super.onStart(); sessao?.aoVoltar() }
}
