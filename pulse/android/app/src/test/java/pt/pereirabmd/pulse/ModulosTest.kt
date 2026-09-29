package pt.pereirabmd.pulse

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import pt.pereirabmd.pulse.util.*
import java.time.ZoneId
import java.time.ZonedDateTime

class ModulosTest {
    // --- Finanças ---
    @Test fun mesesFinancas() {
        assertEquals("setembro de 2026", tituloMesFin("2026-09")); assertEquals("2026-10", somarMeses("2026-09", 1)); assertEquals("2025-12", somarMeses("2026-01", -1)); assertEquals("2026-03", somarMeses("2025-09", 6))
    }
    @Test fun valores() {
        assertEquals(12.5, lerValor("12,5")!!, 0.0); assertEquals(1234.5, lerValor("1 234,50")!!, 0.0); assertNull(lerValor("")); assertNull(lerValor("0")); assertNull(lerValor("-3")); assertNull(lerValor("abc"))
        assertEquals("12,5", valorParaCampo(12.5)); assertEquals("12", valorParaCampo(12.0))
    }

    // --- Peso ---
    @Test fun mediaMovelDeSeteDias() {
        val dia = 86_400_000L
        val m = mediaMovel(listOf(Ponto(0, 100.0), Ponto(dia, 98.0), Ponto(10 * dia, 90.0)))
        assertEquals(100.0, m[0].v, 0.001); assertEquals(99.0, m[1].v, 0.001); assertEquals(90.0, m[2].v, 0.001)     // o 3.º fica sozinho na janela
    }
    @Test fun atividade() { assertEquals(1.2, normalizarAtividade(null), 0.0); assertEquals(1.45, normalizarAtividade(2.0), 0.0); assertEquals(1.7, normalizarAtividade(4.0), 0.0); assertEquals(1.45, normalizarAtividade(1.4), 0.0); assertEquals(1.2, normalizarAtividade(9.0), 0.0) }
    @Test fun deltaKg() { assertEquals("0,0 kg", fmtDeltaKg(0.02)); assertEquals("−1,2 kg", fmtDeltaKg(-1.2)); assertEquals("+0,4 kg", fmtDeltaKg(0.4)) }

    // --- RTO ---
    @Test fun semanasDoMes() {
        val s = semanasDoMes(2026, 8)          // setembro de 2026 começa a uma terça-feira
        assertTrue(s.all { it.size == 7 }); assertNull(s[0][0]); assertEquals("2026-09-01", s[0][1]); assertEquals("2026-09-30", s.last().filterNotNull().last())
    }
    @Test fun diasBloqueadosEMarcas() {
        assertTrue(diaBloqueado("2026-09-26", "2026-09-01"))            // sábado
        assertTrue(diaBloqueado("2026-09-01", "2026-09-02"))            // passado
        assertFalse(diaBloqueado("2026-09-02", "2026-09-02"))
        assertEquals("C", proximaMarca("T")); assertEquals("", proximaMarca("C")); assertEquals("T", proximaMarca(null)); assertEquals("T", proximaMarca(""))
    }
    @Test fun marcaDaCelula() {
        assertEquals("T" to "T", marcaDaCelula("T", true, "A")); assertEquals("Af" to "A", marcaDaCelula("", true, "A")); assertEquals("f" to "holiday", marcaDaCelula("", true, ""))
        assertEquals("F" to "F", marcaDaCelula("", false, "F")); assertEquals("" to "", marcaDaCelula("", false, ""))
    }
    @Test fun notasComIntervalo() {
        assertEquals("2026-09-01" to "2026-09-05", intervaloNota("2026-09-01", "2026-09-05")); assertEquals("2026-09-01" to "2026-09-01", intervaloNota("2026-09-01", null))
        assertNull(intervaloNota("2026-09-05", "2026-09-01")); assertNull(intervaloNota(null, null))
    }

