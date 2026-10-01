package pt.pereirabmd.pulse.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import org.json.JSONObject
import pt.pereirabmd.pulse.data.*
import pt.pereirabmd.pulse.util.*

private val ABAS = listOf("Resumo", "Gráfico", "Registos", "Configuração")
private val CONTROLO = mapOf("acima" to "Acima do controlo", "abaixo" to "Abaixo do controlo", "dentro" to "Dentro do controlo")

/** Peso (ADR-040): Resumo, Gráfico, Registos e Configuração. Os números vêm calculados do servidor (`GET /weight`). */
@Composable
fun PesoEcra(aoVoltar: () -> Unit) {
    var aba by remember { mutableIntStateOf(0) }
    val c = carga { Api.get("/weight") }
    val acoes = rememberAcoes { c.recarregar() }
    EcraModulo("Peso", aoVoltar) {
        Ao(c, "A carregar o teu peso…") { d ->
            Abas(ABAS, aba) { aba = it }
            Rolar {
                ErroAcao(acoes)
                when (aba) {
                    0 -> ResumoTab(d)
                    1 -> GraficoTab(d)
                    2 -> RegistosTab(d, acoes)
                    else -> ConfigTab(d, acoes)
                }
            }
        }
    }
}

@Composable
private fun Estatistica(rotulo: String, valor: String, nota: String? = null, modifier: Modifier = Modifier) {
    Column(modifier) { Meta(rotulo); Texto(valor, Pulse.card); if (nota != null) Meta(nota) }
}

