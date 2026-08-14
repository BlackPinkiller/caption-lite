package com.captions.android

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.getValue
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.setValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.core.content.ContextCompat
import androidx.compose.ui.Modifier
import com.captions.android.platform.session.AndroidScreenAwakeController
import com.captions.android.platform.service.CaptionSessionService
import com.captions.android.ui.settings.SettingsScreen
import com.captions.android.ui.session.SessionScreen
import com.captions.android.ui.session.SessionViewModel
import com.captions.android.ui.theme.CaptionsTheme

class MainActivity : ComponentActivity() {
    private var startAfterMicrophonePermission = false
    private var startAfterNotificationPermission = false
    private var enableOverlayAfterPermission = false
    private val runtime
        get() = (application as CaptionsApplication).runtime
    private val sessionViewModel: SessionViewModel by viewModels {
        SessionViewModel.Factory(runtime.sessionStore)
    }
    private val sessionController get() = runtime.sessionController
    private val modelManager get() = runtime.recognitionModelManager
    private val systemModelManager get() = runtime.systemRecognitionModelManager
    private val translationModelManager get() = runtime.translationModelManager
    private val hyMt2ModelManager get() = runtime.hyMt2ModelManager
    private val screenAwakeController by lazy { AndroidScreenAwakeController(window) }

