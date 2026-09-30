package pt.pereirabmd.pulse.ui

import androidx.compose.foundation.layout.*
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import org.json.JSONObject
import pt.pereirabmd.pulse.data.*
import pt.pereirabmd.pulse.util.*

private val ABAS = listOf("Semana", "Bilhetes", "Pedidos", "Registo")

/** Bilhetes CP (ADR-046): Semana (próximo comboio, passe, editor), Bilhetes, Pedidos e Registo. As regras vivem no servidor e no Pi. */
@Composable
fun BilhetesEcra(aoVoltar: () -> Unit) {
    var aba by remember { mutableIntStateOf(0) }
    var semana by remember { mutableStateOf<String?>(null) }          // null = a próxima semana (o servidor sabe qual é)
    val c = carga(semana) { Api.get("/tickets" + (semana?.let { "?semana=$it" } ?: "")) }
    val acoes = rememberAcoes { c.recarregar() }
    EcraModulo("Bilhetes CP", aoVoltar) {
        Ao(c, "A carregar os bilhetes…") { d ->
            Abas(ABAS, aba) { aba = it }
            Rolar {
                ErroAcao(acoes)
                when (aba) {
                    0 -> SemanaTab(d, { semana = it }, acoes)
                    1 -> BilhetesTab(d)
                    2 -> PedidosTab(d, acoes)
                    else -> RegistoTab(d)
                }
            }
        }
    }
}

@Composable
private fun EstadoViagem(v: JSONObject) {
    val e = v.txtOu("estado"); val c = Pulse.cores
    val txt = (ESTADO_VIAGEM[e] ?: e) + if (e == "em_curso") " · chega por volta das ${v.txtOu("fimEstimado")}" else ""
    Pilula(txt, when (e) { "comprado" -> c.success; "em_curso" -> c.warning; else -> c.text2 }, if (e == "em_curso") c.warningBg else c.surface2)
}

@Composable
private fun ColumnScope.SemanaTab(d: JSONObject, irParaSemana: (String) -> Unit, acoes: Acoes) {
    var editar by remember { mutableStateOf(false) }
    val semana = d.getJSONObject("semana"); val seguinte = d.getJSONObject("semanaSeguinte")
    val viagens = semana.objs("viagens"); val inicio = semana.getString("inicio")
    val ativas = viagens.count { it.bool("ativo") }
    if (seguinte.inteiro("ativas") == 0) Aviso(TipoAviso.AVISO) {
        Texto("Falta configurar a semana de ${intervaloSemana(seguinte.getString("inicio"))}.", Pulse.body2)
        LinkBtn("Configurar", { irParaSemana(seguinte.getString("inicio")); editar = true })
    }
    d.obj("proxima")?.let { v ->
        Bloco(titulo = if (v.txt("estado") == "em_curso") "Em viagem" else "Próximo comboio") {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                Texto(v.txtOu("hora"), Pulse.section); Texto(v.txtOu("origem")); Icon(Icone.SETA, Pulse.cores.text2, 16.dp); Texto(v.txtOu("destino"))
            }
            Texto2("${diaCurto(v.txtOu("data"))} · Comboio ${v.inteiro("comboio")}"); EstadoViagem(v)
            v.obj("compra")?.let { k -> Texto2("Carruagem ${k.txtOu("carruagem")}, lugar ${k.txtOu("lugar")}${k.txtOu("referencia").let { if (it.isNotEmpty()) " · ref. $it" else "" }}") }
        }
    }
    Passe(d, acoes)
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        LinkBtn("‹", { editar = false; irParaSemana(somarDias(inicio, -7)) })
        Texto(intervaloSemana(inicio), Pulse.card, modifier = Modifier.weight(1f), alinhar = TextAlign.Center)
        LinkBtn("›", { editar = false; irParaSemana(somarDias(inicio, 7)) })
    }
    Bloco(titulo = "Viagens  $ativas ativas", extra = { Botao("Configurar semana", { editar = true }, Modifier, Variante.SECUNDARIO, pequeno = true) }) {
        if (viagens.isEmpty()) Texto2("Sem viagens nesta semana.")
        viagens.forEach { v ->
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Texto("${diaCurto(v.txtOu("data"))} · ${v.txtOu("hora")}", Pulse.body, if (v.bool("ativo")) Pulse.cores.text else Pulse.cores.text2); EstadoViagem(v)
                }
                Meta("${v.txtOu("origem")} → ${v.txtOu("destino")} · comboio ${v.inteiro("comboio")}" + (v.obj("compra")?.let { " · carruagem ${it.txtOu("carruagem")}, lugar ${it.txtOu("lugar")}" } ?: ""))
            }
        }
    }
    if (editar) FolhaSemana(d, acoes) { editar = false }
}

