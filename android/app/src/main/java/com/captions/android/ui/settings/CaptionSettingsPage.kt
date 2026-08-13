package com.captions.android.ui.settings

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.sp
import com.captions.android.core.session.DisplayMode
import com.captions.android.core.session.OverlayPosition

@Composable
internal fun CaptionSettingsPage(
    displayMode: DisplayMode,
    overlayEnabled: Boolean,
    backgroundEnabled: Boolean,
    overlayPosition: OverlayPosition,
    onDisplayModeChanged: (DisplayMode) -> Unit,
    onOverlayEnabledChanged: (Boolean) -> Unit,
    onOverlayBackgroundChanged: (Boolean) -> Unit,
    onOverlayPositionChanged: (OverlayPosition) -> Unit,
) {
    SettingsPage {
        SettingGroup(label = "显示内容") {
            ChoiceRow(
                choices = listOf(
                    DisplayMode.Bilingual to "双语",
                    DisplayMode.Source to "原文",
                    DisplayMode.Translation to "译文",
                ),
                selected = displayMode,
                onSelected = onDisplayModeChanged,
            )
        }
        SettingGroup(label = "悬浮字幕") {
            ToggleSetting(
                label = "在其他应用上显示",
                checked = overlayEnabled,
                onCheckedChange = onOverlayEnabledChanged,
            )
            if (overlayEnabled) {
                ChoiceRow(
                    choices = listOf(
                        OverlayPosition.Free to "自由",
                        OverlayPosition.Top to "顶部",
                        OverlayPosition.Bottom to "底部",
                    ),
                    selected = overlayPosition,
                    onSelected = onOverlayPositionChanged,
                )
                ToggleSetting(
                    label = "文字背景",
                    checked = backgroundEnabled,
                    onCheckedChange = onOverlayBackgroundChanged,
                )
            }
        }
    }
}

@Composable
private fun ToggleSetting(
    label: String,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, fontSize = 15.sp)
        Spacer(Modifier.weight(1f))
        Switch(checked = checked, onCheckedChange = onCheckedChange)
    }
}
