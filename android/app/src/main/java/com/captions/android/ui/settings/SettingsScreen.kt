package com.captions.android.ui.settings

import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
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
    onRecognitionEngineChanged: (RecognitionEngine) -> Unit,
    onRecognitionLanguageChanged: (String) -> Unit,
    onDownloadModel: () -> Unit,
    onDownloadSystemModel: () -> Unit,
    onTranslationSettingsChanged: (TranslationSettings) -> Unit,
    onDownloadTranslationModel: () -> Unit,
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
                    onChanged = onTranslationSettingsChanged,
                    onDownloadModel = onDownloadTranslationModel,
                )
                SettingsDestination.Captions -> CaptionSettingsPage(
                    displayMode = state.displayMode,
                    overlayEnabled = state.overlayEnabled,
                    backgroundEnabled = state.overlayBackgroundEnabled,
                    overlayPosition = state.overlayPosition,
                    onDisplayModeChanged = onDisplayModeChanged,
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
    onOpen: (SettingsDestination) -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 18.dp, vertical = 14.dp),
        verticalArrangement = Arrangement.spacedBy(20.dp),
    ) {
        CategoryGroup(label = "核心") {
            SettingsDestinationRow(
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
            SettingsDestinationRow(
                title = "翻译",
                summary = translationSummary(state.translationSettings, translationModelState),
                onClick = { onOpen(SettingsDestination.Translation) },
            )
        }
        CategoryGroup(label = "显示") {
            SettingsDestinationRow(
                title = "字幕",
                summary = captionSummary(state),
                onClick = { onOpen(SettingsDestination.Captions) },
            )
            SettingsDestinationRow(
                title = "外观",
                summary = appearanceSummary(state),
                onClick = { onOpen(SettingsDestination.Appearance) },
            )
        }
    }
}

@Composable
private fun CategoryGroup(label: String, content: @Composable () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
        Text(
            text = label,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontSize = 13.sp,
            modifier = Modifier.padding(horizontal = 8.dp),
        )
        content()
    }
}

@Composable
private fun SettingsDestinationRow(
    title: String,
    summary: String,
    onClick: () -> Unit,
) {
    Surface(
        onClick = onClick,
        modifier = Modifier.fillMaxWidth(),
        shape = MaterialTheme.shapes.large,
        color = MaterialTheme.colorScheme.surfaceVariant,
    ) {
        ListItem(
            headlineContent = { Text(title) },
            supportingContent = {
                Text(summary, maxLines = 1)
            },
            trailingContent = {
                Icon(
                    imageVector = Icons.AutoMirrored.Filled.KeyboardArrowRight,
                    contentDescription = null,
                )
            },
            colors = ListItemDefaults.colors(containerColor = Color.Transparent),
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