@Composable
private fun ColumnScope.ResumoTab(d: JSONObject) {
    val r = d.getJSONObject("resumo"); val cfg = d.getJSONObject("config")
    val ultimo = r.obj("ultimo")
    if (ultimo == null) { Bloco { Texto2("Ainda sem registos — regista o teu primeiro peso no separador Registos.") }; return }
    val a = r.getJSONObject("analise"); val prev = r.getJSONObject("previsao"); val anterior = r.obj("anterior")
    val c = Pulse.cores
    Bloco(titulo = "Peso atual") {
        Texto(fmtPeso(ultimo.optDouble("peso")), Pulse.metric)
        Texto2(if (anterior == null) "Primeiro registo." else {
            val dif = anterior.optDouble("diferenca")
            if (Math.abs(dif) < 0.05) "Igual ao registo de ${fmtDataIso(anterior.txtOu("quando"))}"
            else "${if (dif > 0) "↑" else "↓"} ${fmtPeso(Math.abs(dif))} desde ${fmtDataIso(anterior.txtOu("quando"))}"
        })
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            if (r.inteiro("sequenciaDias") >= 2) Pilula("Sequência de ${plural(r.inteiro("sequenciaDias"), "dia", "dias")}")
            if (r.bool("novoMinimo")) Pilula("Novo mínimo", c.success)
            r.txt("controlo")?.let { k -> Pilula(CONTROLO[k] ?: k, if (k == "dentro") c.success else c.warning) }
        }
    }
    Bloco(titulo = "Objetivo") {
        val prog = r.obj("progresso")
        if (prog != null) {
            LinearProgressIndicator(progress = { (prog.optDouble("pct") / 100).toFloat().coerceIn(0f, 1f) }, Modifier.fillMaxWidth().height(8.dp).clip(RoundedCornerShape(50)), color = c.primary, trackColor = c.surface2)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Texto2(fmtPeso(prog.optDouble("inicial"))); Texto2("${Math.round(prog.optDouble("pct"))}%"); Texto2(fmtPeso(prog.optDouble("alvo")))
            }
        } else Texto2("Define um peso alvo em Configuração para veres o progresso.")
        val perdido = r.real("totalPerdido") ?: 0.0
        val ritmo = r.obj("ritmo"); val faltam = r.obj("faltam")
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Estatistica("Total perdido", if (perdido >= 0) fmtPeso(perdido) else "+" + fmtPeso(-perdido), if (perdido < 0) "Mais do que no primeiro registo" else null, Modifier.weight(1f))
            Estatistica("Ritmo semanal", ritmo?.let { (if (it.optDouble("kgSemana") >= 0) "−" else "+") + fmtKg2(Math.abs(it.optDouble("kgSemana"))) } ?: "—",
                ritmo?.let { (if (it.optDouble("kgDia") >= 0) "−" else "+") + fmtDec(Math.abs(it.optDouble("kgDia")), 3) + " kg/dia" }, Modifier.weight(1f))
            Estatistica("Faltam", faltam?.let { if (it.bool("atingido")) "Atingido" else fmtPeso(it.optDouble("kg")) } ?: "—", modifier = Modifier.weight(1f))
        }
        Texto2(when (prev.txt("estado")) {
            "ok" -> prev.txt("data")?.let { "Ao ritmo atual (~${fmtDec(prev.optDouble("kgSemana"), 2)} kg/sem): objetivo previsto para ${fmtDataIso(it)}." } ?: ""
            "atingido" -> "Objetivo já atingido."
            "poucos_registos" -> "Regista mais alguns pesos para veres uma previsão."
            "sem_alvo" -> "Define o peso alvo em Configuração para veres uma previsão de data."
            "sem_tendencia" -> "Sem tendência de perda clara nos últimos registos — sem previsão de data."
            else -> ""
        })
    }
    Bloco(titulo = "Corpo") {
        val imc = r.obj("imc"); val gasto = r.real("gastoDiario")
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Estatistica("IMC", imc?.let { fmtDec(it.optDouble("valor"), 1) } ?: "—", imc?.txt("classe") ?: if (cfg.real("altura") != null) null else "Define a altura em Configuração", Modifier.weight(1f))
            Estatistica("Gasto diário", if (gasto != null && gasto > 0) "${gasto.toInt()} kcal" else "—", if (gasto != null && gasto > 0) null else "Precisa de altura, nascimento e sexo", Modifier.weight(1f))
            Estatistica("Mín / Máx", r.real("minimo")?.let { "${fmtDec(it, 1)} / ${fmtDec(r.optDouble("maximo"), 1)}" } ?: "—", modifier = Modifier.weight(1f))
        }
    }
    Bloco(titulo = "Análise") {
        val itens = buildList {
            a.obj("tendencia")?.let { add("Tendência (${it.optInt("pontos")} registos em ${it.optInt("dias")} dias)" to "${fmtDec(Math.abs(it.optDouble("kgSemana")), 2)} kg/sem de ${if (it.optDouble("kgSemana") <= 0) "perda" else "ganho"}") }
            a.obj("mensal")?.let { add("Evolução mensal" to "${fmtDeltaKg(it.optDouble("diff"))} vs mês anterior") }
            a.obj("melhorSemana")?.let { add("Melhor semana" to fmtDeltaKg(it.optDouble("diff"))) }
            a.obj("piorSemana")?.let { add("Semana mais difícil" to fmtDeltaKg(it.optDouble("diff"))) }
        }
        if (itens.isEmpty()) Texto2("Regista pesos em pelo menos 3 semanas diferentes para veres tendências e comparações aqui.")
        itens.forEach { (n, v) -> Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) { Texto2(n, Modifier.weight(1f)); Texto(v, Pulse.body2) } }
    }
}

private val PERIODOS = listOf("7d" to ("7 d" to 7), "30d" to ("30 d" to 30), "90d" to ("90 d" to 90), "6m" to ("6 m" to 182), "1a" to ("1 a" to 365), "tudo" to ("Tudo" to 0))

@Composable
private fun ColumnScope.GraficoTab(d: JSONObject) {
    var periodo by remember { mutableStateOf("90d") }
    val todos = d.objs("registos").map { Ponto(instante(it.txtOu("quando")), it.optDouble("peso")) }
    val dias = PERIODOS.first { it.first == periodo }.second.second
    val fim = todos.lastOrNull()?.t ?: 0L
    val pontos = if (dias == 0) todos else todos.filter { it.t >= fim - dias * 86_400_000L }
    val alvo = d.getJSONObject("config").real("pesoAlvo")
    fun iso(t: Long) = java.time.Instant.ofEpochMilli(t).atZone(java.time.ZoneId.systemDefault()).toLocalDate().toString()
    val resumo = if (pontos.isNotEmpty()) "Evolução do peso: ${pontos.size} registos, de ${fmtPeso(pontos.first().v)} em ${fmtDataIso(iso(pontos.first().t))} a ${fmtPeso(pontos.last().v)} em ${fmtDataIso(iso(pontos.last().t))}." else "Sem registos neste período."
    Escolha(PERIODOS.map { it.first to it.second.first }, periodo, { periodo = it })          // 6 períodos repartem a largura (como chips cortavam o «Tudo»)
    Bloco(titulo = "Evolução do peso") {
        GraficoLinha(pontos, mediaMovel(pontos), alvo, resumo)
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Meta("● Peso"); Meta("● Média de 7 dias"); if (alvo != null) Meta("- - Alvo (${fmtPeso(alvo)})")
        }
    }
}

