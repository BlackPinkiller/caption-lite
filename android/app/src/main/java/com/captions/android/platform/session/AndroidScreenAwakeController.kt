package com.captions.android.platform.session

import android.view.Window
import android.view.WindowManager
import com.captions.android.ports.ScreenAwakeController

class AndroidScreenAwakeController(
    private val window: Window,
) : ScreenAwakeController {
    override fun setSessionActive(active: Boolean) {
        if (active) {
            window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        } else {
            window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        }
    }
}
