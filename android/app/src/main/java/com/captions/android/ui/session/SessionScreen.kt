package com.captions.android.ui.session

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.BottomAppBar
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.captions.android.R
import com.captions.android.core.session.DisplayMode
import com.captions.android.core.session.FontChoice
import com.captions.android.core.session.SessionEntry
import com.captions.android.core.session.SessionUiState
import com.captions.android.ui.theme.CaptionsTheme

@Composable
fun SessionScreen(
    state: SessionUiState,
    onToggleMicrophone: () -> Unit,
    onToggleRunning: () -> Unit,
    onOpenSettings: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Scaffold(
        modifier = modifier
            .fillMaxSize()
            .imePadding(),
        containerColor = MaterialTheme.colorScheme.background,
        bottomBar = {
            SessionControls(
                state = state,
                onToggleMicrophone = onToggleMicrophone,
                onToggleRunning = onToggleRunning,
            )
        },
    ) { scaffoldPadding ->
        Box(Modifier.fillMaxSize()) {
            val listState = rememberLazyListState()
            val nearEnd by remember(state.entries.size) {
                derivedStateOf {
                    val lastVisible = listState.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: -1
                    lastVisible >= state.entries.lastIndex - 1
                }
            }

            LaunchedEffect(
                state.entries.size,
                state.entries.lastOrNull()?.source,
                state.entries.lastOrNull()?.translation,
            ) {
                if (state.entries.isNotEmpty() && (nearEnd || state.entries.size == 1)) {
                    listState.animateScrollToItem(state.entries.lastIndex)
                }
            }

            Surface(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(scaffoldPadding)
                    .padding(start = 10.dp, end = 10.dp, top = 6.dp, bottom = 10.dp),
                shape = RoundedCornerShape(22.dp),
                color = MaterialTheme.colorScheme.surface,
                tonalElevation = 1.dp,
                shadowElevation = 1.dp,
            ) {
                LazyColumn(
                    state = listState,
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(
                        start = 14.dp,
                        end = 14.dp,
                        top = 54.dp,
                        bottom = 18.dp,
                    ),
                    verticalArrangement = Arrangement.spacedBy(10.dp, Alignment.Bottom),
                ) {
                    items(state.entries, key = { it.cueId }) { entry ->
                        SessionEntryView(
                            entry = entry,
                            mode = state.displayMode,
                            fontChoice = state.fontChoice,
                            sourceSizeSp = state.sourceSizeSp,
                            translationSizeSp = state.translationSizeSp,
                        )
                    }
                }
            }

            Surface(
                shape = MaterialTheme.shapes.large,
                color = MaterialTheme.colorScheme.surfaceVariant,
                tonalElevation = 2.dp,
                modifier = Modifier
                    .align(Alignment.TopEnd)
                    .padding(
                        top = scaffoldPadding.calculateTopPadding() + 12.dp,
                        end = 18.dp,
                    ),
            ) {
                IconButton(
                    onClick = onOpenSettings,
                    modifier = Modifier.size(48.dp),
                ) {
                    Icon(
                        imageVector = Icons.Default.Settings,
                        contentDescription = "设置",
                        tint = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            if (state.message.isNotEmpty()) {
                Text(
                    text = state.message,
                    color = MaterialTheme.colorScheme.error,
                    fontSize = 12.sp,
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .padding(
                            start = 24.dp,
                            end = 24.dp,
                            bottom = scaffoldPadding.calculateBottomPadding() + 18.dp,
                        ),
                )
            }
        }
    }
}

@Composable
private fun SessionControls(
    state: SessionUiState,
    onToggleMicrophone: () -> Unit,
    onToggleRunning: () -> Unit,
) {
    BottomAppBar(
        containerColor = MaterialTheme.colorScheme.surfaceVariant,
        tonalElevation = 4.dp,
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 12.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            FilledTonalButton(
                onClick = onToggleMicrophone,
                modifier = Modifier
                    .weight(1f)
                    .heightIn(min = 56.dp)
                    .then(
                        if (state.microphoneEnabled) {
                            Modifier
                        } else {
                            Modifier.border(
                                width = 1.dp,
                                color = MaterialTheme.colorScheme.outline,
                                shape = MaterialTheme.shapes.extraLarge,
                            )
                        },
                    ),
            ) {
                Icon(
                    painter = painterResource(
                        if (state.microphoneEnabled) R.drawable.ic_mic else R.drawable.ic_mic_off,
                    ),
                    contentDescription = null,
                    modifier = Modifier.size(20.dp),
                )
                Spacer(Modifier.size(8.dp))
                Text(if (state.microphoneEnabled) "麦克风" else "麦克风关闭")
            }

            Button(
                onClick = onToggleRunning,
                enabled = !state.starting,
                modifier = Modifier
                    .weight(1f)
                    .heightIn(min = 56.dp),
            ) {
                if (state.starting) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(20.dp),
                        strokeWidth = 2.dp,
                    )
                } else {
                    Icon(
                        painter = if (state.running) {
                            painterResource(R.drawable.ic_pause)
                        } else {
                            painterResource(R.drawable.ic_play)
                        },
                        contentDescription = null,
                        modifier = Modifier.size(20.dp),
                    )
                }
                Spacer(Modifier.size(8.dp))
                Text(
                    when {
                        state.starting -> "准备中"
                        state.running -> "暂停"
                        else -> "开始"
                    },
                )
            }
        }
    }
}