@Composable
private fun Passe(d: JSONObject, acoes: Acoes) {
    val avisos = LocalAvisos.current
    val p = d.getJSONObject("passe"); val hoje = d.getString("hoje")
    var editar by remember { mutableStateOf(false) }
    var data by remember { mutableStateOf(p.txt("dataUltimaCompra") ?: hoje) }
    val dias = p.inteiroOuNull("diasRestantes"); val estado = p.txtOu("estado")
    val texto = when {
        estado == "sem_data" || dias == null -> "Indica a data do último carregamento para receberes o aviso antes de expirar."
        dias < 0 -> "Expirou a ${diaMes(p.txtOu("dataExpira"))}"
        dias == 0 -> "Expira hoje"
        else -> "Válido até ${diaMes(p.txtOu("dataExpira"))} (${fmtDias(dias)})"
    }
    Bloco(titulo = "Passe Verde", extra = { if (dias != null) Meta(plural(maxOf(dias, 0), "dia", "dias")) }) {
        p.real("percentagem")?.let { LinearProgressIndicator(progress = { (it / 100).toFloat().coerceIn(0f, 1f) }, Modifier.fillMaxWidth().height(8.dp).clip(RoundedCornerShape(50)), color = Pulse.cores.primary, trackColor = Pulse.cores.surface2) }
        Texto(texto + if (estado == "a_expirar") " Renova na App CP e atualiza a data aqui." else "", Pulse.body2, if (estado == "expirado" || estado == "a_expirar") Pulse.cores.error else Pulse.cores.text2)
        Botao("Atualizar carregamento", { editar = true }, variante = Variante.SECUNDARIO, pequeno = true)
    }
    if (editar) Folha("Atualizar passe", { editar = false }) {
        CampoData("Data do último carregamento", data, { data = it })
        ErroAcao(acoes)
        Botao("Guardar", { acoes.executar("passe", "bilhetes.passe", jo("dataUltimaCompra" to data)) { editar = false; avisos.mostrar("Passe atualizado.") } },
            grande = true, ativo = data.isNotEmpty() && data <= somarDias(hoje, 1) && acoes.ocupado == null, carregando = acoes.ocupado == "passe")
    }
}

