package pt.pereirabmd.pulse.ui

import androidx.compose.foundation.layout.*
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.runtime.*
import kotlinx.coroutines.launch
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.border
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import org.json.JSONObject
import pt.pereirabmd.pulse.data.*
import pt.pereirabmd.pulse.util.*
import java.time.LocalDate

// --- Horário --------------------------------------------------------------------------------------------------------------------

private val NOMES_DIA = listOf("", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo")

@Composable
private fun Aulas(aulas: List<JSONObject>) = aulas.forEach { a -> Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) { Texto(a.txtOu("disciplina"), Pulse.body.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold)); if (a.txtOu("sala").isNotEmpty()) Meta(a.txtOu("sala")) } }

@Composable
private fun VistaDia(dia: JSONObject, hoje: Boolean) {
    val agora = java.util.Calendar.getInstance(); val min = agora.get(java.util.Calendar.HOUR_OF_DAY) * 60 + agora.get(java.util.Calendar.MINUTE)
    fun m(hhmm: String) = hhmm.take(2).toInt() * 60 + hhmm.drop(3).toInt()
    Texto2("Entra às ${dia.txtOu("entra")} · sai às ${dia.txtOu("sai")} · ${dia.inteiro("totalAulas")} aulas")
    dia.objs("slots").forEach { s ->
        val aqui = hoje && min >= m(s.txtOu("ini")) && min < m(s.txtOu("fim"))
        Row(Modifier.fillMaxWidth().then(if (aqui) Modifier.background(Pulse.cores.surface2, RoundedCornerShape(8.dp)).padding(6.dp) else Modifier), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Column(Modifier.width(48.dp)) { Texto(s.txtOu("ini"), Pulse.body2.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold)); Meta(s.txtOu("fim")) }
            Column(Modifier.weight(1f)) {
                Aulas(s.objs("aulas"))
                if (s.bool("dividida")) Meta("turma dividida")
                if (s.bool("ultima")) Meta("Saída às ${s.txtOu("fim")} · aviso às ${dia.txtOu("aviso")}")
                if (aqui) Pilula("A decorrer", Pulse.cores.success)
            }
        }
    }
}

@Composable
fun ColumnScope.HorarioTab() {
    val avisos = LocalAvisos.current
    val c = carga { Api.get("/tasks/schedule") }
    val acoes = rememberAcoes { c.recarregar() }
    var aluno by remember { mutableStateOf<String?>(null) }
    var vista by remember { mutableStateOf("dia") }
    var dia by remember { mutableStateOf<Int?>(null) }
    when (val e = c.estado) {
        Estado.ACarregar -> BrandLoading("A carregar o horário…")
        is Estado.Erro -> EstadoErro(e.mensagem, c.recarregar)
        is Estado.Pronto -> {
            val d = e.dados
            if (!d.bool("disponivel")) { Aviso(TipoAviso.AVISO) { Texto("O horário não está disponível de momento.", Pulse.body2); LinkBtn("Tentar de novo", c.recarregar) }; return }
            val alunos = d.objs("alunos")
            if (alunos.isEmpty()) { Texto2("Ainda não há horário importado."); return }
            val al = alunos.firstOrNull { it.txt("nome") == aluno } ?: alunos[0]
            val diasAl = al.objs("dias"); val comAulas = diasAl.map { it.getInt("dia") }; val diaHoje = d.inteiro("diaHoje")
            val escolhido = dia?.takeIf { it in comAulas } ?: if (diaHoje in comAulas) diaHoje else comAulas.firstOrNull { it > diaHoje } ?: comAulas.firstOrNull()
            val atual = diasAl.firstOrNull { it.getInt("dia") == escolhido }
            val av = d.obj("avisos")
            ErroAcao(acoes)
            Bloco(titulo = "Horário escolar  ·  ano letivo ${d.txtOu("anoLetivo")}") {
                if (alunos.size > 1) Filtros(alunos.map { it.txtOu("nome") to it.txtOu("nome") }, al.txtOu("nome")) { aluno = it }
                Filtros(listOf("dia" to "Dia", "semana" to "Semana"), vista) { vista = it }
                if (vista == "dia") {
                    Filtros(diasAl.map { it.getInt("dia") to (it.txtOu("nome") + if (it.getInt("dia") == diaHoje) " •" else "") }, escolhido ?: -1) { dia = it }
                    if (atual != null) VistaDia(atual, escolhido == diaHoje) else Texto2("Sem aulas neste dia.")
                } else {
                    val slotsSemana = diasAl.flatMap { x -> x.objs("slots").map { s -> "${s.txtOu("ini")}|${s.txtOu("fim")}" } }.distinct().sorted()
                    Column(Modifier.horizontalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            Spacer(Modifier.width(44.dp))
                            diasAl.forEach { x -> Box(Modifier.width(120.dp)) { Texto(x.txtOu("nome"), Pulse.card, if (x.getInt("dia") == diaHoje) Pulse.cores.primary else Pulse.cores.text) } }
                        }
                        slotsSemana.forEach { k ->
                            val (ini, fim) = k.split('|')
                            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                Column(Modifier.width(44.dp)) { Texto(ini, Pulse.body2.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold)); Meta(fim) }
                                diasAl.forEach { x -> Column(Modifier.width(120.dp)) { x.objs("slots").firstOrNull { it.txtOu("ini") == ini && it.txtOu("fim") == fim }?.let { Aulas(it.objs("aulas")) } } }
                            }
                        }
                    }
                }
            }
            if (av != null) Bloco(titulo = "Avisos do horário") {
                Texto2(if (av.bool("ativos")) "Aviso ${av.inteiro("minutos")} min antes de acabar a última aula do dia." else "Avisos do horário pausados.")
                Botao(if (av.bool("ativos")) "Pausar avisos" else "Ativar avisos", {
                    acoes.executar("avisos", "tarefas.avisos_horario", jo("ativos" to !av.bool("ativos"))) {
                        avisos.mostrar(if (av.bool("ativos")) "Avisos do horário pausados (os já agendados são cancelados em poucos minutos)." else "Avisos do horário ativos.")
                    }
                }, variante = Variante.SECUNDARIO, pequeno = true, ativo = acoes.ocupado == null, carregando = acoes.ocupado == "avisos")
            }
        }
    }
}

