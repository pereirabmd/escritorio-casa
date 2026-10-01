package pt.pereirabmd.pulse.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.lifecycle.repeatOnLifecycle
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import pt.pereirabmd.pulse.data.Api
import pt.pereirabmd.pulse.data.mensagemDeErro
import java.time.LocalDate
import java.time.LocalTime
import java.util.UUID

// --- JSON de pedidos ------------------------------------------------------------------------------------------------------------------

/** `jo("a" to 1, "b" to null)`: o `null` vai como JSON `null` (apaga o campo no servidor), não some. */
fun jo(vararg pares: Pair<String, Any?>): JSONObject = JSONObject().also { o -> pares.forEach { (k, v) -> o.put(k, v ?: JSONObject.NULL) } }
fun ja(itens: Iterable<Any?>): JSONArray = JSONArray().also { a -> itens.forEach { a.put(it ?: JSONObject.NULL) } }
fun novoCid(): String = UUID.randomUUID().toString()

// --- Carregar dados -------------------------------------------------------------------------------------------------------------------

sealed interface Estado<out T> {
    data object ACarregar : Estado<Nothing>
    data class Erro(val mensagem: String) : Estado<Nothing>
    data class Pronto<T>(val dados: T) : Estado<T>
}

class Carga<T>(val estado: Estado<T>, val recarregar: () -> Unit) {
    val dados: T? get() = (estado as? Estado.Pronto)?.dados
}

/** Pede dados à API; volta a pedir quando a `chave` muda ou se chama `recarregar()`. Enquanto recarrega mantém os dados antigos (sem piscar). */
@Composable
fun <T> carga(chave: Any? = null, pedir: suspend () -> T): Carga<T> {
    var estado by remember(chave) { mutableStateOf<Estado<T>>(Estado.ACarregar) }
    var versao by remember(chave) { mutableIntStateOf(0) }
    val pedirAtual by rememberUpdatedState(pedir)
    LaunchedEffect(chave, versao) {
        estado = try { Estado.Pronto(pedirAtual()) } catch (e: Exception) {
            if (e is kotlinx.coroutines.CancellationException) throw e
            Estado.Erro(mensagemDeErro(e))
        }
    }
    return Carga(estado) { versao++ }
}

/** Mostra o estado de uma carga: loading de marca, erro com «Tentar de novo», ou o conteúdo. */
@Composable
fun <T> Carga<T>.ao(textoCarregar: String = "A carregar…", conteudo: @Composable (T) -> Unit) {
    when (val e = estado) {
        Estado.ACarregar -> BrandLoading(textoCarregar)
        is Estado.Erro -> EstadoErro(e.mensagem, recarregar)
        is Estado.Pronto -> conteudo(e.dados)
    }
}

// --- Avisos curtos (com «Desfazer») e execução de ações --------------------------------------------------------------------------------

/** Confirmação curta de uma ação já feita, com «Desfazer» quando dá. Avisos de condições que se mantêm NÃO vão aqui (ficam no ecrã). */
class Avisos(val host: SnackbarHostState, private val scope: CoroutineScope) {
    fun mostrar(texto: String, desfazer: (() -> Unit)? = null) {
        scope.launch {
            host.currentSnackbarData?.dismiss()
            val r = host.showSnackbar(texto, if (desfazer != null) "Desfazer" else null, duration = SnackbarDuration.Long)
            if (r == SnackbarResult.ActionPerformed) desfazer?.invoke()
        }
    }
}

val LocalAvisos = staticCompositionLocalOf<Avisos> { error("sem Avisos") }

/**
 * Executa ações do Pulse (`POST /actions/<nome>`) com «a executar» por chave e erro em pt-PT (espelho de `useAcao`).
 * `executar` devolve o `resultado` (um objeto, por isso verdadeiro) ou `null` se falhou; chama `depois` só quando correu bem.
 */
class Acoes(private val scope: CoroutineScope, private val depois: (String) -> Unit) {
    var ocupado by mutableStateOf<String?>(null); private set
    var erro by mutableStateOf<String?>(null)

    fun executar(chave: String, nome: String, params: JSONObject, confirmado: Boolean = false, aoFalhar: () -> Unit = {}, aoConcluir: (JSONObject) -> Unit = {}) {
        if (ocupado != null) return
        scope.launch { val r = executarAgora(chave, nome, params, confirmado); if (r != null) aoConcluir(r) else aoFalhar() }
    }

