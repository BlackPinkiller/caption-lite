package com.captions.android.ui.settings

import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Palette
import androidx.compose.material.icons.filled.Subtitles
import androidx.compose.material.icons.filled.Translate
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.captions.android.core.session.DisplayMode
import com.captions.android.core.session.FontChoice
import com.captions.android.core.session.OverlayPosition
import com.captions.android.core.session.RecognitionEngine
import com.captions.android.core.session.SessionUiState
import com.captions.android.core.session.TranslationEngine
import com.captions.android.core.session.TranslationSettings
import com.captions.android.ports.ModelPhase
import com.captions.android.ports.ModelState

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    state: SessionUiState,
    modelState: ModelState,
    systemModelState: ModelState,
    translationModelState: ModelState,
    gemma4ModelState: ModelState,
    onRecognitionEngineChanged: (RecognitionEngine) -> Unit,
    onRecognitionLanguageChanged: (String) -> Unit,
    onSplitPunctuationChanged: (Boolean) -> Unit,
    onDownloadModel: () -> Unit,
    onDownloadSystemModel: () -> Unit,
    onTranslationSettingsChanged: (TranslationSettings) -> Unit,
    onDownloadTranslationModel: () -> Unit,
    onDownloadGemma4Model: () -> Unit,
    onDisplayModeChanged: (DisplayMode) -> Unit,
    onFontChoiceChanged: (FontChoice) -> Unit,
    onSourceSizeChanged: (Int) -> Unit,
    onTranslationSizeChanged: (Int) -> Unit,
    onOverlayEnabledChanged: (Boolean) -> Unit,
    onOverlayBackgroundChanged: (Boolean) -> Unit,
    onOverlayPositionChanged: (OverlayPosition) -> Unit,
    onDismiss: () -> Unit,
) {
    var destination by rememberSaveable { mutableStateOf(SettingsDestination.Home) }
    val goBack = {
        if (destination == SettingsDestination.Home) {
            onDismiss()
        } else {
            destination = SettingsDestination.Home
        }
    }
    BackHandler(onBack = goBack)

    Scaffold(
        modifier = Modifier.fillMaxSize(),
        containerColor = MaterialTheme.colorScheme.background,
        topBar = {
            TopAppBar(
                title = { Text(destination.title) },
                navigationIcon = {
                    IconButton(onClick = goBack) {
                        Icon(
                            imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = "返回",
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.background,
                ),
            )
        },
    ) { contentPadding ->
        AnimatedContent(
            targetState = destination,
            modifier = Modifier
                .fillMaxSize()
                .padding(contentPadding),
            transitionSpec = {
                if (targetState == SettingsDestination.Home) {
                    (slideInHorizontally { -it / 3 } + fadeIn()) togetherWith
                        (slideOutHorizontally { it } + fadeOut())
                } else {
                    (slideInHorizontally { it } + fadeIn()) togetherWith
                        (slideOutHorizontally { -it / 3 } + fadeOut())
                }
            },
            label = "settings-page",
        ) { page ->
            when (page) {
                SettingsDestination.Home -> SettingsHome(
                    state = state,
                    modelState = modelState,
                    systemModelState = systemModelState,
                    translationModelState = translationModelState,
                    gemma4ModelState = gemma4ModelState,
                    onOpen = { destination = it },
                )
                SettingsDestination.Recognition -> RecognitionSettingsPage(
                    engine = state.recognitionEngine,
                    language = state.translationSettings.sourceLanguage,
                    modelState = modelState,
                    systemModelState = systemModelState,
                    onEngineChanged = onRecognitionEngineChanged,
                    onLanguageChanged = onRecognitionLanguageChanged,
                    onDownloadModel = onDownloadModel,
                    onDownloadSystemModel = onDownloadSystemModel,
                )
                SettingsDestination.Translation -> TranslationSettingsPage(
                    settings = state.translationSettings,
                    modelState = translationModelState,
                    gemma4ModelState = gemma4ModelState,
                    onChanged = onTranslationSettingsChanged,
                    onDownloadModel = onDownloadTranslationModel,
                    onDownloadGemma4Model = onDownloadGemma4Model,
                )
                SettingsDestination.Captions -> CaptionSettingsPage(
                    displayMode = state.displayMode,
                    splitPunctuation = state.splitPunctuation,
                    overlayEnabled = state.overlayEnabled,
                    backgroundEnabled = state.overlayBackgroundEnabled,
                    overlayPosition = state.overlayPosition,
                    onDisplayModeChanged = onDisplayModeChanged,
                    onSplitPunctuationChanged = onSplitPunctuationChanged,
                    onOverlayEnabledChanged = onOverlayEnabledChanged,
                    onOverlayBackgroundChanged = onOverlayBackgroundChanged,
                    onOverlayPositionChanged = onOverlayPositionChanged,
                )
                SettingsDestination.Appearance -> AppearanceSettingsPage(
                    fontChoice = state.fontChoice,
                    sourceSizeSp = state.sourceSizeSp,
                    translationSizeSp = state.translationSizeSp,
                    onFontChoiceChanged = onFontChoiceChanged,
                    onSourceSizeChanged = onSourceSizeChanged,
                    onTranslationSizeChanged = onTranslationSizeChanged,
                )
            }
        }
    }
}

@Composable
private fun SettingsHome(
    state: SessionUiState,
    modelState: ModelState,
    systemModelState: ModelState,
    translationModelState: ModelState,
    gemma4ModelState: ModelState,
    onOpen: (SettingsDestination) -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 18.dp, vertical = 14.dp),
        verticalArrangement = Arrangement.spacedBy(20.dp),
    ) {
        SettingGroup(label = "识别与翻译") {
            SettingsDestinationRow(
                icon = Icons.Filled.Mic,
                title = "语音识别",
                summary = recognitionSummary(
                    state.recognitionEngine,
                    state.translationSettings.sourceLanguage,
                    if (state.recognitionEngine == RecognitionEngine.Nemotron) {
                        modelState
                    } else {
                        systemModelState
                    },
                ),
                onClick = { onOpen(SettingsDestination.Recognition) },
            )
            HorizontalDivider()
            SettingsDestinationRow(
                icon = Icons.Filled.Translate,
                title = "翻译",
                summary = translationSummary(
                    state.translationSettings,
                    if (state.translationSettings.engine == TranslationEngine.Gemma4) {
                        gemma4ModelState
                    } else {
                        translationModelState
                    },
                ),
                onClick = { onOpen(SettingsDestination.Translation) },
            )
        }
        SettingGroup(label = "显示") {
            SettingsDestinationRow(
                icon = Icons.Filled.Subtitles,
                title = "字幕",
                summary = captionSummary(state),
                onClick = { onOpen(SettingsDestination.Captions) },
            )
            HorizontalDivider()
            SettingsDestinationRow(
                icon = Icons.Filled.Palette,
                title = "外观",
                summary = appearanceSummary(state),
                onClick = { onOpen(SettingsDestination.Appearance) },
            )
        }
    }
}

