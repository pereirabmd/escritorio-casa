package pt.pereirabmd.pulse.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import pt.pereirabmd.pulse.data.*
import pt.pereirabmd.pulse.util.*

/** O ecrã do tempo (ADR-092): agora, próximas 24 horas e 5 dias, para onde o aparelho está (ou Aveiro, se não deu a localização). Dados da Open-Meteo, pelo servidor. */
@Composable
fun TempoEcra(aoVoltar: () -> Unit) {
    val pos = LocalPosicao.current
    val pedir = LocalPedirLocalizacao.current
    val c = carga("tempo|$pos") { Api.get(Localizacao.caminho(pos)) }
    EcraModulo("Tempo", aoVoltar) {
        Ao(c, "A consultar a previsão…") { d ->
            Rolar {
                if (d.txtOu("localizacao") == "omissao") {
                    Aviso(TipoAviso.INFO, "Local por omissão: Aveiro. Dá a localização para veres o tempo onde estás.")
                    Botao("Usar a minha localização", pedir, variante = Variante.SECUNDARIO, pequeno = true)
                }
                val agora = d.obj("agora"); val hoje = d.obj("hoje")
                Bloco {
                    Row(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalAlignment = Alignment.CenterVertically) {
                        Icon(iconeTempo(agora?.txtOu("icone").orEmpty()), Pulse.cores.primary, 44.dp)
                        Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Texto(graus(agora?.real("temp")), Pulse.metric)
                            Texto(agora?.txtOu("descricao").orEmpty())
                            Meta("Máx ${graus(hoje?.real("max"))} · Mín ${graus(hoje?.real("min"))}" + (agora?.inteiroOuNull("vento")?.let { " · vento $it km/h" } ?: ""))
                            hoje?.txtOu("nascer")?.takeIf { it.isNotEmpty() }?.let { Meta("Nascer do sol $it · pôr do sol ${hoje.txtOu("poer")}") }
                        }
                    }
                }
                Texto("Próximas 24 horas", Pulse.card)
                Bloco {
                    LazyRow(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                        items(d.objs("horas")) { h ->
                            Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                Meta(h.txtOu("hora"))
                                Icon(iconeTempo(h.txtOu("icone")), Pulse.cores.primary, 22.dp)
                                Texto(graus(h.real("temp")))
                                Meta(h.inteiroOuNull("chuva")?.takeIf { it > 0 }?.let { "$it%" } ?: " ")
                            }
                        }
                    }
                }
                Texto("Próximos dias", Pulse.card)
                Bloco {
                    d.objs("dias").forEachIndexed { i, dia ->
                        Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Texto(if (i == 0) "Hoje" else dia.txtOu("diaSemana"))
                                Meta(dia.txtOu("descricao") + (dia.inteiroOuNull("chuva")?.takeIf { it > 0 }?.let { " · chuva $it%" } ?: ""))
                            }
                            Icon(iconeTempo(dia.txtOu("icone")), Pulse.cores.primary, 24.dp)
                            Texto(graus(dia.real("max")))
                            Meta(graus(dia.real("min")))
                        }
                    }
                }
                Meta("Previsão da Open-Meteo, atualizada às ${d.txtOu("atualizadoEm").drop(11).take(5)}.")
            }
        }
    }
}
