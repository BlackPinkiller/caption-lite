package com.captions.android.ui.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.captions.android.core.session.RecognitionEngine
import com.captions.android.ports.ModelPhase
import com.captions.android.ports.ModelState

@Composable
internal fun RecognitionSettingsPage(
    engine: RecognitionEngine,
    language: String,
    splitPunctuation: Boolean,
    modelState: ModelState,
    systemModelState: ModelState,
    onEngineChanged: (RecognitionEngine) -> Unit,
    onLanguageChanged: (String) -> Unit,
    onSplitPunctuationChanged: (Boolean) -> Unit,
    onDownloadModel: () -> Unit,
    onDownloadSystemModel: () -> Unit,
) {
    SettingsPage {
        SettingGroup(label = "识别引擎") {
            ChoiceRow(
                choices = listOf(
                    RecognitionEngine.Nemotron to "Nemotron",
                    RecognitionEngine.AndroidSystem to "系统识别",
                ),
                selected = engine,
                onSelected = onEngineChanged,
            )
        }
        SettingGroup(label = "语言") {
            LanguageMenu(
                label = "识别语言",
                selected = if (engine == RecognitionEngine.Nemotron) "en" else language,
                onSelected = onLanguageChanged,
                enabled = engine == RecognitionEngine.AndroidSystem,
            )
        }
        SettingGroup(label = "分句") {
            ToggleSetting(
                label = "标点分句",
                checked = splitPunctuation,
                onCheckedChange = onSplitPunctuationChanged,
            )
        }
        if (engine == RecognitionEngine.Nemotron) {
            SettingGroup(label = "本地模型") {
                RecognitionModelStatus(modelState, onDownloadModel)
            }
        } else {
            SettingGroup(label = "系统语言模型") {
                SystemRecognitionModelStatus(systemModelState, onDownloadSystemModel)
            }
        }
    }
}

@Composable
private fun SystemRecognitionModelStatus(state: ModelState, onDownload: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = when (state.phase) {
                ModelPhase.Missing -> "需要下载"
                ModelPhase.Downloading -> state.detail.ifEmpty {
                    state.progressPercent.takeIf { it > 0 }?.let { "下载中 $it%" } ?: "下载中"
                }
                ModelPhase.Preparing -> "正在检查"
                ModelPhase.Ready -> "准备就绪"
                ModelPhase.Error -> state.detail.ifEmpty { "不可用" }
            },
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontSize = 14.sp,
        )
        Spacer(Modifier.weight(1f))
        if (state.phase == ModelPhase.Missing || state.phase == ModelPhase.Error) {
            TextButton(onClick = onDownload) { Text("下载") }
        }
    }
}

@Composable
private fun RecognitionModelStatus(state: ModelState, onDownload: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = 2.dp),
        verticalArrangement = Arrangement.spacedBy(7.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = when (state.phase) {
                    ModelPhase.Missing -> "约 662 MB"
                    ModelPhase.Downloading -> "下载中 ${state.progressPercent}%"
                    ModelPhase.Preparing -> "正在准备"
                    ModelPhase.Ready -> "准备就绪"
                    ModelPhase.Error -> state.detail.ifEmpty { "模型不可用" }
                },
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 14.sp,
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
