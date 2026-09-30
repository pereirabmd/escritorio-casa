package pt.pereirabmd.pulse

import org.junit.Assert.assertEquals
import org.junit.Test
import pt.pereirabmd.pulse.util.ComandoVoz
import pt.pereirabmd.pulse.util.comandoVoz
import pt.pereirabmd.pulse.util.paraLeitura

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

    @Test fun textoParaLerEmVozAlta() {
        assertEquals("Adicionar Pão à lista Casa. Confirmas?", paraLeitura("Adicionar «Pão» à lista «Casa».  Confirmas?"))
        assertEquals("Aveiro para Lisboa Oriente, 06:45", paraLeitura("Aveiro → Lisboa Oriente · 06:45"))
        assertEquals("Feito.", paraLeitura("**Feito.**"))
    }
}
