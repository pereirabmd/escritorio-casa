package pt.pereirabmd.pulse.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import org.json.JSONObject
import pt.pereirabmd.pulse.data.*
import pt.pereirabmd.pulse.util.*
import java.time.LocalDate
import kotlinx.coroutines.launch

private val ABAS = listOf("Calendário", "Ano", "Notas")
private val CATEGORIAS = listOf("Férias", "Astreinte", "RTO Suspensão", "Validação", "Validação Batica")

/** Mapa das datas do JSON: `{ "2026-09-30": "T", … }` -> Map. */
private fun JSONObject.mapa(k: String): Map<String, String> {
    val o = optJSONObject(k) ?: return emptyMap()
    return o.keys().asSequence().associateWith { o.optString(it) }
}
private fun corMarca(classe: String, c: PulseColors): Pair<Color, Color> = when (classe) {      // (fundo, texto)
    "T" -> c.primary.copy(alpha = .22f) to c.primary
    "C" -> c.success.copy(alpha = .22f) to c.success
    "F" -> c.warning.copy(alpha = .22f) to c.warning
    "A" -> c.info.copy(alpha = .22f) to c.info
    "holiday" -> c.surface2 to c.text2
    else -> Color.Transparent to c.text
}

/** RTO (ADR-041): Calendário (toque T→C→vazio), Ano e Notas, com o modo administrador. As regras (quota, saldo) vêm do servidor. */
@Composable
fun RtoEcra(aoVoltar: () -> Unit) {
    val hoje = LocalDate.now()
    var ano by remember { mutableIntStateOf(hoje.year) }
    var mes by remember { mutableIntStateOf(hoje.monthValue - 1) }
    var aba by remember { mutableIntStateOf(0) }
    var admin by remember { mutableStateOf(false) }
    val c = carga(ano) { Api.get("/rto?ano=$ano") }
    val acoes = rememberAcoes { c.recarregar() }
    EcraModulo("RTO", aoVoltar) {
        Ao(c, "A carregar o RTO…") { d ->
            Abas(ABAS, aba) { aba = it }
            Rolar {
                if (admin) Aviso(TipoAviso.AVISO) {
                    Texto("Modo administrador ativo: podes alterar fins de semana, dias e notas já passados, sem restrições.", Pulse.body2)
                    LinkBtn("Desativar", { admin = false })
                }
                ErroAcao(acoes)
                when (aba) {
                    0 -> CalendarioTab(d, acoes, c.recarregar, mes, ano, { a, m -> ano = a; mes = m }, admin) { admin = it }
                    1 -> AnoTab(d) { m -> mes = m; aba = 0 }
                    else -> NotasTab(d, acoes, admin)
                }
            }
        }
    }
}