// --- Piscina --------------------------------------------------------------------------------------------------------------------

private fun dias(n: Int) = "$n dia${if (n == 1) "" else "s"}"

@Composable
fun ColumnScope.PiscinaTab(atualizar: () -> Unit) {
    val avisos = LocalAvisos.current
    val c = carga { Api.get("/tasks/pool") }
    val acoes = rememberAcoes { c.recarregar(); atualizar() }
    when (val e = c.estado) {
        Estado.ACarregar -> BrandLoading("A carregar a piscina…")
        is Estado.Erro -> EstadoErro(e.mensagem, c.recarregar)
        is Estado.Pronto -> {
            val d = e.dados
            ErroAcao(acoes)
            @Composable fun cartao(k: JSONObject) {
                val log = k.txt("tipo") == "log"
                val ultima = k.txtOu("ultima"); val proxima = k.txtOu("proxima"); val estado = k.txtOu("estado"); val destacar = k.bool("destacar")
                val sugerido = if (proxima.isNotEmpty()) (if (k.bool("sugeridoHoje")) "sugerido para hoje" else "sugerido: ${fmtDataIso(proxima)}") else ""
                val desde = k.inteiroOuNull("diasDesde") ?: 0
                val linha = when {
                    log -> if (ultima.isNotEmpty()) "Última vez: ${fmtDataIso(ultima)}" else "Ainda não registada"
                    ultima.isEmpty() -> "Ainda não registada" + if (sugerido.isNotEmpty()) " · $sugerido" else ""
                    estado == "atrasada" -> "Última vez: ${fmtDataIso(ultima)} (há ${dias(desde)}) · por fazer há ${dias(desde)}"
                    else -> "Última vez: ${fmtDataIso(ultima)} (há ${dias(desde)})" + if (sugerido.isNotEmpty()) " · $sugerido" else ""
                }
                val destaque = estado == "atrasada" || destacar
                Row(Modifier.fillMaxWidth().then(if (destaque) Modifier.clip(RoundedCornerShape(8.dp)).background(Pulse.cores.warningBg).padding(8.dp) else Modifier), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Column(Modifier.weight(1f)) {
                        Texto(k.txtOu("nome") + k.txtOu("nota").let { if (it.isNotEmpty()) " ($it)" else "" }, Pulse.body.copy(fontWeight = if (estado == "atrasada" || destacar) androidx.compose.ui.text.font.FontWeight.SemiBold else null), Pulse.cores.text)
                        Meta(linha)
                        if (k.txtOu("notaLonga").isNotEmpty()) Meta(k.txtOu("notaLonga"))
                    }
                    Botao(if (log) "Registar agora" else "Marcar feita hoje", {
                        acoes.executar(k.txtOu("id"), "tarefas.piscina_registar", jo("item" to k.txtOu("id"))) { r ->
                            val ant = r.obj("anterior")
                            avisos.mostrar("${k.txtOu("nome")} registada.", ant?.let { a ->
                                { acoes.executar(k.txtOu("id"), "tarefas.piscina_repor", jo("item" to k.txtOu("id"), "ultimaData" to a.txt("ultimaData"), "proximaData" to a.txt("proximaData"),
                                    "usarIntervaloLongo" to a.bool("usarIntervaloLongo"), "notificacaoEnviada" to a.bool("notificacaoEnviada"))) }
                            })
                        }
                    }, variante = Variante.SECUNDARIO, pequeno = true, ativo = acoes.ocupado == null, carregando = acoes.ocupado == k.txtOu("id"))
                }
            }
            // sugeridas para hoje ou já passadas da data: sobem para o topo e ficam destacadas
            Bloco(titulo = "Manutenção  ·  ${if (d.txt("estacao") == "quente") "meses quentes" else "meses frios"}") {
                d.objs("periodicas").sortedByDescending { it.bool("destacar") || it.txt("estado") == "atrasada" }.forEach { cartao(it) }
            }
            Bloco(titulo = "Outras ações") { Meta("Quando for preciso; só se regista a última vez."); d.objs("outras").forEach { cartao(it) } }
        }
    }
}

