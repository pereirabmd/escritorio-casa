package pt.pereirabmd.pulse.ui

import androidx.compose.runtime.Composable

/** Destino de um módulo pelo seu id (o mesmo do servidor e de `GET /modules`). */
@Composable
fun EcraDoModulo(id: String, sessao: Sessao, aoVoltar: () -> Unit) {
    when (id) {
        "compras" -> ComprasEcra(aoVoltar)
        "financas" -> FinancasEcra(aoVoltar)
        "peso" -> PesoEcra(aoVoltar)
        "rto" -> RtoEcra(aoVoltar)
        "bilhetes" -> BilhetesEcra(aoVoltar, sessao.abaPedida) { sessao.abaPedida = null }
        "tarefas" -> TarefasEcra(aoVoltar, sessao.abaPedida) { sessao.abaPedida = null }
        "calendario" -> CalendarioGoogleEcra(aoVoltar)
        "email" -> EmailEcra(aoVoltar)
        "google" -> GoogleContasEcra(sessao, aoVoltar)
        else -> EcraModulo(id, aoVoltar) { Rolar { Texto2("Em construção.") } }
    }
}
