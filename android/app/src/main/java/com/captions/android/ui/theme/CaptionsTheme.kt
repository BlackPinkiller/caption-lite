package com.captions.android.ui.theme

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

private val CaptionsColors = darkColorScheme(
    background = Color(0xFF101114),
    surface = Color(0xFF1A1B1F),
    surfaceVariant = Color(0xFF25272C),
    surfaceContainerLowest = Color(0xFF0B0C0E),
    surfaceContainerLow = Color(0xFF1D1E22),
    surfaceContainer = Color(0xFF222327),
    surfaceContainerHigh = Color(0xFF2C2E33),
    surfaceContainerHighest = Color(0xFF37393E),
    primary = Color(0xFFF1F2F3),
    onPrimary = Color(0xFF18191C),
    primaryContainer = Color(0xFF34363C),
    onPrimaryContainer = Color(0xFFF1F2F3),
    secondary = Color(0xFFC9CACE),
    onSecondary = Color(0xFF232428),
    secondaryContainer = Color(0xFF2F3136),
    onSecondaryContainer = Color(0xFFF1F2F3),
    onBackground = Color(0xFFF4F4F5),
    onSurface = Color(0xFFF4F4F5),
    onSurfaceVariant = Color(0xFFC5C7CC),
    outline = Color(0xFF44474D),
    outlineVariant = Color(0xFF3A3C41),
    error = Color(0xFFD8B2B2),
)

private val CaptionsShapes = Shapes(
    extraSmall = RoundedCornerShape(4.dp),
    small = RoundedCornerShape(8.dp),
    medium = RoundedCornerShape(12.dp),
    large = RoundedCornerShape(16.dp),
    extraLarge = RoundedCornerShape(28.dp),
)

@Composable
fun CaptionsTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = CaptionsColors,
        shapes = CaptionsShapes,
        content = content,
    )
}
