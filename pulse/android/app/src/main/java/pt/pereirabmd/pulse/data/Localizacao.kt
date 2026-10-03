package pt.pereirabmd.pulse.data

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationManager
import android.os.Build
import androidx.core.content.ContextCompat
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.coroutines.resume

/** A localização aproximada do aparelho para o tempo (ADR-092). Só a permissão de localização aproximada (cerca de 2 km), sem GPS contínuo e sem serviços da Google. */
object Localizacao {
    fun permitida(ctx: Context) = ContextCompat.checkSelfPermission(ctx, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED

    /** «lat,lon» arredondado a 2 casas (cerca de 1 km), ou `null` sem permissão ou sem posição em 8 s. */
    @Suppress("MissingPermission")
    suspend fun obter(ctx: Context): Pair<Double, Double>? {
        if (!permitida(ctx)) return null
        val lm = ctx.getSystemService(Context.LOCATION_SERVICE) as? LocationManager ?: return null
        val fornecedores = listOf(LocationManager.NETWORK_PROVIDER, LocationManager.PASSIVE_PROVIDER, LocationManager.GPS_PROVIDER).filter { runCatching { lm.isProviderEnabled(it) }.getOrDefault(false) }
        // a última conhecida chega (o tempo não muda a 1 km); só se não houver nenhuma se pede uma posição nova
        val ultima = fornecedores.mapNotNull { runCatching { lm.getLastKnownLocation(it) }.getOrNull() }.maxByOrNull { it.time }
        val l = ultima ?: withTimeoutOrNull(8_000) { nova(lm, fornecedores.firstOrNull() ?: return@withTimeoutOrNull null) } ?: return null
        return arredondar(l.latitude) to arredondar(l.longitude)
    }

    private fun arredondar(v: Double) = Math.round(v * 100) / 100.0

    @Suppress("MissingPermission")
    private suspend fun nova(lm: LocationManager, fornecedor: String): Location? = suspendCancellableCoroutine { k ->
        if (Build.VERSION.SDK_INT >= 30) {
            val sinal = android.os.CancellationSignal()
            k.invokeOnCancellation { sinal.cancel() }
            lm.getCurrentLocation(fornecedor, sinal, { it.run() }) { k.resume(it) }
        } else {
            @Suppress("DEPRECATION")
            lm.requestSingleUpdate(fornecedor, { k.resume(it) }, android.os.Looper.getMainLooper())
        }
    }

    fun guardar(store: SessionStore, p: Pair<Double, Double>) { store.ultimaPosicao = "${p.first},${p.second}" }
    fun guardada(store: SessionStore): Pair<Double, Double>? = store.ultimaPosicao?.split(',')?.takeIf { it.size == 2 }?.let { (a, b) -> a.toDoubleOrNull()?.let { x -> b.toDoubleOrNull()?.let { y -> x to y } } }

    /** O caminho do pedido ao servidor (`/weather` com as coordenadas, ou sem elas: Aveiro por omissão). */
    fun caminho(p: Pair<Double, Double>?) = if (p == null) "/weather" else "/weather?lat=${p.first}&lon=${p.second}"
}
