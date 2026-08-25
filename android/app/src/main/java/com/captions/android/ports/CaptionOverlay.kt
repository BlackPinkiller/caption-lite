package com.captions.android.ports

import com.captions.android.core.session.SessionUiState

interface CaptionOverlay : AutoCloseable {
    fun render(state: SessionUiState)
}