@Composable
private fun FolhaSemana(d: JSONObject, acoes: Acoes, aoFechar: () -> Unit) {
    val avisos = LocalAvisos.current
    val semana = d.getJSONObject("semana"); val estacoes = d.strs("estacoes"); val hoje = d.getString("hoje")
    val historico = d.objs("historico")
    var dias by remember { mutableStateOf(diasParaEditor(semana.strs("dias"), semana.objs("viagens"), hoje)) }
    var erros by remember { mutableStateOf<List<List<String>>>(emptyList()) }
    fun mudar(i: Int, f: (DiaEd) -> DiaEd) { dias = dias.mapIndexed { k, x -> if (k == i) f(x) else x } }
    val origemPadrao = estacoes.getOrElse(0) { "" }; val destinoPadrao = estacoes.getOrElse(1) { "" }
    Folha("Configurar ${intervaloSemana(semana.getString("inicio"))}", aoFechar) {
        Meta("A compra automática faz-se no dia anterior, à hora da viagem. Os dias que já passaram não se alteram.")
        dias.forEachIndexed { i, dia ->
            Bloco {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Texto(diaCurto(dia.data) + if (dia.passado) " · passou" else "", Pulse.body, if (dia.passado) Pulse.cores.text2 else Pulse.cores.text, Modifier.weight(1f))
                    if (dia.viagens.isNotEmpty() && !dia.passado) { Meta("Ativo"); Spacer(Modifier.width(6.dp)); androidx.compose.material3.Switch(dia.ativo, { v -> mudar(i) { it.copy(ativo = v) } },
                        colors = androidx.compose.material3.SwitchDefaults.colors(checkedTrackColor = Pulse.cores.primary)) }
                }
                dia.viagens.forEachIndexed { k, v ->
                    fun atual(f: (LinhaEd) -> LinhaEd) = mudar(i) { x -> x.copy(viagens = x.viagens.mapIndexed { j, y -> if (j == k) f(y) else y }) }
                    fun opcoes(sel: String) = (if (sel.isNotEmpty() && sel !in estacoes) estacoes + sel else estacoes).map { it to it }
                    if (dia.passado) Meta("${v.origem} → ${v.destino} · comboio ${v.comboio} · ${v.hora}")
                    else Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        if (historico.isNotEmpty()) Seletor("Comboios que já usei (viagem ${k + 1})", historico.mapIndexed { n, h -> n to "${h.inteiro("comboio")} — ${h.txtOu("origem")} → ${h.txtOu("destino")} (${h.txtOu("hora")})" }, null, { n ->
                            val h = historico[n]; atual { LinhaEd(h.txtOu("origem"), h.txtOu("destino"), h.inteiro("comboio").toString(), h.txtOu("hora")) }
                        }, vazio = "Escolher…")
                        Seletor("Origem", opcoes(v.origem), v.origem.ifEmpty { null }, { s -> atual { it.copy(origem = s) } }, vazio = "Origem…")
                        Seletor("Destino", opcoes(v.destino), v.destino.ifEmpty { null }, { s -> atual { it.copy(destino = s) } }, vazio = "Destino…")
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Campo("Comboio", v.comboio, { t -> atual { it.copy(comboio = t.filter(Char::isDigit).take(5)) } }, Modifier.weight(1f), teclado = androidx.compose.ui.text.input.KeyboardType.Number)
                            CampoHora("Hora de partida", v.hora, { h -> atual { it.copy(hora = h) } }, Modifier.weight(1f), opcional = false)
                        }
                        VerificacaoCp(dia.data, v.origem, v.destino, v.comboio, v.hora) { h -> atual { it.copy(hora = h) } }
                        LinkBtn("Remover viagem ${k + 1}", { mudar(i) { x -> x.copy(viagens = x.viagens.filterIndexed { j, _ -> j != k }) } })
                    }
                }
                if (!dia.passado) LinkBtn("Adicionar viagem a ${diaCurto(dia.data)}", { mudar(i) { x -> x.copy(viagens = x.viagens + LinhaEd(origemPadrao, destinoPadrao)) } })
                erros.getOrNull(i)?.takeIf { it.isNotEmpty() }?.let { e -> Aviso(TipoAviso.ERRO) { e.forEach { Texto(it, Pulse.body2) } } }
            }
        }
        ErroAcao(acoes)
        Botao("Guardar semana", {
            val e = validarDias(dias); erros = e
            if (e.any { it.isNotEmpty() }) return@Botao
            val anteriores = semana.objs("viagens").map { jo("data" to it.txt("data"), "origem" to it.txt("origem"), "destino" to it.txt("destino"), "comboio" to it.optInt("comboio"), "hora" to it.txt("hora"), "ativo" to it.bool("ativo")) }
            acoes.executar("semana", "bilhetes.semana", jo("inicio" to semana.getString("inicio"), "viagens" to ja(viagensParaEnviar(dias)))) { r ->
                aoFechar()
                avisos.mostrar("Semana guardada. O Pi vai ler a nova configuração.") {
                    acoes.executar("desfazer", "bilhetes.semana", jo("inicio" to semana.getString("inicio"), "viagens" to (r.optJSONArray("anteriores") ?: ja(anteriores))))
                }
            }
        }, grande = true, ativo = acoes.ocupado == null, carregando = acoes.ocupado == "semana")
    }
}

