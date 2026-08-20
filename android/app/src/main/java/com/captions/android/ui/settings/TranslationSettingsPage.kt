package com.captions.android.ui.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
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
import com.captions.android.ports.ModelState

@Composable
internal fun TranslationSettingsPage(
    settings: TranslationSettings,
    modelState: ModelState,
    gemma4ModelState: ModelState,
    onChanged: (TranslationSettings) -> Unit,
    onDownloadModel: () -> Unit,
    onDownloadGemma4Model: () -> Unit,
) {
    var advancedOpen by rememberSaveable { mutableStateOf(false) }
    SettingsPage {
        SettingGroup(label = "翻译设置") {
            ToggleSetting(
                label = "启用翻译",
                supportingText = if (settings.enabled) {
                    "当前：${engineName(settings.engine)}"
                } else {
                    "已关闭"
                },
                checked = settings.enabled,
                onCheckedChange = { onChanged(settings.copy(enabled = it)) },
            )
            if (settings.enabled) {
                HorizontalDivider()
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 10.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Text(
                        text = "翻译服务",
                        fontSize = 15.sp,
                        color = MaterialTheme.colorScheme.onSurface,
                    )
                    ChoiceRow(
                        choices = listOf(
                            TranslationEngine.GoogleOnDevice to "Google 本地",
                            TranslationEngine.Google2 to "Google",
                            TranslationEngine.Gemma4 to "Gemma 4",
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
            }
        }
        SettingGroup(label = "语言") {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                LanguageMenu(
                    label = "原文",
                    selected = settings.sourceLanguage,
                    onSelected = {},
                    modifier = Modifier.weight(1f),
                    enabled = false,
                )
                Text("→", color = MaterialTheme.colorScheme.onSurfaceVariant)
                LanguageMenu(
                    label = "译文",
                    selected = settings.targetLanguage,
                    onSelected = { target ->
                        onChanged(settings.copy(targetLanguage = target))
                    },
                    modifier = Modifier.weight(1f),
                    choices = LANGUAGES.filterNot { it.first == settings.sourceLanguage },
                )
            }
        }
        if (settings.enabled) {
            when (settings.engine) {
                TranslationEngine.GoogleOnDevice -> SettingGroup(label = "本地模型") {
                    ModelStatusRow(
                        state = modelState,
                        onDownload = onDownloadModel,
                        missingLabel = "每种语言约 30 MB",
                    )
                }
                TranslationEngine.Gemma4 -> SettingGroup(label = "本地模型") {
                    ModelStatusRow(
                        state = gemma4ModelState,
                        onDownload = onDownloadGemma4Model,
                        missingLabel = "约 2.0 GB",
                        prefix = "Gemma 4 · ",
                    )
                }
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
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 4.dp),
        )
        Column(
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
        ) {
            ChoiceRow(
                choices = listOf(false to "API Free", true to "API Pro"),
                selected = settings.deeplPro,
                onSelected = { onChanged(settings.copy(deeplPro = it)) },
            )
        }
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
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 4.dp),
        )
        OutlinedTextField(
            value = settings.llmApiKey,
            onValueChange = { onChanged(settings.copy(llmApiKey = it)) },
            label = { Text("API 密钥") },
            visualTransformation = PasswordVisualTransformation(),
            singleLine = true,
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 4.dp),
        )
        Row(
            modifier = Modifier.padding(start = 16.dp, top = 4.dp, bottom = 4.dp),
        ) {
            TextButton(onClick = { onAdvancedOpenChanged(!advancedOpen) }) {
                Text(if (advancedOpen) "收起高级设置" else "高级设置")
            }
        }
        if (advancedOpen) {
            OutlinedTextField(
                value = settings.llmBaseUrl,
                onValueChange = { onChanged(settings.copy(llmBaseUrl = it)) },
                label = { Text("API 地址") },
                singleLine = true,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 4.dp),
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
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 4.dp),
            )
            Row(
                modifier = Modifier.padding(start = 16.dp, top = 4.dp, bottom = 4.dp),
            ) {
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
}

private fun engineName(engine: TranslationEngine): String = when (engine) {
    TranslationEngine.GoogleOnDevice -> "Google 本地"
    TranslationEngine.Google2 -> "Google"
    TranslationEngine.DeepL -> "DeepL"
    TranslationEngine.OpenAICompatible -> "LLM"
    TranslationEngine.Gemma4 -> "Gemma 4"
}
