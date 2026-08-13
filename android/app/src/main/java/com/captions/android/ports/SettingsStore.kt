package com.captions.android.ports

import com.captions.android.core.session.AppearanceSettings

interface SettingsStore {
    fun loadAppearance(): AppearanceSettings
    fun saveAppearance(settings: AppearanceSettings)
}
