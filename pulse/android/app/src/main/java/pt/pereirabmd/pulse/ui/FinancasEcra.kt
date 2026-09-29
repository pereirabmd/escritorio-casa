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
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import org.json.JSONObject
import pt.pereirabmd.pulse.data.*
import pt.pereirabmd.pulse.util.*

private val ABAS = listOf("Resumo", "Lançamentos", "Relatórios", "Categorias", "Lembretes")

private fun corDe(hex: String?, por: Color): Color = if (hex == null) por else try { Color(android.graphics.Color.parseColor(hex)) } catch (_: Exception) { por }

@Composable
private fun Barra(fracao: Float, cor: Color) {
    Box(Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(50)).background(Pulse.cores.surface2)) {
        Box(Modifier.fillMaxWidth(fracao.coerceIn(0.02f, 1f)).height(6.dp).clip(RoundedCornerShape(50)).background(cor))
    }
}

/** Finanças (ADR-044): Resumo, Lançamentos, Relatórios, Categorias e Lembretes. As regras (estados, saldos) vêm do servidor. */
@Composable
fun FinancasEcra(aoVoltar: () -> Unit) {
    var aba by remember { mutableIntStateOf(0) }
    var mes by remember { mutableStateOf<String?>(null) }         // null = o mês de hoje (o servidor sabe qual é)
    var modo by remember { mutableStateOf("mes") }
    val c = carga("$mes|$modo") { Api.get("/finance?${mes?.let { "mes=$it&" } ?: ""}janela=$modo") }
    val acoes = rememberAcoes { c.recarregar() }
    EcraModulo("Finanças", aoVoltar) {
        Ao(c, "A carregar as finanças…") { d ->
            // Ao abrir um mês (até ao seguinte) copiam-se-lhe os recorrentes do mês anterior, uma só vez (idempotente no servidor).
            val mesAtual = d.getString("mes"); val hojeMes = d.getString("hoje").take(7)
            LaunchedEffect(mesAtual) {
                if (mesAtual <= somarMeses(hojeMes, 1)) try {
                    val r = Api.post("/actions/financas.preparar_mes", jo("params" to jo("mes" to mesAtual)))
                    if ((r.optJSONObject("resultado")?.optInt("criados") ?: 0) > 0) c.recarregar()
                } catch (_: Exception) { }
            }
            Abas(ABAS, aba) { aba = it }
            Rolar {
                ErroAcao(acoes)
                when (aba) {
                    0 -> ResumoTab(d, modo, { modo = it }, acoes)
                    1 -> LancamentosTab(d, { mes = it }, acoes)
                    2 -> RelatoriosTab(d.getString("mes"))
                    3 -> CategoriasTab(d.objs("categorias"), acoes)
                    else -> LembretesTab(acoes)
                }
            }
        }
    }
}