// --- Config ---------------------------------------------------------------------------------------------------------------------

@Composable
fun ColumnScope.ConfigTab(atualizar: () -> Unit) {
    val avisos = LocalAvisos.current; val ctx = LocalContext.current
    val c = carga { Api.get("/tasks/settings") }
    val acoes = rememberAcoes { c.recarregar(); atualizar() }
    when (val e = c.estado) {
        Estado.ACarregar -> BrandLoading("A carregar a configuração…")
        is Estado.Erro -> EstadoErro(e.mensagem, c.recarregar)
        is Estado.Pronto -> {
            val d = e.dados
            ErroAcao(acoes)
            Pessoas(d, acoes, avisos)
            NaoIncomodar(d, acoes, avisos)
            Resumo(d)
            Sistema(d, acoes, avisos, ctx)
            Bloco(titulo = "Últimas ações") {
                val a = d.objs("auditoria")
                if (a.isEmpty()) Texto2("Ainda não há registos.")
                a.forEach { r -> Meta("${quandoAuditoria(r.txtOu("ts"))} · ${r.txtOu("tarefa").ifEmpty { r.txtOu("acao") }} · ${r.txtOu("pessoa")}") }
            }
            val admin = d.obj("admin")
            if (d.bool("souAdmin") && admin != null) Admin(admin, acoes, avisos)
        }
    }
}

private fun quandoAuditoria(ts: String): String = try {
    val z = java.time.OffsetDateTime.parse(ts).atZoneSameInstant(java.time.ZoneId.systemDefault())
    "%02d/%02d %02d:%02d".format(z.dayOfMonth, z.monthValue, z.hour, z.minute)
} catch (_: Exception) { ts }

