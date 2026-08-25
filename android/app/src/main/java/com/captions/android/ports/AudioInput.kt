package com.captions.android.ports

interface AudioInput : AutoCloseable {
    val running: Boolean

    fun start(
        onSamples: (ShortArray) -> Unit,
        onError: (String) -> Unit,
    )

    fun stop()

    override fun close() = stop()
}