    private val microphonePermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        if (granted) {
            sessionController.setMicrophoneEnabled(true)
            if (startAfterMicrophonePermission) requestNotificationAndStart()
        } else {
            sessionController.setMicrophoneEnabled(false)
            sessionViewModel.showMessage("需要麦克风权限才能识别语音")
        }
        startAfterMicrophonePermission = false
    }

    private val notificationPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) {
        if (startAfterNotificationPermission) startSession()
        startAfterNotificationPermission = false
    }

    private val overlayPermission = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult(),
    ) {
        if (enableOverlayAfterPermission) {
            if (Settings.canDrawOverlays(this)) {
                sessionViewModel.setOverlayEnabled(true)
            } else {
                sessionViewModel.showMessage("需要悬浮窗权限才能显示字幕")
            }
        }
        enableOverlayAfterPermission = false
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        systemModelManager.configure(
            sessionViewModel.state.value.translationSettings.sourceLanguage,
        )
        if (sessionViewModel.state.value.overlayEnabled && !Settings.canDrawOverlays(this)) {
            sessionViewModel.setOverlayEnabled(false)
        }

        setContent {
            val state by sessionViewModel.state.collectAsStateWithLifecycle()
            val modelState by modelManager.state.collectAsStateWithLifecycle()
            val systemModelState by systemModelManager.state.collectAsStateWithLifecycle()
            val translationModelState by translationModelManager.state.collectAsStateWithLifecycle()
            val hyMt2ModelState by hyMt2ModelManager.state.collectAsStateWithLifecycle()
            var settingsOpen by rememberSaveable { mutableStateOf(false) }
            val sessionActive = state.running || state.starting
            DisposableEffect(sessionActive) {
                screenAwakeController.setSessionActive(sessionActive)
                onDispose {
                    if (sessionActive) screenAwakeController.setSessionActive(false)
                }
            }
            CaptionsTheme {
                AnimatedContent(
                    targetState = settingsOpen,
                    modifier = Modifier.fillMaxSize(),
                    transitionSpec = {
                        if (targetState) {
                            (slideInHorizontally { it } + fadeIn()) togetherWith
                                (slideOutHorizontally { -it / 3 } + fadeOut())
                        } else {
                            (slideInHorizontally { -it / 3 } + fadeIn()) togetherWith
                                (slideOutHorizontally { it } + fadeOut())
                        }
                    },
                    label = "main-settings-navigation",
                ) { showSettings ->
                    if (showSettings) {
                        SettingsScreen(
                            state = state,
                            modelState = modelState,
                            systemModelState = systemModelState,
                            translationModelState = translationModelState,
                            hyMt2ModelState = hyMt2ModelState,
                            onRecognitionEngineChanged = {
                                if (state.running || state.starting) {
                                    sessionController.pause()
                                    CaptionSessionService.stop(this@MainActivity)
                                }
                                sessionViewModel.setRecognitionEngine(it)
                                runtime.applyTranslationSettings()
                                systemModelManager.configure(
                                    sessionViewModel.state.value.translationSettings.sourceLanguage,
                                )
                            },
                            onRecognitionLanguageChanged = { language ->
                                sessionViewModel.setTranslationSettings(
                                    state.translationSettings.copy(sourceLanguage = language),
                                )
                                runtime.applyTranslationSettings()
                                systemModelManager.configure(language)
                            },
                            onDownloadModel = modelManager::download,
                            onDownloadSystemModel = systemModelManager::download,
                            onTranslationSettingsChanged = {
                                sessionViewModel.setTranslationSettings(it)
                                runtime.applyTranslationSettings()
                            },
                            onDownloadTranslationModel = translationModelManager::download,
                            onDownloadHyMt2Model = hyMt2ModelManager::download,
                            onDisplayModeChanged = sessionViewModel::setDisplayMode,
                            onFontChoiceChanged = sessionViewModel::setFontChoice,
                            onSourceSizeChanged = sessionViewModel::setSourceSize,
                            onTranslationSizeChanged = sessionViewModel::setTranslationSize,
                            onOverlayEnabledChanged = ::setOverlayEnabled,
                            onOverlayBackgroundChanged = sessionViewModel::setOverlayBackgroundEnabled,
                            onOverlayPositionChanged = sessionViewModel::setOverlayPosition,
                            onDismiss = { settingsOpen = false },
                        )
                    } else {
                        SessionScreen(
                            state = state,
                            onToggleMicrophone = {
                                if (state.microphoneEnabled) {
                                    sessionController.setMicrophoneEnabled(false)
                                } else if (hasMicrophonePermission()) {
                                    sessionController.setMicrophoneEnabled(true)
                                } else {
                                    startAfterMicrophonePermission = false
                                    microphonePermission.launch(Manifest.permission.RECORD_AUDIO)
                                }
                            },
                            onToggleRunning = {
                                if (state.running) {
                                    sessionController.pause()
                                    CaptionSessionService.stop(this@MainActivity)
                                } else if (!state.microphoneEnabled) {
                                    sessionViewModel.showMessage("请先开启麦克风")
                                } else if (hasMicrophonePermission()) {
                                    requestNotificationAndStart()
                                } else {
                                    startAfterMicrophonePermission = true
                                    microphonePermission.launch(Manifest.permission.RECORD_AUDIO)
                                }
                            },
                            onOpenSettings = { settingsOpen = true },
                        )
                    }
                }
            }
        }

        if (!hasMicrophonePermission()) {
            sessionController.setMicrophoneEnabled(false)
            microphonePermission.launch(Manifest.permission.RECORD_AUDIO)
        }
    }

    private fun hasMicrophonePermission(): Boolean =
        ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) ==
            PackageManager.PERMISSION_GRANTED

    private fun requestNotificationAndStart() {
        if (hasNotificationPermission()) {
            startSession()
        } else {
            startAfterNotificationPermission = true
            notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }

    private fun hasNotificationPermission(): Boolean =
        ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED

    private fun startSession() {
        CaptionSessionService.start(this)
        sessionController.start()
    }

    private fun setOverlayEnabled(enabled: Boolean) {
        if (!enabled) {
            sessionViewModel.setOverlayEnabled(false)
        } else if (Settings.canDrawOverlays(this)) {
            sessionViewModel.setOverlayEnabled(true)
        } else {
            enableOverlayAfterPermission = true
            overlayPermission.launch(
                Intent(
                    Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:$packageName"),
                ),
            )
        }
    }

    override fun onStart() {
        super.onStart()
        runtime.setAppVisible(true)
    }

    override fun onResume() {
        super.onResume()
        translationModelManager.configure(sessionViewModel.state.value.translationSettings)
        hyMt2ModelManager.configure(sessionViewModel.state.value.translationSettings)
    }

    override fun onStop() {
        runtime.setAppVisible(false)
        super.onStop()
    }

    override fun onDestroy() {
        screenAwakeController.setSessionActive(false)
        super.onDestroy()
    }
}
