package com.captions.android.platform.audio

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import com.captions.android.BuildConfig
import com.captions.android.ports.AudioInput
import android.util.Log
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread
import kotlin.math.max

class AndroidMicrophoneInput : AudioInput {
    private val active = AtomicBoolean(false)
    private val stateLock = Any()
    private var recorder: AudioRecord? = null
    private var worker: Thread? = null

    override val running: Boolean
        get() = active.get()

    @SuppressLint("MissingPermission")
    override fun start(onSamples: (ShortArray) -> Unit, onError: (String) -> Unit) {
        synchronized(stateLock) {
            if (active.get()) return

            val minBufferBytes = AudioRecord.getMinBufferSize(
                SAMPLE_RATE,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
            )
            require(minBufferBytes > 0) { "无法初始化麦克风" }

            val nextRecorder = AudioRecord.Builder()
                .setAudioSource(MediaRecorder.AudioSource.VOICE_RECOGNITION)
                .setAudioFormat(
                    AudioFormat.Builder()
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                        .setSampleRate(SAMPLE_RATE)
                        .setChannelMask(AudioFormat.CHANNEL_IN_MONO)
                        .build(),
                )
                .setBufferSizeInBytes(max(minBufferBytes, BUFFER_SAMPLES * Short.SIZE_BYTES))
                .build()

            check(nextRecorder.state == AudioRecord.STATE_INITIALIZED) { "无法初始化麦克风" }
            nextRecorder.startRecording()
            recorder = nextRecorder
            active.set(true)
            worker = thread(name = "captions-microphone", isDaemon = true) {
                readLoop(nextRecorder, onSamples, onError)
            }
        }
    }

    override fun stop() {
        val currentRecorder: AudioRecord?
        val currentWorker: Thread?
        synchronized(stateLock) {
            if (!active.getAndSet(false) && recorder == null) return
            currentRecorder = recorder
            currentWorker = worker
        }

        runCatching { currentRecorder?.stop() }
        currentWorker?.join(STOP_JOIN_MILLIS)
        runCatching { currentRecorder?.release() }
        synchronized(stateLock) {
            if (recorder === currentRecorder) recorder = null
            if (worker === currentWorker) worker = null
        }
    }

    private fun readLoop(
        currentRecorder: AudioRecord,
        onSamples: (ShortArray) -> Unit,
        onError: (String) -> Unit,
    ) {
        val buffer = ShortArray(BUFFER_SAMPLES)
        var firstFrame = true
        try {
            while (active.get()) {
                val count = currentRecorder.read(buffer, 0, buffer.size, AudioRecord.READ_BLOCKING)
                if (count > 0) {
                    if (firstFrame && BuildConfig.DEBUG) {
                        Log.d(LOG_TAG, "Microphone capture active: ${SAMPLE_RATE}Hz mono PCM16")
                        firstFrame = false
                    }
                    onSamples(buffer.copyOf(count))
                } else if (count < 0 && active.get()) {
                    Log.e(LOG_TAG, "AudioRecord.read failed: $count")
                    active.set(false)
                    onError("麦克风读取失败")
                }
            }
        } finally {
            runCatching { currentRecorder.stop() }
            runCatching { currentRecorder.release() }
            synchronized(stateLock) {
                if (recorder === currentRecorder) recorder = null
                if (worker === Thread.currentThread()) worker = null
            }
        }
    }

    private companion object {
        const val LOG_TAG = "CaptionsAudio"
        const val SAMPLE_RATE = 16_000
        const val BUFFER_SAMPLES = 1_600
        const val STOP_JOIN_MILLIS = 500L
    }
}