@Composable
private fun ColumnScope.RegistosTab(d: JSONObject, acoes: Acoes) {
    val avisos = LocalAvisos.current
    val registos = d.objs("registos").reversed()          // o mais recente primeiro
    var texto by remember { mutableStateOf(d.getJSONObject("resumo").obj("ultimo")?.optDouble("peso")?.let { decimalTexto(it) } ?: "") }
    var nota by remember { mutableStateOf("") }
    var cid by remember { mutableStateOf(novoCid()) }
    var editar by remember { mutableStateOf<JSONObject?>(null) }
    val valor = lerPesoKg(texto)
    Bloco(titulo = "Registar peso") {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.Bottom) {
            Campo("Peso (kg)", texto, { texto = it }, Modifier.weight(1f), teclado = TecladoNumero, erro = if (texto.isNotEmpty() && valor == null) "Entre 1 e 1000." else null)
        }
        Campo("Nota (opcional)", nota, { nota = it.take(500) })
        Botao("Registar", {
            acoes.executar("novo", "peso.registar", jo("peso" to valor, "nota" to nota.trim(), "cid" to cid)) { cid = novoCid(); nota = ""; avisos.mostrar("Peso registado.") }
        }, grande = true, ativo = valor != null && acoes.ocupado == null, carregando = acoes.ocupado == "novo")
    }
    Bloco(titulo = "Registos  ${registos.size}") {
        if (registos.isEmpty()) Texto2("Ainda sem registos.")
        registos.take(200).forEach { r ->
            Row(Modifier.fillMaxWidth().clickable { editar = r }, verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) { Texto(fmtPeso(r.optDouble("peso"))); Meta("${fmtDataIso(r.txtOu("quando"))} · ${r.txtOu("quando").drop(11).take(5)}${r.txtOu("nota").let { if (it.isNotEmpty()) " · $it" else "" }}") }
                LinkBtn("Editar", { editar = r })
            }
        }
        if (registos.size > 200) Meta("A mostrar os 200 mais recentes.")
    }
    editar?.let { r -> FolhaRegisto(r, acoes, avisos) { editar = null } }
}

private fun lerPesoKg(t: String): Double? = lerDecimal(t)?.takeIf { it in 1.0..1000.0 }?.let { Math.round(it * 100) / 100.0 }

@Composable
private fun FolhaRegisto(r: JSONObject, acoes: Acoes, avisos: Avisos, aoFechar: () -> Unit) {
    var data by remember { mutableStateOf(r.txtOu("quando").take(10)) }
    var hora by remember { mutableStateOf(r.txtOu("quando").drop(11).take(5)) }
    var texto by remember { mutableStateOf(decimalTexto(r.optDouble("peso"))) }
    var nota by remember { mutableStateOf(r.txtOu("nota")) }
    var apagar by remember { mutableStateOf(false) }
    val valor = lerPesoKg(texto)
    Folha("Editar registo", aoFechar) {
        CampoData("Data", data, { data = it })
        CampoHora("Hora", hora, { hora = it }, opcional = false)
        Campo("Peso (kg)", texto, { texto = it }, teclado = TecladoNumero, erro = if (valor == null) "Entre 1 e 1000." else null)
        Campo("Nota", nota, { nota = it.take(500) })
        ErroAcao(acoes)
        Botao("Guardar", {
            acoes.executar("ed", "peso.editar", jo("registo" to r.getInt("id"), "quando" to "$data $hora:00", "peso" to valor, "nota" to nota.trim())) { aoFechar(); avisos.mostrar("Registo atualizado.") }
        }, grande = true, ativo = valor != null && data.isNotEmpty() && hora.length == 5 && acoes.ocupado == null, carregando = acoes.ocupado == "ed")
        LinkBtn("Eliminar registo", { apagar = true })
    }
    if (apagar) Confirmar("Eliminar registo", "Eliminar o registo de ${fmtDataIso(r.txtOu("quando"))}?", "Eliminar", true, {
        apagar = false
        acoes.executar("del", "peso.eliminar", jo("registo" to r.getInt("id")), true) {
            aoFechar()
            avisos.mostrar("Registo eliminado.") { acoes.executar("desfazer", "peso.registar", jo("peso" to r.optDouble("peso"), "quando" to r.txt("quando"), "nota" to r.txtOu("nota"))) }
        }
    }, { apagar = false })
}