@Composable
private fun Pessoas(d: JSONObject, acoes: Acoes, avisos: Avisos) {
    var nome by remember { mutableStateOf("") }; var email by remember { mutableStateOf("") }
    var editar by remember { mutableStateOf<JSONObject?>(null) }
    var remover by remember { mutableStateOf<JSONObject?>(null) }
    var massa by remember { mutableStateOf(false) }
    var erro by remember { mutableStateOf<String?>(null) }
    val pessoas = d.objs("pessoas"); val nomes = pessoas.map { it.txtOu("nome") }
    Bloco(titulo = "Pessoas") {
        val atual = d.txt("pessoaAtual")
        Texto2(if (atual != null) "A tua conta corresponde a $atual (pelo e-mail); é o que o filtro «Minhas» usa." else "Associa o teu e-mail a uma pessoa para poderes usar o filtro «Minhas».")
        erro?.let { Aviso(TipoAviso.ERRO, it) }
        if (pessoas.isEmpty()) Texto2("Ainda não há pessoas. Adiciona a primeira.")
        pessoas.forEach { p ->
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) { Texto(p.txtOu("nome")); Meta(p.txtOu("email").ifEmpty { "sem e-mail definido" }) }
                LinkBtn("Editar", { erro = null; editar = p })
                if (pessoas.size > 1) LinkBtn("Remover", { erro = null; remover = p })
            }
        }
        Campo("Adicionar pessoa", nome, { nome = it.take(60) })
        Campo("E-mail Google (opcional, para o filtro «Minhas»)", email, { email = it }, teclado = KeyboardType.Email)
        Botao("Adicionar", {
            if (nome.isBlank()) { erro = "Escreve um nome."; return@Botao }
            if (nome.contains(',')) { erro = "O nome não pode ter vírgulas."; return@Botao }
            erro = null
            acoes.executar("pessoa-add", "tarefas.pessoa_adicionar", jo("nome" to nome.trim(), "email" to email.trim())) { nome = ""; email = ""; avisos.mostrar("Pessoa adicionada.") }
        }, pequeno = true, ativo = acoes.ocupado == null, carregando = acoes.ocupado == "pessoa-add")
        if (pessoas.size > 1) Botao("Reatribuir tarefas em massa", { erro = null; massa = true }, variante = Variante.SECUNDARIO, pequeno = true)
    }
    editar?.let { p -> FolhaEditarPessoa(p, acoes, avisos) { editar = null } }
    remover?.let { p -> FolhaRemoverPessoa(p, nomes.filter { it != p.txtOu("nome") }, acoes, avisos) { remover = null } }
    if (massa) FolhaMassa(nomes, acoes, avisos) { massa = false }
}

@Composable
private fun FolhaEditarPessoa(p: JSONObject, acoes: Acoes, avisos: Avisos, aoFechar: () -> Unit) {
    var nome by remember { mutableStateOf(p.txtOu("nome")) }; var email by remember { mutableStateOf(p.txtOu("email")) }
    Folha("Editar ${p.txtOu("nome")}", aoFechar) {
        Campo("Nome", nome, { nome = it.take(60) }); Campo("E-mail Google", email, { email = it }, teclado = KeyboardType.Email)
        ErroAcao(acoes)
        Botao("Guardar", { acoes.executar("pessoa-edit", "tarefas.pessoa_editar", jo("nome" to p.txtOu("nome"), "novoNome" to nome.trim(), "email" to email.trim())) { aoFechar(); avisos.mostrar("Pessoa atualizada.") } },
            grande = true, ativo = nome.isNotBlank() && !nome.contains(',') && acoes.ocupado == null, carregando = acoes.ocupado == "pessoa-edit")
        if (nome.contains(',')) Meta("O nome não pode ter vírgulas.")
    }
}

@Composable
private fun FolhaRemoverPessoa(p: JSONObject, outras: List<String>, acoes: Acoes, avisos: Avisos, aoFechar: () -> Unit) {
    var substituto by remember { mutableStateOf(outras.firstOrNull() ?: "") }
    var confirmar by remember { mutableStateOf(false) }
    Folha("Remover ${p.txtOu("nome")}", aoFechar) {
        Texto2("As tarefas por fazer passam para quem escolheres (se não houver nenhuma, não é preciso).")
        Seletor("Quem fica responsável", outras.map { it to it }, substituto, { substituto = it })
        ErroAcao(acoes)
        Botao("Remover", { confirmar = true }, grande = true, variante = Variante.PERIGO, ativo = acoes.ocupado == null)
    }
    if (confirmar) Confirmar("Remover pessoa", "Remover ${p.txtOu("nome")}?", "Remover", true, {
        confirmar = false
        acoes.executar("pessoa-rem", "tarefas.pessoa_remover", jo("nome" to p.txtOu("nome")).also { if (substituto.isNotEmpty()) it.put("substituto", substituto) }, true) { r ->
            aoFechar(); avisos.mostrar(if (r.inteiro("reatribuidas") > 0) "Pessoa removida · ${r.inteiro("reatribuidas")} tarefa(s) passada(s) para $substituto." else "Pessoa removida.")
        }
    }, { confirmar = false })
}

