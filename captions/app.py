from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QObject, QRect, QTimer, Qt, Slot
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
)

from captions.config import (
    AppConfig,
    clone_config,
    load_config,
    model_download_integrity,
    model_download_spec,
    model_is_complete,
    model_preset,
    resolve_model_dir,
    save_config,
)
from captions.hotkey import HotkeyFilter
from captions.segmenter import Segmenter
from captions.task_sessions import CaptureSession, ModelDownloadSession
from captions.translation import HistoryRecord
from captions.translation_session import TranslationJob, TranslationSession
from captions.ui.history_dialog import HistoryDialog
from captions.ui.overlay import OverlayWindow
from captions.ui.settings_dialog import SettingsDialog


class CaptionApplication(QObject):
    MODES = ("bilingual", "source", "translation")

    def __init__(self, qt_app: QApplication) -> None:
        super().__init__()
        self.qt_app = qt_app
        self.config, self.config_path = load_config()
        self.config_load_warning = getattr(self.config, "_load_warning", "")
        self.segmenter = Segmenter(
            max_chars=self.config.segmentation.max_chars,
            max_seconds=self.config.segmentation.max_seconds,
            split_lookback_chars=self.config.segmentation.split_lookback_chars,
            split_lookahead_chars=self.config.segmentation.split_lookahead_chars,
        )
        self.translation_session = TranslationSession(self)
        self.display_generation = 0
        self.display_kind = ""
        self.active_cue_id = 1
        self.status_text = "正在启动"
        self.device_text = "等待识别"
        self.model_text = "正在检测"
        self.status_before_test = ""
        self.capture_session = CaptureSession(self)
        self.download_session = ModelDownloadSession(self)
        self.download_prompt: QMessageBox | None = None
        self.download_succeeded = False
        self.capturing = False
        self.capture_paused = False
        self.auto_standby = False
        self.model_loaded = False
        self.closing = False
        self.restart_after_stop = False
        self.asr_error_message = ""

        self.app_icon = self._app_icon()
        qt_app.setWindowIcon(self.app_icon)
        self.overlay = OverlayWindow(self.config)
        self.history = HistoryDialog()
        self.settings = SettingsDialog(self.config)
        self._connect_ui()
        self._connect_sessions()

        self.clear_timer = QTimer(self)
        self.clear_timer.setSingleShot(True)
        self.clear_timer.timeout.connect(self._clear_if_idle)
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(400)
        self.save_timer.timeout.connect(self._save_config)
        self.quit_watchdog = QTimer(self)
        self.quit_watchdog.setSingleShot(True)
        self.quit_watchdog.setInterval(12000)
        self.quit_watchdog.timeout.connect(self._force_finish_quit)
        self._restore_geometry()

        self.hotkey = HotkeyFilter(
            self.config.hotkey.modifiers, self.config.hotkey.virtual_key
        )
        qt_app.installNativeEventFilter(self.hotkey)
        self.hotkey.activated.connect(self.toggle_lock)
        self.hotkey.register()

        self.tray = self._create_tray()

    def show(self) -> None:
        self.overlay.show()
        self.overlay.raise_()
        self.tray.show()
        if not self.config.translation.google2_api_key.strip():
            self.translation_session.request_google2_key()
        if self.config_load_warning:
            self.tray.showMessage(
                "配置已恢复",
                self.config_load_warning,
                QSystemTrayIcon.MessageIcon.Warning,
                6000,
            )
        if model_is_complete(self.config):
            self._set_model_status("已就绪")
            self._set_status("正在启动识别")
            QTimer.singleShot(0, self.start_capture)
        else:
            self._set_model_missing()
            self._set_status("等待安装模型")
            QTimer.singleShot(0, self._offer_model_download)

    def _connect_ui(self) -> None:
        self.overlay.geometry_changed.connect(self._geometry_changed)
        self.settings.saved.connect(self.apply_settings)
        self.settings.test_translation_requested.connect(self.test_translation)
        self.settings.model_download_requested.connect(
            self._download_model_from_settings
        )

    def _connect_sessions(self) -> None:
        self.capture_session.partial.connect(self._asr_partial)
        self.capture_session.endpoint.connect(self._asr_endpoint)
        self.capture_session.status.connect(self._set_status)
        self.capture_session.model_ready.connect(self._asr_model_ready)
        self.capture_session.auto_standby_changed.connect(
            self._auto_standby_changed
        )
        self.capture_session.error.connect(self._asr_error)
        self.capture_session.finished.connect(self._asr_thread_finished)
        self.download_session.progress.connect(self._model_download_progress)
        self.download_session.status.connect(self._model_download_stage)
        self.download_session.completed.connect(self._model_download_completed)
        self.download_session.cancelled.connect(self._model_download_cancelled)
        self.download_session.error.connect(self._model_download_error)
        self.download_session.finished.connect(self._download_thread_finished)
        self.translation_session.started.connect(self._translation_started)
        self.translation_session.progress.connect(self._translation_progress)
        self.translation_session.result.connect(self._translation_result)
        self.translation_session.error.connect(self._translation_error)
        self.translation_session.cancelled.connect(self._translation_cancelled)
        self.translation_session.previews_discarded.connect(
            self._translation_previews_discarded
        )
        self.translation_session.google2_key_ready.connect(
            self._google2_key_ready
        )
        self.translation_session.google2_key_error.connect(
            self._google2_key_error
        )

    def _create_tray(self) -> QSystemTrayIcon:
        tray = QSystemTrayIcon(self.app_icon, self)
        tray.setToolTip("实时字幕")
        menu = QMenu()
        self.status_action = QAction("状态：正在启动", menu)
        self.status_action.setEnabled(False)
        menu.addAction(self.status_action)
        self.device_action = QAction("设备：等待识别", menu)
        self.device_action.setEnabled(False)
        menu.addAction(self.device_action)
        self.model_action = QAction("模型：正在检测", menu)
        self.model_action.setEnabled(False)
        self.model_action.triggered.connect(self.download_model)
        menu.addAction(self.model_action)
        menu.addSeparator()
        self.capture_action = QAction("开始识别", menu)
        self.capture_action.triggered.connect(self.toggle_capture)
        menu.addAction(self.capture_action)
        show_action = QAction("显示字幕", menu)
        show_action.triggered.connect(self._show_overlay)
        menu.addAction(show_action)
        self.lock_action = QAction("锁定字幕", menu)
        self.lock_action.triggered.connect(self.toggle_lock)
        menu.addAction(self.lock_action)
        menu.addSeparator()
        settings_action = QAction("设置", menu)
        history_action = QAction("本次历史", menu)
        settings_action.triggered.connect(self.show_settings)
        history_action.triggered.connect(self.show_history)
        menu.addAction(settings_action)
        menu.addAction(history_action)
        menu.addSeparator()
        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(self.quit)
        menu.addAction(quit_action)
        tray.setContextMenu(menu)
        tray.activated.connect(
            lambda reason: self._show_overlay()
            if reason == QSystemTrayIcon.ActivationReason.Trigger
            else None
        )
        return tray

    @staticmethod
    def _app_icon() -> QIcon:
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#4477ee"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(4, 8, 56, 44, 12, 12)
        painter.setPen(QColor("white"))
        font = painter.font()
        font.setBold(True)
        font.setPixelSize(27)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "CC")
        painter.end()
        return QIcon(pixmap)

    @Slot()
    def toggle_capture(self) -> None:
        if self.capturing:
            self.stop_capture()
        elif not model_is_complete(self.config):
            self._offer_model_download()
        else:
            self.start_capture()

    def start_capture(self) -> None:
        if self.capture_session.running:
            if self.capture_paused:
                self.capture_session.resume()
                self.capture_paused = False
                self.auto_standby = False
                self.capturing = True
                self.overlay.set_capturing(True)
                self.capture_action.setText("暂停识别")
                self._set_status("正在恢复识别")
            return
        if not model_is_complete(self.config):
            self._set_model_missing()
            return
        self.asr_error_message = ""
        self.model_loaded = False
        self.capture_paused = False
        self._set_status("正在启动识别")
        self._set_model_status("正在加载")
        self.overlay.set_capturing(True)
        self.capture_action.setText("暂停识别")
        self.capturing = True
        self.capture_session.start(self.config)

    def stop_capture(self) -> None:
        if not self.capture_session.running or not self.capturing:
            return
        self.capture_session.pause()
        update = self.segmenter.flush(forced=True)
        if update.committed:
            self._commit(update.committed, True)
        self.capturing = False
        self.capture_paused = True
        self.auto_standby = False
        self.overlay.set_capturing(False)
        self.capture_action.setText("继续识别")
        self._set_status("已暂停")
        if self.model_loaded:
            self._set_model_status("已加载")

    @Slot()
    def _asr_model_ready(self) -> None:
        self.model_loaded = True
        self._set_model_status("已加载")
        if self.capture_paused:
            self._set_status("已暂停")

    @Slot()
    def _asr_thread_finished(self) -> None:
        self.capturing = False
        self.capture_paused = False
        self.auto_standby = False
        self.model_loaded = False
        self.overlay.set_capturing(False)
        self.capture_action.setText("继续识别")
        if self.closing:
            self._maybe_finish_quit()
        else:
            if self.restart_after_stop:
                self.restart_after_stop = False
                self._set_status("正在应用设置并重启识别…")
                QTimer.singleShot(0, self.start_capture)
            elif not self.asr_error_message:
                self._set_status("已暂停")
                if model_is_complete(self.config):
                    self._set_model_status("已就绪")

    @Slot(str, int)
    def _asr_partial(self, raw: str, revision: int) -> None:
        update = self.segmenter.update(raw)
        if update.committed:
            self._commit(update.committed, update.forced)
        active = update.active
        if active:
            self.history.set_live(source=active)
            if self.config.subtitle.mode == "source":
                self.overlay.canvas.set_cue(self.active_cue_id, active, "")
            self.translation_session.schedule_preview(
                active,
                self.history.records,
                self.config.translation,
                self.config.segmentation,
                self.active_cue_id,
            )
            self._restart_clear_timer()

    @Slot()
    def _asr_endpoint(self) -> None:
        update = self.segmenter.flush()
        if update.committed:
            self._commit(update.committed, update.forced)

    @Slot(bool)
    def _auto_standby_changed(self, standby: bool) -> None:
        self.auto_standby = standby
        if standby:
            update = self.segmenter.flush(forced=True)
            if update.committed:
                self._commit(update.committed, True)
            self.overlay.set_capturing(False)
            self._set_status("自动待机")
        elif self.capturing:
            self.overlay.set_capturing(True)

    def _commit(self, source: str, forced: bool) -> None:
        source = source.strip()
        if not source:
            return
        cue_id = self.active_cue_id
        record = HistoryRecord(
            time=datetime.now().strftime("%H:%M:%S"),
            source=source,
            translation="",
            backend=self.config.translation.backend,
            forced=forced,
        )
        index = self.history.commit_live(record)
        self.translation_session.request_commit(
            source,
            self.history.records[:-1],
            self.config.translation,
            record_id=index,
            cue_id=cue_id,
        )
        if self.config.subtitle.mode == "source":
            self.overlay.canvas.set_cue(cue_id, source, "")
        self.active_cue_id += 1
        self._restart_clear_timer()

    @Slot()
    def _translation_previews_discarded(self) -> None:
        if self.display_kind == "preview":
            self.display_generation = 0
            self.display_kind = ""

    @Slot(str)
    def _google2_key_ready(self, key: str) -> None:
        if self.config.translation.google2_api_key.strip():
            return
        self.config.translation.google2_api_key = key
        self.settings.set_google2_api_key(key)
        self._schedule_save()

    @Slot(str)
    def _google2_key_error(self, message: str) -> None:
        if self.config.translation.backend == "google2":
            self._set_status(f"Google2 密钥获取失败：{message}")

    @Slot(int, object)
    def _translation_started(self, generation: int, job: TranslationJob) -> None:
        if job.kind == "test" or generation < self.display_generation:
            return
        self.display_generation = generation
        self.display_kind = job.kind
        if self.config.subtitle.mode == "bilingual":
            QTimer.singleShot(
                650,
                lambda current=generation, current_job=job: self._show_source_fallback(
                    current, current_job
                ),
            )

    def _show_source_fallback(self, generation: int, job: TranslationJob) -> None:
        if (
            not self.translation_session.has_job(generation)
            or generation != self.display_generation
            or self.config.subtitle.mode != "bilingual"
            or self.overlay.canvas.cue_id == job.cue_id
        ):
            return
        self.overlay.canvas.set_cue(job.cue_id, job.source, "")
        self.history.set_live(source=job.source)

    def _display_translation(
        self, job: TranslationJob, text: str, *, final: bool = False
    ) -> None:
        canvas = self.overlay.canvas
        if job.cue_id < canvas.cue_id:
            return
        if (
            job.cue_id == canvas.cue_id
            and not final
            and len(text) <= len(canvas.translation)
        ):
            return
        canvas.set_cue(job.cue_id, job.source, text)

    @Slot(int, object, str)
    def _translation_progress(
        self, generation: int, job: TranslationJob, text: str
    ) -> None:
        if not text:
            return
        if job.kind == "preview" and generation == self.display_generation:
            self._display_translation(job, text)
            self.history.set_live_translation(job.source, text)
        elif job.kind == "commit" and job.index is not None:
            self.history.update_translation(job.index, text)
            if generation == self.display_generation:
                self._display_translation(job, text)

    @Slot(int, object, str)
    def _translation_result(
        self, generation: int, job: TranslationJob, text: str
    ) -> None:
        if job.kind == "preview":
            if generation == self.display_generation:
                self._display_translation(job, text, final=True)
                self.history.set_live_translation(job.source, text)
        elif job.kind == "test":
            self.settings.set_translation_test_status("连接正常", success=True)
            self._set_status(self.status_before_test or "翻译连接正常")
        elif job.index is not None:
            self.history.update_translation(job.index, text)
            if generation == self.display_generation:
                self._display_translation(job, text, final=True)
        self._restart_clear_timer()

    @Slot(int, object, str)
    def _translation_error(
        self, generation: int, job: TranslationJob, message: str
    ) -> None:
        if generation == self.display_generation:
            self.display_generation = 0
            self.display_kind = ""
        if job.kind == "test":
            self.settings.set_translation_test_status(message, success=False)
            self._set_status(self.status_before_test or "翻译连接测试失败")
            return
        self._set_status(f"翻译不可用：{message}")

    @Slot(int, object)
    def _translation_cancelled(self, generation: int, job: TranslationJob) -> None:
        if generation == self.display_generation:
            self.display_generation = 0
            self.display_kind = ""

    @Slot(str)
    def _asr_error(self, message: str) -> None:
        self.asr_error_message = message
        missing = "模型不完整" in message
        compact = "缺少语音识别模型" if missing else "识别无法启动"
        self._set_status(f"识别无法启动：{message}", compact)
        if missing:
            self._set_model_missing()
        self.tray.showMessage(
            "实时字幕",
            message,
            QSystemTrayIcon.MessageIcon.Warning,
            6000,
        )

    @Slot()
    def cycle_mode(self) -> None:
        index = self.MODES.index(self.config.subtitle.mode)
        self.config.subtitle.mode = self.MODES[(index + 1) % len(self.MODES)]
        self.overlay.set_mode(self.config.subtitle.mode)
        self._schedule_save()

    @Slot()
    def toggle_lock(self) -> None:
        locked = not self.config.window.locked
        self.overlay.set_locked(locked)
        self.lock_action.setText("解锁字幕" if locked else "锁定字幕")
        self._schedule_save()

    @Slot()
    def show_history(self) -> None:
        self.history.show()
        self.history.raise_()
        self.history.activateWindow()

    @Slot()
    def show_settings(self) -> None:
        self.settings.load(self.config)
        self.settings.show()
        self.settings.raise_()
        self.settings.activateWindow()

    @Slot(object)
    def apply_settings(self, config: AppConfig) -> None:
        was_capturing = self.capturing
        had_asr_thread = self.capture_session.running
        asr_changed = config.asr != self.config.asr
        model_changed = any(
            getattr(config.asr, name) != getattr(self.config.asr, name)
            for name in (
                "model_variant", "model_dir", "encoder", "decoder", "joiner",
                "tokens", "language",
            )
        )
        if had_asr_thread and model_changed:
            self.restart_after_stop = was_capturing
            self.capture_session.stop()
        elif had_asr_thread and asr_changed:
            self.capture_session.set_auto_standby_seconds(
                config.asr.auto_standby_seconds
            )
        geometry = self.overlay.geometry()
        config.window.x = geometry.x()
        config.window.y = geometry.y()
        config.window.width = geometry.width()
        config.window.height = geometry.height()
        config.window.locked = self.config.window.locked
        self.config = config
        self.segmenter.max_chars = config.segmentation.max_chars
        self.segmenter.max_seconds = config.segmentation.max_seconds
        self.segmenter.split_lookback_chars = (
            config.segmentation.split_lookback_chars
        )
        self.segmenter.split_lookahead_chars = (
            config.segmentation.split_lookahead_chars
        )
        self.overlay.config = config
        self.overlay.canvas.set_style(config.subtitle)
        self.overlay.set_mode(config.subtitle.mode)
        self._save_config()
        if model_is_complete(config):
            if self.model_loaded:
                self._set_model_status("已加载")
            elif not self.capture_session.running:
                self._set_model_status("已就绪")
        else:
            self._set_model_missing()
        if had_asr_thread and model_changed:
            self._set_status("正在应用设置并重启识别…")

    @Slot(object)
    def test_translation(self, config: AppConfig) -> None:
        self.settings.set_translation_test_status("正在测试连接…")
        sample = {
            "ZH": "这是一次翻译连接测试。",
            "JA": "これは翻訳接続のテストです。",
            "KO": "이것은 번역 연결 테스트입니다.",
            "DE": "Dies ist ein Test der Übersetzungsverbindung.",
            "FR": "Ceci est un test de connexion de traduction.",
            "ES": "Esta es una prueba de conexión de traducción.",
            "IT": "Questo è un test della connessione di traduzione.",
            "PT": "Este é um teste da conexão de tradução.",
            "NL": "Dit is een test van de vertaalverbinding.",
            "RU": "Это проверка подключения к переводу.",
        }.get(config.translation.source_lang, "This is a translation test.")
        self.translation_session.request_test(sample, config.translation)
        self.status_before_test = self.status_text
        self._set_status("正在测试翻译连接…")

    def _restart_clear_timer(self) -> None:
        stay = self.config.subtitle.stay_ms
        if stay > 0:
            self.clear_timer.start(stay)

    @Slot()
    def _clear_if_idle(self) -> None:
        if self.segmenter.active or self.translation_session.has_job(
            self.display_generation
        ):
            self._restart_clear_timer()
            return
        self.display_generation = 0
        self.display_kind = ""
        self.overlay.canvas.clear()

    def _offer_model_download(self) -> None:
        if (
            self.closing
            or self.download_session.running
            or model_is_complete(self.config)
            or self.download_prompt is not None
        ):
            return
        prompt = QMessageBox(self.overlay)
        prompt.setWindowTitle("需要语音模型")
        prompt.setIcon(QMessageBox.Icon.Question)
        preset = model_preset(self.config.asr.model_variant)
        prompt.setText(f"未检测到 {preset.label} 语音识别模型。")
        model_megabytes = round(preset.size / (1024 * 1024))
        prompt.setInformativeText(
            f"模型约 {model_megabytes} MB，只需下载一次。是否现在下载？"
        )
        prompt.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        prompt.setDefaultButton(QMessageBox.StandardButton.Yes)
        prompt.finished.connect(self._model_download_prompt_finished)
        self.download_prompt = prompt
        prompt.open()

    @Slot(int)
    def _model_download_prompt_finished(self, result: int) -> None:
        self.download_prompt = None
        if result == QMessageBox.StandardButton.Yes.value:
            self.download_model()

    @Slot()
    def download_model(self) -> None:
        if self.download_session.running:
            return
        if model_is_complete(self.config):
            self._set_model_status("已就绪")
            return
        self.download_succeeded = False
        self._set_status("正在下载模型")
        self._set_model_status("正在连接")
        model_name, model_url = model_download_spec(self.config)
        expected_size, expected_sha256 = model_download_integrity(self.config)
        self.download_session.start(
            resolve_model_dir(self.config),
            model_name=model_name,
            model_url=model_url,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
            required_files=(
                self.config.asr.encoder,
                self.config.asr.decoder,
                self.config.asr.joiner,
                self.config.asr.tokens,
            ),
        )

    @Slot(object)
    def _download_model_from_settings(self, requested: AppConfig) -> None:
        model_dir = requested.asr.model_dir.strip()
        if not model_dir:
            return
        if (
            requested.asr.model_variant != self.config.asr.model_variant
            or model_dir != self.config.asr.model_dir
            or requested.asr.language != self.config.asr.language
        ):
            config = clone_config(self.config)
            config.asr = clone_config(requested).asr
            config.asr.model_dir = model_dir
            self.apply_settings(config)
        self.download_model()

    @Slot(int, int)
    def _model_download_progress(self, downloaded: int, total: int) -> None:
        if total > 0:
            percent = max(0, min(100, round(downloaded * 100 / total)))
            self._set_model_status(f"下载 {percent}%")
        else:
            megabytes = downloaded / (1024 * 1024)
            self._set_model_status(f"已下载 {megabytes:.0f} MB")

    @Slot(str)
    def _model_download_stage(self, text: str) -> None:
        if "解压" in text:
            self._set_model_status("正在解压")
        else:
            self._set_model_status("正在连接")

    @Slot()
    def _model_download_completed(self) -> None:
        self.download_succeeded = True
        self._set_model_status("已就绪")
        self._set_status("模型下载完成")

    @Slot()
    def _model_download_cancelled(self) -> None:
        if not self.closing:
            self._set_status("模型下载已取消")
            self._set_model_missing()

    @Slot(str)
    def _model_download_error(self, message: str) -> None:
        self.download_succeeded = False
        self._set_status("模型下载失败")
        self._set_model_missing()
        if not self.closing:
            self.tray.showMessage(
                "模型下载失败",
                message,
                QSystemTrayIcon.MessageIcon.Warning,
                6000,
            )

    @Slot()
    def _download_thread_finished(self) -> None:
        succeeded = self.download_succeeded and model_is_complete(self.config)
        if self.closing:
            self._maybe_finish_quit()
        elif succeeded:
            self.start_capture()
        else:
            self._set_model_missing()

    def _set_model_missing(self) -> None:
        self.model_text = "未安装"
        if hasattr(self, "model_action"):
            self.model_action.setText("下载语音识别模型…")
            self.model_action.setEnabled(True)
        if hasattr(self, "settings"):
            self.settings.set_model_status("未安装", downloadable=True)
        self._refresh_tray_status()

    def _set_model_status(self, text: str) -> None:
        self.model_text = text
        if hasattr(self, "model_action"):
            self.model_action.setText(f"模型：{text}")
            self.model_action.setEnabled(False)
        if hasattr(self, "settings"):
            self.settings.set_model_status(text)
        self._refresh_tray_status()

    def _set_status(self, text: str, menu_text: str | None = None) -> None:
        if text.startswith("正在识别："):
            self.status_text = "正在识别"
            self.device_text = text.split("：", 1)[1].strip() or "默认播放设备"
            self._set_model_status("已加载")
        elif text.startswith("正在连接系统播放设备"):
            self.status_text = "正在连接播放设备"
            self.device_text = "默认播放设备"
            self._set_model_status("已加载")
        elif text.startswith("播放设备已变化"):
            self.status_text = "正在重连播放设备"
        else:
            self.status_text = menu_text or text.splitlines()[0]
        self._refresh_tray_status()

    def _refresh_tray_status(self) -> None:
        compact_status = self.status_text
        compact_device = self.device_text
        if len(compact_status) > 24:
            compact_status = compact_status[:23] + "…"
        if len(compact_device) > 28:
            compact_device = compact_device[:27] + "…"
        if hasattr(self, "status_action"):
            self.status_action.setText(f"状态：{compact_status}")
        if hasattr(self, "device_action"):
            self.device_action.setText(f"设备：{compact_device}")
        if hasattr(self, "tray"):
            self.tray.setToolTip(
                "实时字幕\n"
                f"状态：{compact_status}\n"
                f"设备：{compact_device}\n"
                f"模型：{self.model_text}"
            )

    def _restore_geometry(self) -> None:
        window = self.config.window
        geometry = QRect(window.x, window.y, max(480, window.width), max(140, window.height))
        screens = QApplication.screens()
        if not any(screen.availableGeometry().intersects(geometry) for screen in screens):
            geometry.moveCenter(QApplication.primaryScreen().availableGeometry().center())
        self.overlay.setGeometry(geometry)
        self.overlay.set_mode(self.config.subtitle.mode)

    def _geometry_changed(self) -> None:
        if self.overlay.isVisible():
            self._schedule_save()

    def _schedule_save(self) -> None:
        self.save_timer.start()

    def _save_config(self) -> None:
        geometry = self.overlay.geometry()
        self.config.window.x = geometry.x()
        self.config.window.y = geometry.y()
        self.config.window.width = geometry.width()
        self.config.window.height = geometry.height()
        save_config(self.config, self.config_path)

    def _show_overlay(self) -> None:
        self.overlay.show()
        self.overlay.raise_()
        self.overlay.activateWindow()

    @Slot()
    def quit(self) -> None:
        if self.closing:
            return
        self.closing = True
        self._save_config()
        self.hotkey.unregister()
        self.translation_session.close()
        if self.download_prompt is not None:
            self.download_prompt.close()
            self.download_prompt = None
        self.download_session.cancel()
        self.capture_session.stop()
        self._set_status("正在安全退出")
        self.overlay.hide()
        self.settings.hide()
        self.history.hide()
        self.quit_watchdog.start()
        self._maybe_finish_quit()

    def _maybe_finish_quit(self) -> None:
        if not self.closing:
            return
        if self.capture_session.running or self.download_session.running:
            return
        self.quit_watchdog.stop()
        self.tray.hide()
        self.qt_app.quit()

    def _force_finish_quit(self) -> None:
        if not self.closing:
            return
        self.tray.hide()
        self.qt_app.exit(0)
