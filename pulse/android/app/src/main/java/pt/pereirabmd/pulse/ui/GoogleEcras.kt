package pt.pereirabmd.pulse.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import org.json.JSONObject
import pt.pereirabmd.pulse.data.*
import pt.pereirabmd.pulse.util.*
import java.time.LocalDate

private fun corDe(hex: String?, por: Color): Color = if (hex == null) por else try { Color(android.graphics.Color.parseColor(hex)) } catch (_: Exception) { por }

// --- Contas Google ---------------------------------------------------------------------------------------------------------------

/** Contas Google (ADR-049/051): ligar (consentimento num Custom Tab, regresso por `pulse://google`), ver o estado e remover. */
@Composable
fun GoogleContasEcra(sessao: Sessao, aoVoltar: () -> Unit) {
    val ctx = LocalContext.current; val scope = rememberCoroutineScope(); val avisos = LocalAvisos.current
    val c = carga { Api.get("/google/accounts") }
    var servicos by remember { mutableStateOf(listOf("gmail", "calendar")) }
    var erro by remember { mutableStateOf<String?>(null) }
    var aLigar by remember { mutableStateOf(false) }
    var remover by remember { mutableStateOf<JSONObject?>(null) }
    val resultado = sessao.resultadoGoogle
    LaunchedEffect(resultado) { if (resultado != null) c.recarregar() }

    EcraModulo("Contas Google", aoVoltar) {
        Ao(c, "A carregar as contas…") { d ->
            val contas = d.objs("contas")
            Rolar {
                resultado?.let { (ok, motivo) ->
                    if (ok) Aviso(TipoAviso.INFO) { Texto("Conta Google ligada.", Pulse.body2); LinkBtn("Fechar", { sessao.limparResultadoGoogle() }) }
                    else Aviso(TipoAviso.ERRO) { Texto(MOTIVOS_GOOGLE[motivo] ?: "Não foi possível ligar a conta Google.", Pulse.body2); LinkBtn("Fechar", { sessao.limparResultadoGoogle() }) }
                }
                erro?.let { Aviso(TipoAviso.ERRO, it) }
                if (contas.isEmpty()) Texto2("Liga uma conta Google para veres o Gmail e o Calendário no Pulse. O Pulse só lê e organiza (marcar como lida, arquivar, estrela) e gere eventos; nunca envia nem apaga emails.")
                contas.forEach { conta ->
                    Bloco {
                        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Texto(conta.txtOu("email"))
                                Meta(conta.strs("servicos").joinToString(" · ") { if (it == "gmail") "Gmail" else "Calendário" })
                            }
                            LinkBtn("Remover", { remover = conta })
                        }
                        if (conta.txt("estado") == "reautorizar") Aviso(TipoAviso.AVISO, "Esta conta pede nova autorização: liga-a outra vez com os mesmos serviços.")
                    }
                }
                if (!d.bool("configurado")) Aviso(TipoAviso.AVISO, "A integração com a Google ainda não está configurada neste servidor.")
                else Bloco(titulo = if (contas.isEmpty()) "Ligar conta Google" else "Ligar outra conta Google") {
                    Texto2("Escolhe os serviços. O consentimento abre num separador seguro da Google e volta a esta app.")
                    MultiChips(listOf("gmail" to "Gmail", "calendar" to "Calendário"), servicos) { servicos = alterna(servicos, it) }
                    Botao("Ligar conta Google", {
                        erro = null; aLigar = true
                        scope.launch {
                            try {
                                val url = Api.post("/google/connect", jo("servicos" to ja(servicos), "cliente" to "android")).getString("url")
                                androidx.browser.customtabs.CustomTabsIntent.Builder().build().launchUrl(ctx, android.net.Uri.parse(url))
                            } catch (e: Exception) { erro = mensagemDeErro(e) } finally { aLigar = false }
                        }
                    }, grande = true, ativo = servicos.isNotEmpty() && !aLigar, carregando = aLigar)
                }
            }
            remover?.let { conta ->
                Confirmar("Remover conta Google", "Remover ${conta.txtOu("email")}? O Pulse deixa de ler o Gmail e o Calendário desta conta e revoga o acesso.", "Remover", true, {
                    remover = null
                    scope.launch {
                        try { Api.delete("/google/accounts/${conta.getInt("id")}"); avisos.mostrar("Conta removida."); c.recarregar() } catch (e: Exception) { erro = mensagemDeErro(e) }
                    }
                }, { remover = null })
            }
        }
    }
}