@Composable
private fun FolhaMassa(nomes: List<String>, acoes: Acoes, avisos: Avisos, aoFechar: () -> Unit) {
    var de by remember { mutableStateOf(nomes[0]) }; var para by remember { mutableStateOf(nomes.getOrElse(1) { nomes[0] }) }
    var confirmar by remember { mutableStateOf(false) }
    Folha("Reatribuir tarefas em massa", aoFechar) {
        Texto2("Passar todas as tarefas por fazer de uma pessoa para outra:")
        Seletor("De", nomes.map { it to it }, de, { de = it }); Seletor("Para", nomes.map { it to it }, para, { para = it })
        if (de == para) Meta("Escolhe pessoas diferentes.")
        ErroAcao(acoes)
        Botao("Reatribuir", { confirmar = true }, grande = true, variante = Variante.PERIGO, ativo = de != para && acoes.ocupado == null)
    }
    if (confirmar) Confirmar("Reatribuir", "Passar as tarefas por fazer de $de para $para?", "Reatribuir", true, {
        confirmar = false
        acoes.executar("massa", "tarefas.reatribuir", jo("de" to de, "para" to para), true) { aoFechar(); avisos.mostrar("Tarefas por fazer passadas de $de para $para.") }
    }, { confirmar = false })
}

@Composable
private fun NaoIncomodar(d: JSONObject, acoes: Acoes, avisos: Avisos) {
    val pref = d.getJSONObject("preferencias")
    var ini by remember(pref.txtOu("naoIncomodarInicio")) { mutableStateOf(pref.txtOu("naoIncomodarInicio")) }
    var fim by remember(pref.txtOu("naoIncomodarFim")) { mutableStateOf(pref.txtOu("naoIncomodarFim")) }
    var erro by remember { mutableStateOf<String?>(null) }
    Bloco(titulo = "Não incomodar") {
        Meta("Janela horária sem notificações. Deixa vazio para desligar.")
        erro?.let { Aviso(TipoAviso.ERRO, it) }
        CampoHora("Início", ini, { ini = it }); CampoHora("Fim", fim, { fim = it })
        Botao("Guardar", {
            if (ini.isEmpty() != fim.isEmpty()) { erro = "Indica o início e o fim (ou deixa ambos vazios para desligar)."; return@Botao }
            erro = null
            acoes.executar("pref", "tarefas.preferencias", jo("naoIncomodarInicio" to ini, "naoIncomodarFim" to fim)) { avisos.mostrar("Preferências guardadas.") }
        }, pequeno = true, ativo = acoes.ocupado == null, carregando = acoes.ocupado == "pref")
    }
}

@Composable
private fun Resumo(d: JSONObject) {
    val r = d.getJSONObject("resumo"); val ps = r.objs("pessoas")
    val max = maxOf(1, ps.maxOfOrNull { it.inteiro("feitas") } ?: 1)
    Bloco(titulo = "Resumo  ·  últimos 7 dias") {
        if (ps.isEmpty()) Texto2("Sem dados ainda.")
        ps.forEach { p ->
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) { Texto(p.txtOu("nome")); Meta("${p.inteiro("feitas")} tarefa${if (p.inteiro("feitas") == 1) "" else "s"}") }
                LinearProgressIndicator(progress = { p.inteiro("feitas").toFloat() / max }, Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(50)), color = Pulse.cores.primary, trackColor = Pulse.cores.surface2)
            }
        }
        r.txt("desequilibrio")?.let { Aviso(TipoAviso.AVISO, "$it tem feito bastante mais do que os outros esta semana.") }
    }
}