private val DIAS = listOf("Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo")
private val ATIVIDADES = listOf(1.2 to "Pouco ativo", 1.45 to "Moderadamente ativo", 1.7 to "Muito ativo")

@Composable
private fun ColumnScope.ConfigTab(d: JSONObject, acoes: Acoes) {
    val avisos = LocalAvisos.current
    val c = d.getJSONObject("config")
    var altura by remember { mutableStateOf(c.real("altura")?.let { decimalTexto(it) } ?: "") }
    var nasc by remember { mutableStateOf(c.txt("nascimento") ?: "") }
    var sexo by remember { mutableStateOf(c.txt("sexo") ?: "") }
    var alvo by remember { mutableStateOf(c.real("pesoAlvo")?.let { decimalTexto(it) } ?: "") }
    var ativ by remember { mutableStateOf(normalizarAtividade(c.real("atividade"))) }
    var dia by remember { mutableIntStateOf(c.inteiro("diaControlo")) }
    var pmin by remember { mutableStateOf(c.real("pesoMin")?.let { decimalTexto(it) } ?: "") }
    var pmax by remember { mutableStateOf(c.real("pesoMax")?.let { decimalTexto(it) } ?: "") }
    var erro by remember { mutableStateOf<String?>(null) }
    fun num(t: String) = if (t.isBlank()) null else lerDecimal(t) ?: Double.NaN

    ErroLocal(erro)
    Bloco(titulo = "Corpo") {
        Campo("Altura (cm)", altura, { altura = it }, teclado = TecladoNumero)
        CampoData("Data de nascimento", nasc, { nasc = it }, opcional = true)
        Seletor("Sexo", listOf("" to "—", "M" to "Masculino", "F" to "Feminino"), sexo, { sexo = it })
        Seletor("Nível de atividade", ATIVIDADES.map { it.first to it.second }, ativ, { ativ = it })
    }
    Bloco(titulo = "Objetivo de peso") {
        Campo("Peso alvo (kg)", alvo, { alvo = it }, teclado = TecladoNumero)
        Campo("Peso mínimo de controlo (kg)", pmin, { pmin = it }, teclado = TecladoNumero)
        Campo("Peso máximo de controlo (kg)", pmax, { pmax = it }, teclado = TecladoNumero)
        Seletor("Dia de controlo", DIAS.mapIndexed { i, n -> i to n }, dia, { dia = it })
    }
    ErroAcao(acoes)
    Botao("Guardar configuração", {
        val v = mapOf("Altura" to num(altura), "Peso alvo" to num(alvo), "Peso mínimo" to num(pmin), "Peso máximo" to num(pmax))
        val mau = v.entries.firstOrNull { (_, x) -> x != null && (x.isNaN() || x <= 0) }
        val mn = v["Peso mínimo"]; val mx = v["Peso máximo"]
        if (mau != null) { erro = "Valor inválido em ${mau.key}."; return@Botao }
        if (mn != null && mx != null && mn > mx) { erro = "O peso mínimo não pode ser maior do que o máximo."; return@Botao }
        erro = null
        acoes.executar("config", "peso.configurar", jo("altura" to v["Altura"], "pesoAlvo" to v["Peso alvo"], "pesoMin" to mn, "pesoMax" to mx,
            "nascimento" to nasc.ifEmpty { null }, "sexo" to sexo.ifEmpty { null }, "atividade" to ativ, "diaControlo" to dia)) { avisos.mostrar("Configuração guardada.") }
    }, grande = true, ativo = acoes.ocupado == null, carregando = acoes.ocupado == "config")
}

@Composable
private fun ErroLocal(erro: String?) { if (erro != null) Aviso(TipoAviso.ERRO, erro) }