@Composable
private fun ColumnScope.AvisosContas(contas: List<JSONObject>) {
    val abrir = LocalAbrir.current
    contas.filter { it.txt("estado") != "ok" }.forEach { c ->
        Aviso(TipoAviso.AVISO) {
            if (c.txt("estado") == "reautorizar") { Texto("A conta ${c.txtOu("email")} pede nova autorização.", Pulse.body2); LinkBtn("Volta a ligá-la", { abrir("google") }) }
            else Texto("Não foi possível ler a conta ${c.txtOu("email")}: ${c.txtOu("erro")}", Pulse.body2)
        }
    }
}

@Composable
private fun ColumnScope.SemContas(configurado: Boolean, texto: String) {
    val abrir = LocalAbrir.current
    Aviso(TipoAviso.INFO, if (configurado) texto else "A integração com a Google ainda não está configurada neste servidor.")
    Botao("Contas Google", { abrir("google") }, variante = Variante.SECUNDARIO, pequeno = true)
}

// --- Calendário Google ---------------------------------------------------------------------------------------------------------

private data class Rascunho(val conta: String, val calendario: String, val titulo: String, val data: String, val dataFim: String, val diaInteiro: Boolean,
                            val inicio: String, val fim: String, val local: String, val descricao: String)

private fun paraRascunho(e: JSONObject) = Rascunho(e.inteiro("conta").toString(), e.txtOu("calendario"), e.txtOu("titulo"), e.txtOu("data"), if (e.txt("dataFim") == e.txt("data")) "" else e.txtOu("dataFim"),
    e.bool("diaInteiro"), e.txt("inicio") ?: "09:00", e.txt("fim") ?: "10:00", e.txtOu("local"), e.txtOu("descricao"))