    // --- Bilhetes ---
    @Test fun datasDosBilhetes() {
        assertEquals("seg 05/10", diaCurto("2026-10-05")); assertEquals("05/10 a 11/10", intervaloSemana("2026-10-05")); assertEquals("2026-10-01", somarDias("2026-09-30", 1))
    }
    @Test fun validacaoDaSemana() {
        val ok = LinhaEd("Aveiro", "Lisboa", "123", "07:42")
        val dias = listOf(DiaEd("2026-10-05", true, false, listOf(ok, ok, LinhaEd("A", "A", "x", "25:00"), LinhaEd("", "", "1", "07:00"))), DiaEd("2026-10-04", true, true, listOf(LinhaEd())), DiaEd("2026-10-06", true, false, emptyList()))
        val e = validarDias(dias)
        assertTrue(e[0].any { it.contains("repete a viagem 1") }); assertTrue(e[0].any { it.contains("origem e o destino são iguais") }); assertTrue(e[0].any { it.contains("comboio inválido") })
        assertTrue(e[0].any { it.contains("hora inválida") }); assertTrue(e[0].any { it.contains("escolhe a origem") })
        assertTrue(e[1].isEmpty()); assertTrue(e[2].isEmpty())          // dias passados e sem viagens não se validam
    }
    @Test fun editorDaSemana() {
        val v = JSONObject("""{"data":"2026-10-05","origem":"Aveiro","destino":"Lisboa","comboio":123,"hora":"07:42","ativo":false}""")
        val d = diasParaEditor(listOf("2026-10-05", "2026-10-06"), listOf(v), "2026-10-06")
        assertFalse(d[0].ativo); assertTrue(d[0].passado); assertEquals("123", d[0].viagens[0].comboio); assertTrue(d[1].ativo && d[1].viagens.isEmpty())
        val env = viagensParaEnviar(diasParaEditor(listOf("2026-10-05"), listOf(v), "2026-10-01"))
        assertEquals(123, env[0].getInt("comboio")); assertFalse(env[0].getBoolean("ativo"))
    }
    @Test fun classesDoRegisto() { assertEquals("ok", classeRegisto("CONFIRMED", "COMPRA")); assertEquals("warn", classeRegisto("SOLD_OUT", "COMPRA")); assertEquals("err", classeRegisto("FAILED", "COMPRA")); assertEquals("", classeRegisto(null, "PREFLIGHT")) }

    // --- Tarefas ---
    @Test fun calendarioDeTarefas() {
        assertEquals("2026-08-30" to "2026-10-03", intervaloMes("2026-09-15"))          // grelha de domingo a sábado
        assertEquals("2026-09-27" to "2026-10-03", intervaloSemanaDomingo("2026-09-30"))
        assertEquals("27 set – 3 out", tituloSemana("2026-09-27", "2026-10-03")); assertEquals("Setembro de 2026", tituloMes("2026-09-15"))
        assertEquals(35, listaDatas("2026-08-30", "2026-10-03").size)
    }
    @Test fun quandoDasTarefas() { assertEquals("hoje às 08:00", quando("2026-09-30 08:00", "2026-09-30")); assertEquals("ontem às 21:10", quando("2026-09-29 21:10", "2026-09-30")); assertEquals("27/09 às 07:00", quando("2026-09-27 07:00", "2026-09-30")) }
    @Test fun filtroDeTarefas() { assertTrue(passaFiltro("Ana", "todas", null)); assertTrue(passaFiltro("Ana", "minhas", "Ana")); assertFalse(passaFiltro("Bruno", "minhas", "Ana")); assertTrue(passaFiltro("Bruno", "Bruno", null)) }
    @Test fun csv() { val c = csvHistorico(listOf(listOf("Lixo", "Casa \"A\"", "2026-09-30", "Ana", "Feita", ""))); assertTrue(c.startsWith("﻿\"Tarefa\"")); assertTrue(c.contains("\"Casa \"\"A\"\"\"")) }
    @Test fun alternarLista() { assertEquals(listOf("a", "b"), alterna(listOf("a"), "b")); assertEquals(listOf("a"), alterna(listOf("a", "b"), "b")) }

    // --- Email ---
    @Test fun quandoDaMensagem() {
        val agora = ZonedDateTime.of(2026, 9, 30, 10, 0, 0, 0, ZoneId.systemDefault())
        assertEquals("há 30 min", quandoMensagem("2026-09-30T09:30:00", agora)); assertEquals("agora", quandoMensagem("2026-09-30T09:59:30", agora))
        assertEquals("hoje 07:15", quandoMensagem("2026-09-30T07:15:00", agora)); assertEquals("ontem", quandoMensagem("2026-09-29T20:00:00", agora)); assertEquals("28/09", quandoMensagem("2026-09-28T20:00:00", agora))
        assertEquals("", quandoMensagem("", agora)); assertEquals("", quandoMensagem("lixo", agora))
    }
}
