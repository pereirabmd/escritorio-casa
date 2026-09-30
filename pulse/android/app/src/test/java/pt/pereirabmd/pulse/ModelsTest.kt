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

    @Test fun tarefasComPiscinaESaidaDoAluno() {
        val j = JSONObject("""{"estado":"ok","data":"2026-09-30","modulos":{"tarefas":{"estado":"ok","dados":{"hoje":[],"atrasadas":0,"feitasHoje":0,"totalHoje":0,
          "piscina":[{"id":"P02","nome":"Testar pH e cloro","nota":"","estado":"atrasada","ultima":"2026-09-20","proxima":"2026-09-23","diasDesde":10}],
          "horario":{"aluno":"Bruno","entra":"08:30","sai":"16:15","aviso":"15:45"}}}}}""")
        val t = parseHoje(j).tarefas.dados!!
        assertEquals("P02", t.piscina[0].id); assertEquals(10, t.piscina[0].diasDesde); assertEquals("16:15", t.horario!!.sai)
        assertTrue(parseHoje(hoje).tarefas.dados!!.piscina.isEmpty()); assertNull(parseHoje(hoje).tarefas.dados!!.horario)     // servidor antigo: sem os campos novos
    }

    @Test fun ordemDosCartoes() {
        assertEquals(listOf("peso", "tarefas"), parseHoje(JSONObject("""{"estado":"ok","data":"2026-09-30","ordem":["peso","tarefas"],"modulos":{}}""")).ordem)
        assertTrue(parseHoje(hoje).ordem.isEmpty())          // servidor antigo: vale a ordem de origem
    }

    @Test fun atualizacaoParcialSoMudaOsModulosPedidos() {
        val antes = parseHoje(hoje)
        val novo = parseHoje(JSONObject("""{"estado":"ok","data":"2026-09-29","modulos":{"peso":{"estado":"ok","dados":{"registadoHoje":true,"sugestao":80.6,"ultimo":{"quando":"2026-09-29 07:30:00","peso":80.6}}}}}"""))
        val depois = antes.fundir(novo, setOf("peso"))
        assertEquals(80.6, depois.peso.dados!!.ultimoPeso!!, 0.001)
        assertEquals(antes.tarefas, depois.tarefas); assertEquals(antes.financas, depois.financas)       // o resto fica como estava
        assertFalse(depois.degradado)                                                                     // o peso que falhava passou a ok
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