@Composable
fun CalendarioGoogleEcra(aoVoltar: () -> Unit) {
    val hoje = LocalDate.now().toString()
    var ancora by remember { mutableStateOf(hoje) }
    var escolhido by remember { mutableStateOf(hoje) }
    var novo by remember { mutableStateOf(false) }
    var editar by remember { mutableStateOf<JSONObject?>(null) }
    val (de, ate) = intervaloMes(ancora)
    val c = carga("$de|$ate") { Api.get("/calendar?de=$de&ate=$ate") }
    val acoes = rememberAcoes { c.recarregar() }
    val avisos = LocalAvisos.current
    val mesAtual = ancora.take(7)
    fun mover(n: Int) { val nova = LocalDate.parse(ancora).withDayOfMonth(1).plusMonths(n.toLong()).toString(); ancora = nova; escolhido = if (nova.take(7) == hoje.take(7)) hoje else nova }

    EcraModulo("Calendário", aoVoltar) {
        Ao(c, "A carregar a agenda…") { d ->
            Rolar {
                if (!d.bool("ligado")) { SemContas(d.bool("configurado"), "Liga uma conta Google com o Calendário para veres aqui os teus eventos."); return@Rolar }
                val contas = d.objs("contas")
                val dias = d.objs("dias").associate { it.txtOu("data") to it.objs("eventos") }
                AvisosContas(contas)
                Bloco(titulo = tituloMes(ancora), extra = { LinkBtn("‹", { mover(-1) }); LinkBtn("›", { mover(1) }) }) {
                    LinkBtn("Hoje", { ancora = hoje; escolhido = hoje })
                    Row(Modifier.fillMaxWidth()) { DIAS_CURTO.forEach { Meta(it, Modifier.weight(1f).wrapContentWidth(Alignment.CenterHorizontally)) } }
                    listaDatas(de, ate).chunked(7).forEach { semana ->
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                            semana.forEach { dia ->
                                val evs = dias[dia] ?: emptyList()
                                val cores = evs.map { it.txt("cor") ?: "" }.distinct().take(3)
                                val fora = !dia.startsWith(mesAtual)
                                val fds = diaDaSemana(LocalDate.parse(dia)).let { it == 0 || it == 6 }
                                Column(Modifier.weight(1f).height(48.dp).clip(RoundedCornerShape(8.dp)).background(if (dia == escolhido) Pulse.cores.surface2 else Color.Transparent)
                                    .border(if (dia == hoje) 2.dp else if (dia == escolhido) 1.dp else 0.dp, if (dia == hoje) Pulse.cores.primary else Pulse.cores.text2, RoundedCornerShape(8.dp))
                                    .clickable { escolhido = dia }, horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                                    Text(dia.takeLast(2).toInt().toString(), style = Pulse.body2, color = if (fora) Pulse.cores.text2.copy(alpha = .5f) else if (fds) Pulse.cores.text2 else Pulse.cores.text)
                                    Row(horizontalArrangement = Arrangement.spacedBy(2.dp), modifier = Modifier.height(6.dp)) { cores.forEach { Box(Modifier.size(5.dp).clip(CircleShape).background(corDe(it.ifEmpty { null }, Pulse.cores.accent))) } }
                                }
                            }
                        }
                    }
                }
                ErroAcao(acoes)
                Bloco(titulo = fmtDataLonga(java.util.Calendar.getInstance().apply { time = java.sql.Date.valueOf(escolhido) }), extra = { Botao("Novo evento", { novo = true }, Modifier, Variante.SECUNDARIO, pequeno = true) }) {
                    val evs = dias[escolhido] ?: emptyList()
                    if (evs.isEmpty()) Texto2("Sem eventos neste dia.")
                    evs.forEach { e ->
                        Row(Modifier.fillMaxWidth().clickable(enabled = e.bool("podeEditar")) { editar = e }, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            Box(Modifier.size(10.dp).clip(CircleShape).background(corDe(e.txt("cor"), Pulse.cores.accent)))
                            Column(Modifier.weight(1f)) {
                                Texto(e.txtOu("titulo"))
                                Meta((if (e.bool("diaInteiro")) "Dia inteiro" else "${e.txtOu("inicio")}–${e.txtOu("fim")}") +
                                    (if (e.txt("dataFim") != e.txt("data")) " · até ${e.txtOu("dataFim").drop(8)}/${e.txtOu("dataFim").drop(5).take(2)}" else "") +
                                    (e.txtOu("local").let { if (it.isNotEmpty()) " · $it" else "" }) + (if (contas.size > 1) " · ${e.txtOu("contaEmail")}" else ""))
                                if (e.txtOu("descricao").isNotEmpty()) Meta(e.txtOu("descricao"))
                            }
                            if (e.bool("podeEditar")) LinkBtn("Editar", { editar = e })
                        }
                    }
                }
                if (novo) FolhaEvento(null, d, escolhido, acoes, avisos) { novo = false }
                editar?.let { FolhaEvento(it, d, escolhido, acoes, avisos) { editar = null } }
            }
        }
    }
}

