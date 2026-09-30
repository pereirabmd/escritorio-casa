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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import org.json.JSONObject
import pt.pereirabmd.pulse.data.*
import java.text.Normalizer

private fun semAcentos(s: String) = Normalizer.normalize(s, Normalizer.Form.NFD).replace(Regex("\\p{Mn}+"), "").lowercase()
private fun paraRestaurar(i: JSONObject) = jo("produto" to i.optInt("produto"), "quantidade" to i.inteiroOuNull("quantidade"), "nota" to i.txtOu("nota"), "estado" to i.txtOu("estado"))
private fun restaurar(lista: Int, itens: List<JSONObject>) = jo("lista" to lista, "itens" to ja(itens.map(::paraRestaurar)))

/** Compras (ADR-047/048): listas «Casa» partilhada e pessoais, catálogo de 338 produtos, favoritos, sugestões. */
@Composable
fun ComprasEcra(aoVoltar: () -> Unit) {
    var lista by remember { mutableStateOf<Int?>(null) }
    var aba by remember { mutableIntStateOf(0) }
    var novaLista by remember { mutableStateOf(false) }
    val c = carga(lista) { Api.get("/shopping" + (lista?.let { "?lista=$it" } ?: "")) }
    val acoes = rememberAcoes { c.recarregar() }
    val avisos = LocalAvisos.current
    AtualizarPeriodicamente(30_000, c.recarregar)

    EcraModulo("Compras", aoVoltar) {
        Ao(c, "A carregar as compras…") { d ->
            val listas = d.objs("listas"); val atual = d.getJSONObject("lista")
            val pendentes = d.optInt("pendentes")
            Abas(listOf("Lista" + if (pendentes > 0) " ($pendentes)" else "", "Catálogo"), aba) { aba = it }
            Rolar {
                Filtros(listas.map { it.getInt("id") to (it.txtOu("nome") + if (it.inteiro("pendentes") > 0) "  ${it.inteiro("pendentes")}" else "") } + (-1 to "+ Nova lista"),
                    atual.getInt("id")) { if (it == -1) novaLista = true else { lista = it } }
                Meta(if (atual.txt("tipo") == "partilhada") "Lista partilhada: todas as contas a veem e alteram." else "Lista pessoal: só tu a vês.")
                ErroAcao(acoes)
                if (aba == 0) ListaTab(d, acoes, avisos, { aba = 1 }) { lista = null } else CatalogoTab(d, acoes, avisos)
            }
            if (novaLista) FolhaNovaLista(acoes, { novaLista = false }) { id -> novaLista = false; lista = id; avisos.mostrar("Lista criada.") }
        }
    }
}

@Composable
private fun FolhaNovaLista(acoes: Acoes, aoFechar: () -> Unit, aoCriar: (Int) -> Unit) {
    var nome by remember { mutableStateOf("") }
    var tipo by remember { mutableStateOf("pessoal") }
    Folha("Nova lista", aoFechar) {
        Campo("Nome", nome, { nome = it.take(60) })
        Escolha(listOf("pessoal" to "Pessoal", "partilhada" to "Partilhada"), tipo, { tipo = it })
        Meta(if (tipo == "pessoal") "Só tu vês esta lista." else "Todas as contas veem e alteram esta lista.")
        ErroAcao(acoes)
        Botao("Criar", { acoes.executar("nova-lista", "compras.lista_criar", jo("nome" to nome.trim(), "tipo" to tipo)) { aoCriar(it.optInt("id")) } },
            grande = true, ativo = nome.isNotBlank() && acoes.ocupado == null, carregando = acoes.ocupado == "nova-lista")
    }
}

@Composable
private fun FolhaUltimaChamada(lista: Int, acoes: Acoes, avisos: Avisos, aoFechar: () -> Unit) {
    var mensagem by remember { mutableStateOf("") }
    Folha("Última chamada", aoFechar) {
        Texto2("Avisa toda a gente de que vais fechar a lista e ir às compras. Só se pode fazer uma vez.")
        Campo("Mensagem (opcional)", mensagem, { mensagem = it.take(120) })
        ErroAcao(acoes)
        Botao("Avisar toda a gente", {
            acoes.executar("ultima-chamada", "compras.ultima_chamada", jo("lista" to lista, "mensagem" to mensagem.trim()), true) {
                aoFechar(); avisos.mostrar("Última chamada enviada a toda a gente.")
            }
        }, grande = true, ativo = acoes.ocupado == null, carregando = acoes.ocupado == "ultima-chamada")
    }
}

