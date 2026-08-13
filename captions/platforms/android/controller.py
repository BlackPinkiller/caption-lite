from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Slot
from PySide6.QtQml import QQmlApplicationEngine

from captions.config import load_config, model_is_complete
from captions.core.diagnostics import Diagnostics
from captions.platforms.android.permissions import MicrophonePermissionBroker
from captions.platforms.android.ui.view_model import AndroidViewModel
from captions.segmenter import Segmenter
from captions.task_sessions import CaptureSession
from captions.translation import HistoryRecord
from captions.translation_session import TranslationJob, TranslationSession


class AndroidApplication(QObject):
    def __init__(self, application) -> None:
        super().__init__(application)
        self.application = application
        self.config, self.config_path = load_config()
        self.diagnostics = Diagnostics(
            self.config.debug.enabled,
            self.config_path.parent / "runtime" / "captions-debug.jsonl",
        )
        self.segmenter = Segmenter(
            max_chars=self.config.segmentation.max_chars,
            max_seconds=self.config.segmentation.max_seconds,
            split_lookback_chars=self.config.segmentation.split_lookback_chars,
            split_lookahead_chars=self.config.segmentation.split_lookahead_chars,
        )
        self.history: list[HistoryRecord] = []
        self.active_cue_id = 1
        self.capture_session = CaptureSession(self, self.diagnostics)
        self.translation_session = TranslationSession(self, self.diagnostics)
        self.permission = MicrophonePermissionBroker(application, self)
        self.view_model = AndroidViewModel(self)
        self.view_model.set_appearance(
            display_mode=self.config.subtitle.mode,
            font_family=self.config.subtitle.font_family,
            source_size=self.config.subtitle.source_size,
            translation_size=self.config.subtitle.translation_size,
        )
        self.engine = QQmlApplicationEngine(self)
        self.engine.rootContext().setContextProperty("viewModel", self.view_model)
        self._connect_signals()

    def _connect_signals(self) -> None:
        self.view_model.startRequested.connect(self._start_requested)
        self.view_model.pauseRequested.connect(self._pause_requested)
        self.view_model.microphoneRequested.connect(self._microphone_requested)
        self.permission.granted.connect(self._microphone_granted)
        self.permission.denied.connect(self._microphone_denied)
        self.capture_session.partial.connect(self._asr_partial)
        self.capture_session.endpoint.connect(self._asr_endpoint)
        self.capture_session.error.connect(self.view_model.set_error)
        self.translation_session.progress.connect(self._translation_progress)
        self.translation_session.result.connect(self._translation_result)
        self.translation_session.error.connect(self._translation_error)
        self.application.aboutToQuit.connect(self.close)

    def show(self) -> bool:
        qml_path = Path(__file__).with_name("ui") / "Main.qml"
        self.engine.load(str(qml_path))
        return bool(self.engine.rootObjects())

    @Slot()
    def _start_requested(self) -> None:
        self.view_model.clear_error()
        if self.view_model.microphoneEnabled:
            self.permission.request()
        else:
            self.view_model.set_running(True)

    @Slot()
    def _pause_requested(self) -> None:
        self.view_model.set_running(False)
        self._pause_capture()

    @Slot(bool)
    def _microphone_requested(self, enabled: bool) -> None:
        if not enabled:
            self.view_model.set_microphone_enabled(False)
            self._pause_capture()
        else:
            self.permission.request()

    @Slot()
    def _microphone_granted(self) -> None:
        self.view_model.set_microphone_enabled(True)
        if not self.view_model.running:
            self.view_model.set_running(True)
        if not model_is_complete(self.config):
            self.view_model.set_running(False)
            self.view_model.set_error("需要先在设置中下载语音模型")
            return
        if self.capture_session.running:
            self.capture_session.resume()
        else:
            self.capture_session.start(self.config)

    @Slot()
    def _microphone_denied(self) -> None:
        self.view_model.set_microphone_enabled(False)
        self.view_model.set_running(False)
        self.view_model.set_error("需要麦克风权限才能开始识别")

    def _pause_capture(self) -> None:
        if self.capture_session.running:
            self.capture_session.pause()
        update = self.segmenter.flush(forced=True)
        if update.committed:
            self._commit(update.committed, True)

    @Slot(str, int)
    def _asr_partial(self, raw: str, revision: int) -> None:
        update = self.segmenter.update(raw)
        if update.committed:
            self._commit(update.committed, update.forced)
        if not update.active:
            return
        self.view_model.session_model.set_current(
            self.active_cue_id,
            update.active,
        )
        if self.config.translation.enabled:
            self.translation_session.schedule_preview(
                update.active,
                self.history,
                self.config.translation,
                self.config.segmentation,
                self.active_cue_id,
            )

    @Slot()
    def _asr_endpoint(self) -> None:
        update = self.segmenter.flush()
        if update.committed:
            self._commit(update.committed, update.forced)

    def _commit(self, source: str, forced: bool) -> None:
        source = source.strip()
        if not source:
            return
        cue_id = self.active_cue_id
        self.view_model.session_model.set_current(cue_id, source)
        self.view_model.session_model.commit_current()
        record = HistoryRecord(
            time=datetime.now().strftime("%H:%M:%S"),
            source=source,
            translation="",
            backend=(
                self.config.translation.backend
                if self.config.translation.enabled
                else "off"
            ),
            forced=forced,
        )
        previous = list(self.history)
        self.history.append(record)
        if self.config.translation.enabled:
            self.translation_session.request_commit(
                source,
                previous,
                self.config.translation,
                record_id=cue_id,
                cue_id=cue_id,
            )
        self.active_cue_id += 1

    @Slot(int, object, str)
    def _translation_progress(
        self,
        generation: int,
        job: TranslationJob,
        text: str,
    ) -> None:
        if text:
            self.view_model.session_model.set_translation(job.cue_id, text)

    @Slot(int, object, str)
    def _translation_result(
        self,
        generation: int,
        job: TranslationJob,
        text: str,
    ) -> None:
        if text:
            self.view_model.session_model.set_translation(job.cue_id, text)
        if job.kind == "commit":
            for index, record in enumerate(self.history, start=1):
                if index == job.cue_id:
                    record.translation = text
                    break

    @Slot(int, object, str)
    def _translation_error(
        self,
        generation: int,
        job: TranslationJob,
        message: str,
    ) -> None:
        self.view_model.set_error(f"翻译不可用：{message}")

    @Slot()
    def close(self) -> None:
        self.capture_session.stop()
        self.translation_session.close()
