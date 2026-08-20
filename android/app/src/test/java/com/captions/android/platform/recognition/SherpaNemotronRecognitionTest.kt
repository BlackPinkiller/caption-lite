package com.captions.android.platform.recognition

import com.captions.android.core.session.NemotronModel
import org.junit.Assert.assertEquals
import org.junit.Test

class SherpaNemotronRecognitionTest {
    @Test
    fun onlyEnglish560UsesTheShorterVadPreRoll() {
        assertEquals(32, vadPreRollWindows(NemotronModel.English560Ms))
        assertEquals(48, vadPreRollWindows(NemotronModel.English1120Ms))
    }
}
