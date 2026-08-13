package com.captions.android

import android.app.Application
import com.captions.android.platform.app.AndroidAppRuntime

class CaptionsApplication : Application() {
    private val runtimeDelegate = lazy { AndroidAppRuntime(applicationContext) }
    val runtime: AndroidAppRuntime by runtimeDelegate

    override fun onTerminate() {
        if (runtimeDelegate.isInitialized()) runtime.close()
        super.onTerminate()
    }
}
