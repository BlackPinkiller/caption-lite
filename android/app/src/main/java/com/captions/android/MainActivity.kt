package com.captions.android

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.runtime.getValue
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.setValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.core.content.ContextCompat
import androidx.compose.foundation.layout.Box
import com.captions.android.platform.session.AndroidScreenAwakeController
import com.captions.android.ui.settings.SettingsPanel
import com.captions.android.ui.session.SessionScreen
import com.captions.android.ui.session.SessionViewModel
import com.captions.android.ui.theme.CaptionsTheme

class MainActivity : ComponentActivity() {
    private var startAfterMicrophonePermission = false
    private val runtime
        get() = (application as CaptionsApplication).runtime
    private val sessionViewModel: SessionViewModel by viewModels {
        SessionViewModel.Factory(runtime.sessionStore)
    }
    private val sessionController get() = runtime.sessionController
    private val modelManager get() = runtime.recognitionModelManager
    private val translationModelManager get() = runtime.translationModelManager
    private val screenAwakeController by lazy { AndroidScreenAwakeController(window) }

    private val microphonePermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        if (granted) {
            sessionController.setMicrophoneEnabled(true)
            if (startAfterMicrophonePermission) sessionController.start()
        } else {
            sessionController.setMicrophoneEnabled(false)
            sessionViewModel.showMessage("需要麦克风权限才能识别语音")
        }
        startAfterMicrophonePermission = false
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        translationModelManager.configure(sessionViewModel.state.value.translationSettings)

        setContent {
            val state by sessionViewModel.state.collectAsStateWithLifecycle()
            val modelState by modelManager.state.collectAsStateWithLifecycle()
            val translationModelState by translationModelManager.state.collectAsStateWithLifecycle()
            var settingsOpen by rememberSaveable { mutableStateOf(false) }
            val sessionActive = state.running || state.starting
            DisposableEffect(sessionActive) {
                screenAwakeController.setSessionActive(sessionActive)
                onDispose {
                    if (sessionActive) screenAwakeController.setSessionActive(false)
                }
            }
            BackHandler(enabled = settingsOpen) { settingsOpen = false }
            CaptionsTheme {
                Box {
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
                            } else if (!state.microphoneEnabled) {
                                sessionViewModel.showMessage("请先开启麦克风")
                            } else if (hasMicrophonePermission()) {
                                sessionController.start()
                            } else {
                                startAfterMicrophonePermission = true
                                microphonePermission.launch(Manifest.permission.RECORD_AUDIO)
                            }
                        },
                        onOpenSettings = { settingsOpen = true },
                    )
                    if (settingsOpen) {
                        SettingsPanel(
                            state = state,
                            modelState = modelState,
                            translationModelState = translationModelState,
                            onRecognitionEngineChanged = {
                                if (state.running || state.starting) sessionController.pause()
                                sessionViewModel.setRecognitionEngine(it)
                            },
                            onDownloadModel = modelManager::download,
                            onTranslationSettingsChanged = {
                                sessionViewModel.setTranslationSettings(it)
                                runtime.applyTranslationSettings()
                            },
                            onDownloadTranslationModel = translationModelManager::download,
                            onDisplayModeChanged = sessionViewModel::setDisplayMode,
                            onFontChoiceChanged = sessionViewModel::setFontChoice,
                            onSourceSizeChanged = sessionViewModel::setSourceSize,
                            onTranslationSizeChanged = sessionViewModel::setTranslationSize,
                            onDismiss = { settingsOpen = false },
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

    override fun onDestroy() {
        screenAwakeController.setSessionActive(false)
        super.onDestroy()
    }
}