@Composable
private fun ColumnScope.ListaTab(d: JSONObject, acoes: Acoes, avisos: Avisos, abrirCatalogo: () -> Unit, aoApagarLista: () -> Unit) {
    val atual = d.getJSONObject("lista")
    val partilhada = atual.txt("tipo") == "partilhada"
    val comprados = d.objs("comprados")
    val grupos = d.objs("grupos")
    var limpar by remember { mutableStateOf(false) }
    var gerir by remember { mutableStateOf(false) }
    var detalhe by remember { mutableStateOf<JSONObject?>(null) }
    var ultimaAberta by remember { mutableStateOf(false) }

    if (atual.bool("padrao")) {
        val u = d.optJSONObject("ultimaChamada")
        if (u != null) Bloco(titulo = "Última chamada") {
            val hora = java.text.SimpleDateFormat("HH:mm", java.util.Locale("pt", "PT")).format(java.util.Date(u.optLong("criado") * 1000))
            val msg = u.txtOu("mensagem")
            Texto2("${u.txtOu("por").ifEmpty { "Alguém" }} avisou toda a gente às $hora${if (msg.isEmpty()) "." else ": $msg"}")
        } else Botao("Última chamada", { ultimaAberta = true }, Modifier, Variante.SECUNDARIO, pequeno = true)
    }
    if (ultimaAberta) FolhaUltimaChamada(atual.getInt("id"), acoes, avisos) { ultimaAberta = false }

    if (d.optInt("pendentes") == 0 && comprados.isEmpty()) Bloco {
        Texto2("A lista «${atual.txtOu("nome")}» está vazia. Escolhe produtos no catálogo com um toque.")
        Botao("Abrir o catálogo", abrirCatalogo, pequeno = true)
    }
    val (fechadas, guardarFechadas) = rememberFechadas("compras.fechadas.lista")
    val ids = grupos.map { it.getJSONObject("categoria").txtOu("id") }
    if (grupos.size > 1) LinkBtn(if (ids.all { it in fechadas }) "Expandir todas" else "Encolher todas", { guardarFechadas(if (ids.all { it in fechadas }) emptySet() else ids.toSet()) })
    grupos.forEach { g ->
        val cat = g.getJSONObject("categoria"); val id = cat.txtOu("id"); val aberto = id !in fechadas
        Bloco {
            CabecalhoRecolhivel(cat.txtOu("nome"), g.objs("itens").size, aberto, { guardarFechadas(if (aberto) fechadas + id else fechadas - id) })
            if (aberto) g.objs("itens").forEach { LinhaItem(it, acoes, avisos, partilhada) { detalhe = it } }
        }
    }
    if (d.optInt("pendentes") > 0 && comprados.isEmpty()) Meta("Toca no círculo de um item quando o comprares.")
    if (comprados.isNotEmpty()) Bloco(titulo = "Comprados  ${comprados.size}", extra = { if (!limpar) Botao("Limpar comprados", { limpar = true }, Modifier, Variante.SECUNDARIO, pequeno = true) }) {
        comprados.forEach { LinhaItem(it, acoes, avisos, partilhada) { detalhe = it } }
    }
    Sugestoes(d, acoes, avisos)
    if (!atual.bool("padrao")) LinkBtn(if (gerir) "Fechar gestão da lista" else "Gerir esta lista", { gerir = !gerir })
    if (gerir && !atual.bool("padrao")) GerirLista(atual, acoes, avisos, aoApagarLista)

    detalhe?.let { i -> FolhaDetalhes(i, d, acoes, avisos) { detalhe = null } }
    if (limpar) Confirmar("Limpar comprados", "Apagar ${comprados.size} ${if (comprados.size == 1) "item" else "itens"} da lista?", "Apagar", perigo = true, aoConfirmar = {
        limpar = false
        acoes.executar("limpar", "compras.limpar_comprados", jo("lista" to atual.getInt("id")), true) { r ->
            val removidos = r.objs("removidos")
            avisos.mostrar("${removidos.size} ${if (removidos.size == 1) "item comprado removido" else "itens comprados removidos"}.") {
                acoes.executar("desfazer", "compras.restaurar", restaurar(atual.getInt("id"), removidos))
            }
        }
    }, aoCancelar = { limpar = false })
}

