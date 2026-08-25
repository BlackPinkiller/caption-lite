package com.captions.android.ui.settings

import androidx.compose.foundation.layout.padding
import androidx.compose.material3.HorizontalDivider
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.captions.android.core.session.FontChoice

@Composable
internal fun AppearanceSettingsPage(
    fontChoice: FontChoice,
    sourceSizeSp: Int,
    translationSizeSp: Int,
    onFontChoiceChanged: (FontChoice) -> Unit,
    onSourceSizeChanged: (Int) -> Unit,
    onTranslationSizeChanged: (Int) -> Unit,
) {
    SettingsPage {
        SettingGroup(label = "字体") {
            SegmentedChoiceRow(
                choices = listOf(
                    FontChoice.System to "系统",
                    FontChoice.Serif to "衬线",
                    FontChoice.Monospace to "等宽",
                ),
                selected = fontChoice,
                onSelected = onFontChoiceChanged,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
            )
            HorizontalDivider()
            SizeSetting("原文字号", sourceSizeSp, onSourceSizeChanged)
            HorizontalDivider()
            SizeSetting("译文字号", translationSizeSp, onTranslationSizeChanged)
        }
    }
}