@Composable
private fun ColumnScope.CalendarioTab(d: JSONObject, acoes: Acoes, atualizar: () -> Unit, mes: Int, ano: Int, irPara: (Int, Int) -> Unit, admin: Boolean, aoAdmin: (Boolean) -> Unit) {
    val avisos = LocalAvisos.current
    val hojeIso = LocalDate.now().toString()
    var escolhido by remember { mutableStateOf<String?>(null) }
    var confirmarAdmin by remember { mutableStateOf(false) }
    var modoFerias by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    // A marca aparece logo ao tocar (o Pi demora alguns segundos a responder): o servidor confirma em segundo plano e, se falhar, a marca volta atrás.
    var otim by remember(d) { mutableStateOf(emptyMap<String, String>()) }
    var pendentes by remember { mutableIntStateOf(0) }
    val dias = d.mapa("dias").toMutableMap().also { m -> otim.forEach { (k, v) -> if (v.isEmpty()) m.remove(k) else m[k] = v } }
    val feriados = d.mapa("feriados"); val marcasNotas = d.mapa("marcasNotas")
    val ferias = d.strs("ferias").toSet()
    val notas = d.objs("notas")
    val prefixo = "%04d-%02d".format(ano, mes + 1)
    val dia = escolhido?.takeIf { it.startsWith(prefixo) }
    val anterior = if (mes == 0) ano - 1 to 11 else ano to mes - 1
    val seguinte = if (mes == 11) ano + 1 to 0 else ano to mes + 1
    val hoje = d.getJSONObject("hoje"); val t = d.getJSONObject("totais")

    fun contar(a: Int, m: Int): Pair<Int, Int> {
        val p = "%04d-%02d-".format(a, m + 1); var tt = 0; var cc = 0
        dias.forEach { (data, v) -> if (data.startsWith(p) && data !in ferias) { if (v == "T") tt++ else cc++ } }
        return tt to cc
    }
    val atual = contar(ano, mes); val ant = contar(anterior.first, anterior.second)
    fun dif(n: Int) = if (n == 0) "sem alteração" else "${if (n > 0) "↑" else "↓"} ${plural(Math.abs(n), "dia", "dias")}"

    fun tocar(data: String) {
        escolhido = data
        if (!admin && diaBloqueado(data, hojeIso)) { avisos.mostrar("Fim de semana ou dia já passado: ativa o modo administrador para o alterar."); return }
        if (modoFerias) {
            if (acoes.ocupado != null) return
            val era = data in ferias
            acoes.executar("ferias-$data", "rto.ferias_dia", jo("data" to data, "admin" to admin)) {
                avisos.mostrar(if (era) "Dia de férias removido." else "Dia marcado como férias.") { acoes.executar("ferias-$data", "rto.ferias_dia", jo("data" to data, "admin" to admin)) }
            }
            return
        }
        if (data in ferias) { avisos.mostrar("Dia de férias: liga «Férias» para o remover."); return }
        val nova = proximaMarca(dias[data])
        otim = otim + (data to nova); pendentes++
        scope.launch {
            try { Api.post("/actions/rto.marcar_dia", jo("params" to jo("data" to data, "marca" to nova, "admin" to admin))) }
            catch (e: Exception) { if (e is kotlinx.coroutines.CancellationException) throw e; otim = otim - data; acoes.erro = mensagemDeErro(e) }
            finally { pendentes--; if (pendentes == 0) atualizar() }
        }
    }

    Bloco(titulo = "Hoje: ${textoHoje(hoje.txtOu("estado"))}${if (hoje.txt("estado") == "feriado" && !hoje.txt("nome").isNullOrEmpty()) " — ${hoje.txt("nome")}" else ""}") {
        val pm = d.obj("proximaMudanca")
        val extra = if (hoje.bool("astreinte") && hoje.txt("estado") != "astreinte") "Astreinte" else if (pm != null) textoProximaMudanca(pm.txtOu("tipo"), pm.inteiro("dias"), pm.txt("nome")) else ""
        if (extra.isNotEmpty()) Texto2(extra)
    }
    Bloco(titulo = "Calendário") {
        Escolha(listOf(false to "Normal", true to "Administrador"), admin || confirmarAdmin, { querAdmin -> if (!querAdmin) { aoAdmin(false); confirmarAdmin = false } else if (!admin) confirmarAdmin = true })
        Meta(if (admin) "Sem restrições de data" else "Fins de semana e dias passados bloqueados")
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            LinkBtn("‹", { irPara(anterior.first, anterior.second) })
            Texto("${nomeMes(mes)} $ano", Pulse.card, modifier = Modifier.weight(1f), alinhar = TextAlign.Center)
            LinkBtn("Hoje", { val h = LocalDate.now(); irPara(h.year, h.monthValue - 1); escolhido = h.toString() })
            LinkBtn("›", { irPara(seguinte.first, seguinte.second) })
        }
        Row(Modifier.fillMaxWidth()) { DIAS_SEMANA_LETRA.forEach { Meta(it, Modifier.weight(1f).wrapContentWidth(Alignment.CenterHorizontally)) } }
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            semanasDoMes(ano, mes).forEach { semana ->
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    semana.forEachIndexed { j, data ->
                        if (data == null) { Spacer(Modifier.weight(1f).height(46.dp)); return@forEachIndexed }
                        val (texto, classe) = marcaDaCelula(dias[data] ?: "", data in feriados, if (data in dias) "" else marcasNotas[data] ?: "")
                        val (fundo, tinta) = corMarca(classe, Pulse.cores)
                        val info = notas.any { n -> intervaloNota(n.txt("dataInicio"), n.txt("dataFim"))?.let { it.first <= data && data <= it.second } == true } || data in feriados
                        Column(Modifier.weight(1f).height(46.dp).clip(RoundedCornerShape(8.dp)).background(fundo)
                            .then(if (data == hojeIso) Modifier.border(2.dp, Pulse.cores.primary, RoundedCornerShape(8.dp)) else if (dia == data) Modifier.border(1.5.dp, Pulse.cores.text2, RoundedCornerShape(8.dp))
                            else if (fundo == Color.Transparent) Modifier.border(1.dp, Pulse.cores.line, RoundedCornerShape(8.dp)) else Modifier)
                            .clickable { tocar(data) }, horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                            Text(data.takeLast(2).toInt().toString(), style = Pulse.meta, color = if (j >= 5) Pulse.cores.text2 else Pulse.cores.text)
                            Text(texto.ifEmpty { if (info) "·" else " " }, style = Pulse.card, color = tinta)
                        }
                    }
                }
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Filtros(listOf(true to "Férias"), if (modoFerias) true else false) { modoFerias = !modoFerias }
            Meta(if (modoFerias) "Toca num dia para marcar ou tirar férias (F)" else "Toca num dia: T → C → vazio")
        }
        Meta("T · Escritório   C · Casa   F · Férias   A · Astreinte   f · Feriado")
        if (dia != null) {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Texto(fmtDataLonga(java.util.Calendar.getInstance().apply { time = java.sql.Date.valueOf(dia) }), Pulse.card)
                if (dia in feriados) Texto2("Feriado — ${feriados[dia]}")
                notas.filter { n -> intervaloNota(n.txt("dataInicio"), n.txt("dataFim"))?.let { it.first <= dia && dia <= it.second } == true }
                    .forEach { n -> Texto2("${n.txt("categoria").orEmpty().ifEmpty { "Nota" }}${n.txt("descricao").orEmpty().let { if (it.isNotEmpty()) " — $it" else "" }}") }
                if (dia in ferias) Meta("Dia de férias: não conta para o RTO.")
            }
        }
    }
    if (ant.first + ant.second > 0) Bloco(titulo = "${if (ano == LocalDate.now().year && mes == LocalDate.now().monthValue - 1) "Este mês" else nomeMes(mes)} vs ${nomeMes(anterior.second)}") {
        LinhaValor("Escritório", dif(atual.first - ant.first)); LinhaValor("Casa", dif(atual.second - ant.second))
    }
    Totais(d, t)
    if (confirmarAdmin && !admin) Confirmar("Ativar o modo administrador?", "Vais poder alterar qualquer registo, incluindo dias e notas já passados e fins de semana, sem restrições.", "Ativar",
        aoConfirmar = { aoAdmin(true); confirmarAdmin = false }, aoCancelar = { confirmarAdmin = false })
}

