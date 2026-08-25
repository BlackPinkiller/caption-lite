package com.captions.android.ui.settings

import androidx.compose.foundation.layout.padding
import androidx.compose.material3.HorizontalDivider
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.captions.android.core.session.RecognitionEngine
import com.captions.android.core.session.NemotronModel
import com.captions.android.ports.ModelState

@Composable
internal fun RecognitionSettingsPage(
    engine: RecognitionEngine,
    nemotronModel: NemotronModel,
    language: String,
    modelState: ModelState,
    systemModelState: ModelState,
    onEngineChanged: (RecognitionEngine) -> Unit,
    onNemotronModelChanged: (NemotronModel) -> Unit,
    onLanguageChanged: (String) -> Unit,
    onDownloadModel: () -> Unit,
    onDownloadSystemModel: () -> Unit,
) {
    SettingsPage {
        SettingGroup(label = "识别引擎") {
            SegmentedChoiceRow(
                choices = listOf(
                    RecognitionEngine.Nemotron to "Nemotron",
                    RecognitionEngine.AndroidSystem to "系统识别",
                ),
                selected = engine,
                onSelected = onEngineChanged,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
            )
            HorizontalDivider()
            SettingDropdown(
                title = "识别语言",
                selectedLabel = if (engine == RecognitionEngine.Nemotron) {
                    "英语"
                } else {
                    languageName(language)
                },
                onSelected = onLanguageChanged,
                enabled = engine == RecognitionEngine.AndroidSystem,
            )
        }
        if (engine == RecognitionEngine.Nemotron) {
            SettingGroup(label = "本地模型") {
                SettingDropdown(
                    title = "模型延迟",
                    selectedLabel = nemotronModel.label(),
                    onSelected = { value ->
                        onNemotronModelChanged(NemotronModel.valueOf(value))
                    },
                    choices = NemotronModel.entries.map { it.name to it.label() },
                )
                HorizontalDivider()
                ModelStatusRow(
                    state = modelState,
                    onDownload = onDownloadModel,
                    missingLabel = "约 662 MB",
                    prefix = "Nemotron · ",
                    preparingLabel = "正在准备",
                    errorFallback = "模型不可用",
                )
            }
        } else {
            SettingGroup(label = "系统语言模型") {
                ModelStatusRow(
                    state = systemModelState,
                    onDownload = onDownloadSystemModel,
                    missingLabel = "需要下载",
                )
            }
        }
    }
}

private fun NemotronModel.label(): String = when (this) {
    NemotronModel.English560Ms -> "560 ms"
    NemotronModel.English1120Ms -> "1120 ms"
}