    suspend fun executarAgora(chave: String, nome: String, params: JSONObject, confirmado: Boolean = false): JSONObject? {
        ocupado = chave; erro = null
        return try {
            val corpo = jo("params" to params).also { if (confirmado) it.put("confirmado", true) }
            val r = Api.post("/actions/$nome", corpo, if (nome.startsWith("bilhetes.cp_") || nome == "bilhetes.troca_armar") Api.LEITURA_CP_MS else 20_000).optJSONObject("resultado") ?: JSONObject()
            depois(nome); r
        } catch (e: Exception) {
            if (e is kotlinx.coroutines.CancellationException) throw e
            erro = mensagemDeErro(e); null
        } finally { ocupado = null }
    }
}

@Composable
/** `depois` recebe o nome da ação executada (por exemplo `peso.registar`). */
fun rememberAcoes(depois: (String) -> Unit): Acoes {
    val scope = rememberCoroutineScope()
    val atual by rememberUpdatedState(depois)
    return remember { Acoes(scope) { nome -> atual(nome) } }
}

@Composable
fun ErroAcao(acoes: Acoes) {
    acoes.erro?.let { e ->
        Aviso(TipoAviso.ERRO) { Texto(e, Pulse.body2); LinkBtn("Fechar", { acoes.erro = null }) }
    }
}

// --- Estrutura de ecrãs ---------------------------------------------------------------------------------------------------------------

/** Ecrã de um módulo: cabeçalho com «‹ Mais», título e o conteúdo. */
@Composable
fun EcraModulo(titulo: String, aoVoltar: () -> Unit, subtitulo: String? = null, conteudo: @Composable ColumnScope.() -> Unit) {
    Column(Modifier.fillMaxSize().background().statusBarsPadding()) {
        Column(Modifier.padding(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 4.dp)) {
            LinkBtn("‹ Mais", aoVoltar)
            Texto(titulo, Pulse.page)
            if (subtitulo != null) Texto2(subtitulo)
        }
        conteudo()
    }
}

/** Conteúdo que rola, com o espaçamento do Design System. */
@Composable
fun ColumnScope.Rolar(modifier: Modifier = Modifier, conteudo: @Composable ColumnScope.() -> Unit) {
    Column(modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(10.dp), content = conteudo)
}

@Composable
fun Abas(nomes: List<String>, selecionada: Int, aoMudar: (Int) -> Unit) {
    val c = Pulse.cores
    val separadores: @Composable () -> Unit = {
        nomes.forEachIndexed { i, n ->
            Tab(selected = i == selecionada, onClick = { aoMudar(i) }, text = { Text(n, style = Pulse.body2.copy(fontWeight = FontWeight.Medium), maxLines = 1) },
                selectedContentColor = c.primary, unselectedContentColor = c.text2)
        }
    }
    val indicador: @Composable (List<TabPosition>) -> Unit = { pos -> if (selecionada < pos.size) TabRowDefaults.SecondaryIndicator(with(TabRowDefaults) { Modifier.tabIndicatorOffset(pos[selecionada]) }, color = c.primary) }
    // até 4 separadores curtos cabem no ecrã: repartem a largura (a linha de baixo vai de lado a lado); com mais (ou nomes compridos), rolam
    if (nomes.size <= 4 && nomes.all { it.length <= 10 }) TabRow(selectedTabIndex = selecionada, containerColor = c.bg, contentColor = c.primary, indicator = indicador, divider = { HorizontalDivider(color = c.line) }, tabs = separadores)
    else ScrollableTabRow(selectedTabIndex = selecionada, containerColor = c.bg, contentColor = c.primary, edgePadding = 12.dp, indicator = indicador, divider = { HorizontalDivider(color = c.line) }, tabs = separadores)
}