@Composable
private fun LinhaItem(i: JSONObject, acoes: Acoes, avisos: Avisos, partilhada: Boolean, aoDetalhes: () -> Unit) {
    val feito = i.txt("estado") == "comprado"
    val c = Pulse.cores
    Row(Modifier.fillMaxWidth().clickable(onClick = aoDetalhes), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Visto(feito, {
            acoes.executar("c-${i.getInt("id")}", "compras.comprado", jo("item" to i.getInt("id"), "comprado" to !feito)) {
                if (!feito) avisos.mostrar("${i.txtOu("nome")} comprado.") { acoes.executar("desfazer", "compras.comprado", jo("item" to i.getInt("id"), "comprado" to false)) }
            }
        }, (if (feito) "Voltar a pôr por comprar: " else "Marcar como comprado: ") + i.txtOu("nome"), acoes.ocupado == "c-${i.getInt("id")}", acoes.ocupado == null)
        ShopIcon(i.txtOu("icone"), if (feito) c.text2 else c.text, 24.dp)
        Column(Modifier.weight(1f)) {
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(i.txtOu("nome"), style = Pulse.body.let { if (feito) it.copy(textDecoration = TextDecoration.LineThrough) else it }, color = if (feito) c.text2 else c.text)
                i.inteiroOuNull("quantidade")?.let { Pilula("$it×") }
            }
            val extra = listOf(i.txtOu("nota"), if (partilhada && i.txtOu("adicionadoPor").isNotEmpty()) "por ${i.txtOu("adicionadoPor").substringBefore('@')}" else "").filter { it.isNotEmpty() }
            if (extra.isNotEmpty()) Meta(extra.joinToString(" · "))
        }
        LinkBtn("Detalhes", aoDetalhes)
    }
}

@Composable
private fun FolhaDetalhes(i: JSONObject, d: JSONObject, acoes: Acoes, avisos: Avisos, aoFechar: () -> Unit) {
    var quantidade by remember { mutableStateOf(i.inteiroOuNull("quantidade")?.toString() ?: "") }
    var nota by remember { mutableStateOf(i.txtOu("nota")) }
    val quantidadeOk = quantidade.isEmpty() || (quantidade.length <= 3 && quantidade.all { it.isDigit() } && quantidade.toInt() >= 1)
    val outras = d.objs("listas").filter { it.getInt("id") != i.getInt("lista") }
    Folha(i.txtOu("nome"), aoFechar) {
        Campo("Quantidade (opcional)", quantidade, { quantidade = it }, teclado = androidx.compose.ui.text.input.KeyboardType.Number, erro = if (!quantidadeOk) "Usa um número inteiro (1 a 999)." else null)
        Campo("Nota", nota, { nota = it.take(80) })
        ErroAcao(acoes)
        Botao("Guardar", {
            acoes.executar("d", "compras.detalhes", jo("item" to i.getInt("id"), "quantidade" to quantidade.toIntOrNull(), "nota" to nota.trim())) { aoFechar(); avisos.mostrar("Detalhes guardados.") }
        }, grande = true, ativo = quantidadeOk && acoes.ocupado == null, carregando = acoes.ocupado == "d")
        if (outras.isNotEmpty()) Seletor("Passar para outra lista", outras.map { it.getInt("id") to it.txtOu("nome") }, null, { l ->
            acoes.executar("m", "compras.mover", jo("item" to i.getInt("id"), "lista" to l)) {
                aoFechar(); avisos.mostrar("${i.txtOu("nome")} passou para ${outras.first { it.getInt("id") == l }.txtOu("nome")}.")
            }
        }, vazio = "Passar para…")
        Botao("Remover da lista", {
            acoes.executar("r", "compras.remover", jo("item" to i.getInt("id"))) { r ->
                aoFechar()
                avisos.mostrar("${i.txtOu("nome")} removido.") { acoes.executar("desfazer", "compras.restaurar", restaurar(i.getInt("lista"), listOf(r))) }
            }
        }, grande = true, variante = Variante.PERIGO, ativo = acoes.ocupado == null)
    }
}