@Composable
private fun Sistema(d: JSONObject, acoes: Acoes, avisos: Avisos, ctx: android.content.Context) {
    val s = d.obj("saude"); val scope = rememberCoroutineScope()
    var erro by remember { mutableStateOf<String?>(null) }
    Bloco(titulo = "Sistema") {
        erro?.let { Aviso(TipoAviso.ERRO, it) }
        when {
            s == null -> Texto2("Não foi possível verificar o estado do Pi.")
            s.txt("ultimaExecucao") == null -> Aviso(TipoAviso.AVISO, "A reconciliação dos avisos no Pi ainda não correu nenhuma vez.")
            else -> {
                val cont = s.obj("contagens")
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Pilula(if (s.bool("saudavel")) "Em dia" else "Atrasada", if (s.bool("saudavel")) Pulse.cores.success else Pulse.cores.warning)
                    Texto2("Última reconciliação dos avisos no Pi: há ${s.inteiro("minutosDesde")} min.")
                }
                if (cont != null) Meta("Mensagens ntfy: ${cont.inteiro("sem_alteracao")} agendadas em dia · ${cont.inteiro("agendado")} novas · ${cont.inteiro("reagendado")} reagendadas · ${cont.inteiro("cancelado")} canceladas · ${cont.inteiro("fora_do_horizonte")} para depois (fora dos 3 dias)")
            }
        }
        Botao("Atualizar tarefas agora", {
            acoes.executar("gerar", "tarefas.gerar", jo()) { r -> avisos.mostrar("Tarefas atualizadas (${r.inteiro("criadas")} nova${if (r.inteiro("criadas") == 1) "" else "s"}).") }
        }, variante = Variante.SECUNDARIO, pequeno = true, ativo = acoes.ocupado == null, carregando = acoes.ocupado == "gerar")
        Botao("Exportar histórico (CSV)", {
            erro = null
            scope.launch {
                try {
                    val h = Api.get("/tasks/history").objs("linhas")
                    if (h.isEmpty()) { avisos.mostrar("Sem histórico para exportar."); return@launch }
                    partilharFicheiro(ctx, "tarefas-historico-${LocalDate.now()}.csv", csvHistorico(h.map { l -> listOf("tarefa", "categoria", "data", "pessoa", "estado", "dataConclusao").map { l.txtOu(it) } }))
                    avisos.mostrar("Histórico exportado.")
                } catch (e: Exception) { erro = mensagemDeErro(e) }
            }
        }, variante = Variante.SECUNDARIO, pequeno = true)
        Meta("As notificações por pessoa (utilizador e palavra-passe do ntfy) configuram-se na app dedicada das Tarefas; o Pulse terá as suas próprias (ADR-032).")
    }
}

@Composable
private fun Admin(p: JSONObject, acoes: Acoes, avisos: Avisos) {
    val raiz = p.strs("raiz"); val pessoas = p.objs("pessoas"); val notifs = p.objs("notificacoes")
    var admins by remember { mutableStateOf(p.strs("admins").filter { it !in raiz }) }
    var destinos by remember { mutableStateOf(notifs.associate { it.txtOu("id") to it.strs("destinatarios") }) }
    var confirmar by remember { mutableStateOf(false) }
    Bloco(titulo = "Administração") {
        Texto("Administradores", Pulse.card); Meta("Só se pode escolher pessoas com e-mail registado.")
        pessoas.forEach { x ->
            val fixo = x.bool("fixo"); val em = x.txtOu("email")
            Interruptor(x.txtOu("nome"), fixo || em in admins, { admins = alterna(admins, em) }, if (fixo) "administrador fixo" else em.ifEmpty { "sem e-mail" }).let { }
        }
        notifs.forEach { n ->
            Texto("Notificações: ${n.txtOu("nome")}${if (n.bool("padrao")) " (predefinição)" else ""}", Pulse.card); Meta(n.txtOu("descricao"))
            pessoas.forEach { x -> Interruptor(x.txtOu("nome"), x.txtOu("nome") in (destinos[n.txtOu("id")] ?: emptyList()), { destinos = destinos + (n.txtOu("id") to alterna(destinos[n.txtOu("id")] ?: emptyList(), x.txtOu("nome"))) }) }
        }
        Botao("Guardar administração", { confirmar = true }, pequeno = true, ativo = acoes.ocupado == null)
    }
    if (confirmar) Confirmar("Confirmar alterações", "Mudar quem administra e quem recebe os avisos gerais?", "Confirmar", aoConfirmar = {
        confirmar = false
        acoes.executar("admin", "tarefas.admin", jo("admins" to ja(admins), "notificacoes" to JSONObject().also { o -> destinos.forEach { (k, v) -> o.put(k, ja(v)) } }), true) { avisos.mostrar("Guardado. Os avisos agendados ajustam-se em poucos minutos.") }
    }, aoCancelar = { confirmar = false })
}