/** Escolha entre poucas opções (segmentos). */
@Composable
fun <T> Escolha(opcoes: List<Pair<T, String>>, valor: T, aoMudar: (T) -> Unit, modifier: Modifier = Modifier) {
    val c = Pulse.cores
    Row(modifier.clip(RoundedCornerShape(Pulse.rM)).border(1.dp, c.line, RoundedCornerShape(Pulse.rM)), horizontalArrangement = Arrangement.spacedBy(0.dp)) {
        opcoes.forEach { (v, nome) ->
            val sel = v == valor
            Box(Modifier.weight(1f).background(if (sel) c.primary else c.surface).clickable { aoMudar(v) }.padding(vertical = 10.dp, horizontal = 8.dp), contentAlignment = Alignment.Center) {
                Text(nome, style = Pulse.body2.copy(fontWeight = FontWeight.Medium), color = if (sel) c.primaryInk else c.text)
            }
        }
    }
}

/** Filtros em linha (chips). */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun <T> Filtros(opcoes: List<Pair<T, String>>, valor: T, aoMudar: (T) -> Unit) {
    CompositionLocalProvider(LocalMinimumInteractiveComponentEnforcement provides false) {
    // sem `fillMaxWidth`: numa linha com outro elemento (legenda, «Hoje») ocupava a largura toda e deixava o vizinho sem espaço (uma letra por linha)
    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        opcoes.forEach { (v, nome) ->
            FilterChip(selected = v == valor, onClick = { aoMudar(v) }, label = { Text(nome, style = Pulse.body2) },
                colors = FilterChipDefaults.filterChipColors(selectedContainerColor = Pulse.cores.primary, selectedLabelColor = Pulse.cores.primaryInk, containerColor = Pulse.cores.surface, labelColor = Pulse.cores.text),
                border = FilterChipDefaults.filterChipBorder(true, v == valor, borderColor = Pulse.cores.line, selectedBorderColor = Pulse.cores.primary))
        }
    }
    }
}

// --- Formulários ---------------------------------------------------------------------------------------------------------------------

/** Só os testes de capturas a ligam: as folhas passam a desenhar-se no próprio ecrã. */
internal var folhasEmLinha = false

