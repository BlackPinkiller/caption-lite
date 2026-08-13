from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal, Slot

from captions.platforms.android.ui.session_model import SessionListModel


class AndroidViewModel(QObject):
    runningChanged = Signal()
    microphoneEnabledChanged = Signal()
    displayModeChanged = Signal()
    fontFamilyChanged = Signal()
    sourceSizeChanged = Signal()
    translationSizeChanged = Signal()
    startRequested = Signal()
    pauseRequested = Signal()
    microphoneRequested = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.session_model = SessionListModel(self)
        self._running = False
        self._microphone_enabled = True
        self._display_mode = "bilingual"
        self._font_family = "sans-serif"
        self._source_size = 14
        self._translation_size = 16

    @Property(QObject, constant=True)
    def sessionModel(self) -> QObject:
        return self.session_model

    @Property(bool, notify=runningChanged)
    def running(self) -> bool:
        return self._running

    @Property(bool, notify=microphoneEnabledChanged)
    def microphoneEnabled(self) -> bool:
        return self._microphone_enabled

    @Property(str, notify=displayModeChanged)
    def displayMode(self) -> str:
        return self._display_mode

    @Property(str, notify=fontFamilyChanged)
    def fontFamily(self) -> str:
        return self._font_family

    @Property(int, notify=sourceSizeChanged)
    def sourceSize(self) -> int:
        return self._source_size

    @Property(int, notify=translationSizeChanged)
    def translationSize(self) -> int:
        return self._translation_size

    @Slot()
    def toggleRunning(self) -> None:
        if self._running:
            self.pauseRequested.emit()
        else:
            self.startRequested.emit()

    @Slot()
    def toggleMicrophone(self) -> None:
        self.microphoneRequested.emit(not self._microphone_enabled)

    def set_running(self, running: bool) -> None:
        running = bool(running)
        if running == self._running:
            return
        self._running = running
        self.runningChanged.emit()

    def set_microphone_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self._microphone_enabled:
            return
        self._microphone_enabled = enabled
        self.microphoneEnabledChanged.emit()

    def set_appearance(
        self,
        *,
        display_mode: str,
        font_family: str,
        source_size: int,
        translation_size: int,
    ) -> None:
        if display_mode in {"bilingual", "source", "translation"}:
            if display_mode != self._display_mode:
                self._display_mode = display_mode
                self.displayModeChanged.emit()
        font_family = font_family.strip() or "sans-serif"
        if font_family != self._font_family:
            self._font_family = font_family
            self.fontFamilyChanged.emit()
        source_size = max(12, min(40, int(source_size)))
        if source_size != self._source_size:
            self._source_size = source_size
            self.sourceSizeChanged.emit()
        translation_size = max(12, min(40, int(translation_size)))
        if translation_size != self._translation_size:
            self._translation_size = translation_size
            self.translationSizeChanged.emit()
