package pt.pereirabmd.pulse.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import coil.ImageLoader
import coil.compose.AsyncImage
import coil.decode.ImageDecoderDecoder
import coil.request.ImageRequest

/** Assets de marca (`assets/branding`), WebP animados. */
enum class Marca(val ficheiro: String) {
    SPLASH("pulse_splash"), LOADING("pulse_loading"), ERRO("pulse_error"), SUCESSO("pulse_success"), ONDA("onda_semfim")
}

@Composable
fun MarcaImagem(marca: Marca, tamanho: androidx.compose.ui.unit.Dp, modifier: Modifier = Modifier) {
    val ctx = LocalContext.current
    val loader = remember(ctx) { ImageLoader.Builder(ctx).components { add(ImageDecoderDecoder.Factory()) }.build() }
    AsyncImage(
        model = ImageRequest.Builder(ctx).data("file:///android_asset/branding/${marca.ficheiro}.webp").build(),
        imageLoader = loader, contentDescription = null, modifier = modifier.size(tamanho),
    )
}

/** Loading de marca (ecrãs inteiros e arranque). */
@Composable
fun BrandLoading(texto: String = "A carregar…", modifier: Modifier = Modifier) {
    Column(modifier.fillMaxWidth().padding(24.dp).semantics { liveRegion = LiveRegionMode.Polite }, horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        MarcaImagem(Marca.LOADING, 96.dp)
        Text(texto, style = Pulse.body2, color = Pulse.cores.text2)
    }
}

@Composable
fun Texto(t: String, estilo: androidx.compose.ui.text.TextStyle = Pulse.body, cor: Color = Pulse.cores.text, modifier: Modifier = Modifier, alinhar: TextAlign? = null, linhas: Int = Int.MAX_VALUE) =
    Text(t, style = estilo, color = cor, modifier = modifier, textAlign = alinhar, maxLines = linhas)

@Composable fun Texto2(t: String, modifier: Modifier = Modifier) = Texto(t, Pulse.body2, Pulse.cores.text2, modifier)
@Composable fun Meta(t: String, modifier: Modifier = Modifier) = Texto(t, Pulse.meta, Pulse.cores.text2, modifier)

enum class TipoAviso { ERRO, AVISO, INFO }

/** Aviso persistente (não é um toast): fica enquanto a condição se mantiver. */
@Composable
fun Aviso(tipo: TipoAviso, modifier: Modifier = Modifier, conteudo: @Composable ColumnScope.() -> Unit) {
    val c = Pulse.cores
    val (fundo, tinta) = when (tipo) { TipoAviso.ERRO -> c.errorBg to c.error; TipoAviso.AVISO -> c.warningBg to c.warning; TipoAviso.INFO -> c.surface2 to c.info }
    Row(modifier.fillMaxWidth().clip(RoundedCornerShape(Pulse.rM)).background(fundo).padding(12.dp).semantics { liveRegion = LiveRegionMode.Polite }, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Icon(if (tipo == TipoAviso.INFO) Icone.INFO else Icone.ALERTA, tinta, 20.dp, Modifier.padding(top = 2.dp))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp), content = conteudo)
    }
}

@Composable fun Aviso(tipo: TipoAviso, texto: String, modifier: Modifier = Modifier) = Aviso(tipo, modifier) { Texto(texto, Pulse.body2, Pulse.cores.text) }

enum class Variante { PRIMARIO, SECUNDARIO, PERIGO }

@Composable
fun Botao(texto: String, aoClicar: () -> Unit, modifier: Modifier = Modifier, variante: Variante = Variante.PRIMARIO, grande: Boolean = false, pequeno: Boolean = false, ativo: Boolean = true, carregando: Boolean = false) {
    val c = Pulse.cores
    val altura = if (pequeno) 40.dp else if (grande) 52.dp else 48.dp
    val m = modifier.then(if (grande) Modifier.fillMaxWidth() else Modifier).heightIn(min = altura)
    val forma = RoundedCornerShape(Pulse.rM)
    val on = ativo && !carregando
    when (variante) {
        Variante.PRIMARIO -> Button(aoClicar, m, enabled = on, shape = forma, colors = ButtonDefaults.buttonColors(containerColor = c.primary, contentColor = c.primaryInk,
            disabledContainerColor = c.primary.copy(alpha = .55f), disabledContentColor = c.primaryInk)) { ConteudoBotao(texto, carregando) }
        else -> OutlinedButton(aoClicar, m, enabled = on, shape = forma, border = BorderStroke(1.dp, c.line),
            colors = ButtonDefaults.outlinedButtonColors(contentColor = if (variante == Variante.PERIGO) c.error else c.text)) { ConteudoBotao(texto, carregando) }
    }
}

@Composable
private fun ConteudoBotao(texto: String, carregando: Boolean) {
    if (carregando) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp, color = LocalContentColor.current)
    Text(texto, style = Pulse.body2.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.Medium))
}