@Composable
private fun SettingsDestinationRow(
    icon: ImageVector,
    title: String,
    summary: String,
    onClick: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        SettingsTonalIcon(icon = icon, contentDescription = null)
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f)) {
            Text(title, fontSize = 15.sp, color = MaterialTheme.colorScheme.onSurface)
            Spacer(Modifier.height(2.dp))
            Text(
                text = summary,
                fontSize = 12.sp,
                lineHeight = 17.sp,
                maxLines = 2,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Spacer(Modifier.width(12.dp))
        Icon(
            imageVector = Icons.AutoMirrored.Filled.KeyboardArrowRight,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

private fun recognitionSummary(
    engine: RecognitionEngine,
    language: String,
    state: ModelState,
): String = when (engine) {
    RecognitionEngine.AndroidSystem ->
        "系统识别 · ${languageName(language)} · ${modelSummary(state)}"
    RecognitionEngine.Nemotron -> "Nemotron · 英语 · ${modelSummary(state)}"
}

private fun translationSummary(settings: TranslationSettings, state: ModelState): String {
    if (!settings.enabled) return "已关闭"
    val engine = when (settings.engine) {
        TranslationEngine.GoogleOnDevice -> "Google 本地 · ${modelSummary(state)}"
        TranslationEngine.Google2 -> "Google"
        TranslationEngine.DeepL -> "DeepL"
        TranslationEngine.OpenAICompatible -> "LLM"
        TranslationEngine.Gemma4 -> "Gemma 4 · ${modelSummary(state)}"
    }
    return "$engine · ${languageName(settings.sourceLanguage)} → ${languageName(settings.targetLanguage)}"
}

private fun captionSummary(state: SessionUiState): String {
    val content = when (state.displayMode) {
        DisplayMode.Bilingual -> "双语"
        DisplayMode.Source -> "原文"
        DisplayMode.Translation -> "译文"
    }
    return if (state.overlayEnabled) "$content · 悬浮开启" else "$content · 悬浮关闭"
}

private fun appearanceSummary(state: SessionUiState): String {
    val font = when (state.fontChoice) {
        FontChoice.System -> "系统字体"
        FontChoice.Serif -> "衬线字体"
        FontChoice.Monospace -> "等宽字体"
    }
    return "$font · ${state.sourceSizeSp} / ${state.translationSizeSp}"
}

private fun modelSummary(state: ModelState): String = when (state.phase) {
    ModelPhase.Missing -> "未下载"
    ModelPhase.Downloading -> "下载中"
    ModelPhase.Preparing -> "准备中"
    ModelPhase.Ready -> "准备就绪"
    ModelPhase.Error -> "不可用"
}

private enum class SettingsDestination(val title: String) {
    Home("设置"),
    Recognition("语音识别"),
    Translation("翻译"),
    Captions("字幕"),
    Appearance("外观"),
}
