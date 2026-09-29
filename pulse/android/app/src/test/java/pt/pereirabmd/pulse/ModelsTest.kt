package pt.pereirabmd.pulse

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import pt.pereirabmd.pulse.data.*

class ModelsTest {
    private val hoje = JSONObject("""
      {"estado":"degradado","data":"2026-09-29","modulos":{
        "tarefas":{"estado":"ok","dados":{"hoje":[{"id":"a","nome":"Lixo","categoria":"Casa","hora":"08:00"}],"atrasadas":2,"feitasHoje":1,"totalHoje":2}},
        "bilhetes":{"estado":"ok","dados":{"proximo":{"data":"2026-09-30","hora":"07:42","origem":"Aveiro","destino":"Lisboa","comboio":123,"emCurso":true,"fimEstimado":"10:42","compra":null},"passe":{"dataExpira":null,"diasRestantes":null}}},
        "rto":{"estado":"ok","dados":{"dias":[{"data":"2026-09-28","diaSemana":1,"marca":"T","hoje":false}],"contagem":{"T":2,"C":1}}},
        "peso":{"estado":"indisponivel","dados":null},
        "financas":{"estado":"ok","dados":{"proximas":[{"id":1,"descricao":"Luz","valor":45.5,"categoria":"Casa","diasAte":3,"vencida":false}],"vencidas":0,"total":1,"valorTotal":45.5}},
        "compras":{"estado":"desativado","dados":null},
        "calendario":{"estado":"nao_ligado","dados":null},
        "email":{"estado":"ok","dados":{"porLer":3,"mensagens":[{"de":"Ana","assunto":"Fatura"}],"comProblemas":[{"email":"x@y.pt"}]}}}}
    """)

    @Test fun parseHoje() {
        val h = parseHoje(hoje)
        assertTrue(h.degradado)
        assertEquals("Lixo", h.tarefas.dados!!.hoje[0].nome); assertEquals(2, h.tarefas.dados!!.atrasadas)
        val v = h.bilhetes.dados!!.proximo!!
        assertTrue(v.emCurso); assertNull(v.compra); assertEquals("10:42", v.fimEstimado); assertNull(h.bilhetes.dados!!.passe!!.diasRestantes)
        assertEquals(2, h.rto.dados!!.escritorio); assertEquals("T", h.rto.dados!!.dias[0].marca)
        assertEquals("indisponivel", h.peso.estado); assertNull(h.peso.dados)
        assertEquals(45.5, h.financas.dados!!.valorTotal, 0.001)
        assertTrue(h.compras!!.escondido); assertEquals("nao_ligado", h.calendario.estado); assertFalse(h.calendario.escondido)
        assertEquals(listOf("x@y.pt"), h.email.dados!!.comProblemas)
        assertEquals(listOf("Peso"), h.falhados())          // nao_ligado e desativado não contam como falha
    }

    @Test fun moduloEmFaltaNaoRebenta() {
        val h = parseHoje(JSONObject("""{"estado":"ok","data":"2026-09-29","modulos":{}}"""))
        assertEquals("erro", h.tarefas.estado); assertNull(h.compras)
    }

    @Test fun utilizadorEModulos() {
        val u = parseUtilizador(JSONObject("""{"id":3,"email":"a@b.pt","nome":"Ana","admin":false,"mudarPassword":true}"""))
        assertTrue(u.mudarPassword); assertEquals("Ana", u.nome)
        val m = parseModulos(JSONObject("""{"modulos":[{"id":"peso","nome":"Peso","disponivel":true,"ativo":false}]}"""))
        assertFalse(m[0].ativo)
    }

    @Test fun atualizacao() {
        val j = JSONObject("""{"versionCode":3,"versionName":"0.3.0","url":"pulse-0.3.0.apk","sha256":"ABC","notas":"novo"}""")
        val a = Updater.interpretar(j, 1)!!
        assertEquals("0.3.0", a.versionName); assertEquals("abc", a.sha256); assertTrue(a.url.endsWith("/apk/pulse-0.3.0.apk"))
        assertNull(Updater.interpretar(j, 3))                                   // já tem esta versão
        assertNull(Updater.interpretar(JSONObject("""{"versionCode":9,"url":"https://mau.example/x.apk"}"""), 1))   // só descarrega do servidor do Pulse
    }
}