/** Folha de baixo para criar/editar. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun Folha(titulo: String, aoFechar: () -> Unit, conteudo: @Composable ColumnScope.() -> Unit) {
    val c = Pulse.cores
    if (folhasEmLinha) {                 // só nas capturas de ecrãs (testes JVM): o diálogo da folha não entra na imagem
        Column(Modifier.fillMaxWidth().background(c.surface).padding(horizontal = 16.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) { Texto(titulo, Pulse.section); conteudo() }
        return
    }
    ModalBottomSheet(onDismissRequest = aoFechar, containerColor = c.surface, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)) {
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp).padding(bottom = 24.dp).navigationBarsPadding().imePadding(),
            verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Texto(titulo, Pulse.section)
            conteudo()
        }
    }
}

@Composable
fun Confirmar(titulo: String, texto: String, rotulo: String = "Confirmar", perigo: Boolean = false, aoConfirmar: () -> Unit, aoCancelar: () -> Unit) {
    val c = Pulse.cores
    AlertDialog(onDismissRequest = aoCancelar, containerColor = c.surface,
        title = { Texto(titulo, Pulse.section) }, text = { Texto2(texto) },
        confirmButton = { TextButton(onClick = aoConfirmar) { Text(rotulo, color = if (perigo) c.error else c.primary) } },
        dismissButton = { TextButton(onClick = aoCancelar) { Text("Cancelar", color = c.text2) } })
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CampoData(rotulo: String, valor: String, aoMudar: (String) -> Unit, modifier: Modifier = Modifier, minimo: String? = null, opcional: Boolean = false) {
    val c = Pulse.cores
    var aberto by remember { mutableStateOf(false) }
    Column(modifier, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(rotulo, style = Pulse.body2.copy(fontWeight = FontWeight.Medium), color = c.text)
        Row(Modifier.fillMaxWidth().heightIn(min = 52.dp).clip(RoundedCornerShape(Pulse.rM)).background(c.surface).border(1.dp, c.line, RoundedCornerShape(Pulse.rM)).clickable { aberto = true }.padding(horizontal = 16.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Texto(if (valor.isEmpty()) "Escolher data" else pt.pereirabmd.pulse.util.fmtDataIso(valor), Pulse.body, if (valor.isEmpty()) c.text2 else c.text, Modifier.weight(1f))
            if (opcional && valor.isNotEmpty()) LinkBtn("Limpar", { aoMudar("") })
            Icon(Icone.CALENDARIO, c.text2, 20.dp)
        }
    }
    if (aberto) {
        val ms = valor.takeIf { it.length >= 10 }?.let { runCatching { LocalDate.parse(it.take(10)).atStartOfDay(java.time.ZoneOffset.UTC).toInstant().toEpochMilli() }.getOrNull() }
        val min = minimo?.let { runCatching { LocalDate.parse(it.take(10)).atStartOfDay(java.time.ZoneOffset.UTC).toInstant().toEpochMilli() }.getOrNull() }
        val estado = rememberDatePickerState(initialSelectedDateMillis = ms, selectableDates = object : SelectableDates {
            override fun isSelectableDate(utcTimeMillis: Long) = min == null || utcTimeMillis >= min
        })
        DatePickerDialog(onDismissRequest = { aberto = false },
            confirmButton = { TextButton({
                estado.selectedDateMillis?.let { aoMudar(java.time.Instant.ofEpochMilli(it).atZone(java.time.ZoneOffset.UTC).toLocalDate().toString()) }; aberto = false
            }) { Text("Escolher", color = c.primary) } },
            dismissButton = { TextButton({ aberto = false }) { Text("Cancelar", color = c.text2) } },
            colors = DatePickerDefaults.colors(containerColor = c.surface)) { DatePicker(estado, colors = DatePickerDefaults.colors(containerColor = c.surface, selectedDayContainerColor = c.primary, todayDateBorderColor = c.primary)) }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CampoHora(rotulo: String, valor: String, aoMudar: (String) -> Unit, modifier: Modifier = Modifier, opcional: Boolean = true) {
    val c = Pulse.cores
    var aberto by remember { mutableStateOf(false) }
    Column(modifier, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(rotulo, style = Pulse.body2.copy(fontWeight = FontWeight.Medium), color = c.text)
        Row(Modifier.fillMaxWidth().heightIn(min = 52.dp).clip(RoundedCornerShape(Pulse.rM)).background(c.surface).border(1.dp, c.line, RoundedCornerShape(Pulse.rM)).clickable { aberto = true }.padding(horizontal = 16.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Texto(valor.ifEmpty { "Sem hora" }, Pulse.body, if (valor.isEmpty()) c.text2 else c.text, Modifier.weight(1f))
            if (opcional && valor.isNotEmpty()) LinkBtn("Limpar", { aoMudar("") })
        }
    }
    if (aberto) {
        val t = valor.takeIf { it.length >= 5 }?.let { runCatching { LocalTime.parse(it.take(5)) }.getOrNull() } ?: LocalTime.of(9, 0)
        val estado = rememberTimePickerState(t.hour, t.minute, is24Hour = true)
        AlertDialog(onDismissRequest = { aberto = false }, containerColor = c.surface,
            text = { TimePicker(estado, colors = TimePickerDefaults.colors(selectorColor = c.primary, clockDialSelectedContentColor = c.primaryInk)) },
            confirmButton = { TextButton({ aoMudar("%02d:%02d".format(estado.hour, estado.minute)); aberto = false }) { Text("Escolher", color = c.primary) } },
            dismissButton = { TextButton({ aberto = false }) { Text("Cancelar", color = c.text2) } })
    }
}

/** Menu de escolha de uma opção (lista suspensa). */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun <T> Seletor(rotulo: String, opcoes: List<Pair<T, String>>, valor: T?, aoMudar: (T) -> Unit, modifier: Modifier = Modifier, vazio: String = "Escolher") {
    val c = Pulse.cores
    var aberto by remember { mutableStateOf(false) }
    Column(modifier, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(rotulo, style = Pulse.body2.copy(fontWeight = FontWeight.Medium), color = c.text)
        Box {
            Row(Modifier.fillMaxWidth().heightIn(min = 52.dp).clip(RoundedCornerShape(Pulse.rM)).background(c.surface).border(1.dp, c.line, RoundedCornerShape(Pulse.rM)).clickable { aberto = true }.padding(horizontal = 16.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                val nome = opcoes.firstOrNull { it.first == valor }?.second
                Texto(nome ?: vazio, Pulse.body, if (nome == null) c.text2 else c.text, Modifier.weight(1f))
                Icon(Icone.SETA, c.text2, 16.dp)
            }
            DropdownMenu(aberto, { aberto = false }, Modifier.background(c.surface)) {
                opcoes.forEach { (v, n) -> DropdownMenuItem(text = { Text(n, color = c.text) }, onClick = { aoMudar(v); aberto = false }) }
            }
        }
    }
}

@Composable
fun Interruptor(texto: String, valor: Boolean, aoMudar: (Boolean) -> Unit, sub: String? = null) {
    Row(Modifier.fillMaxWidth().heightIn(min = 48.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Column(Modifier.weight(1f)) { Texto(texto); if (sub != null) Meta(sub) }
        Switch(valor, aoMudar, colors = SwitchDefaults.colors(checkedTrackColor = Pulse.cores.primary))
    }
}

/** Botão «check» redondo das listas (concluir/comprar/pagar). */
@Composable
fun Visto(feito: Boolean, aoClicar: () -> Unit, descricao: String, ocupado: Boolean = false, ativo: Boolean = true) {
    val c = Pulse.cores
    Box(Modifier.size(40.dp).clip(androidx.compose.foundation.shape.CircleShape).border(1.5.dp, if (feito) c.success else c.line, androidx.compose.foundation.shape.CircleShape)
        .background(if (feito) c.success else Color.Transparent).clickable(enabled = ativo && !ocupado, onClick = aoClicar)
        .androidxSemantics(descricao), contentAlignment = Alignment.Center) {
        if (ocupado) CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp, color = c.primary)
        else Icon(Icone.CERTO, if (feito) c.primaryInk else c.text2, 18.dp)
    }
}

private fun Modifier.androidxSemantics(d: String) = this.then(Modifier.semantics { contentDescription = d })

@Composable
fun Vazio(texto: String) = Box(Modifier.fillMaxWidth().padding(vertical = 24.dp), contentAlignment = Alignment.Center) { Texto2(texto) }

@Composable
fun LinhaValor(rotulo: String, valor: String, destaque: Color? = null) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Texto2(rotulo); Texto(valor, Pulse.body2.copy(fontWeight = FontWeight.SemiBold), destaque ?: Pulse.cores.text)
    }
}

