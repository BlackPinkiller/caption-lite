package com.captions.android.ui.settings

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.captions.android.core.session.DisplayMode
import com.captions.android.core.session.OverlayPosition
import com.captions.android.core.recognition.PunctuationMode

@Composable
internal fun CaptionSettingsPage(
    displayMode: DisplayMode,
    punctuationMode: PunctuationMode,
    overlayEnabled: Boolean,
    backgroundEnabled: Boolean,
    overlayPosition: OverlayPosition,
    onDisplayModeChanged: (DisplayMode) -> Unit,
    onPunctuationModeChanged: (PunctuationMode) -> Unit,
    onOverlayEnabledChanged: (Boolean) -> Unit,
    onOverlayBackgroundChanged: (Boolean) -> Unit,
    onOverlayPositionChanged: (OverlayPosition) -> Unit,
) {
    SettingsPage {
        SettingGroup(label = "显示内容") {
            SegmentedChoiceRow(
                choices = listOf(
                    DisplayMode.Bilingual to "双语",
                    DisplayMode.Source to "原文",
                    DisplayMode.Translation to "译文",
                ),
                selected = displayMode,
                onSelected = onDisplayModeChanged,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
            )
        }
        SettingGroup(label = "分句") {
            SegmentedChoiceRow(
                choices = listOf(
                    PunctuationMode.Off to "关闭",
                    PunctuationMode.Sentence to "句末",
                    PunctuationMode.All to "所有",
                ),
                selected = punctuationMode,
                onSelected = onPunctuationModeChanged,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
            )
        }
        SettingGroup(label = "悬浮字幕") {
            ToggleSetting(
                label = "在其他应用上显示",
                checked = overlayEnabled,
                onCheckedChange = onOverlayEnabledChanged,
            )
            if (overlayEnabled) {
                HorizontalDivider()
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 10.dp),
                ) {
                    Text(
                        text = "位置",
                        fontSize = 15.sp,
                        color = MaterialTheme.colorScheme.onSurface,
                    )
                    Spacer(Modifier.height(10.dp))
                    SegmentedChoiceRow(
                        choices = listOf(
                            OverlayPosition.Free to "自由",
                            OverlayPosition.Top to "顶部",
                            OverlayPosition.Bottom to "底部",
                        ),
                        selected = overlayPosition,
                        onSelected = onOverlayPositionChanged,
                    )
                }
                HorizontalDivider()
                ToggleSetting(
                    label = "文字背景",
                    checked = backgroundEnabled,
                    onCheckedChange = onOverlayBackgroundChanged,
                )
            }
        }
    }
}