@Composable
private fun ColumnScope.ResumoTab(d: JSONObject, modo: String, aoModo: (String) -> Unit, acoes: Acoes) {
    val r = d.getJSONObject("resumo"); val janela = d.getJSONObject("janela"); val atrasadas = d.getJSONObject("atrasadas")
    val itens = atrasadas.objs("itens")
    val porCategoria = r.objs("porCategoria")
    val maximo = maxOf(porCategoria.maxOfOrNull { it.optDouble("total") } ?: 1.0, 1.0)
    val saldo = r.optDouble("saldo")
    Filtros(listOf("mes" to "Mês", "30d" to "Próximos 30 dias"), modo, aoModo)
    Meta("${fmtDataIso(janela.txtOu("de"))} – ${fmtDataIso(janela.txtOu("ate"))}")
    if (itens.isNotEmpty()) Aviso(TipoAviso.AVISO, "${plural(itens.size, "despesa vencida e por pagar", "despesas vencidas e por pagar")} · ${fmtEuro(atrasadas.optDouble("total"))}")
    Bloco(titulo = "Ativo − passivo") {
        LinhaValor("Rendimento", fmtEuro(r.optDouble("rendimento")), Pulse.cores.success)
        LinhaValor("Despesas por pagar", "− " + fmtEuro(r.optDouble("porPagar")))
        LinhaValor("Saldo do período", fmtEuro(saldo), if (saldo < 0) Pulse.cores.error else null)
        if (saldo < 0) Meta("Défice de ${fmtEuro(-saldo)}: será preciso cobrir com liquidez ou crédito.")
        if (r.optDouble("emAtraso") > 0) Meta("Com as vencidas de antes do período (${fmtEuro(r.optDouble("emAtraso"))}): ${fmtEuro(r.optDouble("saldoComAtraso"))}")
    }
    if (itens.isNotEmpty()) Bloco(titulo = "Vencidos e não pagos") { itens.forEach { LinhaConta(it, d, acoes) } }
    Bloco(titulo = "Despesas por categoria") {
        if (porCategoria.isEmpty()) Texto2("Sem despesas neste período.")
        porCategoria.forEach { c ->
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) { Texto(c.txtOu("nome")); Texto(fmtEuro(c.optDouble("total"))) }
                Barra((c.optDouble("total") / maximo).toFloat(), corDe(c.txt("cor"), Pulse.cores.accent))
            }
        }
    }
}

/** Uma conta com «pagar/anular»; tocar abre editar/apagar. */
@Composable
private fun LinhaConta(l: JSONObject, d: JSONObject, acoes: Acoes) {
    val avisos = LocalAvisos.current
    var abrir by remember { mutableStateOf(false) }
    val id = l.getInt("id"); val paga = l.txt("estado") == "pago"; val rend = l.txt("tipo") == "rendimento"
    val c = Pulse.cores
    Row(Modifier.fillMaxWidth().clickable { abrir = true }, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Visto(paga, {
            if (paga) acoes.executar("pg-$id", "financas.anular_pagamento", jo("lancamento" to id)) { avisos.mostrar("Pagamento anulado.") }
            else acoes.executar("pg-$id", "financas.pagar", jo("lancamento" to id)) {
                avisos.mostrar("Marcado como ${if (rend) "recebido" else "paga"}.") { acoes.executar("desfazer", "financas.anular_pagamento", jo("lancamento" to id)) }
            }
        }, (if (paga) "Anular pagamento: " else "Marcar como ${if (rend) "recebido" else "paga"}: ") + l.txtOu("descricao"), acoes.ocupado == "pg-$id", acoes.ocupado == null)
        Column(Modifier.weight(1f)) {
            Text(l.txtOu("descricao"), style = Pulse.body.let { if (paga) it.copy(textDecoration = TextDecoration.LineThrough) else it }, color = if (paga) c.text2 else c.text)
            val estado = l.txtOu("estado")
            Meta(l.txtOu("categoria") + " · " + fmtDataIso(l.txtOu("data_vencimento")) + (if (l.bool("recorrente")) " · recorrente" else "") +
                (if (estado == "vencido" || estado == "hoje") " · " + ESTADO_TXT[estado] else ""))
        }
        Texto((if (rend) "+ " else "") + fmtEuro(l.optDouble("valor")), Pulse.body, if (rend) c.success else c.text)
    }
    if (abrir) FolhaLancamento(l, d, acoes, avisos) { abrir = false }
}

