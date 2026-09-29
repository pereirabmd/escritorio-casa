package pt.pereirabmd.pulse.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import pt.pereirabmd.pulse.data.Tema

/** Design System Pulse (`docs/DESIGN_SYSTEM.md`, `web/src/styles/tokens.css`): os mesmos tokens da Web. */
data class PulseColors(
    val bg: Color, val surface: Color, val surface2: Color, val primary: Color, val primaryInk: Color, val accent: Color,
    val text: Color, val text2: Color, val line: Color, val success: Color, val warning: Color, val warningBg: Color,
    val error: Color, val errorBg: Color, val info: Color, val escuro: Boolean,
)

private val Claro = PulseColors(
    bg = Color(0xFFF7FAFC), surface = Color(0xFFFFFFFF), surface2 = Color(0xFFEEF4F6), primary = Color(0xFF1E5B67), primaryInk = Color(0xFFFFFFFF),
    accent = Color(0xFF22C7B8), text = Color(0xFF16222A), text2 = Color(0xFF56666F), line = Color(0x1C16222A), success = Color(0xFF2F9E72),
    warning = Color(0xFFA97A1E), warningBg = Color(0x29D9A441), error = Color(0xFFC24848), errorBg = Color(0x1FD95C5C), info = Color(0xFF3F7FC0), escuro = false,
)
private val Escuro = PulseColors(
    bg = Color(0xFF0C1418), surface = Color(0xFF142027), surface2 = Color(0xFF1B2A32), primary = Color(0xFF56B8C4), primaryInk = Color(0xFF08161A),
    accent = Color(0xFF2DD4C3), text = Color(0xFFEAF2F4), text2 = Color(0xFF9DB0B8), line = Color(0x1FEAF2F4), success = Color(0xFF3CBF8A),
    warning = Color(0xFFD9A441), warningBg = Color(0x29D9A441), error = Color(0xFFE07474), errorBg = Color(0x29D95C5C), info = Color(0xFF6AA6E6), escuro = true,
)

val LocalPulse = staticCompositionLocalOf { Claro }

object Pulse {
    val cores: PulseColors @Composable get() = LocalPulse.current
    val page get() = TextStyle(fontSize = 28.sp, lineHeight = 34.sp, fontWeight = FontWeight.SemiBold)
    val section get() = TextStyle(fontSize = 22.sp, lineHeight = 28.sp, fontWeight = FontWeight.SemiBold)
    val card get() = TextStyle(fontSize = 15.sp, lineHeight = 20.sp, fontWeight = FontWeight.SemiBold)
    val body get() = TextStyle(fontSize = 16.sp, lineHeight = 24.sp)
    val body2 get() = TextStyle(fontSize = 14.sp, lineHeight = 20.sp)
    val meta get() = TextStyle(fontSize = 12.sp, lineHeight = 16.sp)
    val metric get() = TextStyle(fontSize = 32.sp, lineHeight = 38.sp, fontWeight = FontWeight.SemiBold)
    val rXs = 6.dp; val rS = 8.dp; val rM = 12.dp; val rL = 16.dp
}

@Composable
fun PulseTheme(tema: Tema, content: @Composable () -> Unit) {
    val escuro = when (tema) { Tema.SISTEMA -> isSystemInDarkTheme(); Tema.CLARO -> false; Tema.ESCURO -> true }
    val c = if (escuro) Escuro else Claro
    val esquema = (if (escuro) darkColorScheme() else lightColorScheme()).copy(
        primary = c.primary, onPrimary = c.primaryInk, background = c.bg, onBackground = c.text, surface = c.surface, onSurface = c.text,
        surfaceVariant = c.surface2, onSurfaceVariant = c.text2, outline = c.line, error = c.error, secondary = c.accent,
        primaryContainer = c.surface2, onPrimaryContainer = c.primary,
    )
    CompositionLocalProvider(LocalPulse provides c) { MaterialTheme(colorScheme = esquema, content = content) }
}
