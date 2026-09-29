package pt.pereirabmd.pulse.ui

import android.content.Context
import android.content.Intent
import android.net.Uri
import pt.pereirabmd.pulse.BuildConfig

/** Módulos que ainda não têm ecrã nativo abrem a Web do Pulse no navegador (a mesma conta, as mesmas regras do servidor). */
fun abrirNaWeb(ctx: Context, rota: String) {
    ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(BuildConfig.SERVER + rota)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
}