@Composable
private fun FolhaLancamento(inicial: JSONObject?, d: JSONObject, acoes: Acoes, avisos: Avisos, aoFechar: () -> Unit) {
    val categorias = d.objs("categorias")
    var tipo by remember { mutableStateOf(inicial?.txt("tipo") ?: "despesa") }
    var descricao by remember { mutableStateOf(inicial?.txtOu("descricao") ?: "") }
    var texto by remember { mutableStateOf(inicial?.let { valorParaCampo(it.optDouble("valor")) } ?: "") }
    var categoria by remember { mutableStateOf(inicial?.inteiro("categoria_id") ?: categorias.firstOrNull()?.getInt("id")) }
    var venc by remember { mutableStateOf(inicial?.txtOu("data_vencimento") ?: (d.getString("mes") + "-01")) }
    var recorrente by remember { mutableStateOf(inicial?.bool("recorrente") ?: false) }
    var apagar by remember { mutableStateOf(false) }
    val cid = remember { novoCid() }
    val valor = lerValor(texto)
    val ok = descricao.isNotBlank() && valor != null && categoria != null && venc.isNotEmpty()
    val chave = if (inicial != null) "ed" else "novo"
    Folha(if (inicial != null) "Editar lançamento" else "Novo lançamento", aoFechar) {
        Escolha(listOf("despesa" to "Despesa", "rendimento" to "Rendimento"), tipo, { tipo = it })
        Campo("Descrição", descricao, { descricao = it.take(100) })
        Campo("Valor (€)", texto, { texto = it }, teclado = TecladoNumero, erro = if (texto.isNotEmpty() && valor == null) "Escreve um valor maior que zero." else null)
        Seletor("Categoria", categorias.map { it.getInt("id") to it.txtOu("nome") }, categoria, { categoria = it })
        CampoData("Vencimento", venc, { venc = it })
        Interruptor("Recorrente (repete-se todos os meses)", recorrente, { recorrente = it })
        ErroAcao(acoes)
        Botao(if (inicial != null) "Guardar" else "Adicionar", {
            val base = jo("tipo" to tipo, "descricao" to descricao.trim(), "valor" to valor, "categoriaId" to categoria, "dataVencimento" to venc, "recorrente" to recorrente)
            if (inicial != null) {
                base.put("lancamento", inicial.getInt("id"))
                if (venc.take(7) != inicial.txtOu("data_vencimento").take(7)) base.put("mesReferencia", venc.take(7))
                acoes.executar(chave, "financas.editar", base) { avisos.mostrar("Lançamento atualizado."); aoFechar() }
            } else { base.put("cid", cid); acoes.executar(chave, "financas.criar", base) { avisos.mostrar("Lançamento criado."); aoFechar() } }
        }, grande = true, ativo = ok && acoes.ocupado == null, carregando = acoes.ocupado == chave)
        if (inicial != null) LinkBtn("Apagar lançamento", { apagar = true })
    }
    if (apagar && inicial != null) Confirmar("Apagar lançamento", "Apagar «${inicial.txtOu("descricao")}»?", "Apagar", true, {
        apagar = false
        acoes.executar("del", "financas.apagar", jo("lancamento" to inicial.getInt("id")), true) {
            aoFechar()
            avisos.mostrar("Lançamento apagado.") {
                acoes.executar("desfazer", "financas.criar", jo("tipo" to inicial.txt("tipo"), "descricao" to inicial.txt("descricao"), "valor" to inicial.optDouble("valor"),
                    "categoriaId" to inicial.optInt("categoria_id"), "dataVencimento" to inicial.txt("data_vencimento"), "dataPagamento" to inicial.txt("data_pagamento"),
                    "recorrente" to inicial.bool("recorrente"), "mesReferencia" to inicial.txt("mes_referencia")))
            }
        }
    }, { apagar = false })
}