/** Número decimal com vírgula ou ponto: «104,8» → 104.8; vazio/ inválido → null. */
fun lerDecimal(t: String): Double? = t.trim().replace(',', '.').takeIf { it.isNotEmpty() }?.toDoubleOrNull()?.takeIf { it.isFinite() }
fun decimalTexto(v: Double?): String = if (v == null) "" else (if (v % 1.0 == 0.0) v.toLong().toString() else v.toString()).replace('.', ',')

val TecladoNumero = KeyboardType.Decimal

val LocalUtilizador = staticCompositionLocalOf<pt.pereirabmd.pulse.data.Utilizador> { error("sem utilizador") }

/** Bloco (superfície com contorno) sem cabeçalho: as secções dentro dos ecrãs. */
@Composable
fun Bloco(modifier: Modifier = Modifier, titulo: String? = null, extra: @Composable RowScope.() -> Unit = {}, conteudo: @Composable ColumnScope.() -> Unit) {
    val c = Pulse.cores
    Column(modifier.fillMaxWidth().clip(RoundedCornerShape(Pulse.rL)).background(c.surface).border(1.dp, c.line, RoundedCornerShape(Pulse.rL)).padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (titulo != null) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(titulo, style = Pulse.card, color = c.text, modifier = Modifier.weight(1f)); extra()
        }
        conteudo()
    }
}

/** Dados partilhados que outros alteram: volta a pedir de tempos a tempos enquanto o ecrã está à vista. */
@Composable
fun AtualizarPeriodicamente(ms: Long, recarregar: () -> Unit) {
    val dono = androidx.lifecycle.compose.LocalLifecycleOwner.current
    val atual by rememberUpdatedState(recarregar)
    LaunchedEffect(dono) {
        dono.lifecycle.repeatOnLifecycle(androidx.lifecycle.Lifecycle.State.RESUMED) {
            while (true) { kotlinx.coroutines.delay(ms); atual() }
        }
    }
}