@Composable
private fun ColumnScope.BilhetesTab(d: JSONObject) {
    val b = d.getJSONObject("bilhetes"); val proximos = b.objs("proximos"); val anteriores = b.objs("anteriores")
    if (proximos.size + anteriores.size == 0) { Texto2("Ainda não há bilhetes comprados. Aparecem aqui quando o Pi os compra."); return }
    @Composable fun cartao(k: JSONObject) = Bloco {
        Meta(diaCurto(k.txtOu("data")))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            Texto(k.txtOu("hora"), Pulse.section); Texto(k.txtOu("origem")); Icon(Icone.SETA, Pulse.cores.text2, 16.dp); Texto(k.txtOu("destino"))
        }
        Texto2("Comboio ${k.inteiro("comboio")}")
        Pilula("Carruagem ${k.txtOu("carruagem").ifEmpty { "—" }} · Lugar ${k.txtOu("lugar").ifEmpty { "—" }}", Pulse.cores.success)
        if (k.txtOu("referencia").isNotEmpty()) Meta("ref. ${k.txtOu("referencia")}")
    }
    if (proximos.isNotEmpty()) { Texto("Próximos", Pulse.card); proximos.forEach { cartao(it) } }
    if (anteriores.isNotEmpty()) { Texto("Anteriores", Pulse.card); anteriores.forEach { cartao(it) } }
}

@Composable
private fun ColumnScope.PedidosTab(d: JSONObject, acoes: Acoes) {
    val pedidos = d.objs("pedidos")
    if (pedidos.isEmpty()) { Texto2("Sem pedidos pendentes. Aparecem aqui viagens da semana que esgotaram as tentativas normais: podes forçar uma nova tentativa ou deixar o Pi repetir sozinho."); return }
    Bloco(titulo = "Pedidos pendentes  ${pedidos.size}") { pedidos.forEach { LinhaPedido(it, acoes) } }
}

@Composable
private fun LinhaPedido(p: JSONObject, acoes: Acoes) {
    val avisos = LocalAvisos.current
    val id = p.getInt("id")
    var minutos by remember { mutableStateOf((p.inteiroOuNull("intervaloMinutos") ?: 15).toString()) }
    val n = minutos.toIntOrNull() ?: 0
    val minutosOk = n in 1..1440
    val estado = p.txtOu("estado"); val ambiguo = estado == "AMBIGUO"; val aTentar = estado == "A_TENTAR"; val retry = p.bool("retry")
    val c = Pulse.cores
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            Texto("${diaCurto(p.txtOu("data"))} · ${p.txtOu("hora")}"); Pilula(ESTADO_PEDIDO[estado] ?: estado, if (ambiguo) c.warning else if (estado == "CONFIRMADO") c.success else c.text2, if (ambiguo) c.warningBg else c.surface2)
        }
        Meta("${p.txtOu("origem")} → ${p.txtOu("destino")} · comboio ${p.inteiro("comboio")}")
        p.txt("mensagem")?.takeIf { it.isNotEmpty() }?.let { Meta(it) }
        if (ambiguo) Meta("Confirma na App CP se a compra chegou a ser feita antes de tentares outra vez.")
        else {
            Botao(if (aTentar) "A tentar…" else "Tentar agora", {
                acoes.executar("forcar-$id", "bilhetes.pedido_forcar", jo("pedido" to id)) { avisos.mostrar("Pedido marcado para tentar já. O Pi corre a fila a cada minuto.") }
            }, variante = Variante.SECUNDARIO, pequeno = true, ativo = !aTentar && acoes.ocupado == null, carregando = acoes.ocupado == "forcar-$id")
            Interruptor("Repetir automaticamente", retry, { on ->
                if (!on || minutosOk) acoes.executar("retry-$id", "bilhetes.pedido_repetir", jo("pedido" to id, "retry" to on).also { o ->
                    if (on) o.put("intervaloMinutos", n) else p.inteiroOuNull("intervaloMinutos")?.let { o.put("intervaloMinutos", it) }
                }) { avisos.mostrar(if (on) "Repetição automática ligada, de $n em $n min." else "Repetição automática desligada.") }
            })
            Campo("Minutos entre tentativas", minutos, { minutos = it.filter(Char::isDigit).take(4) }, teclado = androidx.compose.ui.text.input.KeyboardType.Number, erro = if (!minutosOk) "Entre 1 e 1440." else null)
        }
    }
}