@Composable
private fun Totais(d: JSONObject, t: JSONObject) {
    fun num(v: Double) = if (v % 1.0 == 0.0) v.toLong().toString() else v.toString().replace('.', ',')
    val cores = Pulse.cores
    fun tier(v: Double) = if (v < 0) cores.error else if (v <= 10) cores.warning else cores.success
    Bloco(titulo = "Totais de ${d.inteiro("ano")}") {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Column(Modifier.weight(1f)) { Meta("Escritório"); Texto(t.inteiro("T").toString(), Pulse.card) }
            Column(Modifier.weight(1f)) { Meta("Casa"); Texto(t.inteiro("C").toString(), Pulse.card); Meta("${t.optDouble("pctQuota").let { num(it) }}% da quota anual") }
            Column(Modifier.weight(1f)) { Meta("Quota até hoje"); Texto(num(t.optDouble("quotaProRata")), Pulse.card); Meta("de ${t.inteiro("quotaAnual")} por ano") }
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Column(Modifier.weight(1f)) { Meta("Saldo"); Texto(num(t.optDouble("saldo")), Pulse.metric, tier(t.optDouble("saldo"))) }
            Column(Modifier.weight(1f)) { Meta("Saldo condicional"); Texto(num(t.optDouble("saldoCondicional")), Pulse.metric, tier(t.optDouble("saldoCondicional"))) }
        }
        var ver by remember { mutableStateOf(false) }
        LinkBtn(if (ver) "Esconder o cálculo do saldo" else "Como se calcula o saldo", { ver = !ver })
        if (ver) {
            LinhaValor("Dias em casa (marcados)", "${t.inteiro("C")}")
            LinhaValor("Astreinte (crédito de 1 dia cada)", "−${t.inteiro("creditosAstreinte")}")
            LinhaValor("Dias em casa (ajustado)", "${t.inteiro("CCondicional")}")
            LinhaValor("Dias decorridos do ano", "${t.inteiro("decorridos")} de ${t.inteiro("diasAno")}")
            LinhaValor("Quota pro-rata", "${t.inteiro("quotaAnual")} × ${t.inteiro("decorridos")}/${t.inteiro("diasAno")} = ${num(t.optDouble("quotaProRata"))}")
            LinhaValor("Saldo", "${num(t.optDouble("quotaProRata"))} − ${t.inteiro("C")} = ${num(t.optDouble("saldo"))}")
            LinhaValor("Saldo condicional", "${num(t.optDouble("quotaProRata"))} − ${t.inteiro("CCondicional")} = ${num(t.optDouble("saldoCondicional"))}")
            Meta("Dias de férias nunca contam. Durante a «RTO suspensão» os dias em casa não contam no saldo condicional.")
        }
    }
}