@Composable
private fun SessionEntryView(
    entry: SessionEntry,
    mode: DisplayMode,
    fontChoice: FontChoice,
    sourceSizeSp: Int,
    translationSizeSp: Int,
) {
    val fontFamily = when (fontChoice) {
        FontChoice.System -> FontFamily.SansSerif
        FontChoice.Serif -> FontFamily.Serif
        FontChoice.Monospace -> FontFamily.Monospace
    }
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .widthIn(max = maxWidth)
                .then(
                    if (entry.current) {
                        Modifier
                            .background(Color(0xFF292B30), RoundedCornerShape(12.dp))
                            .padding(horizontal = 11.dp, vertical = 9.dp)
                    } else {
                        Modifier
                    },
                ),
            verticalArrangement = Arrangement.spacedBy(2.dp),
        ) {
            if (mode != DisplayMode.Translation && entry.source.isNotEmpty()) {
                Text(
                    text = entry.source,
                    color = if (entry.current) Color(0xFFC9CBD0) else Color(0xFF96999F),
                    fontSize = sourceSizeSp.sp,
                    fontFamily = fontFamily,
                    lineHeight = (sourceSizeSp * 1.16f).sp,
                )
            }
            if (mode != DisplayMode.Source && entry.translation.isNotEmpty()) {
                Text(
                    text = entry.translation,
                    color = if (entry.current) Color.White else Color(0xFF96999F),
                    fontSize = translationSizeSp.sp,
                    fontFamily = fontFamily,
                    lineHeight = (translationSizeSp * 1.16f).sp,
                    fontWeight = if (entry.current) FontWeight.Medium else FontWeight.Normal,
                )
            }
        }
    }
}

@Preview(showBackground = true, widthDp = 390, heightDp = 844)
@Composable
private fun SessionScreenPreview() {
    CaptionsTheme {
        SessionScreen(
            state = SessionUiState(
                entries = listOf(
                    SessionEntry(1, "The simplest interface leaves room for the conversation.", "最简单的界面，应该把空间留给对话。"),
                    SessionEntry(2, "Past sentences remain readable without competing for attention.", "历史内容依然清晰，但不会抢走视觉重心。"),
                    SessionEntry(3, "The current sentence is gently emphasized.", "当前句只做轻量强调。", current = true),
                ),
            ),
            onToggleMicrophone = {},
            onToggleRunning = {},
            onOpenSettings = {},
        )
    }
}