@Composable
private fun FolhaEvento(editar: JSONObject?, agenda: JSONObject, diaEscolhido: String, acoes: Acoes, avisos: Avisos, aoFechar: () -> Unit) {
    var r by remember { mutableStateOf(editar?.let(::paraRascunho) ?: Rascunho(agenda.objs("contas").firstOrNull { it.txt("estado") == "ok" }?.inteiro("id")?.toString() ?: "", "", "", diaEscolhido, "", false, "09:00", "10:00", "", "")) }
    var apagar by remember { mutableStateOf(false) }
    val contasCal = agenda.objs("contas").filter { it.txt("estado") == "ok" }
    val editaveis = agenda.objs("calendarios").filter { it.inteiro("conta").toString() == r.conta && it.bool("podeEditar") }
    val horasOk = r.diaInteiro || (r.inicio.isNotEmpty() && r.fim.isNotEmpty() && (r.dataFim.ifEmpty { r.data } + r.fim) > (r.data + r.inicio))
    val ok = r.titulo.isNotBlank() && r.data.isNotEmpty() && horasOk && (r.dataFim.isEmpty() || r.dataFim >= r.data) && (editar != null || editaveis.isNotEmpty())
    Folha(if (editar != null) "Editar evento" else "Novo evento", aoFechar) {
        Campo("Título", r.titulo, { r = r.copy(titulo = it.take(200)) })
        if (editar == null && contasCal.size > 1) Seletor("Conta", contasCal.map { it.inteiro("id").toString() to it.txtOu("email") }, r.conta, { r = r.copy(conta = it, calendario = "") })
        if (editar == null && editaveis.size > 1) Seletor("Calendário", editaveis.map { it.txtOu("id") to it.txtOu("nome") }, r.calendario.ifEmpty { (editaveis.firstOrNull { it.bool("principal") } ?: editaveis[0]).txtOu("id") }, { r = r.copy(calendario = it) })
        CampoData("Data", r.data, { r = r.copy(data = it) })
        CampoData("Até (opcional)", r.dataFim, { r = r.copy(dataFim = it) }, minimo = r.data, opcional = true)
        Interruptor("Dia inteiro", r.diaInteiro, { r = r.copy(diaInteiro = it) })
        if (!r.diaInteiro) { CampoHora("Início", r.inicio, { r = r.copy(inicio = it) }, opcional = false); CampoHora("Fim", r.fim, { r = r.copy(fim = it) }, opcional = false); if (!horasOk) Meta("O fim tem de ser depois do início.") }
        Campo("Local (opcional)", r.local, { r = r.copy(local = it.take(200)) })
        Campo("Notas (opcional)", r.descricao, { r = r.copy(descricao = it.take(500)) })
        if (editar == null && editaveis.isEmpty()) Meta("Esta conta não tem nenhum calendário onde possas criar eventos.")
        ErroAcao(acoes)
        Botao(if (editar != null) "Guardar" else "Criar evento", {
            val comum = jo("titulo" to r.titulo.trim(), "data" to r.data, "local" to r.local.trim(), "descricao" to r.descricao.trim())
            if (r.dataFim.isNotEmpty() && r.dataFim != r.data) comum.put("dataFim", r.dataFim)
            if (!r.diaInteiro) { comum.put("inicio", r.inicio); comum.put("fim", r.fim) }
            if (editar != null) { comum.put("conta", editar.getInt("conta")); comum.put("calendario", editar.txtOu("calendario")); comum.put("evento", editar.txtOu("id")); acoes.executar("evento", "calendario.editar", comum) { avisos.mostrar("Evento atualizado."); aoFechar() } }
            else { comum.put("conta", r.conta.toInt()); comum.put("calendario", r.calendario.ifEmpty { "primary" }); acoes.executar("evento", "calendario.criar", comum) { avisos.mostrar("Evento criado."); aoFechar() } }
        }, grande = true, ativo = ok && acoes.ocupado == null, carregando = acoes.ocupado == "evento")
        if (editar != null) LinkBtn("Apagar evento", { apagar = true })
    }
    if (apagar && editar != null) Confirmar("Apagar evento", "Apagar «${editar.txtOu("titulo")}»?", "Apagar", true, {
        apagar = false
        acoes.executar("apagar", "calendario.apagar", jo("conta" to editar.getInt("conta"), "calendario" to editar.txtOu("calendario"), "evento" to editar.txtOu("id")), true) {
            aoFechar()
            avisos.mostrar("Evento apagado.") {
                val p = jo("conta" to editar.getInt("conta"), "calendario" to editar.txtOu("calendario"), "titulo" to editar.txtOu("titulo"), "data" to editar.txtOu("data"), "local" to editar.txtOu("local"), "descricao" to editar.txtOu("descricao"))
                if (editar.txt("dataFim") != editar.txt("data")) p.put("dataFim", editar.txtOu("dataFim"))
                if (!editar.bool("diaInteiro")) { p.put("inicio", editar.txtOu("inicio")); p.put("fim", editar.txtOu("fim")) }
                acoes.executar("desfazer", "calendario.criar", p)
            }
        }
    }, { apagar = false })
}

// --- Email -----------------------------------------------------------------------------------------------------------------------