@Composable
private fun ColumnScope.AnoTab(d: JSONObject, abrirMes: (Int) -> Unit) {
    val ano = d.inteiro("ano"); val dias = d.mapa("dias"); val feriados = d.mapa("feriados"); val marcasNotas = d.mapa("marcasNotas")
    val mensal = d.objs("mensal")
    Texto2("Visão de $ano. Toca num mês para o abrir no calendário.")
    (0..11).chunked(2).forEach { par ->
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            par.forEach { m ->
                val r = mensal.getOrNull(m)
                Column(Modifier.weight(1f).clip(RoundedCornerShape(Pulse.rM)).background(Pulse.cores.surface).border(1.dp, Pulse.cores.line, RoundedCornerShape(Pulse.rM)).clickable { abrirMes(m) }.padding(10.dp),
                    verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Texto(MESES_NOME[m], Pulse.card)
                    semanasDoMes(ano, m).forEach { sem ->
                        Row(horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                            sem.forEach { data ->
                                val classe = if (data == null) "" else marcaDaCelula(dias[data] ?: "", data in feriados, if (data in dias) "" else marcasNotas[data] ?: "").second
                                val cor = if (data == null) Color.Transparent else if (classe.isEmpty()) Pulse.cores.surface2 else corMarca(classe, Pulse.cores).second
                                Box(Modifier.weight(1f).height(8.dp).clip(RoundedCornerShape(2.dp)).background(cor))
                            }
                        }
                    }
                    Meta("${r?.inteiro("t") ?: 0} T · ${r?.inteiro("c") ?: 0} C")
                }
            }
        }
    }
}

private fun intervaloTexto(n: JSONObject): String {
    val iv = intervaloNota(n.txt("dataInicio"), n.txt("dataFim")) ?: return "Sem data"
    return if (iv.first == iv.second) fmtDataIso(iv.first) else "${fmtDataIso(iv.first)} a ${fmtDataIso(iv.second)}"
}

@Composable
private fun ColumnScope.NotasTab(d: JSONObject, acoes: Acoes, admin: Boolean) {
    val avisos = LocalAvisos.current
    var verTodas by remember { mutableStateOf(false) }
    var editar by remember { mutableStateOf<JSONObject?>(null) }
    var nova by remember { mutableStateOf(false) }
    var gerar by remember { mutableStateOf(false) }
    val ano = d.inteiro("ano").toString()
    val notas = d.objs("notas").filter { n -> verTodas || listOf(n.txt("dataInicio"), n.txt("dataFim")).any { it?.startsWith(ano) == true } }
        .sortedWith(compareBy({ intervaloNota(it.txt("dataInicio"), it.txt("dataFim"))?.first ?: "9999" }, { it.optInt("id") }))
    if (!admin) Meta("Notas em datas já passadas só se criam, alteram ou apagam no modo administrador (separador Calendário).")
    Botao("Nova nota", { nova = true }, pequeno = true)
    Bloco(titulo = "Notas de ${if (verTodas) "todos os anos" else ano}  ${notas.size}", extra = { LinkBtn(if (verTodas) "Só $ano" else "Ver todas", { verTodas = !verTodas }) }) {
        if (notas.isEmpty()) Texto2("Sem notas.")
        notas.take(300).forEach { n ->
            Row(Modifier.fillMaxWidth().clickable { editar = n }, verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Texto((n.txt("categoria").orEmpty().ifEmpty { "Nota" }) + n.txt("descricao").orEmpty().let { if (it.isNotEmpty()) " — $it" else "" }); Meta(intervaloTexto(n))
                }
                LinkBtn("Editar", { editar = n })
            }
        }
        if (notas.size > 300) Meta("A mostrar as 300 primeiras.")
    }
    Bloco(titulo = "Validações periódicas") {
        Texto2("Cria uma validação de 14 em 14 dias, alternando os dois tipos, a partir de uma conhecida.")
        Botao("Gerar validações", { gerar = true }, variante = Variante.SECUNDARIO, pequeno = true)
    }
    if (nova) FolhaNota(null, acoes, avisos, admin) { nova = false }
    editar?.let { FolhaNota(it, acoes, avisos, admin) { editar = null } }
    if (gerar) FolhaGerar(acoes, avisos) { gerar = false }
}