@Composable
private fun ColumnScope.LancamentosTab(d: JSONObject, irParaMes: (String) -> Unit, acoes: Acoes) {
    val avisos = LocalAvisos.current
    var novo by remember { mutableStateOf(false) }
    val mes = d.getString("mes")
    val lancs = d.objs("lancamentos")
    val porPagar = lancs.filter { it.txt("estado") != "pago" }; val pagos = lancs.filter { it.txt("estado") == "pago" }
    val t = d.getJSONObject("totaisMes"); val atrasadas = d.getJSONObject("atrasadas").objs("itens")
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        LinkBtn("‹", { irParaMes(somarMeses(mes, -1)) })
        Texto(tituloMesFin(mes), Pulse.card, modifier = Modifier.weight(1f), alinhar = TextAlign.Center)
        LinkBtn("›", { irParaMes(somarMeses(mes, 1)) })
    }
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        listOf("Rendimento" to t.optDouble("rendimento"), "Despesas" to t.optDouble("despesas"), "Por pagar" to t.optDouble("porPagar")).forEach { (n, v) ->
            Column { Meta(n); Texto(fmtEuro(v)) }
        }
    }
    if (atrasadas.isNotEmpty()) Aviso(TipoAviso.AVISO, "${plural(atrasadas.size, "despesa vencida e por pagar", "despesas vencidas e por pagar")} · ${fmtEuro(d.getJSONObject("atrasadas").optDouble("total"))} (ver no Resumo)")
    Botao("Novo lançamento", { novo = true }, pequeno = true)
    if (lancs.isEmpty()) Texto2("Sem lançamentos em ${tituloMesFin(mes)}.")
    if (porPagar.isNotEmpty()) Bloco(titulo = "Por pagar / receber  ${porPagar.size}") { porPagar.forEach { LinhaConta(it, d, acoes) } }
    if (pagos.isNotEmpty()) Bloco(titulo = "Pagos / recebidos  ${pagos.size}") { pagos.forEach { LinhaConta(it, d, acoes) } }
    if (novo) FolhaLancamento(null, d, acoes, avisos) { novo = false }
}

@Composable
private fun ColumnScope.RelatoriosTab(mes: String) {
    var n by remember { mutableIntStateOf(6) }
    val de = somarMeses(mes, -(n - 1))
    val c = carga("$de|$mes") { Api.get("/finance/reports?de=$de&ate=$mes") }
    Filtros(listOf(3 to "3 meses", 6 to "6 meses", 12 to "12 meses"), n) { n = it }
    Meta("${tituloMesFin(de)} a ${tituloMesFin(mes)}")
    when (val e = c.estado) {
        Estado.ACarregar -> BrandLoading("A calcular o relatório…")
        is Estado.Erro -> EstadoErro(e.mensagem, c.recarregar)
        is Estado.Pronto -> {
            val r = e.dados; val meses = r.objs("meses"); val cats = r.objs("categorias")
            val maximo = maxOf(meses.maxOfOrNull { maxOf(it.optDouble("rendimento"), it.optDouble("despesas")) } ?: 1.0, 1.0)
            Bloco(titulo = "Rendimento e despesas por mês") {
                meses.forEach { m ->
                    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Texto(tituloMesFin(m.txtOu("mes"))); Texto(fmtEuro(m.optDouble("saldo")), Pulse.body, if (m.optDouble("saldo") < 0) Pulse.cores.error else Pulse.cores.text)
                        }
                        Meta("Rendimento ${fmtEuro(m.optDouble("rendimento"))} · Despesas ${fmtEuro(m.optDouble("despesas"))}")
                        Barra((m.optDouble("despesas") / maximo).toFloat(), Pulse.cores.error)
                        Barra((m.optDouble("rendimento") / maximo).toFloat(), Pulse.cores.accent)
                    }
                }
                val tot = r.getJSONObject("totais")
                LinhaValor("Total", "Rendimento ${fmtEuro(tot.optDouble("rendimento"))} · Despesas ${fmtEuro(tot.optDouble("despesas"))}")
            }
            Bloco(titulo = "Despesas por categoria") {
                if (cats.isEmpty()) Texto2("Sem despesas neste período.")
                cats.forEach { k ->
                    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) { Texto(k.txtOu("nome")); Texto(fmtEuro(k.optDouble("total"))) }
                        Barra((k.optDouble("total") / cats[0].optDouble("total").coerceAtLeast(0.01)).toFloat(), corDe(k.txt("cor"), Pulse.cores.accent))
                    }
                }
            }
        }
    }
}