@Composable
fun LinkBtn(texto: String, aoClicar: () -> Unit, modifier: Modifier = Modifier) =
    Text(texto, style = Pulse.body2.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.Medium), color = Pulse.cores.primary,
        modifier = modifier.clip(RoundedCornerShape(Pulse.rXs)).clickable(onClick = aoClicar).padding(vertical = 6.dp, horizontal = 4.dp))

@Composable
fun Campo(rotulo: String, valor: String, aoMudar: (String) -> Unit, modifier: Modifier = Modifier, erro: String? = null, teclado: KeyboardType = KeyboardType.Text,
          password: Boolean = false, aoConcluir: (() -> Unit)? = null) {
    val c = Pulse.cores
    var ver by remember { mutableStateOf(false) }
    Column(modifier, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(rotulo, style = Pulse.body2.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.Medium), color = c.text)
        OutlinedTextField(
            value = valor, onValueChange = aoMudar, modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp), singleLine = true, isError = erro != null,
            shape = RoundedCornerShape(Pulse.rM),
            visualTransformation = if (password && !ver) PasswordVisualTransformation() else VisualTransformation.None,
            keyboardOptions = KeyboardOptions(keyboardType = if (password) KeyboardType.Password else teclado, autoCorrect = false,
                imeAction = if (aoConcluir != null) androidx.compose.ui.text.input.ImeAction.Done else androidx.compose.ui.text.input.ImeAction.Next),
            keyboardActions = androidx.compose.foundation.text.KeyboardActions(onDone = { aoConcluir?.invoke() }),
            trailingIcon = if (password) { {
                IconButton({ ver = !ver }) { Icon(if (ver) Icone.OLHO_OFF else Icone.OLHO, c.text2, 20.dp) }
            } } else null,
            colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = c.primary, unfocusedBorderColor = c.line, focusedContainerColor = c.surface, unfocusedContainerColor = c.surface,
                errorBorderColor = c.error, errorContainerColor = c.surface, focusedTextColor = c.text, unfocusedTextColor = c.text, cursorColor = c.primary),
        )
        if (erro != null) Text(erro, style = Pulse.meta, color = c.error)
    }
}

/** Cartão com cabeçalho (ícone, título, extra) como no Hoje da Web. Sem cartões dentro de cartões (CLAUDE.md). */
@Composable
fun Cartao(icone: Icone, titulo: String, modifier: Modifier = Modifier, aoTocar: (() -> Unit)? = null, extra: @Composable RowScope.() -> Unit = {}, conteudo: @Composable ColumnScope.() -> Unit) {
    val c = Pulse.cores
    // aoTocar: tocar no cartão (fora dos botões e linhas com toque próprio) leva ao módulo
    Column(modifier.fillMaxWidth().clip(RoundedCornerShape(Pulse.rL)).background(c.surface).border(1.dp, c.line, RoundedCornerShape(Pulse.rL))
        .then(if (aoTocar != null) Modifier.clickable(onClickLabel = "Abrir $titulo") { aoTocar() } else Modifier).padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Icon(icone, c.primary, 22.dp)
            Text(titulo, style = Pulse.card, color = c.text, modifier = Modifier.weight(1f).semantics { contentDescription = titulo })
            extra()
        }
        conteudo()
    }
}

@Composable
fun Pilula(texto: String, cor: Color = Pulse.cores.text2, fundo: Color = Pulse.cores.surface2) =
    Text(texto, style = Pulse.meta, color = cor, modifier = Modifier.clip(RoundedCornerShape(50)).background(fundo).padding(horizontal = 8.dp, vertical = 2.dp))

/** Linha de lista: conteúdo principal e, opcionalmente, um extremo. */
@Composable
fun Linha(modifier: Modifier = Modifier, inicio: (@Composable () -> Unit)? = null, fim: (@Composable () -> Unit)? = null, principal: @Composable ColumnScope.() -> Unit) {
    Row(modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        inicio?.invoke()
        Column(Modifier.weight(1f), content = principal)
        fim?.invoke()
    }
}

@Composable
fun Divisor() = HorizontalDivider(color = Pulse.cores.line)

/** Erro completo de um ecrã (estado `error`): imagem de marca, mensagem e «Tentar de novo». */
@Composable
fun EstadoErro(mensagem: String, aoTentar: () -> Unit) {
    Column(Modifier.fillMaxWidth().padding(16.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        MarcaImagem(Marca.ERRO, 96.dp)
        Aviso(TipoAviso.ERRO, mensagem)
        Botao("Tentar de novo", aoTentar, variante = Variante.SECUNDARIO, pequeno = true)
    }
}

/** Fundo do ecrã (token `bg`). */
@Composable
fun Modifier.background(): Modifier = this.then(Modifier.background(Pulse.cores.bg))
