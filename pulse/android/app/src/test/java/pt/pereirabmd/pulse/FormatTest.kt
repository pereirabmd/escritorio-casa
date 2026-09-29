package pt.pereirabmd.pulse

import org.junit.Assert.*
import org.junit.Test
import pt.pereirabmd.pulse.util.*
import java.util.Calendar

class FormatTest {
    @Test fun euro() { assertEquals("1 245,50 €", fmtEuro(1245.5)); assertEquals("0,00 €", fmtEuro(0.0)); assertEquals("12,00 €", fmtEuro(12.0)) }
    @Test fun peso() = assertEquals("104,8 kg", fmtPeso(104.8))
    @Test fun datas() { assertEquals("28/09/2026", fmtDataIso("2026-09-28")); assertEquals("28 de setembro", fmtDiaMes("2026-09-28")); assertEquals("1 de janeiro", fmtDiaMes("2026-01-01")) }
    @Test fun dataLonga() { val c = Calendar.getInstance().apply { clear(); set(2026, Calendar.SEPTEMBER, 28) }; assertEquals("Segunda-feira, 28 de setembro", fmtDataLonga(c)) }
    @Test fun saudacoes() { assertEquals("Boa noite", saudacao(3)); assertEquals("Bom dia", saudacao(9)); assertEquals("Boa tarde", saudacao(15)); assertEquals("Boa noite", saudacao(22)) }
    @Test fun dias() { assertEquals("hoje", fmtDias(0)); assertEquals("amanhã", fmtDias(1)); assertEquals("em 5 dias", fmtDias(5)); assertEquals("há 3 dias", fmtDias(-3)); assertEquals("ontem", fmtDias(-1)) }
    @Test fun plurais() { assertEquals("1 tarefa", plural(1, "tarefa", "tarefas")); assertEquals("3 tarefas", plural(3, "tarefa", "tarefas")) }

    @Test fun regrasPassword() {
        assertFalse(todasOk(regrasPassword("curta", "", "a@b.pt")))
        assertFalse(todasOk(regrasPassword("1234567890", "x", "a@b.pt")))
        assertFalse(todasOk(regrasPassword("bruno@casa.pt", "x", "bruno@casa.pt")))
        assertFalse(todasOk(regrasPassword("aaaaaaaaaaaa", "x", "a@b.pt")))
        assertFalse(todasOk(regrasPassword("umaboapassword", "umaboapassword", "a@b.pt")))
        assertTrue(todasOk(regrasPassword("umaboapassword", "provisoria", "a@b.pt")))
    }
}