@Composable
fun EmailEcra(aoVoltar: () -> Unit) {
    var filtro by remember { mutableStateOf("importantes") }
    var conta by remember { mutableStateOf<Int?>(null) }
    var aberta by remember { mutableStateOf<JSONObject?>(null) }
    val c = carga("$filtro|$conta") { Api.get("/mail?filtro=$filtro${conta?.let { "&conta=$it" } ?: ""}") }
    val acoes = rememberAcoes { c.recarregar() }
    EcraModulo("Email", aoVoltar) {
        Ao(c, "A carregar o email…") { d ->
            Rolar {
                if (!d.bool("ligado")) { SemContas(d.bool("configurado"), "Liga uma conta Google com o Gmail para veres aqui as tuas mensagens."); return@Rolar }
                val contas = d.objs("contas"); val msgs = d.objs("mensagens")
                Filtros(listOf("importantes" to "Importantes", "entrada" to "Caixa de entrada", "por_ler" to "Por ler"), filtro) { filtro = it }
                if (contas.size > 1 || conta != null) Filtros(listOf<Pair<Int?, String>>(null to "Todas") + contas.map { it.getInt("id") as Int? to it.txtOu("email") }, conta) { conta = it }
                AvisosContas(contas)
                ErroAcao(acoes)
                if (msgs.isEmpty()) Texto2(if (filtro == "por_ler") "Nada por ler." else "Sem mensagens.")
                else Bloco {
                    msgs.forEach { m ->
                        Row(Modifier.fillMaxWidth().clickable { aberta = m }, verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            Column(Modifier.weight(1f)) {
                                val nova = !m.bool("lida")
                                Texto(m.txtOu("de") + if (m.bool("estrela")) " ★" else "", Pulse.body.let { if (nova) it.copy(fontWeight = FontWeight.SemiBold) else it })
                                Texto(m.txtOu("assunto"), Pulse.body2.let { if (nova) it.copy(fontWeight = FontWeight.SemiBold) else it }, if (nova) Pulse.cores.text else Pulse.cores.text2, linhas = 1)
                                Meta(m.txtOu("resumo").take(120))
                            }
                            Meta(quandoMensagem(m.txtOu("data")) + if (contas.size > 1) " · ${m.txtOu("contaEmail")}" else "")
                        }
                    }
                }
                Botao("Atualizar", c.recarregar, variante = Variante.SECUNDARIO, pequeno = true)
                aberta?.let { m -> FolhaMensagem(m, acoes, c.recarregar) { aberta = null } }
            }
        }
    }
}

@Composable
private fun FolhaMensagem(m: JSONObject, acoes: Acoes, atualizar: () -> Unit, aoFechar: () -> Unit) {
    val avisos = LocalAvisos.current
    val detalhe = carga("${m.getInt("conta")}|${m.txtOu("id")}") { Api.get("/mail/${m.getInt("conta")}/${m.txtOu("id")}") }
    val ident = jo("conta" to m.getInt("conta"), "mensagem" to m.txtOu("id"))
    fun com(vararg extra: Pair<String, Any?>) = jo("conta" to m.getInt("conta"), "mensagem" to m.txtOu("id"), *extra)
    Folha(m.txtOu("assunto"), aoFechar) {
        when (val e = detalhe.estado) {
            Estado.ACarregar -> BrandLoading("A abrir a mensagem…")
            is Estado.Erro -> Aviso(TipoAviso.ERRO, e.mensagem)
            is Estado.Pronto -> {
                val d = e.dados
                Meta("De ${d.txtOu("de")} <${d.txtOu("deEmail")}>${d.txtOu("para").let { if (it.isNotEmpty()) " · Para $it" else "" }}")
                // o conteúdo de um email não é de confiança: mostra-se sempre como texto simples, nunca como HTML
                androidx.compose.foundation.text.selection.SelectionContainer { Texto(d.txtOu("corpo").ifEmpty { "(sem texto)" }, Pulse.body2) }
                if (d.bool("temAnexos")) Meta("Esta mensagem tem anexos, que o Pulse não mostra. Abre-a no Gmail para os ver.")
            }
        }
        ErroAcao(acoes)
        Botao(if (m.bool("lida")) "Marcar como por ler" else "Marcar como lida", { acoes.executar("l", "email.lida", com("lida" to !m.bool("lida"))) { atualizar(); aoFechar() } }, variante = Variante.SECUNDARIO, pequeno = true, ativo = acoes.ocupado == null)
        Botao("Arquivar", {
            acoes.executar("a", "email.arquivar", com("arquivado" to true)) {
                aoFechar(); atualizar(); avisos.mostrar("Mensagem arquivada.") { acoes.executar("desfazer", "email.arquivar", com("arquivado" to false)); atualizar() }
            }
        }, variante = Variante.SECUNDARIO, pequeno = true, ativo = acoes.ocupado == null)
        Botao(if (m.bool("estrela")) "Tirar estrela" else "Pôr estrela", { acoes.executar("e", "email.estrela", com("estrela" to !m.bool("estrela"))) { atualizar(); aoFechar() } }, variante = Variante.SECUNDARIO, pequeno = true, ativo = acoes.ocupado == null)
    }
}