@Composable
private fun Sugestoes(d: JSONObject, acoes: Acoes, avisos: Avisos) {
    val s = d.getJSONObject("sugestoes"); val acabar = s.objs("acabar"); val frequentes = s.objs("frequentes")
    if (acabar.size + frequentes.size == 0) return
    val lista = d.getJSONObject("lista").getInt("id")
    fun linha(x: JSONObject, texto: String): @Composable () -> Unit = {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            ShopIcon(x.txtOu("icone"), Pulse.cores.text, 24.dp)
            Column(Modifier.weight(1f)) { Texto(x.txtOu("nome")); Meta(texto) }
            Column(horizontalAlignment = Alignment.End) {
                LinkBtn("Adicionar", { acoes.executar("s-${x.getInt("produto")}", "compras.adicionar", jo("lista" to lista, "produto" to x.getInt("produto"))) { avisos.mostrar("${x.txtOu("nome")} na lista.") } })
                LinkBtn("Não sugerir", {
                    acoes.executar("i-${x.getInt("produto")}", "compras.sugestao_ignorar", jo("produto" to x.getInt("produto"), "valor" to true)) {
                        avisos.mostrar("Deixámos de sugerir ${x.txtOu("nome")}.") { acoes.executar("desfazer", "compras.sugestao_ignorar", jo("produto" to x.getInt("produto"), "valor" to false)) }
                    }
                })
            }
        }
    }
    Bloco(titulo = "Sugestões") {
        Meta("Calculadas do que costumas comprar. Ignora à vontade: nada é adicionado sozinho.")
        if (acabar.isNotEmpty()) {
            Texto("Talvez esteja a acabar", Pulse.card)
            acabar.forEach { linha(it, "Costumas comprar de ${it.optInt("intervaloDias")} em ${it.optInt("intervaloDias")} dias · última compra há ${it.optInt("diasDesde")} dias")() }
        }
        if (frequentes.isNotEmpty()) {
            Texto("Costumas comprar", Pulse.card)
            frequentes.forEach { linha(it, "${it.optInt("compras")} ${if (it.optInt("compras") == 1) "vez" else "vezes"} nos últimos 90 dias · última há ${it.optInt("diasDesde")} ${if (it.optInt("diasDesde") == 1) "dia" else "dias"}")() }
        }
    }
}

@Composable
private fun GerirLista(l: JSONObject, acoes: Acoes, avisos: Avisos, aoApagar: () -> Unit) {
    var nome by remember(l.getInt("id")) { mutableStateOf(l.txtOu("nome")) }
    var apagar by remember { mutableStateOf(false) }
    Bloco {
        Campo("Nome da lista", nome, { nome = it.take(60) })
        Botao("Renomear", { acoes.executar("lista-nome", "compras.lista_editar", jo("lista" to l.getInt("id"), "nome" to nome.trim())) { avisos.mostrar("Lista renomeada.") } },
            variante = Variante.SECUNDARIO, pequeno = true, ativo = nome.isNotBlank() && nome.trim() != l.txtOu("nome") && acoes.ocupado == null, carregando = acoes.ocupado == "lista-nome")
        LinkBtn("Apagar esta lista", { apagar = true })
    }
    if (apagar) Confirmar("Apagar a lista", "Apagar «${l.txtOu("nome")}» e os seus ${l.inteiro("total")} itens?", "Apagar lista", true, {
        apagar = false
        acoes.executar("lista-apagar", "compras.lista_apagar", jo("lista" to l.getInt("id")), true) { aoApagar(); avisos.mostrar("Lista apagada.") }
    }, { apagar = false })
}

