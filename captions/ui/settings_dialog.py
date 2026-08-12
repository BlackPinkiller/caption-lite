from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QFontComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from captions.config import (
    AppConfig,
    MODEL_CATALOG,
    SubtitleConfig,
    apply_model_preset,
    clone_config,
    default_model_dir,
    model_is_complete,
)
from captions.ui.caption_canvas import CaptionCanvas


def _forward_wheel_to_page(widget: QWidget, event) -> None:
    parent = widget.parentWidget()
    while parent is not None and not isinstance(parent, QAbstractScrollArea):
        parent = parent.parentWidget()
    if parent is None:
        event.ignore()
        return
    QApplication.sendEvent(parent.viewport(), event)


class WheelSafeComboBox(QComboBox):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event) -> None:  # noqa: N802
        _forward_wheel_to_page(self, event)


class WheelSafeSpinBox(QSpinBox):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event) -> None:  # noqa: N802
        _forward_wheel_to_page(self, event)


class WheelSafeDoubleSpinBox(QDoubleSpinBox):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event) -> None:  # noqa: N802
        _forward_wheel_to_page(self, event)


class WheelSafeFontComboBox(QFontComboBox):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event) -> None:  # noqa: N802
        _forward_wheel_to_page(self, event)


class ExpandableSection(QWidget):
    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.toggle = QToolButton()
        self.toggle.setText(title)
        self.toggle.setCheckable(True)
        self.toggle.setChecked(False)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setAutoRaise(True)
        self.toggle.setStyleSheet("font-weight:600;padding:4px 0")
        self.toggle.toggled.connect(self._set_expanded)
        layout.addWidget(self.toggle)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(18, 0, 0, 0)
        self.body_layout.setSpacing(10)
        self.body.hide()
        layout.addWidget(self.body)

    def addWidget(self, widget: QWidget) -> None:  # noqa: N802
        self.body_layout.addWidget(widget)

    def _set_expanded(self, expanded: bool) -> None:
        self.toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self.body.setVisible(expanded)


class ColorButton(QPushButton):
    color_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.value = "#ffffff"
        self.clicked.connect(self.choose)

    def set_color(self, value: str) -> None:
        self.value = value
        self.setText(value)
        color = QColor(value)
        if color.isValid():
            foreground = "#000" if color.lightness() > 150 else "#fff"
            self.setStyleSheet(f"background:{value};color:{foreground};padding:5px")
        self.color_changed.emit(value)

    def choose(self) -> None:
        color = QColorDialog.getColor(QColor(self.value), self)
        if color.isValid():
            self.set_color(color.name(QColor.NameFormat.HexArgb))