@Composable
private fun ColumnScope.RegistoTab(d: JSONObject) {
    var filtro by remember { mutableStateOf("tudo") }
    val c = Pulse.cores
    val linhas = d.objs("registo").filter { r ->
        filtro == "tudo" || (if (filtro == "compras") Regex("COMPRA", RegexOption.IGNORE_CASE).containsMatchIn(r.txtOu("tipo")) else classeRegisto(r.txt("resultado"), r.txtOu("tipo")) in listOf("err", "warn"))
    }
    Filtros(listOf("tudo" to "Tudo", "compras" to "Compras", "problemas" to "Problemas"), filtro) { filtro = it }
    if (linhas.isEmpty()) { Texto2("Sem registos para mostrar."); return }
    Bloco {
        linhas.forEach { r ->
            val classe = classeRegisto(r.txt("resultado"), r.txtOu("tipo"))
            val oQue = listOfNotNull(r.inteiroOuNull("comboio")?.let { "comboio $it" }, r.txt("data")?.takeIf { it.isNotEmpty() }?.let { diaMes(it) }).joinToString(" · ")
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Texto("${diaMes(r.txtOu("ts").take(10))} ${r.txtOu("ts").drop(11).take(5)}")
                    Pilula(RESULTADO_REGISTO[r.txt("resultado") ?: ""] ?: r.txt("resultado") ?: (TIPO_REGISTO[r.txtOu("tipo")] ?: r.txtOu("tipo")),
                        if (classe == "ok") c.success else if (classe.isNotEmpty()) c.warning else c.text2, if (classe.isNotEmpty() && classe != "ok") c.warningBg else c.surface2)
                }
                if (oQue.isNotEmpty()) Meta(oQue)
                r.txt("erro")?.takeIf { it.isNotEmpty() }?.let { Meta(it) }
            }
        }
    }
}


/** Confere na CP (pelo servidor: as chaves nunca vão para o telemóvel) o comboio, a data, o percurso e a hora. Consultivo: nunca impede de guardar (ADR-068). */
@Composable
private fun VerificacaoCp(data: String, origem: String, destino: String, comboio: String, hora: String, aoUsarHora: (String) -> Unit) {
    val pronto = comboio.isNotEmpty() && origem.isNotEmpty() && destino.isNotEmpty() && origem != destino
    val chave = "$data|$origem|$destino|$comboio|$hora"
    var res by remember { mutableStateOf<Pair<String, JSONObject>?>(null) }
    LaunchedEffect(chave) {
        if (!pronto) { res = null; return@LaunchedEffect }
        kotlinx.coroutines.delay(450)
        val q = "comboio=$comboio&data=$data&origem=${android.net.Uri.encode(origem)}&destino=${android.net.Uri.encode(destino)}" + if (hora.isNotEmpty()) "&hora=${android.net.Uri.encode(hora)}" else ""
        try {
            val r = Api.get("/tickets/timetable?$q")
            res = chave to r
            if (r.txt("estado") == "preenchido" && hora.isEmpty()) r.txt("sugestaoHora")?.takeIf { it.isNotEmpty() }?.let(aoUsarHora)      // hora em falta: preenche-se com a da CP
        } catch (e: Exception) { if (e is kotlinx.coroutines.CancellationException) throw e; res = null }
    }
    val (c, r) = res ?: return
    if (!pronto || c != chave) return
    val estado = r.txtOu("estado"); val mensagem = r.txtOu("mensagem")
    when (estado) {
        "desligado" -> Unit
        "aviso" -> Aviso(TipoAviso.AVISO) {
            Texto("Verifica na CP: $mensagem", Pulse.body2)
            r.txt("sugestaoHora")?.takeIf { it.isNotEmpty() && it != hora }?.let { s -> LinkBtn("Usar $s", { aoUsarHora(s) }) }
        }
        else -> Meta(if (estado == "confirmado") "✓ $mensagem" else mensagem)
    }
}