// --- Catálogo -------------------------------------------------------------------------------------------------------------------------

@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun ColumnScope.CatalogoTab(d: JSONObject, acoes: Acoes, avisos: Avisos) {
    val admin = LocalUtilizador.current.admin
    var busca by remember { mutableStateOf("") }
    var filtro by remember { mutableStateOf("todos") }
    var gerir by remember { mutableStateOf(false) }
    var criar by remember { mutableStateOf(false) }
    var editar by remember { mutableStateOf<Int?>(null) }
    val q = semAcentos(busca.trim())
    val categorias = d.objs("categorias"); val produtos = d.objs("produtos")
    val ocultas = categorias.filter { it.bool("oculta") }.map { it.txtOu("id") }.toSet()
    val lista = d.getJSONObject("lista").getInt("id")

    val visiveis = produtos.filter { p ->
        val estado = p.txt("estado")
        when {
            p.bool("oculto") && !gerir && estado == null -> false           // escondidos só em «Gerir» (ou se já estão na lista)
            p.txtOu("categoria") in ocultas && q.isEmpty() && estado == null -> false
            q.isNotEmpty() && !semAcentos(p.txtOu("nome")).contains(q) -> false
            filtro == "favoritos" -> p.bool("favorito")
            else -> filtro == "todos" || p.txtOu("categoria") == filtro
        }
    }
    val porCategoria = categorias.filter { it.txtOu("id") !in ocultas || q.isNotEmpty() || visiveis.any { p -> p.txtOu("categoria") == it.txtOu("id") } }
        .map { it to visiveis.filter { p -> p.txtOu("categoria") == it.txtOu("id") } }.filter { it.second.isNotEmpty() }
    val existeExato = q.isNotEmpty() && produtos.any { semAcentos(it.txtOu("nome")) == q }

    fun tocar(p: JSONObject) {
        if (gerir) { editar = p.getInt("id"); return }
        val id = p.getInt("id")
        if (p.txt("estado") == "pendente" && p.inteiroOuNull("item") != null) {
            acoes.executar("p-$id", "compras.remover", jo("item" to p.getInt("item"))) { r ->
                avisos.mostrar("${p.txtOu("nome")} tirado da lista.") { acoes.executar("desfazer", "compras.restaurar", restaurar(lista, listOf(r))) }
            }
        } else acoes.executar("p-$id", "compras.adicionar", jo("lista" to lista, "produto" to id)) { avisos.mostrar("${p.txtOu("nome")} na lista.") }
    }
    fun esconderCategoria(id: String, nome: String, valor: Boolean) {
        acoes.executar("cat-$id", "compras.categoria_ocultar", jo("categoria" to id, "valor" to valor)) {
            if (valor && filtro == id) filtro = "todos"
            avisos.mostrar(if (valor) "$nome escondida." else "$nome visível outra vez.") { acoes.executar("desfazer", "compras.categoria_ocultar", jo("categoria" to id, "valor" to !valor)) }
        }
    }

    Campo("Procurar produto", busca, { busca = it; criar = false })
    Filtros(listOf("todos" to "Tudo", "favoritos" to "Favoritos") + categorias.filter { !it.bool("oculta") && produtos.any { p -> p.txtOu("categoria") == it.txtOu("id") } }.map { it.txtOu("id") to it.txtOu("nome") },
        filtro) { filtro = it }
    Interruptor("Gerir catálogo", gerir, { gerir = it; editar = null }, if (gerir) "Toca num produto para o gerir (esconder; editar ou apagar os teus)." else null)
    ErroAcao(acoes)
    if (q.isNotEmpty() && !existeExato) Botao("Criar «${busca.trim()}»", { criar = true }, variante = Variante.SECUNDARIO, pequeno = true)

    if (gerir && q.isEmpty() && categorias.any { it.bool("oculta") }) Bloco(titulo = "Categorias escondidas") {
        categorias.filter { it.bool("oculta") }.forEach { c ->
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Texto(c.txtOu("nome"), modifier = Modifier.weight(1f)); LinkBtn("Mostrar", { esconderCategoria(c.txtOu("id"), c.txtOu("nome"), false) })
            }
        }
    }
    if (visiveis.isEmpty()) Texto2(if (filtro == "favoritos") "Ainda não marcaste favoritos. Toca na estrela de um produto." else "Nenhum produto encontrado.")
    val (fechadas, guardarFechadas) = rememberFechadas("compras.fechadas.catalogo")
    val idsCat = porCategoria.map { it.first.txtOu("id") }
    if (porCategoria.size > 1 && q.isEmpty()) LinkBtn(if (idsCat.all { it in fechadas }) "Expandir todas" else "Encolher todas", { guardarFechadas(if (idsCat.all { it in fechadas }) emptySet() else idsCat.toSet()) })
    porCategoria.forEach { (cat, ps) ->
        val id = cat.txtOu("id"); val aberto = q.isNotEmpty() || id !in fechadas       // a pesquisa mostra sempre os resultados
        CabecalhoRecolhivel(cat.txtOu("nome"), ps.size, aberto, { if (q.isEmpty()) guardarFechadas(if (aberto) fechadas + id else fechadas - id) }) {
            if (gerir && q.isEmpty()) LinkBtn("Esconder", { esconderCategoria(id, cat.txtOu("nome"), true) })
        }
        if (aberto) Grelha(ps, 3) { p -> Azulejo(p, gerir, acoes) { tocar(p) } }
    }

    if (criar) FolhaCriarProduto(busca.trim(), d, acoes, avisos) { criar = false; busca = "" }
    editar?.let { id -> produtos.firstOrNull { it.getInt("id") == id }?.let { FolhaEditarProduto(it, d, acoes, avisos, admin) { editar = null } } }
}

