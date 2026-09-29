package pt.pereirabmd.pulse.util

import java.time.DayOfWeek
import java.time.LocalDate
import java.time.temporal.TemporalAdjusters

/** Regras de apresentação das Tarefas (espelho de `web/src/lib/tarefas.ts`); ocorrências, atrasos e rotações vêm do servidor. */
val DIAS_TAREFA = listOf("Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sab")
val DIAS_NOME = mapOf("Dom" to "Domingo", "Seg" to "Segunda", "Ter" to "Terça", "Qua" to "Quarta", "Qui" to "Quinta", "Sex" to "Sexta", "Sab" to "Sábado")
val RECORRENCIAS = listOf("Diaria" to "Todos os dias", "Semanal" to "Semanal", "Dias especificos" to "Dias específicos", "Mensal" to "Mensal",
    "Trimestral" to "A cada 3 meses", "Semestral" to "A cada 6 meses", "Pontual" to "Uma só vez")
val COM_DIAS = listOf("Semanal", "Dias especificos")
val COM_DATA = listOf("Pontual", "Trimestral", "Semestral")
val DIAS_CURTO = listOf("Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb")
private val MESES = listOf("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")
private val MESES_CURTO = listOf("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")

/** «hoje às 08:00», «ontem às 21:10» ou «29/09 às 07:00» a partir de «AAAA-MM-DD HH:MM». */
fun quando(dataConclusao: String, hoje: String): String {
    val p = dataConclusao.split(' ')
    if (p.size < 2 || p[0].isEmpty()) return dataConclusao
    val (d, h) = p[0] to p[1]
    return when (d) {
        hoje -> "hoje às $h"
        LocalDate.parse(hoje).minusDays(1).toString() -> "ontem às $h"
        else -> "${d.substring(8, 10)}/${d.substring(5, 7)} às $h"
    }
}

fun passaFiltro(pessoa: String, filtro: String, minha: String?) = when (filtro) { "todas" -> true; "minhas" -> pessoa == minha; else -> pessoa == filtro }

// --- Calendário: semanas de domingo a sábado, como na app dedicada ---
/** Domingo = 0 … sábado = 6. */
fun diaDaSemana(d: LocalDate) = d.dayOfWeek.value % 7

fun intervaloMes(ancora: String): Pair<String, String> {
    val d = LocalDate.parse(ancora)
    val primeiro = d.withDayOfMonth(1); val ultimo = d.with(TemporalAdjusters.lastDayOfMonth())
    return primeiro.minusDays(diaDaSemana(primeiro).toLong()).toString() to ultimo.plusDays((6 - diaDaSemana(ultimo)).toLong()).toString()
}

fun intervaloSemanaDomingo(ancora: String): Pair<String, String> {
    val ini = LocalDate.parse(ancora).let { it.minusDays(diaDaSemana(it).toLong()) }
    return ini.toString() to ini.plusDays(6).toString()
}

fun tituloMes(ancora: String): String { val d = LocalDate.parse(ancora); return "${MESES[d.monthValue - 1].replaceFirstChar { it.uppercase() }} de ${d.year}" }

fun tituloSemana(de: String, ate: String): String {
    val a = LocalDate.parse(de); val b = LocalDate.parse(ate)
    return if (a.monthValue == b.monthValue) "${a.dayOfMonth}–${b.dayOfMonth} de ${MESES[b.monthValue - 1]}" else "${a.dayOfMonth} ${MESES_CURTO[a.monthValue - 1]} – ${b.dayOfMonth} ${MESES_CURTO[b.monthValue - 1]}"
}

/** Cor estável por categoria (as categorias são livres, por isso não há tabela fixa): tom HSL → ARGB. */
fun corCategoria(nome: String): Int {
    var h = 0
    for (c in nome) h = (h * 31 + c.code) % 360
    return android.graphics.Color.HSVToColor(floatArrayOf(h.toFloat(), 0.62f, 0.78f))
}

fun listaDatas(de: String, ate: String): List<String> = generateSequence(LocalDate.parse(de)) { it.plusDays(1) }.takeWhile { it <= LocalDate.parse(ate) }.map { it.toString() }.toList()

/** Exporta o histórico como CSV (com BOM, para o Excel abrir os acentos). */
fun csvHistorico(linhas: List<List<String>>): String {
    val cab = listOf("Tarefa", "Categoria", "Data", "Pessoa", "Estado", "DataConclusao")
    fun aspas(v: String) = "\"" + v.replace("\"", "\"\"") + "\""
    return "﻿" + (listOf(cab) + linhas).joinToString("\n") { l -> l.joinToString(",") { aspas(it) } }
}

fun alterna(lista: List<String>, v: String) = if (v in lista) lista - v else lista + v
