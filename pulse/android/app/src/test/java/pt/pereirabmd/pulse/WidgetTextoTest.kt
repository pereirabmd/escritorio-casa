package pt.pereirabmd.pulse

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import pt.pereirabmd.pulse.data.*
import pt.pereirabmd.pulse.util.graus
import pt.pereirabmd.pulse.widgets.linhasDoWidget
import pt.pereirabmd.pulse.widgets.tempoDoWidget

class WidgetTextoTest {
    private fun hoje(
        tarefas: Modulo<TarefasDados> = Modulo("ok", TarefasDados(emptyList(), 0, 2, 5)),
        bilhetes: Modulo<BilhetesDados> = Modulo("ok", BilhetesDados(Viagem("2026-10-05", "06:45", "Aveiro", "Lisboa Oriente", 520, false, null, Compra("24", "78")), null)),
        rto: Modulo<RtoDados> = Modulo("ok", RtoDados(listOf(DiaRto("2026-10-02", 5, "C", true)), 2, 3)),
        peso: Modulo<PesoDados> = Modulo("ok", PesoDados("2026-10-02 07:00:00", 80.6, true, 80.6)),
    ) = Hoje(false, "2026-10-02", tarefas, bilhetes, rto, peso, Modulo("desativado", null), null, Modulo("desativado", null), Modulo("desativado", null))

    @Test fun `o widget resume comboio, tarefas, RTO e peso`() {
        val l = linhasDoWidget(hoje())
        assertEquals("05/10 06:45 · comboio 520", l.comboio)
        assertEquals("Aveiro → Lisboa Oriente · carruagem 24, lugar 78", l.comboioDetalhe)
        assertEquals("2 de 5 feitas", l.tarefas); assertEquals("Casa", l.rto); assertEquals("registado hoje", l.peso)
    }

    @Test fun `o comboio de hoje diz hoje e sem bilhete diz por comprar`() {
        val v = Viagem("2026-10-02", "17:30", "Lisboa Oriente", "Aveiro", 731, false, null, null)
        val l = linhasDoWidget(hoje(bilhetes = Modulo("ok", BilhetesDados(v, null))))
        assertEquals("hoje 17:30 · comboio 731", l.comboio); assertEquals("Lisboa Oriente → Aveiro · por comprar", l.comboioDetalhe)
        assertEquals("sem viagens marcadas", linhasDoWidget(hoje(bilhetes = Modulo("ok", BilhetesDados(null, null)))).comboio)
    }

    @Test fun `tarefas atrasadas, nada para hoje e RTO por marcar`() {
        assertEquals("1 de 3 feitas · 2 atrasadas", linhasDoWidget(hoje(tarefas = Modulo("ok", TarefasDados(emptyList(), 2, 1, 3)))).tarefas)
        assertEquals("1 atrasada", linhasDoWidget(hoje(tarefas = Modulo("ok", TarefasDados(emptyList(), 1, 0, 0)))).tarefas)
        assertEquals("nada para hoje", linhasDoWidget(hoje(tarefas = Modulo("ok", TarefasDados(emptyList(), 0, 0, 0)))).tarefas)
        assertEquals("por marcar", linhasDoWidget(hoje(rto = Modulo("ok", RtoDados(listOf(DiaRto("2026-10-02", 5, "", true)), 0, 0)))).rto)
        assertEquals("Escritório", linhasDoWidget(hoje(rto = Modulo("ok", RtoDados(listOf(DiaRto("2026-10-02", 5, "T", true)), 0, 0)))).rto)
    }

    @Test fun `um modulo em baixo mostra um traco e peso por registar`() {
        val l = linhasDoWidget(hoje(tarefas = Modulo("indisponivel", null), bilhetes = Modulo("erro", null), rto = Modulo("indisponivel", null), peso = Modulo("ok", PesoDados(null, null, false, null))))
        assertEquals(listOf("—", "—", "—", "por registar"), listOf(l.comboio, l.tarefas, l.rto, l.peso))
    }

    @Test fun `o tempo do widget tem icone, temperatura, maxima, minima e chuva`() {
        val t = tempoDoWidget(JSONObject("""{"agora":{"temp":17.4,"icone":"nublado"},"hoje":{"max":20.2,"min":11.6,"chuva":40}}"""))
        assertEquals("nublado", t?.icone); assertEquals("17°", t?.temp); assertEquals("20°/12° · 40%", t?.maxMin)
        assertEquals("20°/12°", tempoDoWidget(JSONObject("""{"agora":{"temp":17,"icone":"sol"},"hoje":{"max":20,"min":12,"chuva":0}}"""))?.maxMin)
        assertNull(tempoDoWidget(null))
    }

    @Test fun `graus arredonda e sem valor mostra traco`() {
        assertEquals("17°", graus(17.4)); assertEquals("18°", graus(17.5)); assertEquals("–", graus(null)); assertEquals("-1°", graus(-0.6))
    }
}