private val PALETA = listOf("#E07474", "#E0A13F", "#D9C93F", "#6FBF73", "#2FA7A0", "#4E92D9", "#7A6FD9", "#C070C0", "#8A918E", "#A0704E")

@Composable
private fun ColumnScope.CategoriasTab(categorias: List<JSONObject>, acoes: Acoes) {
    val avisos = LocalAvisos.current
    var nome by remember { mutableStateOf("") }
    var editar by remember { mutableStateOf<JSONObject?>(null) }
    Bloco(titulo = "Nova categoria") {
        Campo("Nome da categoria", nome, { nome = it.take(40) })
        Botao("Adicionar", { acoes.executar("nova-cat", "financas.categoria_criar", jo("nome" to nome.trim())) { nome = ""; avisos.mostrar("Categoria criada.") } },
            pequeno = true, ativo = nome.isNotBlank() && acoes.ocupado == null, carregando = acoes.ocupado == "nova-cat")
    }
    Bloco(titulo = "Categorias  ${categorias.size}") {
        categorias.forEach { c ->
            Row(Modifier.fillMaxWidth().clickable { editar = c }, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Box(Modifier.size(14.dp).clip(CircleShape).background(corDe(c.txt("cor"), Color(0xFF8A918E))))
                Texto(c.txtOu("nome"), modifier = Modifier.weight(1f)); LinkBtn("Editar", { editar = c })
            }
        }
    }
    editar?.let { c -> FolhaCategoria(c, acoes, avisos) { editar = null } }
}

@Composable
private fun FolhaCategoria(c: JSONObject, acoes: Acoes, avisos: Avisos, aoFechar: () -> Unit) {
    var nome by remember { mutableStateOf(c.txtOu("nome")) }
    var cor by remember { mutableStateOf(c.txt("cor") ?: "#8A918E") }
    var apagar by remember { mutableStateOf(false) }
    Folha("Editar categoria", aoFechar) {
        Campo("Nome", nome, { nome = it.take(40) })
        Texto("Cor", Pulse.body2.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.Medium))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            PALETA.forEach { h ->
                Box(Modifier.size(28.dp).clip(CircleShape).background(corDe(h, Color.Gray)).border(if (cor.equals(h, true)) 3.dp else 0.dp, Pulse.cores.text, CircleShape).clickable { cor = h })
            }
        }
        ErroAcao(acoes)
        Botao("Guardar", {
            val p = jo("categoria" to c.getInt("id"))
            if (nome.trim() != c.txtOu("nome")) p.put("nome", nome.trim())
            if (!cor.equals(c.txt("cor") ?: "", true)) p.put("cor", cor)
            if (p.length() == 1) aoFechar() else acoes.executar("cat", "financas.categoria_editar", p) { aoFechar(); avisos.mostrar("Categoria atualizada.") }
        }, grande = true, ativo = nome.isNotBlank() && acoes.ocupado == null, carregando = acoes.ocupado == "cat")
        LinkBtn("Apagar categoria", { apagar = true })
    }
    if (apagar) Confirmar("Apagar categoria", "Só apaga se «${c.txtOu("nome")}» não tiver lançamentos.", "Apagar", true, {
        apagar = false
        acoes.executar("cat", "financas.categoria_eliminar", jo("categoria" to c.getInt("id")), true) {
            aoFechar()
            avisos.mostrar("Categoria apagada.") { acoes.executar("desfazer", "financas.categoria_criar", jo("nome" to c.txtOu("nome")).also { o -> c.txt("cor")?.let { o.put("cor", it) } }) }
        }
    }, { apagar = false })
}

