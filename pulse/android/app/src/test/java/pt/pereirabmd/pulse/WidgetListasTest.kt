package pt.pereirabmd.pulse

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test
import pt.pereirabmd.pulse.data.*
import pt.pereirabmd.pulse.widgets.linhasCompras
import pt.pereirabmd.pulse.widgets.linhasTarefas
import pt.pereirabmd.pulse.widgets.removerDaCache

class WidgetListasTest {
    private fun hoje(tarefas: Modulo<TarefasDados>, compras: Modulo<ComprasDados>?) =
        Hoje(false, "2026-10-03", tarefas, Modulo("desativado", null), Modulo("desativado", null), Modulo("desativado", null), Modulo("desativado", null), compras, Modulo("desativado", null), Modulo("desativado", null))

    @Test fun `as linhas das tarefas e das compras vem do Hoje`() {
        val h = hoje(Modulo("ok", TarefasDados(listOf(Tarefa("I1", "Limpar WC", "Casa", "18:30:00"), Tarefa("I2", "Regar", "", "")), 0, 0, 2)),
            Modulo("ok", ComprasDados(2, listOf(ItemCompras(7, "Leite", 2, "sem lactose"), ItemCompras(8, "Pão", 1, "")))))
        assertEquals(listOf("t:I1" to "Limpar WC", "t:I2" to "Regar"), linhasTarefas(h).map { it.chave to it.texto })
        assertEquals(listOf("Casa · 18:30", ""), linhasTarefas(h).map { it.meta })
        assertEquals(listOf("c:7" to "×2 · sem lactose", "c:8" to ""), linhasCompras(h).map { it.chave to it.meta })
    }

    @Test fun `modulo em baixo ou sem compras dao lista vazia`() {
        val h = hoje(Modulo("indisponivel", null), null)
        assertEquals(0, linhasTarefas(h).size); assertEquals(0, linhasCompras(h).size)
    }

    private fun cache() = JSONObject("""{"hoje":{"modulos":{
        "tarefas":{"estado":"ok","dados":{"hoje":[{"id":"I1","nome":"A"},{"id":"I2","nome":"B"}],"feitasHoje":1,"totalHoje":3}},
        "compras":{"estado":"ok","dados":{"pendentes":2,"itens":[{"item":7,"nome":"Leite"},{"item":8,"nome":"Pão"}]}}}}}""")

    @Test fun `marcar uma tarefa no widget tira-a da cache e conta mais uma feita`() {
        val c = cache(); removerDaCache(c, "t:I1")
        val d = c.getJSONObject("hoje").getJSONObject("modulos").getJSONObject("tarefas").getJSONObject("dados")
        assertEquals(1, d.getJSONArray("hoje").length()); assertEquals("I2", d.getJSONArray("hoje").getJSONObject(0).getString("id")); assertEquals(2, d.getInt("feitasHoje"))
    }

    @Test fun `marcar uma compra no widget tira-a da cache e desconta uma pendente`() {
        val c = cache(); removerDaCache(c, "c:7")
        val d = c.getJSONObject("hoje").getJSONObject("modulos").getJSONObject("compras").getJSONObject("dados")
        assertEquals(1, d.getJSONArray("itens").length()); assertEquals(8, d.getJSONArray("itens").getJSONObject(0).getInt("item")); assertEquals(1, d.getInt("pendentes"))
        removerDaCache(c, "c:99"); assertEquals(1, d.getJSONArray("itens").length())            // uma chave desconhecida não mexe em nada
    }
}
