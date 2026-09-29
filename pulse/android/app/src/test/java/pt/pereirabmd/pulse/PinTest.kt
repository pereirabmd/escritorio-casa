package pt.pereirabmd.pulse

import org.junit.Assert.*
import org.junit.Test
import pt.pereirabmd.pulse.data.Pin

class PinTest {
    @Test fun hashConfereSoComOPinCerto() {
        val sal = Pin.novoSal(); val h = Pin.hash("123456", sal)
        assertTrue(Pin.confere("123456", sal, h)); assertFalse(Pin.confere("123457", sal, h))
        assertFalse(Pin.confere("123456", Pin.novoSal(), h))               // outro sal, outro hash
    }
    @Test fun validacao() { assertTrue(Pin.valido("000000")); assertFalse(Pin.valido("12345")); assertFalse(Pin.valido("12345a")); assertFalse(Pin.valido("1234567")) }
}