@Composable
private fun ColumnScope.LembretesTab(acoes: Acoes) {
    val avisos = LocalAvisos.current
    val c = carga { Api.get("/finance/reminders") }
    var novo by remember { mutableStateOf(false) }
    Botao("Novo lembrete", { novo = true }, pequeno = true)
    when (val e = c.estado) {
        Estado.ACarregar -> BrandLoading("A carregar os lembretes…")
        is Estado.Erro -> EstadoErro(e.mensagem, c.recarregar)
        is Estado.Pronto -> {
            val ls = e.dados.objs("lembretes")
            Bloco(titulo = "Lembretes  ${ls.size}") {
                if (ls.isEmpty()) Texto2("Sem lembretes agendados.")
                ls.forEach { l -> LinhaLembrete(l, acoes, avisos, c.recarregar) }
            }
        }
    }
    if (novo) FolhaLembrete(acoes, avisos, { novo = false }) { c.recarregar() }
}

@Composable
private fun LinhaLembrete(l: JSONObject, acoes: Acoes, avisos: Avisos, atualizar: () -> Unit) {
    var apagar by remember { mutableStateOf(false) }
    val id = l.getInt("id"); val ativo = l.bool("ativo")
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Column(Modifier.weight(1f)) {
            Texto(l.txtOu("titulo"), Pulse.body, if (ativo) Pulse.cores.text else Pulse.cores.text2)
            Meta("${fmtDataIso(l.txtOu("data"))} às ${l.txtOu("hora")} · ${if (l.txt("repeticao") == "mensal") "todos os meses" else "uma vez"}${if (ativo) "" else " · pausado"}${l.txtOu("nota").let { if (it.isNotEmpty()) " · $it" else "" }}")
        }
        Column(horizontalAlignment = Alignment.End) {
            LinkBtn(if (ativo) "Pausar" else "Reativar", {
                acoes.executar("lem-$id", "financas.lembrete_editar", jo("lembrete" to id, "ativo" to !ativo)) { atualizar(); avisos.mostrar(if (ativo) "Lembrete pausado." else "Lembrete reativado.") }
            })
            LinkBtn("Apagar", { apagar = true })
        }
    }
    if (apagar) Confirmar("Apagar lembrete", "Apagar «${l.txtOu("titulo")}»?", "Apagar", true, {
        apagar = false
        acoes.executar("lem-$id", "financas.lembrete_eliminar", jo("lembrete" to id), true) {
            atualizar()
            avisos.mostrar("Lembrete apagado.") {
                acoes.executar("desfazer", "financas.lembrete_criar", jo("titulo" to l.txt("titulo"), "nota" to l.txtOu("nota"), "data" to l.txt("data"), "hora" to l.txt("hora"), "repeticao" to l.txt("repeticao"))) { atualizar() }
            }
        }
    }, { apagar = false })
}

@Composable
private fun FolhaLembrete(acoes: Acoes, avisos: Avisos, aoFechar: () -> Unit, aoCriar: () -> Unit) {
    var titulo by remember { mutableStateOf("") }; var nota by remember { mutableStateOf("") }
    var data by remember { mutableStateOf("") }; var hora by remember { mutableStateOf("09:00") }
    var repeticao by remember { mutableStateOf("unica") }
    Folha("Novo lembrete", aoFechar) {
        Meta("Chega como notificação, depois da hora marcada.")
        Campo("Título", titulo, { titulo = it.take(100) })
        Campo("Nota (opcional)", nota, { nota = it.take(300) })
        CampoData("Data", data, { data = it })
        CampoHora("Hora", hora, { hora = it }, opcional = false)
        Escolha(listOf("unica" to "Uma vez", "mensal" to "Todos os meses"), repeticao, { repeticao = it })
        ErroAcao(acoes)
        Botao("Agendar", {
            acoes.executar("novo-lem", "financas.lembrete_criar", jo("titulo" to titulo.trim(), "nota" to nota.trim(), "data" to data, "hora" to hora, "repeticao" to repeticao)) {
                aoCriar(); aoFechar(); avisos.mostrar("Lembrete agendado.")
            }
        }, grande = true, ativo = titulo.isNotBlank() && data.isNotEmpty() && hora.length == 5 && acoes.ocupado == null, carregando = acoes.ocupado == "novo-lem")
    }
}