@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun <T> Grelha(itens: List<T>, colunas: Int, celula: @Composable (T) -> Unit) {
    FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp), maxItemsInEachRow = colunas) {
        itens.forEach { Box(Modifier.weight(1f)) { celula(it) } }
        repeat((colunas - itens.size % colunas) % colunas) { Spacer(Modifier.weight(1f)) }
    }
}

@Composable
private fun Azulejo(p: JSONObject, gerir: Boolean, acoes: Acoes, aoTocar: () -> Unit) {
    val c = Pulse.cores
    val naLista = p.txt("estado") == "pendente"; val comprado = p.txt("estado") == "comprado"
    val id = p.getInt("id")
    Box(Modifier.fillMaxWidth()) {
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(Pulse.rM)).background(if (naLista) c.surface2 else c.surface)
            .border(if (naLista) 2.dp else 1.dp, if (naLista) c.primary else c.line, RoundedCornerShape(Pulse.rM))
            .clickable(enabled = acoes.ocupado == null, onClick = aoTocar).padding(10.dp),
            horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(4.dp)) {
            ShopIcon(p.txtOu("icone"), if (comprado || p.bool("oculto")) c.text2 else if (naLista) c.primary else c.text, 28.dp)
            Text(p.txtOu("nome"), style = Pulse.meta, color = c.text, maxLines = 2, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
        }
        Text(if (p.bool("favorito")) "★" else "☆", color = if (p.bool("favorito")) c.warning else c.text2, style = Pulse.body,
            modifier = Modifier.align(Alignment.TopEnd).clip(RoundedCornerShape(50)).clickable(enabled = acoes.ocupado == null) {
                acoes.executar("f-$id", "compras.favorito", jo("produto" to id, "valor" to !p.bool("favorito")))
            }.padding(horizontal = 6.dp, vertical = 2.dp))
    }
}

@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun EscolherCategoriaIcone(d: JSONObject, categoria: String, aoCategoria: (String) -> Unit, icone: String?, aoIcone: (String?) -> Unit) {
    val ctx = LocalContext.current
    val c = Pulse.cores
    Seletor("Categoria", d.objs("categorias").map { it.txtOu("id") to it.txtOu("nome") }, categoria, aoCategoria)
    Texto("Ícone", Pulse.body2.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.Medium))
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        val opcoes = listOf<String?>(null) + ShopIcons.nomes(ctx)
        opcoes.forEach { n ->
            val sel = icone == n
            Box(Modifier.size(44.dp).clip(RoundedCornerShape(Pulse.rS)).background(if (sel) c.surface2 else c.surface).border(if (sel) 2.dp else 1.dp, if (sel) c.primary else c.line, RoundedCornerShape(Pulse.rS))
                .clickable { aoIcone(n) }, contentAlignment = Alignment.Center) {
                if (n == null) Text("Auto", style = Pulse.meta, color = c.text) else ShopIcon(n, if (sel) c.primary else c.text, 22.dp)
            }
        }
    }
}

