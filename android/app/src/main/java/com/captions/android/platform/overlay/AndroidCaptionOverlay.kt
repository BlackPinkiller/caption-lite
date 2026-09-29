package com.captions.android.platform.overlay

import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.provider.Settings
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.LinearLayout
import android.widget.TextView
import com.captions.android.core.session.DisplayMode
import com.captions.android.core.session.FontChoice
import com.captions.android.core.session.OverlayPosition
import com.captions.android.core.session.SessionUiState
import com.captions.android.core.session.effectiveDisplayMode
import com.captions.android.core.session.overlayEntry
import com.captions.android.ports.CaptionOverlay
import kotlin.math.roundToInt

class AndroidCaptionOverlay(context: Context) : CaptionOverlay {
    private val appContext = context.applicationContext
    private val windowManager = appContext.getSystemService(WindowManager::class.java)
    private val source = captionView()
    private val translation = captionView()
    private val root = LinearLayout(appContext).apply {
        orientation = LinearLayout.VERTICAL
        gravity = Gravity.CENTER_HORIZONTAL
        addView(source)
        addView(translation)
    }
    private val params = WindowManager.LayoutParams(
        WindowManager.LayoutParams.WRAP_CONTENT,
        WindowManager.LayoutParams.WRAP_CONTENT,
        WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
        WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
            WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL or
            WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
        android.graphics.PixelFormat.TRANSLUCENT,
    )
    private var attached = false
    private var position = OverlayPosition.Bottom
    private var touchStartX = 0f
    private var touchStartY = 0f
    private var windowStartX = 0
    private var windowStartY = 0

    init {
        root.setOnTouchListener(::onTouch)
    }

    override fun render(state: SessionUiState) {
        val active = state.starting || state.running
        val entry = state.overlayEntry()
        val displayMode = state.effectiveDisplayMode()
        val shouldShow = state.overlayEnabled && active && entry != null &&
            Settings.canDrawOverlays(appContext)
        if (!shouldShow) {
            detach()
            return
        }

        source.text = entry.source
        translation.text = entry.translation
        source.visibility = if (
            displayMode != DisplayMode.Translation && source.text.isNotBlank()
        ) View.VISIBLE else View.GONE
        translation.visibility = if (
            displayMode != DisplayMode.Source && translation.text.isNotBlank()
        ) View.VISIBLE else View.GONE
        source.textSize = state.sourceSizeSp.toFloat()
        translation.textSize = state.translationSizeSp.toFloat()
        val captionMaxWidth = (windowManager.currentWindowMetrics.bounds.width() - dp(32))
            .coerceAtLeast(dp(160))
        source.maxWidth = captionMaxWidth
        translation.maxWidth = captionMaxWidth
        val typeface = when (state.fontChoice) {
            FontChoice.System -> Typeface.DEFAULT
            FontChoice.Serif -> Typeface.SERIF
            FontChoice.Monospace -> Typeface.MONOSPACE
        }
        source.typeface = typeface
        translation.typeface = Typeface.create(typeface, Typeface.BOLD)
        val background = state.overlayBackgroundEnabled
        styleCaption(source, background, secondary = true)
        styleCaption(translation, background, secondary = false)
        applyPosition(state.overlayPosition)
        if (attached) {
            windowManager.updateViewLayout(root, params)
        } else {
            windowManager.addView(root, params)
            attached = true
        }
    }

    override fun close() = detach()

    private fun captionView() = TextView(appContext).apply {
        gravity = Gravity.CENTER
        maxLines = 2
        ellipsize = null
        includeFontPadding = false
        setTextColor(Color.WHITE)
        setShadowLayer(dp(3).toFloat(), 0f, dp(1).toFloat(), Color.BLACK)
        layoutParams = LinearLayout.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
        ).apply {
            gravity = Gravity.CENTER_HORIZONTAL
            bottomMargin = dp(3)
        }
    }

    private fun styleCaption(view: TextView, background: Boolean, secondary: Boolean) {
        view.setTextColor(if (secondary) Color.rgb(225, 225, 228) else Color.WHITE)
        if (background) {
            view.setPadding(dp(9), dp(4), dp(9), dp(4))
            view.background = GradientDrawable().apply {
                color = android.content.res.ColorStateList.valueOf(Color.argb(184, 12, 13, 16))
                cornerRadius = dp(7).toFloat()
            }
            view.setShadowLayer(0f, 0f, 0f, Color.TRANSPARENT)
        } else {
            view.setPadding(dp(2), dp(1), dp(2), dp(1))
            view.background = null
            view.setShadowLayer(dp(3).toFloat(), 0f, dp(1).toFloat(), Color.BLACK)
        }
    }

    private fun applyPosition(newPosition: OverlayPosition) {
        if (position == newPosition && attached) return
        position = newPosition
        when (newPosition) {
            OverlayPosition.Top -> {
                params.gravity = Gravity.TOP or Gravity.CENTER_HORIZONTAL
                params.x = 0
                params.y = dp(72)
            }
            OverlayPosition.Bottom -> {
                params.gravity = Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL
                params.x = 0
                params.y = dp(96)
            }
            OverlayPosition.Free -> {
                params.gravity = Gravity.TOP or Gravity.START
                val bounds = windowManager.currentWindowMetrics.bounds
                params.x = ((bounds.width() - root.width) / 2).coerceAtLeast(0)
                params.y = (bounds.height() * 0.72f).roundToInt()
            }
        }
    }

    private fun onTouch(view: View, event: MotionEvent): Boolean {
        if (position != OverlayPosition.Free) return false
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                touchStartX = event.rawX
                touchStartY = event.rawY
                windowStartX = params.x
                windowStartY = params.y
                return true
            }
            MotionEvent.ACTION_MOVE -> {
                val bounds = windowManager.currentWindowMetrics.bounds
                params.x = (windowStartX + event.rawX - touchStartX).roundToInt()
                    .coerceIn(0, (bounds.width() - view.width).coerceAtLeast(0))
                params.y = (windowStartY + event.rawY - touchStartY).roundToInt()
                    .coerceIn(0, (bounds.height() - view.height).coerceAtLeast(0))
                if (attached) windowManager.updateViewLayout(root, params)
                return true
            }
            MotionEvent.ACTION_UP,
            MotionEvent.ACTION_CANCEL,
            -> return true
        }
        return false
    }

    private fun detach() {
        if (!attached) return
        windowManager.removeView(root)
        attached = false
    }

    private fun dp(value: Int): Int =
        (value * appContext.resources.displayMetrics.density).roundToInt()
}
