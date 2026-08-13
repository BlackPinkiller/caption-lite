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
    modelState: ModelState,
    onEngineChanged: (RecognitionEngine) -> Unit,
    onDownloadModel: () -> Unit,
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
        if (engine == RecognitionEngine.Nemotron) {
            SettingGroup(label = "本地模型") {
                RecognitionModelStatus(modelState, onDownloadModel)
            }
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