@Composable
private fun FolhaCriarProduto(nome: String, d: JSONObject, acoes: Acoes, avisos: Avisos, aoFechar: () -> Unit) {
    var categoria by remember { mutableStateOf("outros") }
    var icone by remember { mutableStateOf<String?>(null) }
    Folha("Criar «$nome»", aoFechar) {
        EscolherCategoriaIcone(d, categoria, { categoria = it }, icone) { icone = it }
        ErroAcao(acoes)
        Botao("Criar e pôr na lista", {
            val p = jo("lista" to d.getJSONObject("lista").getInt("id"), "nome" to nome, "categoria" to categoria)
            icone?.let { p.put("icone", it) }
            acoes.executar("criar", "compras.adicionar", p) { avisos.mostrar("$nome criado e posto na lista."); aoFechar() }
        }, grande = true, ativo = acoes.ocupado == null, carregando = acoes.ocupado == "criar")
    }
}

@Composable
private fun FolhaEditarProduto(p: JSONObject, d: JSONObject, acoes: Acoes, avisos: Avisos, admin: Boolean, aoFechar: () -> Unit) {
    var nome by remember { mutableStateOf(p.txtOu("nome")) }
    var categoria by remember { mutableStateOf(p.txtOu("categoria")) }
    var icone by remember { mutableStateOf<String?>(p.txtOu("icone")) }
    var apagar by remember { mutableStateOf(false) }
    val proprio = !p.bool("builtin")
    Folha(p.txtOu("nome"), aoFechar) {
        if (proprio) {
            Campo("Nome", nome, { nome = it.take(80) })
            EscolherCategoriaIcone(d, categoria, { categoria = it }, icone) { icone = it }
            Botao("Guardar", {
                val params = jo("produto" to p.getInt("id"))
                if (nome.trim() != p.txtOu("nome")) params.put("nome", nome.trim())
                if (categoria != p.txtOu("categoria")) params.put("categoria", categoria)
                if (icone != null && icone != p.txtOu("icone")) params.put("icone", icone)
                if (params.length() == 1) aoFechar()
                else acoes.executar("prod", "compras.produto_editar", params) { avisos.mostrar("Produto atualizado."); aoFechar() }
            }, grande = true, ativo = nome.isNotBlank() && acoes.ocupado == null, carregando = acoes.ocupado == "prod")
        } else Meta("Produto de série: podes escondê-lo ou marcá-lo como favorito, mas não alterá-lo.")
        ErroAcao(acoes)
        Botao(if (p.bool("oculto")) "Mostrar no catálogo" else "Esconder do catálogo", {
            acoes.executar("oculto", "compras.ocultar", jo("produto" to p.getInt("id"), "valor" to !p.bool("oculto"))) { aoFechar() }
        }, variante = Variante.SECUNDARIO, pequeno = true, ativo = acoes.ocupado == null)
        if (proprio) LinkBtn("Apagar produto", { apagar = true })
        if (proprio && !admin) Meta("Só quem o criou (ou o administrador) altera ou apaga.")
    }
    if (apagar) Confirmar("Apagar produto", "Apagar «${p.txtOu("nome")}» do catálogo?", "Apagar produto", true, {
        apagar = false
        acoes.executar("prod", "compras.produto_apagar", jo("produto" to p.getInt("id")), true) {
            avisos.mostrar("${p.txtOu("nome")} apagado.") { acoes.executar("desfazer", "compras.produto_criar", jo("nome" to p.txtOu("nome"), "categoria" to p.txtOu("categoria"), "icone" to p.txtOu("icone"))) }
            aoFechar()
        }
    }, { apagar = false })
}
