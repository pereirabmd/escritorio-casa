package pt.pereirabmd.pulse.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.runtime.*
import androidx.compose.ui.unit.dp
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import org.json.JSONObject
import pt.pereirabmd.pulse.data.*
import pt.pereirabmd.pulse.util.*

private data class Form(
    val id: String?, val nome: String, val categoria: String, val recorrencia: String, val dias: List<String>, val data: String, val diaMes: String,
    val hora: String, val pessoa: String, val prioridade: String, val rotacao: List<String>, val dependeDe: String, val copia: Boolean = false,
)

private fun vazio(d: JSONObject, ultima: String): Form = Form(null, "", d.strs("categorias").let { if (ultima in it) ultima else it.firstOrNull() ?: "" }, "Diaria", emptyList(), "", "1", "08:00",
    d.strs("pessoas").firstOrNull() ?: "", "Media", emptyList(), "")

private fun deTarefa(t: JSONObject, copia: Boolean): Form {
    val ehData = t.txtOu("recorrencia") in COM_DATA
    return Form(if (copia) null else t.txtOu("id"), if (copia) "${t.txtOu("nome")} (cópia)" else t.txtOu("nome"), t.txtOu("categoria"), t.txtOu("recorrencia"),
        if (ehData) emptyList() else t.txtOu("diasSemana").split(',').filter { it.isNotEmpty() }, if (ehData) t.txtOu("diasSemana") else "", (t.inteiroOuNull("diaMes") ?: 1).toString(),
        t.txtOu("horaNotificacao").ifEmpty { "08:00" }, t.txtOu("pessoaPadrao"), t.txtOu("prioridade").ifEmpty { "Media" },
        t.txtOu("rotacaoPessoas").split(',').filter { it.isNotEmpty() }, t.txtOu("dependeDe"), copia)
}

@Composable
fun ColumnScope.CatalogoTab(d: JSONObject, acoes: Acoes) {
    val avisos = LocalAvisos.current; val ctx = LocalContext.current
    var form by remember { mutableStateOf<Form?>(null) }
    var pesquisa by remember { mutableStateOf("") }
    val termo = pesquisa.trim().lowercase()
    val tarefas = d.objs("tarefas")
    val lista = if (termo.isEmpty()) tarefas else tarefas.filter { t -> listOf(t.txtOu("nome"), t.txtOu("categoria"), t.txtOu("pessoaPadrao")).any { it.lowercase().contains(termo) } }
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.Bottom) {
        Campo("Pesquisar por nome, categoria ou pessoa", pesquisa, { pesquisa = it }, Modifier.weight(1f))
    }
    Botao("Nova tarefa", { form = vazio(d, UiPrefs.ler(ctx, "tarefas.ultimaCategoria")) }, pequeno = true)
    Bloco(titulo = "Tarefas  ${lista.size}") {
        if (tarefas.isEmpty()) Texto2("Ainda não há tarefas. Cria a primeira em «Nova tarefa».")
        else if (lista.isEmpty()) Texto2("Nenhuma tarefa corresponde à pesquisa.")
        lista.forEach { t ->
            Row(Modifier.fillMaxWidth().clickable { form = deTarefa(t, false) }, verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Texto(t.txtOu("nome"))
                    Meta(listOf(t.txtOu("categoria"), t.txtOu("resumo"), t.txtOu("hora"), t.txtOu("pessoaPadrao")).filter { it.isNotEmpty() }.joinToString(" · ") + if (t.txt("prioridade") == "Alta") " · Prioridade alta" else "")
                }
                Column(horizontalAlignment = Alignment.End) { LinkBtn("Editar", { form = deTarefa(t, false) }); LinkBtn("Duplicar", { form = deTarefa(t, true) }) }
            }
        }
    }
    form?.let { f -> FolhaTarefa(f, d, acoes, avisos) { form = null } }
}