/** Estado de uma carga dentro de um ecrã de módulo: loading de marca, erro com «Tentar de novo», ou o conteúdo (a rolar). */
@Composable
fun <T> ColumnScope.Ao(c: Carga<T>, texto: String = "A carregar…", conteudo: @Composable ColumnScope.(T) -> Unit) {
    when (val e = c.estado) {
        Estado.ACarregar -> Rolar { BrandLoading(texto) }
        is Estado.Erro -> Rolar { EstadoErro(e.mensagem, c.recarregar) }
        is Estado.Pronto -> conteudo(e.dados)
    }
}

/** Navega para um módulo (`tarefas`, `peso`…) ou ecrã (`google`) a partir de qualquer cartão. */
val LocalAbrir = staticCompositionLocalOf<(String) -> Unit> { {} }

/** Chips de escolha múltipla (dias da semana, rotação de pessoas…). */
@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class, ExperimentalMaterial3Api::class)
@Composable
fun MultiChips(opcoes: List<Pair<String, String>>, selecionados: List<String>, aoAlternar: (String) -> Unit) {
    val c = Pulse.cores
    CompositionLocalProvider(LocalMinimumInteractiveComponentEnforcement provides false) {
    androidx.compose.foundation.layout.FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        opcoes.forEach { (v, nome) ->
            FilterChip(selected = v in selecionados, onClick = { aoAlternar(v) }, label = { Text(nome, style = Pulse.body2) },
                colors = FilterChipDefaults.filterChipColors(selectedContainerColor = c.primary, selectedLabelColor = c.primaryInk, containerColor = c.surface, labelColor = c.text),
                border = FilterChipDefaults.filterChipBorder(true, v in selecionados, borderColor = c.line, selectedBorderColor = c.primary))
        }
    }
    }
}

/** Preferências locais de interface (filtro escolhido, última categoria…): só conveniência, nunca dados. */
object UiPrefs {
    private fun p(ctx: android.content.Context) = ctx.getSharedPreferences("pulse_ui", android.content.Context.MODE_PRIVATE)
    fun ler(ctx: android.content.Context, k: String, por: String = ""): String = try { p(ctx).getString(k, por) ?: por } catch (_: Exception) { por }
    fun guardar(ctx: android.content.Context, k: String, v: String) { try { p(ctx).edit().putString(k, v).apply() } catch (_: Exception) { } }
}

/** O logo do Pulse (no lugar do ícone genérico do «Hoje»). */
@Composable
fun LogoPulse(tamanho: androidx.compose.ui.unit.Dp = 24.dp, alfa: Float = 1f, modifier: Modifier = Modifier) {
    androidx.compose.foundation.Image(androidx.compose.ui.res.painterResource(pt.pereirabmd.pulse.R.drawable.pulse_icon), null, modifier.size(tamanho), alpha = alfa)
}

/** Cabeçalho de uma secção que se expande e encolhe (categorias das Compras). */
@Composable
fun CabecalhoRecolhivel(titulo: String, contagem: Int?, aberto: Boolean, aoAlternar: () -> Unit, modifier: Modifier = Modifier, extra: @Composable RowScope.() -> Unit = {}) {
    val c = Pulse.cores
    Row(modifier.fillMaxWidth().clip(RoundedCornerShape(Pulse.rS)).clickable(onClick = aoAlternar).padding(vertical = 4.dp).semantics { contentDescription = "$titulo, ${if (aberto) "expandida" else "encolhida"}" },
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Icon(Icone.SETA, c.text2, 16.dp, Modifier.rotate(if (aberto) 90f else 0f))
        Text(titulo, style = Pulse.card, color = c.text, modifier = Modifier.weight(1f, fill = false))
        if (contagem != null) Text("$contagem", style = Pulse.meta, color = c.text2)
        Spacer(Modifier.weight(1f))
        extra()
    }
}

/** As secções encolhidas guardam-se no telemóvel (por ecrã), separadas por vírgulas. */
@Composable
fun rememberFechadas(chave: String): Pair<Set<String>, (Set<String>) -> Unit> {
    val ctx = androidx.compose.ui.platform.LocalContext.current
    var s by remember(chave) { mutableStateOf(UiPrefs.ler(ctx, chave).split(',').filter { it.isNotEmpty() }.toSet()) }
    return s to { novo -> s = novo; UiPrefs.guardar(ctx, chave, novo.joinToString(",")) }
}
