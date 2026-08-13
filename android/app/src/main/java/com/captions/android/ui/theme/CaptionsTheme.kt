package com.captions.android.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val CaptionsColors = darkColorScheme(
    background = Color(0xFF101114),
    surface = Color(0xFF1A1B1F),
    surfaceVariant = Color(0xFF25272C),
    primary = Color(0xFFF1F2F3),
    onPrimary = Color(0xFF18191C),
    primaryContainer = Color(0xFF34363C),
    onPrimaryContainer = Color(0xFFF1F2F3),
    onBackground = Color(0xFFF4F4F5),
    onSurface = Color(0xFFF4F4F5),
    onSurfaceVariant = Color(0xFFC5C7CC),
    outline = Color(0xFF44474D),
    error = Color(0xFFD8B2B2),
)

@Composable
fun CaptionsTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = CaptionsColors,
        content = content,
    )
}
