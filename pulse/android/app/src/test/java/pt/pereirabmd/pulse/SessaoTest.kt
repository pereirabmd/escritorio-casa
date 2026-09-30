package pt.pereirabmd.pulse

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import pt.pereirabmd.pulse.ui.devoVerificarAtualizacao

class SessaoTest {
    @Test fun verificaAoVoltarSoDepoisDeUmTempo() {
        assertTrue(devoVerificarAtualizacao(0, 1_000))                     // nunca verificou
        assertFalse(devoVerificarAtualizacao(1_000, 1_000 + 9 * 60_000))   // há 9 min: não insiste
        assertTrue(devoVerificarAtualizacao(1_000, 1_000 + 11 * 60_000))   // há 11 min: pergunta outra vez
    }
}