@Composable
private fun FolhaTarefa(inicial: Form, d: JSONObject, acoes: Acoes, avisos: Avisos, aoFechar: () -> Unit) {
    val ctx = LocalContext.current
    var f by remember { mutableStateOf(inicial) }
    var erro by remember { mutableStateOf<String?>(null) }
    var mais by remember { mutableStateOf(inicial.prioridade != "Media" || inicial.rotacao.isNotEmpty() || inicial.dependeDe.isNotEmpty()) }
    var apagar by remember { mutableStateOf(false) }
    val cid = remember { novoCid() }
    val pessoas = d.strs("pessoas"); val categorias = d.strs("categorias")
    Folha(if (f.id != null) "Editar tarefa" else if (f.copia) "Duplicar tarefa" else "Nova tarefa", aoFechar) {
        erro?.let { Aviso(TipoAviso.ERRO, it) }
        Campo("Nome", f.nome, { f = f.copy(nome = it.take(200)) })
        Seletor("Categoria", categorias.map { it to it }, f.categoria.ifEmpty { null }, { f = f.copy(categoria = it) })
        Seletor("Repetição", RECORRENCIAS, f.recorrencia, { f = f.copy(recorrencia = it) })
        CampoHora("Hora do aviso", f.hora, { f = f.copy(hora = it) }, opcional = false)
        if (f.recorrencia in COM_DIAS) {
            Texto("Dias da semana", Pulse.body2.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.Medium))
            MultiChips(DIAS_TAREFA.map { it to (DIAS_NOME[it] ?: it) }, f.dias) { f = f.copy(dias = alterna(f.dias, it)) }
        }
        if (f.recorrencia == "Mensal") Campo("Dia do mês", f.diaMes, { f = f.copy(diaMes = it.filter(Char::isDigit).take(2)) }, teclado = KeyboardType.Number)
        if (f.recorrencia in COM_DATA) CampoData(if (f.recorrencia == "Pontual") "Data" else "Data de início", f.data, { f = f.copy(data = it) })
        if (pessoas.isNotEmpty()) Seletor("Pessoa", pessoas.map { it to it }, f.pessoa.ifEmpty { null }, { f = f.copy(pessoa = it) })
        LinkBtn(if (mais) "− Menos opções" else "+ Mais opções", { mais = !mais })
        if (mais) {
            Texto("Prioridade", Pulse.body2.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.Medium))
            Escolha(listOf("Alta" to "Alta", "Media" to "Média", "Baixa" to "Baixa"), f.prioridade, { f = f.copy(prioridade = it) })
            if (pessoas.isNotEmpty()) {
                Texto("Rotação entre pessoas", Pulse.body2.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.Medium))
                MultiChips(pessoas.map { it to it }, f.rotacao) { f = f.copy(rotacao = alterna(f.rotacao, it)) }
            }
            Seletor("Só depois de…", listOf("" to "— Nenhuma dependência —") + d.objs("tarefas").filter { it.txtOu("id") != f.id }.map { it.txtOu("id") to it.txtOu("nome") }, f.dependeDe, { f = f.copy(dependeDe = it) })
        }
        ErroAcao(acoes)
        Botao("Guardar", {
            if (f.nome.isBlank() || f.categoria.isEmpty()) { erro = "Preenche o nome e a categoria."; return@Botao }
            if (f.recorrencia in COM_DIAS && f.dias.isEmpty()) { erro = "Escolhe pelo menos um dia da semana."; return@Botao }
            if (f.recorrencia in COM_DATA && f.data.isEmpty()) { erro = if (f.recorrencia == "Pontual") "Escolhe a data." else "Escolhe a data de início."; return@Botao }
            val dm = f.diaMes.toIntOrNull()
            if (f.recorrencia == "Mensal" && (dm == null || dm !in 1..31)) { erro = "Dia do mês inválido."; return@Botao }
            erro = null
            val base = jo("nome" to f.nome.trim(), "categoria" to f.categoria, "recorrencia" to f.recorrencia, "hora" to f.hora, "pessoa" to f.pessoa, "prioridade" to f.prioridade,
                "rotacao" to ja(f.rotacao), "dependeDe" to f.dependeDe)
            if (f.recorrencia in COM_DIAS) base.put("dias", ja(f.dias))
            if (f.recorrencia in COM_DATA) base.put("data", f.data)
            if (f.recorrencia == "Mensal") base.put("diaMes", dm)
            UiPrefs.guardar(ctx, "tarefas.ultimaCategoria", f.categoria)
            if (f.id != null) { base.put("tarefa", f.id); acoes.executar("form", "tarefas.editar", base) { avisos.mostrar("Tarefa atualizada."); aoFechar() } }
            else { base.put("cid", cid); acoes.executar("form", "tarefas.criar", base) { avisos.mostrar("Tarefa criada."); aoFechar() } }
        }, grande = true, ativo = acoes.ocupado == null, carregando = acoes.ocupado == "form")
        if (f.id != null) LinkBtn("Apagar tarefa", { apagar = true })
    }
    if (apagar && f.id != null) Confirmar("Apagar tarefa", "Apagar? O histórico mantém-se; as pendentes desaparecem.", "Apagar", true, {
        apagar = false
        acoes.executar("del", "tarefas.apagar", jo("tarefa" to f.id), true) { aoFechar(); avisos.mostrar("Tarefa apagada.") }
    }, { apagar = false })
}
