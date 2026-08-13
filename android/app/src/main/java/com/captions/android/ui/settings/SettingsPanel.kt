package com.captions.android.ui.settings

import androidx.compose.foundation.background
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.IconButton
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.captions.android.core.session.DisplayMode
import com.captions.android.core.session.FontChoice
import com.captions.android.core.session.RecognitionEngine
import com.captions.android.core.session.SessionUiState
import com.captions.android.ports.ModelPhase
import com.captions.android.ports.ModelState

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsPanel(
    state: SessionUiState,
    modelState: ModelState,
    onRecognitionEngineChanged: (RecognitionEngine) -> Unit,
    onDownloadModel: () -> Unit,
    onDisplayModeChanged: (DisplayMode) -> Unit,
    onFontChoiceChanged: (FontChoice) -> Unit,
    onSourceSizeChanged: (Int) -> Unit,
    onTranslationSizeChanged: (Int) -> Unit,
    onDismiss: () -> Unit,
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = MaterialTheme.colorScheme.surface,
        contentColor = MaterialTheme.colorScheme.onSurface,
        tonalElevation = 6.dp,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(start = 22.dp, end = 22.dp, bottom = 28.dp),
            verticalArrangement = Arrangement.spacedBy(18.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = "设置",
                    fontSize = 20.sp,
                    fontWeight = FontWeight.Medium,
                )
                Spacer(Modifier.weight(1f))
                TextButton(onClick = onDismiss) { Text("完成") }
            }
            SettingGroup(label = "语音识别") {
                ChoiceRow(
                    choices = listOf(
                        RecognitionEngine.Nemotron to "Nemotron",
                        RecognitionEngine.AndroidSystem to "系统识别",
                    ),
                    selected = state.recognitionEngine,
                    onSelected = onRecognitionEngineChanged,
                )
                if (state.recognitionEngine == RecognitionEngine.Nemotron) {
                    ModelStatusRow(modelState, onDownloadModel)
                }
            }
            SettingGroup(label = "显示模式") {
                ChoiceRow(
                    choices = listOf(
                        DisplayMode.Bilingual to "双语",
                        DisplayMode.Source to "原文",
                        DisplayMode.Translation to "译文",
                    ),
                    selected = state.displayMode,
                    onSelected = onDisplayModeChanged,
                )
            }
            SettingGroup(label = "字体") {
                ChoiceRow(
                    choices = listOf(
                        FontChoice.System to "系统",
                        FontChoice.Serif to "衬线",
                        FontChoice.Monospace to "等宽",
                    ),
                    selected = state.fontChoice,
                    onSelected = onFontChoiceChanged,
                )
            }
            SizeSetting(
                label = "原文字号",
                value = state.sourceSizeSp,
                onChanged = onSourceSizeChanged,
            )
            SizeSetting(
                label = "译文字号",
                value = state.translationSizeSp,
                onChanged = onTranslationSizeChanged,
            )
        }
    }
}

@Composable
private fun ModelStatusRow(state: ModelState, onDownload: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = 2.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = when (state.phase) {
                    ModelPhase.Missing -> "本地模型 · 约 464 MB"
                    ModelPhase.Downloading -> "下载中 ${state.progressPercent}%"
                    ModelPhase.Preparing -> "正在准备模型"
                    ModelPhase.Ready -> "准备就绪"
                    ModelPhase.Error -> state.detail.ifEmpty { "模型不可用" }
                },
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 13.sp,
            )
            Spacer(Modifier.weight(1f))
            if (state.phase == ModelPhase.Missing || state.phase == ModelPhase.Error) {
                TextButton(onClick = onDownload) { Text("下载") }
            }
        }
        if (state.phase == ModelPhase.Downloading) {
            LinearProgressIndicator(
                progress = { state.progressPercent / 100f },
                modifier = Modifier.fillMaxWidth(),
            )
        } else if (state.phase == ModelPhase.Preparing) {
            LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
        }
    }
}

@Composable
private fun SettingGroup(label: String, content: @Composable () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
        content()
    }
}

@Composable
private fun <T> ChoiceRow(
    choices: List<Pair<T, String>>,
    selected: T,
    onSelected: (T) -> Unit,
) {
    Row(horizontalArrangement = Arrangement.spacedBy(7.dp)) {
        choices.forEach { (value, label) ->
            val isSelected = value == selected
            TextButton(
                onClick = { onSelected(value) },
                modifier = Modifier.background(
                    color = if (isSelected) MaterialTheme.colorScheme.primaryContainer else Color.Transparent,
                    shape = MaterialTheme.shapes.large,
                ),
            ) {
                Text(
                    text = label,
                    color = if (isSelected) {
                        MaterialTheme.colorScheme.onPrimaryContainer
                    } else {
                        MaterialTheme.colorScheme.onSurfaceVariant
                    },
                )
            }
        }
    }
}

@Composable
private fun SizeSetting(label: String, value: Int, onChanged: (Int) -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
        Spacer(Modifier.weight(1f))
        IconButton(onClick = { onChanged(value - 1) }) {
            Text("−", fontSize = 21.sp)
        }
        Text(
            text = value.toString(),
            fontSize = 15.sp,
            modifier = Modifier.widthIn(min = 28.dp),
        )
        IconButton(onClick = { onChanged(value + 1) }) {
            Text("+", fontSize = 19.sp)
        }
    }
}