@Composable
private fun FolhaNota(nota: JSONObject?, acoes: Acoes, avisos: Avisos, admin: Boolean, aoFechar: () -> Unit) {
    var inicio by remember { mutableStateOf(nota?.txt("dataInicio").orEmpty()) }
    var fim by remember { mutableStateOf(nota?.txt("dataFim").orEmpty()) }
    var categoria by remember { mutableStateOf(nota?.txt("categoria").orEmpty()) }
    var descricao by remember { mutableStateOf(nota?.txt("descricao").orEmpty()) }
    var erro by remember { mutableStateOf<String?>(null) }
    var apagar by remember { mutableStateOf(false) }
    Folha(if (nota == null) "Nova nota" else "Editar nota", aoFechar) {
        erro?.let { Aviso(TipoAviso.ERRO, it) }
        CampoData("Data de início", inicio, { inicio = it }, opcional = true)
        CampoData("Data de fim", fim, { fim = it }, opcional = true)
        Seletor("Categoria (sugestões)", CATEGORIAS.map { it to it }, categoria.takeIf { it in CATEGORIAS }, { categoria = it }, vazio = "Escolher uma sugestão")
        Campo("Categoria", categoria, { categoria = it.take(100) })
        Campo("Descrição", descricao, { descricao = it.take(500) })
        ErroAcao(acoes)
        Botao(if (nota == null) "Adicionar nota" else "Guardar alterações", {
            if (inicio.isEmpty() && fim.isEmpty() && categoria.isBlank() && descricao.isBlank()) { erro = "A nota não pode estar vazia."; return@Botao }
            if (inicio.isNotEmpty() && fim.isNotEmpty() && fim < inicio) { erro = "A data de fim é anterior à de início."; return@Botao }
            erro = null
            val corpo = jo("inicio" to inicio.ifEmpty { null }, "fim" to fim.ifEmpty { null }, "categoria" to categoria.trim(), "descricao" to descricao.trim(), "admin" to admin)
            if (nota == null) acoes.executar("nota", "rto.nota_criar", corpo) { aoFechar(); avisos.mostrar("Nota criada.") }
            else { corpo.put("nota", nota.getInt("id")); acoes.executar("nota", "rto.nota_editar", corpo) { aoFechar(); avisos.mostrar("Nota atualizada.") } }
        }, grande = true, ativo = acoes.ocupado == null, carregando = acoes.ocupado == "nota")
        if (nota != null) LinkBtn("Eliminar nota", { apagar = true })
    }
    if (apagar && nota != null) Confirmar("Eliminar nota", "Eliminar esta nota?", "Eliminar", true, {
        apagar = false
        acoes.executar("del", "rto.nota_eliminar", jo("nota" to nota.getInt("id"), "admin" to admin), true) {
            aoFechar()
            avisos.mostrar("Nota eliminada.") {
                acoes.executar("desfazer", "rto.nota_restaurar", jo("nota" to nota.getInt("id"), "inicio" to nota.txt("dataInicio"), "fim" to nota.txt("dataFim"),
                    "categoria" to nota.txtOu("categoria"), "descricao" to nota.txtOu("descricao"), "admin" to true))
            }
        }
    }, { apagar = false })
}

@Composable
private fun FolhaGerar(acoes: Acoes, avisos: Avisos, aoFechar: () -> Unit) {
    var ref by remember { mutableStateOf("") }; var ate by remember { mutableStateOf("") }; var tipo by remember { mutableStateOf("Validação") }
    var erro by remember { mutableStateOf<String?>(null) }
    Folha("Gerar validações", aoFechar) {
        Texto2("Cria uma validação de 14 em 14 dias, alternando os dois tipos, a partir de uma conhecida.")
        erro?.let { Aviso(TipoAviso.ERRO, it) }
        CampoData("Data de uma validação conhecida", ref, { ref = it })
        Seletor("Tipo dessa validação", listOf("Validação" to "Normal", "Validação Batica" to "Batica"), tipo, { tipo = it })
        CampoData("Gerar até", ate, { ate = it })
        ErroAcao(acoes)
        Botao("Gerar validações", {
            if (ref.isEmpty() || ate.isEmpty()) { erro = "Preenche a data de referência e a data limite."; return@Botao }
            if (ate < ref) { erro = "A data limite tem de ser depois da data de referência."; return@Botao }
            erro = null
            acoes.executar("gerar", "rto.gerar_validacoes", jo("referencia" to ref, "ate" to ate, "tipo" to tipo)) { r ->
                aoFechar(); avisos.mostrar("${r.inteiro("criadas")} validações criadas${if (r.inteiro("existentes") > 0) " (${r.inteiro("existentes")} já existiam)" else ""}.")
            }
        }, grande = true, ativo = acoes.ocupado == null, carregando = acoes.ocupado == "gerar")
    }
}
