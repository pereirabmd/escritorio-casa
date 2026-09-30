package pt.pereirabmd.pulse

import org.junit.Assert.assertEquals
import org.junit.Test
import pt.pereirabmd.pulse.util.ComandoVoz
import pt.pereirabmd.pulse.util.comandoVoz

class AssistenteTest {
    @Test fun confirmaECancelaPorVozSoComFrasesInteiras() {
        assertEquals(ComandoVoz.CONFIRMAR, comandoVoz("Confirma.", true))
        assertEquals(ComandoVoz.CONFIRMAR, comandoVoz("  Sim! ", true))
        assertEquals(ComandoVoz.CONFIRMAR, comandoVoz("Avança", true))
        assertEquals(ComandoVoz.CANCELAR, comandoVoz("Não", true))
        assertEquals(ComandoVoz.CANCELAR, comandoVoz("cancela", true))
        assertEquals(ComandoVoz.NENHUM, comandoVoz("sim, e acrescenta leite", true))
        assertEquals(ComandoVoz.NENHUM, comandoVoz("adiciona pão", true))
    }

    @Test fun semPropostasNaoHaNadaAConfirmar() {
        assertEquals(ComandoVoz.NENHUM, comandoVoz("confirma", false))
    }
}
