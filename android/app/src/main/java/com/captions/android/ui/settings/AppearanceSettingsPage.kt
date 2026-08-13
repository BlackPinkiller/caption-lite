package com.captions.android.ui.settings

import androidx.compose.runtime.Composable
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
            ChoiceRow(
                choices = listOf(
                    FontChoice.System to "系统",
                    FontChoice.Serif to "衬线",
                    FontChoice.Monospace to "等宽",
                ),
                selected = fontChoice,
                onSelected = onFontChoiceChanged,
            )
        }
        SettingGroup(label = "字号") {
            SizeSetting("原文", sourceSizeSp, onSourceSizeChanged)
            SizeSetting("译文", translationSizeSp, onTranslationSizeChanged)
        }
    }
}
