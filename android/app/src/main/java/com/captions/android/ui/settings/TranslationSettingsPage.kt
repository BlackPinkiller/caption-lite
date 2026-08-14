package com.captions.android.ui.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.captions.android.core.session.TranslationEngine
import com.captions.android.core.session.TranslationSettings
import com.captions.android.core.translation.DEFAULT_LLM_PROMPT
import com.captions.android.ports.ModelPhase
import com.captions.android.ports.ModelState

@Composable
internal fun TranslationSettingsPage(
    settings: TranslationSettings,
    modelState: ModelState,
    onChanged: (TranslationSettings) -> Unit,
    onDownloadModel: () -> Unit,
) {
    var advancedOpen by rememberSaveable { mutableStateOf(false) }
    SettingsPage {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text("启用翻译", fontSize = 15.sp)
                Text(
                    if (settings.enabled) engineName(settings.engine) else "已关闭",
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
            SettingGroup(label = "翻译服务") {
                ChoiceRow(
                    choices = listOf(
                        TranslationEngine.GoogleOnDevice to "Google 本地",
                        TranslationEngine.Google2 to "Google",
                    ),
                    selected = settings.engine,
                    onSelected = { onChanged(settings.copy(engine = it)) },
                )
                ChoiceRow(
                    choices = listOf(
                        TranslationEngine.DeepL to "DeepL",
                        TranslationEngine.OpenAICompatible to "LLM",
                    ),
                    selected = settings.engine,
                    onSelected = { onChanged(settings.copy(engine = it)) },
                )
            }
            SettingGroup(label = "语言") {
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
            }
            when (settings.engine) {
                TranslationEngine.GoogleOnDevice -> TranslationModelStatus(
                    modelState,
                    onDownloadModel,
                )
                TranslationEngine.Google2 -> Unit
                TranslationEngine.DeepL -> DeepLSettings(settings, onChanged)
                TranslationEngine.OpenAICompatible -> LlmSettings(
                    settings = settings,
                    advancedOpen = advancedOpen,
                    onAdvancedOpenChanged = { advancedOpen = it },
                    onChanged = onChanged,
                )
            }
        }
    }
}

@Composable
private fun DeepLSettings(
    settings: TranslationSettings,
    onChanged: (TranslationSettings) -> Unit,
) {
    SettingGroup(label = "DeepL") {
        OutlinedTextField(
            value = settings.deeplApiKey,
            onValueChange = { onChanged(settings.copy(deeplApiKey = it)) },
            label = { Text("API 密钥") },
            visualTransformation = PasswordVisualTransformation(),
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        ChoiceRow(
            choices = listOf(false to "API Free", true to "API Pro"),
            selected = settings.deeplPro,
            onSelected = { onChanged(settings.copy(deeplPro = it)) },
        )
    }
}

@Composable
private fun LlmSettings(
    settings: TranslationSettings,
    advancedOpen: Boolean,
    onAdvancedOpenChanged: (Boolean) -> Unit,
    onChanged: (TranslationSettings) -> Unit,
) {
    SettingGroup(label = "LLM") {
        OutlinedTextField(
            value = settings.llmModel,
            onValueChange = { onChanged(settings.copy(llmModel = it)) },
            label = { Text("模型") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = settings.llmApiKey,
            onValueChange = { onChanged(settings.copy(llmApiKey = it)) },
            label = { Text("API 密钥") },
            visualTransformation = PasswordVisualTransformation(),
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        TextButton(onClick = { onAdvancedOpenChanged(!advancedOpen) }) {
            Text(if (advancedOpen) "收起高级设置" else "高级设置")
        }
        if (advancedOpen) {
            OutlinedTextField(
                value = settings.llmBaseUrl,
                onValueChange = { onChanged(settings.copy(llmBaseUrl = it)) },
                label = { Text("API 地址") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )
            SizeSetting(
                label = "上下文句数",
                value = settings.contextSegments,
                onChanged = {
                    onChanged(settings.copy(contextSegments = it.coerceIn(0, 12)))
                },
            )
            OutlinedTextField(
                value = settings.llmPromptTemplate,
                onValueChange = { onChanged(settings.copy(llmPromptTemplate = it)) },
                label = { Text("提示词") },
                minLines = 5,
                modifier = Modifier.fillMaxWidth(),
            )
            TextButton(
                onClick = {
                    onChanged(settings.copy(llmPromptTemplate = DEFAULT_LLM_PROMPT))
                },
            ) {
                Text("恢复默认")
            }
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
private fun TranslationModelStatus(state: ModelState, onDownload: () -> Unit) {
    SettingGroup(label = "本地模型") {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = when (state.phase) {
                    ModelPhase.Missing -> "每种语言约 30 MB"
                    ModelPhase.Downloading -> "正在下载"
                    ModelPhase.Preparing -> "正在检查"
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
    }
}

private fun engineName(engine: TranslationEngine): String = when (engine) {
    TranslationEngine.GoogleOnDevice -> "Google 本地"
    TranslationEngine.Google2 -> "Google"
    TranslationEngine.DeepL -> "DeepL"
    TranslationEngine.OpenAICompatible -> "LLM"
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
