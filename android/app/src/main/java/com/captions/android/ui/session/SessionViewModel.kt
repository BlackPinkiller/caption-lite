package com.captions.android.ui.session

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import com.captions.android.core.session.SessionStore
import com.captions.android.ports.SessionStateController
import com.captions.android.ports.SettingsStore

class SessionViewModel(
    private val session: SessionStateController,
) : ViewModel(), SessionStateController by session {
    constructor(settingsStore: SettingsStore) : this(SessionStore(settingsStore))

    class Factory(
        private val session: SessionStateController,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            require(modelClass.isAssignableFrom(SessionViewModel::class.java))
            return SessionViewModel(session) as T
        }
    }
}