class SettingsDialog(QDialog):
    saved = Signal(object)
    test_translation_requested = Signal(object)
    model_download_requested = Signal(object)

    def __init__(self, config: AppConfig, parent=None) -> None:
        super().__init__(parent)
        self.config = clone_config(config)
        self._loading = False
        self.setWindowTitle("实时字幕设置")
        self.resize(680, 620)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self._build_general()
        self._build_appearance()
        self._build_glossary()
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.load(config)

    def _build_general(self) -> None:
        self._build_recognition()
        self._build_translation()

    def _build_recognition(self) -> None:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        controls = QWidget()
        controls_layout = QVBoxLayout(controls)

        model_group = QGroupBox("语音识别")
        form = QFormLayout(model_group)
        self.model_variant = WheelSafeComboBox()
        for key, preset in MODEL_CATALOG.items():
            self.model_variant.addItem(preset.label, key)
        form.addRow("识别模型", self.model_variant)
        self.model_dir = QLineEdit()
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._browse_model)
        row = QHBoxLayout()
        row.addWidget(self.model_dir, 1)
        row.addWidget(browse)
        self.model_status = QPushButton("正在检测模型…")
        self.model_status.setEnabled(False)
        self.model_status.clicked.connect(
            lambda: self.model_download_requested.emit(self.values())
        )
        form.addRow("模型状态", self.model_status)
        self.model_dir.textChanged.connect(self._refresh_model_path_status)
        self.asr_language = WheelSafeComboBox()
        for label, code in (
            ("自动检测", "auto"), ("英语", "en"), ("西班牙语", "es"),
            ("法语", "fr"), ("意大利语", "it"), ("葡萄牙语", "pt"),
            ("荷兰语", "nl"), ("德语", "de"), ("土耳其语", "tr"),
            ("俄语", "ru"), ("阿拉伯语", "ar"), ("印地语", "hi"),
            ("日语", "ja"), ("韩语", "ko"), ("越南语", "vi"),
            ("乌克兰语", "uk"), ("普通话（实验性）", "zh"),
            ("波兰语（实验性）", "pl"), ("瑞典语（实验性）", "sv"),
            ("捷克语（实验性）", "cs"), ("挪威语（实验性）", "nb"),
            ("丹麦语（实验性）", "da"), ("保加利亚语（实验性）", "bg"),
            ("芬兰语（实验性）", "fi"), ("克罗地亚语（实验性）", "hr"),
            ("斯洛伐克语（实验性）", "sk"), ("匈牙利语（实验性）", "hu"),
            ("罗马尼亚语（实验性）", "ro"), ("爱沙尼亚语（实验性）", "et"),
        ):
            self.asr_language.addItem(label, code)
        form.addRow("识别语言", self.asr_language)
        self.model_variant.currentIndexChanged.connect(self._model_variant_changed)
        controls_layout.addWidget(model_group)

        standby_group = QGroupBox("自动待机")
        standby_form = QFormLayout(standby_group)
        self.auto_standby = WheelSafeComboBox()
        for label, seconds in (
            ("关闭（默认）", 0), ("30 秒无声音", 30), ("1 分钟无声音", 60),
            ("3 分钟无声音", 180), ("5 分钟无声音", 300),
        ):
            self.auto_standby.addItem(label, seconds)
        standby_form.addRow("进入待机", self.auto_standby)
        standby_note = QLabel("待机时保留识别模型，只停止 ASR 解码；继续监听播放电平，声音恢复后自动唤醒。")
        standby_note.setWordWrap(True)
        standby_note.setStyleSheet("color:#777")
        standby_form.addRow("", standby_note)
        controls_layout.addWidget(standby_group)

        advanced = ExpandableSection("高级识别设置")
        self.recognition_advanced = advanced
        model_files_group = QGroupBox("模型文件")
        model_files_form = QFormLayout(model_files_group)
        model_files_form.addRow("模型目录", row)
        advanced.addWidget(model_files_group)

        segmentation_group = QGroupBox("分句与实时预览")
        form = QFormLayout(segmentation_group)
        self.max_chars = WheelSafeSpinBox()
        self.max_chars.setRange(40, 1000)
        self.max_chars.setSuffix(" 字符")
        form.addRow("分句软长度", self.max_chars)
        self.split_lookback = WheelSafeSpinBox()
        self.split_lookback.setRange(0, 200)
        self.split_lookback.setSuffix(" 字符")
        form.addRow("向前回找标点", self.split_lookback)
        self.split_lookahead = WheelSafeSpinBox()
        self.split_lookahead.setRange(0, 500)
        self.split_lookahead.setSuffix(" 字符")
        form.addRow("向后等待标点", self.split_lookahead)
        self.max_seconds = WheelSafeSpinBox()
        self.max_seconds.setRange(5, 120)
        self.max_seconds.setSuffix(" 秒")
        form.addRow("强制分句时间上限", self.max_seconds)
        self.preview_min_chars = WheelSafeSpinBox()
        self.preview_min_chars.setRange(0, 100)
        self.preview_min_chars.setSuffix(" 字符")
        form.addRow("预览发送长度下限", self.preview_min_chars)
        self.preview_interval = WheelSafeSpinBox()
        self.preview_interval.setRange(100, 10000)
        self.preview_interval.setSingleStep(100)
        self.preview_interval.setSuffix(" ms")
        form.addRow("预览最迟发送间隔", self.preview_interval)
        self.preview_char_delta = WheelSafeSpinBox()
        self.preview_char_delta.setRange(1, 200)
        self.preview_char_delta.setSuffix(" 字符")
        form.addRow("立即发送变动量", self.preview_char_delta)
        advanced.addWidget(segmentation_group)
        controls_layout.addWidget(advanced)
        controls_layout.addStretch(1)
        scroll.setWidget(controls)
        page_layout.addWidget(scroll)
        self.tabs.addTab(page, "识别")

    def _build_translation(self) -> None:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        controls = QWidget()
        controls_layout = QVBoxLayout(controls)

        language_group = QGroupBox("翻译语言")
        language_form = QFormLayout(language_group)
        self.source_lang = WheelSafeComboBox()
        for label, code in (
            ("自动检测", "AUTO"),
            ("英语（默认）", "EN"),
            ("中文", "ZH"),
            ("日语", "JA"),
            ("韩语", "KO"),
            ("德语", "DE"),
            ("法语", "FR"),
            ("西班牙语", "ES"),
            ("意大利语", "IT"),
            ("葡萄牙语", "PT"),
            ("荷兰语", "NL"),
            ("俄语", "RU"),
        ):
            self.source_lang.addItem(label, code)
        language_form.addRow("源语言", self.source_lang)
        self.target_lang = WheelSafeComboBox()
        for label, code in (
            ("简体中文（默认）", "ZH-HANS"),
            ("繁体中文", "ZH-HANT"),
            ("英语", "EN-US"),
            ("日语", "JA"),
            ("韩语", "KO"),
            ("德语", "DE"),
            ("法语", "FR"),
            ("西班牙语", "ES"),
            ("意大利语", "IT"),
            ("葡萄牙语", "PT"),
            ("荷兰语", "NL"),
            ("俄语", "RU"),
        ):
            self.target_lang.addItem(label, code)
        language_form.addRow("目标语言", self.target_lang)
        controls_layout.addWidget(language_group)

        service_group = QGroupBox("翻译服务")
        service_form = QFormLayout(service_group)
        self.backend = WheelSafeComboBox()
        self.backend.addItem("llama.cpp + Hy-MT2", "llama")
        self.backend.addItem("Google2", "google2")
        self.backend.addItem("DeepL API", "deepl")
        service_form.addRow("翻译后端", self.backend)
        self.backend_options = QStackedWidget()

        llama_page = QWidget()
        llama_form = QFormLayout(llama_page)
        llama_form.setContentsMargins(0, 0, 0, 0)
        self.llama_url = QLineEdit()
        llama_form.addRow("服务地址", self.llama_url)
        self.stream = QCheckBox("启用流式响应")
        llama_form.addRow("", self.stream)
        self.backend_options.addWidget(llama_page)

        google_page = QWidget()
        google_form = QFormLayout(google_page)
        google_form.setContentsMargins(0, 0, 0, 0)
        self.google2_api_key = QLineEdit()
        self.google2_api_key.setPlaceholderText("首次使用时自动从 Google 获取")
        google_form.addRow("密钥", self.google2_api_key)
        google_note = QLabel("程序会自动获取并保存，通常无需修改；需要时可直接覆盖。")
        google_note.setWordWrap(True)
        google_note.setStyleSheet("color:#777")
        google_form.addRow("", google_note)
        self.backend_options.addWidget(google_page)

        deepl_page = QWidget()
        deepl_form = QFormLayout(deepl_page)
        deepl_form.setContentsMargins(0, 0, 0, 0)
        self.deepl_api_key = QLineEdit()
        self.deepl_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.deepl_api_key.setPlaceholderText("也可使用 DEEPL_API_KEY 环境变量")
        deepl_form.addRow("API 密钥", self.deepl_api_key)
        self.deepl_api_plan = WheelSafeComboBox()
        self.deepl_api_plan.addItem("DeepL API Free", "free")
        self.deepl_api_plan.addItem("DeepL API Pro", "pro")
        deepl_form.addRow("API 套餐", self.deepl_api_plan)
        key_note = QLabel("密钥使用 Windows 当前用户加密后保存在本地配置中。")
        key_note.setStyleSheet("color:#777")
        key_note.setWordWrap(True)
        deepl_form.addRow("", key_note)
        self.backend_options.addWidget(deepl_page)
        service_form.addRow("", self.backend_options)
        self.translation_test_button = QPushButton("测试翻译连接")
        self.translation_test_button.clicked.connect(
            lambda: self.test_translation_requested.emit(self.values())
        )
        service_form.addRow("", self.translation_test_button)
        self.translation_test_status = QLabel("")
        self.translation_test_status.setWordWrap(True)
        self.translation_test_status.hide()
        service_form.addRow("", self.translation_test_status)
        self.backend.currentIndexChanged.connect(self._update_backend_controls)
        controls_layout.addWidget(service_group)

        self.preference_group = QGroupBox("翻译表达")
        form = QFormLayout(self.preference_group)
        self.preference = QTextEdit()
        self.preference.setPlaceholderText("例如：人名保留英文；语气自然简洁")
        self.preference.setMaximumHeight(90)
        form.addRow("翻译偏好", self.preference)
        preference_note = QLabel("翻译偏好与术语表由 Llama 后端使用。")
        preference_note.setStyleSheet("color:#777")
        form.addRow("", preference_note)
        controls_layout.addWidget(self.preference_group)

        advanced = ExpandableSection("高级翻译设置")
        self.translation_advanced = advanced
        request_group = QGroupBox("请求")
        request_form = QFormLayout(request_group)
        self.timeout = WheelSafeSpinBox()
        self.timeout.setRange(1000, 120000)
        self.timeout.setSuffix(" ms")
        request_form.addRow("请求超时", self.timeout)
        advanced.addWidget(request_group)
        self.context_group = QGroupBox("Llama 上下文")
        context_form = QFormLayout(self.context_group)
        self.context_segments = WheelSafeSpinBox()
        self.context_segments.setRange(0, 12)
        self.context_segments.setSuffix(" 条")
        context_form.addRow("参考上文", self.context_segments)
        self.context_chars = WheelSafeSpinBox()
        self.context_chars.setRange(0, 12000)
        self.context_chars.setSingleStep(200)
        self.context_chars.setSuffix(" 字符")
        context_form.addRow("字符上限", self.context_chars)
        advanced.addWidget(self.context_group)
        controls_layout.addWidget(advanced)
        controls_layout.addStretch(1)
        scroll.setWidget(controls)
        page_layout.addWidget(scroll)
        self.tabs.addTab(page, "翻译")

    def _build_appearance(self) -> None:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        self.style_preview = CaptionCanvas(self.config.subtitle, preview=True)
        self.style_preview.setMinimumHeight(190)
        self.style_preview.set_content(
            source="After early nightfall, the yellow lamps would light up here and there.",
            translation="夜幕初降后，黄色灯光便在各处亮起。",
        )
        self.style_preview.set_cue(
            1, "The city was quiet.", "城市一片寂静。"
        )
        self.style_preview.set_cue(
            2, "A lamp came on in the distance.", "远处亮起了一盏灯。"
        )
        self.style_preview.set_cue(
            3,
            "After early nightfall, the yellow lamps would light up here and there.",
            "夜幕初降后，黄色灯光便在各处亮起。",
        )
        page_layout.addWidget(self.style_preview)
        preview_hint = QLabel("预览会按当前窗口宽度实际换行；保存后立即应用到字幕。")
        preview_hint.setStyleSheet("color:#777")
        preview_row = QHBoxLayout()
        preview_row.addWidget(preview_hint, 1)
        reset_appearance = QPushButton("恢复推荐外观")
        reset_appearance.clicked.connect(self._restore_default_appearance)
        preview_row.addWidget(reset_appearance)
        page_layout.addLayout(preview_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        controls = QWidget()
        controls_layout = QVBoxLayout(controls)
        typography_group = QGroupBox("内容与排版")
        typography_form = QFormLayout(typography_group)
        self.mode = WheelSafeComboBox()
        self.mode.addItem("识别文本 + 翻译文本", "bilingual")
        self.mode.addItem("仅识别文本", "source")
        self.mode.addItem("仅翻译文本", "translation")
        typography_form.addRow("显示内容", self.mode)
        self.max_rows = WheelSafeSpinBox()
        self.max_rows.setRange(2, 6)
        self.max_rows.setSuffix(" 行")
        typography_form.addRow("最大行数", self.max_rows)
        self.font = WheelSafeFontComboBox()
        typography_form.addRow("字体", self.font)
        self.source_size = WheelSafeSpinBox()
        self.translation_size = WheelSafeSpinBox()
        for control in (self.source_size, self.translation_size):
            control.setRange(14, 72)
            control.setSuffix(" px")
        typography_form.addRow("识别文字号", self.source_size)
        typography_form.addRow("翻译文字号", self.translation_size)
        self.weight = WheelSafeSpinBox()
        self.weight.setRange(100, 900)
        self.weight.setSingleStep(100)
        typography_form.addRow("字重", self.weight)
        self.align = WheelSafeComboBox()
        self.align.addItem("居中", "center")
        self.align.addItem("左对齐", "left")
        self.align.addItem("右对齐", "right")
        typography_form.addRow("对齐", self.align)
        controls_layout.addWidget(typography_group)

        readability_group = QGroupBox("背景与可读性")
        readability_form = QFormLayout(readability_group)
        self.text_color = ColorButton()
        self.outline_color = ColorButton()
        readability_form.addRow("文字颜色", self.text_color)
        readability_form.addRow("描边颜色", self.outline_color)
        self.outline_width = WheelSafeDoubleSpinBox()
        self.outline_width.setRange(0, 8)
        self.outline_width.setSingleStep(0.5)
        readability_form.addRow("描边宽度", self.outline_width)
        self.shadow = QCheckBox("启用阴影")
        readability_form.addRow("", self.shadow)
        self.background = WheelSafeComboBox()
        self.background.addItem("每行自适应", "line")
        self.background.addItem("字幕块", "block")
        self.background.addItem("无背景", "none")
        readability_form.addRow("背景", self.background)
        self.background_color = QLineEdit()
        self.background_color.setPlaceholderText("rgba(0,0,0,0.62)")
        readability_form.addRow("背景颜色", self.background_color)
        self.padding = WheelSafeSpinBox()
        self.padding.setRange(0, 48)
        readability_form.addRow("内边距", self.padding)
        controls_layout.addWidget(readability_group)

        timing_group = QGroupBox("显示时序")
        timing_form = QFormLayout(timing_group)
        self.stay = WheelSafeSpinBox()
        self.stay.setRange(0, 60000)
        self.stay.setSuffix(" ms")
        timing_form.addRow("字幕停留", self.stay)
        controls_layout.addWidget(timing_group)
        controls_layout.addStretch(1)
        scroll.setWidget(controls)
        page_layout.addWidget(scroll, 1)
        self.tabs.addTab(page, "外观")
        for control in (
            self.mode,
            self.max_rows,
            self.font,
            self.source_size,
            self.translation_size,
            self.weight,
            self.outline_width,
            self.shadow,
            self.align,
            self.background,
            self.background_color,
            self.padding,
            self.stay,
        ):
            if isinstance(control, QLineEdit):
                control.textChanged.connect(self._update_style_preview)
            elif isinstance(control, QCheckBox):
                control.toggled.connect(self._update_style_preview)
            elif isinstance(control, QComboBox):
                control.currentIndexChanged.connect(self._update_style_preview)
            else:
                control.valueChanged.connect(self._update_style_preview)
        self.text_color.color_changed.connect(self._update_style_preview)
        self.outline_color.color_changed.connect(self._update_style_preview)

    def _build_glossary(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        label = QLabel("每行一个术语，格式：识别文本 = 目标译文。只把当前上下文命中的术语发给 Llama 翻译模型。")
        label.setWordWrap(True)
        layout.addWidget(label)
        self.glossary = QTextEdit()
        self.glossary.setPlaceholderText("Vault = 避难所\nBrotherhood of Steel = 钢铁兄弟会")
        layout.addWidget(self.glossary)
        self.tabs.addTab(page, "术语表")

    def load(self, config: AppConfig) -> None:
        self._loading = True
        self.config = clone_config(config)
        self._select(self.model_variant, config.asr.model_variant)
        self.model_dir.setText(config.asr.model_dir)
        self._select(self.asr_language, config.asr.language)
        self._select(self.auto_standby, config.asr.auto_standby_seconds)
        self._select(self.source_lang, config.translation.source_lang)
        self._select(self.target_lang, config.translation.target_lang)
        self._select(self.backend, config.translation.backend)
        self.llama_url.setText(config.translation.llama_url)
        self.google2_api_key.setText(config.translation.google2_api_key)
        self.deepl_api_key.setText(config.translation.deepl_api_key)
        self._select(self.deepl_api_plan, config.translation.deepl_api_plan)
        self.timeout.setValue(config.translation.timeout_ms)
        self.stream.setChecked(config.translation.stream)
        self.context_segments.setValue(config.translation.context_segments)
        self.context_chars.setValue(config.translation.context_chars)
        self.max_chars.setValue(config.segmentation.max_chars)
        self.split_lookback.setValue(config.segmentation.split_lookback_chars)
        self.split_lookahead.setValue(config.segmentation.split_lookahead_chars)
        self.max_seconds.setValue(config.segmentation.max_seconds)
        self.preview_min_chars.setValue(config.segmentation.preview_min_chars)
        self.preview_interval.setValue(config.segmentation.preview_interval_ms)
        self.preview_char_delta.setValue(config.segmentation.preview_char_delta)
        self.preference.setPlainText(config.translation.preference)
        self._select(self.mode, config.subtitle.mode)
        self.max_rows.setValue(config.subtitle.max_rows)
        self.font.setCurrentFont(QFont(config.subtitle.font_family))
        self.source_size.setValue(config.subtitle.source_size)
        self.translation_size.setValue(config.subtitle.translation_size)
        self.weight.setValue(config.subtitle.font_weight)
        self.text_color.set_color(config.subtitle.text_color)
        self.outline_color.set_color(config.subtitle.outline_color)
        self.outline_width.setValue(config.subtitle.outline_width)
        self.shadow.setChecked(config.subtitle.shadow)
        self._select(self.align, config.subtitle.align)
        self._select(self.background, config.subtitle.background)
        self.background_color.setText(config.subtitle.background_color)
        self.padding.setValue(config.subtitle.padding)
        self.stay.setValue(config.subtitle.stay_ms)
        self.glossary.setPlainText(
            "\n".join(f"{source} = {target}" for source, target in config.translation.glossary.items())
        )
        self._loading = False
        self._update_model_controls()
        self._update_backend_controls()
        self._refresh_model_path_status()
        self._update_style_preview()

    def set_google2_api_key(self, key: str) -> None:
        if not self.google2_api_key.text().strip():
            self.google2_api_key.setText(key)

    def set_model_status(self, text: str, downloadable: bool = False) -> None:
        self.model_status.setText(
            "下载语音识别模型…" if downloadable else f"模型：{text}"
        )
        self.model_status.setEnabled(downloadable)

    def set_translation_test_status(
        self, text: str, *, success: bool | None = None
    ) -> None:
        self.translation_test_status.setText(text)
        self.translation_test_status.setVisible(bool(text))
        if success is True:
            color = "#2e7d32"
        elif success is False:
            color = "#b3261e"
        else:
            color = "#777"
        self.translation_test_status.setStyleSheet(f"color:{color}")
        self.translation_test_button.setEnabled(not text or success is not None)

    def _refresh_model_path_status(self, *args) -> None:
        if not hasattr(self, "model_status"):
            return
        config = clone_config(self.config)
        config.asr.model_dir = self.model_dir.text().strip()
        if model_is_complete(config):
            self.set_model_status("已就绪")
        else:
            self.set_model_status("未安装", downloadable=True)

    @staticmethod
    def _select(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(max(0, index))

    def values(self) -> AppConfig:
        config = clone_config(self.config)
        selected_variant = self.model_variant.currentData()
        if selected_variant != config.asr.model_variant:
            apply_model_preset(config.asr, selected_variant)
        else:
            config.asr.model_variant = selected_variant
        config.asr.model_dir = self.model_dir.text().strip()
        config.asr.language = self.asr_language.currentData()
        config.asr.auto_standby_seconds = self.auto_standby.currentData()
        config.translation.backend = self.backend.currentData()
        config.translation.source_lang = self.source_lang.currentData()
        config.translation.target_lang = self.target_lang.currentData()
        config.translation.llama_url = self.llama_url.text().strip()
        config.translation.google2_api_key = self.google2_api_key.text().strip()
        config.translation.deepl_api_key = self.deepl_api_key.text().strip()
        config.translation.deepl_api_plan = self.deepl_api_plan.currentData()
        config.translation.timeout_ms = self.timeout.value()
        config.translation.stream = self.stream.isChecked()
        config.translation.context_segments = self.context_segments.value()
        config.translation.context_chars = self.context_chars.value()
        config.segmentation.max_chars = self.max_chars.value()
        config.segmentation.split_lookback_chars = self.split_lookback.value()
        config.segmentation.split_lookahead_chars = self.split_lookahead.value()
        config.segmentation.max_seconds = self.max_seconds.value()
        config.segmentation.preview_min_chars = self.preview_min_chars.value()
        config.segmentation.preview_interval_ms = self.preview_interval.value()
        config.segmentation.preview_char_delta = self.preview_char_delta.value()
        config.translation.preference = self.preference.toPlainText().strip()
        terms: dict[str, str] = {}
        for line in self.glossary.toPlainText().splitlines():
            if "=" in line:
                source, target = line.split("=", 1)
                if source.strip() and target.strip():
                    terms[source.strip()] = target.strip()
        config.translation.glossary = terms
        config.subtitle.mode = self.mode.currentData()
        config.subtitle.max_rows = self.max_rows.value()
        config.subtitle.font_family = self.font.currentFont().family()
        config.subtitle.source_size = self.source_size.value()
        config.subtitle.translation_size = self.translation_size.value()
        config.subtitle.font_weight = self.weight.value()
        config.subtitle.text_color = self.text_color.value
        config.subtitle.outline_color = self.outline_color.value
        config.subtitle.outline_width = self.outline_width.value()
        config.subtitle.shadow = self.shadow.isChecked()
        config.subtitle.align = self.align.currentData()
        config.subtitle.background = self.background.currentData()
        config.subtitle.background_color = self.background_color.text().strip()
        config.subtitle.padding = self.padding.value()
        config.subtitle.stay_ms = self.stay.value()
        return config

    def _save(self) -> None:
        self.saved.emit(self.values())
        self.accept()

    def _update_style_preview(self, *args) -> None:
        if not hasattr(self, "style_preview"):
            return
        config = self.values()
        self.style_preview.set_style(config.subtitle)

    def _restore_default_appearance(self) -> None:
        defaults = SubtitleConfig()
        self._select(self.mode, defaults.mode)
        self.max_rows.setValue(defaults.max_rows)
        self.font.setCurrentFont(QFont(defaults.font_family))
        self.source_size.setValue(defaults.source_size)
        self.translation_size.setValue(defaults.translation_size)
        self.weight.setValue(defaults.font_weight)
        self.text_color.set_color(defaults.text_color)
        self.outline_color.set_color(defaults.outline_color)
        self.outline_width.setValue(defaults.outline_width)
        self.shadow.setChecked(defaults.shadow)
        self._select(self.align, defaults.align)
        self._select(self.background, defaults.background)
        self.background_color.setText(defaults.background_color)
        self.padding.setValue(defaults.padding)
        self.stay.setValue(defaults.stay_ms)
        self._update_style_preview()

    def _model_variant_changed(self, *args) -> None:
        if not self._loading:
            self.model_dir.setText(default_model_dir(self.model_variant.currentData()))
        self._update_model_controls()
        self._refresh_model_path_status()

    def _update_model_controls(self) -> None:
        supports_language = MODEL_CATALOG[
            self.model_variant.currentData()
        ].supports_language
        self.asr_language.setEnabled(supports_language)
        if not supports_language:
            self._select(self.asr_language, "auto")

    def _update_backend_controls(self, *args) -> None:
        self.backend_options.setCurrentIndex(max(0, self.backend.currentIndex()))
        llama = self.backend.currentData() == "llama"
        self.preference_group.setVisible(llama)
        self.context_group.setVisible(llama)
        self.set_translation_test_status("")

    def _browse_model(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "选择语音识别模型目录")
        if selected:
            self.model_dir.setText(str(Path(selected)))
