package com.captions.android.platform.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.captions.android.CaptionsApplication
import com.captions.android.MainActivity
import com.captions.android.R
import com.captions.android.core.session.SessionUiState
import com.captions.android.platform.overlay.AndroidCaptionOverlay
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.launch

class CaptionSessionService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val runtime get() = (application as CaptionsApplication).runtime
    private lateinit var notificationManager: NotificationManager
    private lateinit var overlay: AndroidCaptionOverlay
    private var observedActiveSession = false
    private var displayedNotificationStatus = ""

    override fun onCreate() {
        super.onCreate()
        notificationManager = getSystemService(NotificationManager::class.java)
        overlay = AndroidCaptionOverlay(this)
        createNotificationChannel()
        val initialState = runtime.sessionStore.state.value
        displayedNotificationStatus = notificationStatus(initialState)
        startForeground(
            NOTIFICATION_ID,
            notification(displayedNotificationStatus),
            ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE,
        )
        scope.launch {
            combine(runtime.sessionStore.state, runtime.appVisible) { state, appVisible ->
                state to appVisible
            }.collectLatest { (state, appVisible) ->
                overlay.render(
                    if (appVisible) state.copy(overlayEnabled = false) else state,
                )
                val active = state.starting || state.running
                if (active) {
                    observedActiveSession = true
                    val status = notificationStatus(state)
                    if (status != displayedNotificationStatus) {
                        displayedNotificationStatus = status
                        notificationManager.notify(NOTIFICATION_ID, notification(status))
                    }
                } else if (observedActiveSession) {
                    stopForeground(STOP_FOREGROUND_REMOVE)
                    stopSelf()
                }
            }
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_PAUSE) {
            runtime.sessionController.pause()
        }
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        scope.cancel()
        overlay.close()
        if (runtime.sessionStore.state.value.let { it.starting || it.running }) {
            runtime.sessionController.pause()
        }
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun createNotificationChannel() {
        notificationManager.createNotificationChannel(
            NotificationChannel(
                CHANNEL_ID,
                "实时字幕会话",
                NotificationManager.IMPORTANCE_LOW,
            ).apply {
                description = "识别运行状态"
                setSound(null, null)
                enableVibration(false)
            },
        )
    }

    private fun notification(status: String): Notification {
        val openApp = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
            },
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val pause = PendingIntent.getService(
            this,
            1,
            Intent(this, CaptionSessionService::class.java).setAction(ACTION_PAUSE),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_mic)
            .setContentTitle("实时字幕")
            .setContentText(status)
            .setContentIntent(openApp)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .addAction(R.drawable.ic_pause, "暂停", pause)
            .build()
    }

    private fun notificationStatus(state: SessionUiState): String = when {
        state.starting -> "正在准备"
        !state.microphoneEnabled -> "会话进行中 · 麦克风关闭"
        state.translationSettings.enabled -> "正在识别与翻译"
        else -> "正在识别"
    }

    companion object {
        private const val CHANNEL_ID = "captions_session"
        private const val NOTIFICATION_ID = 1001
        private const val ACTION_PAUSE = "com.captions.android.action.PAUSE"

        fun start(context: Context) {
            ContextCompat.startForegroundService(
                context,
                Intent(context, CaptionSessionService::class.java),
            )
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, CaptionSessionService::class.java))
        }
    }
}
