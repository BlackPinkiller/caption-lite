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
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.IconButton
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.Switch
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
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
import com.captions.android.core.session.TranslationSettings
import com.captions.android.ports.ModelPhase
import com.captions.android.ports.ModelState

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsPanel(
    state: SessionUiState,
    modelState: ModelState,
    translationModelState: ModelState,
    onRecognitionEngineChanged: (RecognitionEngine) -> Unit,
    onDownloadModel: () -> Unit,
    onTranslationSettingsChanged: (TranslationSettings) -> Unit,
    onDownloadTranslationModel: () -> Unit,
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
            TranslationSettingsGroup(
                settings = state.translationSettings,
                modelState = translationModelState,
                onChanged = onTranslationSettingsChanged,
                onDownloadModel = onDownloadTranslationModel,
            )
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
private fun TranslationSettingsGroup(
    settings: TranslationSettings,
    modelState: ModelState,
    onChanged: (TranslationSettings) -> Unit,
    onDownloadModel: () -> Unit,
) {
    SettingGroup(label = "翻译") {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text("Google 本地", fontSize = 15.sp)
                Text(
                    if (settings.enabled) "使用设备端语言模型" else "已关闭",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 12.sp,
                )
            }
            Spacer(Modifier.weight(1f))
            Switch(
                checked = settings.enabled,
                onCheckedChange = { onChanged(settings.copy(enabled = it)) },
            )
        }
        if (settings.enabled) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                LanguageMenu(
                    label = "原文",
                    selected = settings.sourceLanguage,
                    onSelected = { source ->
                        onChanged(
                            if (source == settings.targetLanguage) {
                                settings.copy(
                                    sourceLanguage = source,
                                    targetLanguage = settings.sourceLanguage,
                                )
                            } else {
                                settings.copy(sourceLanguage = source)
                            },
                        )
                    },
                    modifier = Modifier.weight(1f),
                )
                Text("→", color = MaterialTheme.colorScheme.onSurfaceVariant)
                LanguageMenu(
                    label = "译文",
                    selected = settings.targetLanguage,
                    onSelected = { target ->
                        onChanged(
                            if (target == settings.sourceLanguage) {
                                settings.copy(
                                    sourceLanguage = settings.targetLanguage,
                                    targetLanguage = target,
                                )
                            } else {
                                settings.copy(targetLanguage = target)
                            },
                        )
                    },
                    modifier = Modifier.weight(1f),
                )
            }
            TranslationModelStatusRow(modelState, onDownloadModel)
        }
    }
}

@Composable
private fun LanguageMenu(
    label: String,
    selected: String,
    onSelected: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    var expanded by remember { mutableStateOf(false) }
    Column(modifier = modifier) {
        Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
        TextButton(
            onClick = { expanded = true },
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(LANGUAGES.firstOrNull { it.first == selected }?.second ?: selected)
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            LANGUAGES.forEach { (code, name) ->
                DropdownMenuItem(
                    text = { Text(name) },
                    onClick = {
                        expanded = false
                        onSelected(code)
                    },
                )
            }
        }
    }
}

@Composable
private fun TranslationModelStatusRow(state: ModelState, onDownload: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = when (state.phase) {
                ModelPhase.Missing -> "语言模型 · 每种约 30 MB"
                ModelPhase.Downloading,
                ModelPhase.Preparing,
                -> "正在下载语言模型"
                ModelPhase.Ready -> "准备就绪"
                ModelPhase.Error -> state.detail.ifEmpty { "语言模型不可用" }
            },
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontSize = 13.sp,
        )
        Spacer(Modifier.weight(1f))
        if (state.phase == ModelPhase.Missing || state.phase == ModelPhase.Error) {
            TextButton(onClick = onDownload) { Text("下载") }
        }
    }
}

private val LANGUAGES = listOf(
    "en" to "英语",
    "zh" to "中文",
    "ja" to "日语",
    "ko" to "韩语",
    "de" to "德语",
    "fr" to "法语",
    "es" to "西班牙语",
    "it" to "意大利语",
    "pt" to "葡萄牙语",
    "ru" to "俄语",
)

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
                    ModelPhase.Missing -> "本地模型 · 约 662 MB"
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
