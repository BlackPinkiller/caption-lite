from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from captions.core.settings import AppConfig, LlmProviderConfig, SubtitleConfig, clone_config
from captions.core.model_catalog import (
    MODEL_CATALOG,
    apply_model_preset,
    default_model_dir,
    model_preset,
    supports_high_precision,
)
from captions.core.subtitle_style import (
    SUBTITLE_THEME_PRESETS,
    apply_subtitle_theme,
    subtitle_custom_style,
    subtitle_style_values,
)
from captions.adapters.model_files import model_install_key, model_is_complete
from captions.ui.translation_test_feedback import TranslationTestFeedback
from captions.core.prompt_template import DEFAULT_LLM_PROMPT_TEMPLATE
from captions.ui.caption_canvas import CaptionCanvas
from captions.ui.settings_widgets import (
    BACKEND_SEPARATOR_ROLE,
    BackendComboBox,
    ColorButton,
    ExpandableSection,
    PromptTemplateEdit,
    TitleActionGroupBox,
    WheelSafeComboBox,
    WheelSafeDoubleSpinBox,
    WheelSafeFontComboBox,
    WheelSafeSpinBox,
)


LLM_BACKEND_PREFIX = "llm:"
ADD_LLM_PROVIDER = "add_llm_provider"


ASR_LANGUAGE_LABELS = {
    "auto": "自动检测",
    "en": "英语",
    "es": "西班牙语",
    "fr": "法语",
    "it": "意大利语",
    "pt": "葡萄牙语",
    "nl": "荷兰语",
    "de": "德语",
    "tr": "土耳其语",
    "ru": "俄语",
    "ar": "阿拉伯语",
    "hi": "印地语",
    "ja": "日语",
    "ko": "韩语",
    "vi": "越南语",
    "uk": "乌克兰语",
    "pl": "波兰语（实验性）",
    "sv": "瑞典语（实验性）",
    "cs": "捷克语（实验性）",
    "nb": "挪威语（实验性）",
    "da": "丹麦语（实验性）",
    "bg": "保加利亚语（实验性）",
    "fi": "芬兰语（实验性）",
    "hr": "克罗地亚语（实验性）",
    "sk": "斯洛伐克语（实验性）",
    "zh": "普通话（实验性）",
    "hu": "匈牙利语（实验性）",
    "ro": "罗马尼亚语（实验性）",
    "et": "爱沙尼亚语（实验性）",
}


class SettingsDialog(QDialog):
    saved = Signal(object)
    test_translation_requested = Signal(object)
    model_download_requested = Signal(object)

    def __init__(self, config: AppConfig, parent=None) -> None:
        super().__init__(parent)
        self.config = clone_config(config)
        self._loading = False
        self._applying_theme = False
        self._draft_custom_style = subtitle_custom_style(config.subtitle)
        self._llm_providers: list[LlmProviderConfig] = []
        self._current_llm_provider_id: str | None = None
        self._model_download_target: AppConfig | None = None
        self._model_download_text = ""
        self._active_model_status: tuple[tuple[str, ...], str, bool] | None = None
        self.setWindowTitle("实时字幕设置")
        self.resize(680, 620)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self._build_general()
        self._build_appearance()
        self._build_glossary()
        self.translation_test_feedback = TranslationTestFeedback(
            self.translation_test_status, self.translation_test_button,
            self.translation_enabled.isChecked, self,
        )
        for signal in (
            self.llm_base_url.textChanged, self.llm_model.textChanged,
            self.llm_api_key.textChanged, self.llm_type.currentIndexChanged,
            self.stream.toggled, self.google2_api_key.textChanged,
            self.deepl_api_key.textChanged, self.deepl_api_plan.currentIndexChanged,
            self.source_lang.currentIndexChanged, self.target_lang.currentIndexChanged,
            self.timeout.valueChanged, self.context_segments.valueChanged,
            self.context_chars.valueChanged, self.prompt_template.textChanged,
            self.glossary.textChanged, self.translation_enabled.toggled, self.finished,
        ):
            signal.connect(self.translation_test_feedback.clear)
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
        self.asr_precision = WheelSafeComboBox()
        self.asr_precision.addItem("轻量（默认）", "int8")
        self.asr_precision.addItem("高精度（NVIDIA GPU）", "fp32")
        self.asr_precision_label = QLabel("识别精度")
        form.addRow(self.asr_precision_label, self.asr_precision)
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
        self._populate_asr_languages("english", "en")
        form.addRow("识别语言", self.asr_language)
        self.model_variant.currentIndexChanged.connect(self._model_variant_changed)
        self.asr_precision.currentIndexChanged.connect(
            self._recognition_precision_changed
        )
        self.asr_language.currentIndexChanged.connect(
            self._recognition_language_changed
        )
        controls_layout.addWidget(model_group)

        standby_group = QGroupBox("自动待机")
        standby_form = QFormLayout(standby_group)
        self.auto_standby = WheelSafeComboBox()
        for label, seconds in (
            ("关闭", 0), ("30 秒无声音（默认）", 30), ("1 分钟无声音", 60),
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
        self.model_files_group = model_files_group
        model_files_form = QFormLayout(model_files_group)
        model_files_form.addRow("模型目录", row)
        advanced.addWidget(model_files_group)

        performance_group = QGroupBox("性能与响应")
        performance_form = QFormLayout(performance_group)
        self.asr_threads = WheelSafeComboBox()
        for label, threads in (
            ("1", 1),
            ("2", 2),
            ("4", 4),
            ("8", 8),
        ):
            self.asr_threads.addItem(label, threads)
        performance_form.addRow("识别线程数", self.asr_threads)
        self.silence_endpoint = WheelSafeDoubleSpinBox()
        self.silence_endpoint.setRange(0.3, 1.5)
        self.silence_endpoint.setDecimals(1)
        self.silence_endpoint.setSingleStep(0.1)
        self.silence_endpoint.setSuffix(" 秒")
        performance_form.addRow("静音断句等待", self.silence_endpoint)
        self.silence_min_chars = WheelSafeSpinBox()
        self.silence_min_chars.setRange(1, 100)
        self.silence_min_chars.setSuffix(" 字符")
        performance_form.addRow("分句最小字符数", self.silence_min_chars)
        advanced.addWidget(performance_group)

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
        self.punctuation_mode = WheelSafeComboBox()
        self.punctuation_mode.addItem("关闭", "off")
        self.punctuation_mode.addItem("仅句末", "sentence")
        self.punctuation_mode.addItem("所有标点", "all")
        self.punctuation_mode.setToolTip("停顿与模型端点始终分句")
        form.addRow("标点分句", self.punctuation_mode)
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
        self.translation_language_group = language_group
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

        service_group = TitleActionGroupBox(
            "翻译服务",
            "已开启",
            unchecked_action_text="已关闭",
        )
        self.translation_service_group = service_group
        self.translation_enabled = service_group.action_button
        service_form = QFormLayout(service_group)
        self.backend = BackendComboBox()
        self.backend.delete_requested.connect(self._delete_llm_provider)
        service_form.addRow("翻译后端", self.backend)
        self.backend_options = QStackedWidget()

        llama_page = QWidget()
        llama_form = QFormLayout(llama_page)
        llama_form.setContentsMargins(0, 0, 0, 0)
        identity = QWidget()
        identity_layout = QHBoxLayout(identity)
        identity_layout.setContentsMargins(0, 0, 0, 0)
        identity_layout.setSpacing(8)
        self.llm_name = QLineEdit()
        self.llm_name.setPlaceholderText("名称")
        identity_layout.addWidget(self.llm_name, 1)
        identity_layout.addWidget(QLabel("接口"))
        self.llm_type = WheelSafeComboBox()
        self.llm_type.addItem("OpenAI Compatible", "openai_compatible")
        identity_layout.addWidget(self.llm_type, 1)
        llama_form.addRow("名称", identity)
        self.llm_base_url = QLineEdit()
        self.llm_base_url.setPlaceholderText("例如：https://api.openai.com/v1")
        llama_form.addRow("API 地址", self.llm_base_url)
        self.llm_model = QLineEdit()
        self.llm_model.setPlaceholderText("输入模型名称")
        llama_form.addRow("模型", self.llm_model)
        self.llm_api_key = QLineEdit()
        self.llm_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.llm_api_key.setPlaceholderText("输入 API 密钥")
        llama_form.addRow("API 密钥", self.llm_api_key)
        self.stream = QCheckBox("启用流式响应")
        llama_form.addRow("", self.stream)
        self.backend_options.addWidget(llama_page)

        google_page = QWidget()
        google_form = QFormLayout(google_page)
        google_form.setContentsMargins(0, 0, 0, 0)
        self.google2_api_key = QLineEdit()
        self.google2_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.google2_api_key.setPlaceholderText("首次使用时自动从 Google 获取")
        google_form.addRow("密钥", self.google2_api_key)
        google_note = QLabel("自动获取网页组件密钥；无需填写 Google Cloud 项目密钥。")
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
        self.llm_name.textChanged.connect(self._update_llm_provider_name)
        controls_layout.addWidget(service_group)

        advanced = ExpandableSection("高级翻译设置")
        self.translation_advanced = advanced
        request_group = QGroupBox("请求")
        request_form = QFormLayout(request_group)
        self.timeout = WheelSafeSpinBox()
        self.timeout.setRange(1000, 120000)
        self.timeout.setSuffix(" ms")
        request_form.addRow("请求超时", self.timeout)
        advanced.addWidget(request_group)
        self.context_group = QGroupBox("LLM 上下文")
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
        self.prompt_group = TitleActionGroupBox("LLM 提示词", "恢复默认")
        prompt_layout = QVBoxLayout(self.prompt_group)
        self.reset_prompt_button = self.prompt_group.action_button
        self.reset_prompt_button.setToolTip("恢复内置提示词模板")
        self.prompt_group.actionTriggered.connect(self._restore_default_prompt)
        self.prompt_template = PromptTemplateEdit()
        self.prompt_template.setMinimumHeight(180)
        self.prompt_template.setMaximumHeight(260)
        self.prompt_template.setToolTip(
            "可用占位符：{src} 源语言；{dst} 目标语言；{ctx} 上下文；"
            "{terms} 术语；{text} 当前文本。必须保留 {text}。"
        )
        prompt_layout.addWidget(self.prompt_template)
        advanced.addWidget(self.prompt_group)
        self.translation_service_group.actionToggled.connect(
            self._update_translation_enabled
        )
        controls_layout.addWidget(advanced)
        controls_layout.addStretch(1)
        scroll.setWidget(controls)
        page_layout.addWidget(scroll)
        self.tabs.addTab(page, "翻译")

    def _build_appearance(self) -> None:
        page = QWidget()
        page_layout = QVBoxLayout(page)

        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("主题"))
        self.appearance_theme = WheelSafeComboBox()
        for theme, preset in SUBTITLE_THEME_PRESETS.items():
            self.appearance_theme.addItem(preset["label"], theme)
        self.appearance_theme.addItem("自定义", "custom")
        theme_row.addWidget(self.appearance_theme, 1)
        page_layout.addLayout(theme_row)

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
        self.style_preview.set_cue(
            4, "Footsteps echoed along the street.", "脚步声在街道上回响。"
        )
        self.style_preview.set_cue(
            5, "A window opened above the square.", "广场上方的一扇窗户打开了。"
        )
        self.style_preview.set_cue(
            6, "Then the evening bells began to ring.", "随后，晚钟响了起来。"
        )
        page_layout.addWidget(self.style_preview)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        controls = QWidget()
        controls_layout = QVBoxLayout(controls)
        content_group = QGroupBox("内容与布局")
        content_form = QFormLayout(content_group)
        self.mode = WheelSafeComboBox()
        self.mode.addItem("识别文本 + 翻译文本", "bilingual")
        self.mode.addItem("仅识别文本", "source")
        self.mode.addItem("仅翻译文本", "translation")
        content_form.addRow("显示内容", self.mode)
        self.max_sentences = WheelSafeSpinBox()
        self.max_sentences.setRange(1, 6)
        self.max_sentences.setSuffix(" 句")
        content_form.addRow("最大句数", self.max_sentences)
        self.mode.currentIndexChanged.connect(self._update_sentence_minimum)
        self._update_sentence_minimum()
        self.align = WheelSafeComboBox()
        self.align.addItem("居中", "center")
        self.align.addItem("左对齐", "left")
        self.align.addItem("右对齐", "right")
        content_form.addRow("对齐", self.align)
        self.width_percent = WheelSafeSpinBox()
        self.width_percent.setRange(30, 90)
        self.width_percent.setSingleStep(5)
        self.width_percent.setSuffix(" %")
        self.width_percent.setToolTip("占所在屏幕可用宽度的比例。")
        content_form.addRow("字幕宽度", self.width_percent)
        self.stay = WheelSafeSpinBox()
        self.stay.setRange(0, 60000)
        self.stay.setSuffix(" ms")
        content_form.addRow("字幕停留", self.stay)
        controls_layout.addWidget(content_group)

        typography_group = QGroupBox("文字")
        typography_form = QFormLayout(typography_group)
        self.font = WheelSafeFontComboBox()
        typography_form.addRow("字体", self.font)
        self.source_size = WheelSafeSpinBox()
        self.translation_size = WheelSafeSpinBox()
        for control in (self.source_size, self.translation_size):
            control.setRange(14, 72)
            control.setSuffix(" px")
        typography_form.addRow("识别文字号", self.source_size)
        typography_form.addRow("翻译文字号", self.translation_size)
        self.text_color = ColorButton()
        typography_form.addRow("文字颜色", self.text_color)
        self.line_spacing = WheelSafeSpinBox()
        self.line_spacing.setRange(0, 32)
        self.line_spacing.setSuffix(" px")
        typography_form.addRow("行间距", self.line_spacing)
        controls_layout.addWidget(typography_group)

        readability_group = QGroupBox("背景与效果")
        readability_form = QFormLayout(readability_group)
        self.outline_color = ColorButton()
        readability_form.addRow("描边颜色", self.outline_color)
        self.outline_width = WheelSafeDoubleSpinBox()
        self.outline_width.setRange(0, 1)
        self.outline_width.setDecimals(1)
        self.outline_width.setSingleStep(0.1)
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
        self.background_radius = WheelSafeSpinBox()
        self.background_radius.setRange(0, 24)
        self.background_radius.setSuffix(" px")
        readability_form.addRow("背景圆角", self.background_radius)
        self.background_padding_y = WheelSafeSpinBox()
        self.background_padding_y.setRange(0, 24)
        self.background_padding_y.setSuffix(" px")
        readability_form.addRow("背景上下留白", self.background_padding_y)
        self.padding = WheelSafeSpinBox()
        self.padding.setRange(0, 48)
        self.padding.setSuffix(" px")
        readability_form.addRow("文字内边距", self.padding)
        controls_layout.addWidget(readability_group)

        self.appearance_advanced = ExpandableSection("字幕层级")
        hierarchy_group = QGroupBox()
        hierarchy_form = QFormLayout(hierarchy_group)
        self.preview_opacity = WheelSafeSpinBox()
        self.preview_opacity.setRange(0, 100)
        self.preview_opacity.setSuffix(" %")
        hierarchy_form.addRow("当前字幕", self.preview_opacity)
        self.old_opacity = WheelSafeSpinBox()
        self.old_opacity.setRange(0, 100)
        self.old_opacity.setSuffix(" %")
        hierarchy_form.addRow("历史字幕", self.old_opacity)
        self.appearance_advanced.addWidget(hierarchy_group)
        controls_layout.addWidget(self.appearance_advanced)
        controls_layout.addStretch(1)
        scroll.setWidget(controls)
        page_layout.addWidget(scroll, 1)
        self.tabs.addTab(page, "外观")
        self.appearance_theme.currentIndexChanged.connect(self._theme_changed)
        for control in (
            self.font,
            self.source_size,
            self.translation_size,
            self.align,
            self.outline_width,
            self.shadow,
            self.background,
            self.background_color,
            self.background_radius,
            self.background_padding_y,
            self.padding,
            self.line_spacing,
            self.preview_opacity,
            self.old_opacity,
        ):
            if isinstance(control, QLineEdit):
                control.textChanged.connect(self._appearance_value_changed)
            elif isinstance(control, QCheckBox):
                control.toggled.connect(self._appearance_value_changed)
            elif isinstance(control, QComboBox):
                control.currentIndexChanged.connect(self._appearance_value_changed)
            else:
                control.valueChanged.connect(self._appearance_value_changed)
        for control in (self.mode, self.max_sentences, self.stay, self.width_percent):
            if isinstance(control, QComboBox):
                control.currentIndexChanged.connect(self._update_style_preview)
            else:
                control.valueChanged.connect(self._update_style_preview)
        self.text_color.color_changed.connect(self._appearance_value_changed)
        self.outline_color.color_changed.connect(self._appearance_value_changed)

    def _build_glossary(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        label = QLabel(
            "每行一个术语，格式：原文 = 译文。使用 LLM 翻译时，仅提供当前字幕及上下文中命中的术语。"
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        self.glossary = QTextEdit()
        self.glossary.setPlaceholderText("Vault = 避难所\nBrotherhood of Steel = 钢铁兄弟会")
        layout.addWidget(self.glossary)
        self.tabs.addTab(page, "术语表")

    def _set_style_controls(self, style: SubtitleConfig) -> None:
        self.font.setCurrentFont(QFont(style.font_family))
        self.source_size.setValue(style.source_size)
        self.translation_size.setValue(style.translation_size)
        self.text_color.set_color(style.text_color)
        self.outline_color.set_color(style.outline_color)
        self.outline_width.setValue(style.outline_width)
        self.shadow.setChecked(style.shadow)
        self._select(self.align, style.align)
        self._select(self.background, style.background)
        self.background_color.setText(style.background_color)
        self.background_radius.setValue(style.background_radius)
        self.background_padding_y.setValue(style.background_padding_y)
        self.padding.setValue(style.padding)
        self.line_spacing.setValue(style.line_spacing)
        self.preview_opacity.setValue(round(style.preview_opacity * 100))
        self.old_opacity.setValue(round(style.old_opacity * 100))

    def _update_sentence_minimum(self, *args) -> None:
        minimum = 2 if self.mode.currentData() == "bilingual" else 1
        self.max_sentences.setMinimum(minimum)

    def load(self, config: AppConfig) -> None:
        self._loading = True
        self.config = clone_config(config)
        self._draft_custom_style = subtitle_custom_style(config.subtitle)
        self._select(self.model_variant, config.asr.model_variant)
        self._select(self.asr_precision, config.asr.precision)
        self.model_dir.setText(config.asr.model_dir)
        self._populate_asr_languages(
            config.asr.model_variant,
            config.asr.language,
        )
        self._select(self.auto_standby, config.asr.auto_standby_seconds)
        self._select(self.asr_threads, config.asr.num_threads)
        self.silence_endpoint.setValue(config.asr.silence_endpoint_ms / 1000)
        self.silence_min_chars.setValue(config.asr.silence_min_chars)
        self._select(self.source_lang, config.translation.source_lang)
        self._select(self.target_lang, config.translation.target_lang)
        self._llm_providers = clone_config(config).translation.llm_providers
        self._current_llm_provider_id = None
        self._populate_backend_options(
            config.translation.backend,
            config.translation.llm_provider_id,
        )
        self.google2_api_key.setText(config.translation.google2_api_key)
        self.deepl_api_key.setText(config.translation.deepl_api_key)
        self._select(self.deepl_api_plan, config.translation.deepl_api_plan)
        self.timeout.setValue(config.translation.timeout_ms)
        self.context_segments.setValue(config.translation.context_segments)
        self.context_chars.setValue(config.translation.context_chars)
        self.max_chars.setValue(config.segmentation.max_chars)
        self.split_lookback.setValue(config.segmentation.split_lookback_chars)
        self.split_lookahead.setValue(config.segmentation.split_lookahead_chars)
        self.max_seconds.setValue(config.segmentation.max_seconds)
        self._select(
            self.punctuation_mode,
            config.segmentation.punctuation_mode,
        )
        self.preview_min_chars.setValue(config.segmentation.preview_min_chars)
        self.preview_interval.setValue(config.segmentation.preview_interval_ms)
        self.preview_char_delta.setValue(config.segmentation.preview_char_delta)
        self.prompt_template.setPlainText(config.translation.prompt_template)
        self.translation_enabled.setChecked(config.translation.enabled)
        self._update_translation_enabled(config.translation.enabled)
        self._select(self.mode, config.subtitle.mode)
        self.max_sentences.setValue(config.subtitle.max_sentences)
        appearance_theme = config.subtitle.theme
        if appearance_theme in SUBTITLE_THEME_PRESETS:
            preset_style = SubtitleConfig()
            apply_subtitle_theme(preset_style, appearance_theme)
            if subtitle_style_values(preset_style) != subtitle_style_values(
                config.subtitle
            ):
                appearance_theme = "custom"
                self._draft_custom_style = subtitle_style_values(config.subtitle)
        self._select(self.appearance_theme, appearance_theme)
        self._set_style_controls(config.subtitle)
        self.stay.setValue(config.subtitle.stay_ms)
        self.width_percent.setValue(config.window.width_percent)
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

    def _restore_default_prompt(self) -> None:
        self.prompt_template.setPlainText(DEFAULT_LLM_PROMPT_TEMPLATE)
        self.prompt_template.setFocus()

    def _update_translation_enabled(self, enabled: bool) -> None:
        self.translation_language_group.setEnabled(enabled)
        self.translation_service_group.set_content_enabled(enabled)
        self.translation_advanced.setEnabled(enabled)

    def set_model_status(
        self, text: str, downloadable: bool = False, *, target: AppConfig | None = None,
    ) -> None:
        if target is not None:
            self._active_model_status = (model_install_key(target), text, downloadable)
            self._refresh_model_path_status()
            return
        active = text.startswith(
            ("下载 ", "已下载 ", "正在连接", "正在解压", "正在准备", "正在安装")
        )
        if downloadable:
            verb = "重新下载" if text.endswith("失败") else "下载"
            label = (
                f"{verb}高精度识别组件…"
                if self.asr_precision.currentData() == "fp32"
                else f"{verb}语音识别模型…"
            )
        elif active:
            label = text
        else:
            label = f"模型：{text}"
        self.model_status.setText(label)
        self.model_status.setToolTip(
            f"模型：{text}" if downloadable and text.endswith("失败") else label
        )
        self.model_status.setEnabled(downloadable)

    def set_model_download_status(
        self,
        target: AppConfig | None,
        text: str = "",
    ) -> None:
        self._model_download_target = (
            clone_config(target) if target is not None else None
        )
        self._model_download_text = text
        self._refresh_model_path_status()

    def set_translation_test_status(
        self, text: str, *, success: bool | None = None
    ) -> None:
        if not text:
            self.translation_test_feedback.clear()
        else:
            self.translation_test_feedback.show_status(text, success=success)

    def _refresh_model_path_status(self, *args) -> None:
        if not hasattr(self, "model_status"):
            return
        config = self._selected_model_config()
        target = self._model_download_target
        if target is not None:
            if model_install_key(config) == model_install_key(target):
                self.set_model_status(self._model_download_text or "正在连接")
            else:
                target_label = (
                    "高精度识别组件"
                    if target.asr.precision == "fp32"
                    else model_preset(target.asr.model_variant).label
                )
                label = "其他模型正在下载…"
                self.model_status.setText(label)
                self.model_status.setToolTip(
                    f"{target_label}：{self._model_download_text or '正在连接'}"
                )
                self.model_status.setEnabled(False)
            return
        active = self._active_model_status
        if active is not None and model_install_key(config) == active[0]:
            self.set_model_status(active[1], downloadable=active[2])
        elif model_is_complete(config):
            self.set_model_status("已就绪")
        else:
            self.set_model_status("未安装", downloadable=True)

    def _selected_model_config(self) -> AppConfig:
        config = clone_config(self.config)
        selected_variant = self.model_variant.currentData()
        if selected_variant != config.asr.model_variant:
            apply_model_preset(config.asr, selected_variant)
        config.asr.precision = self.asr_precision.currentData()
        config.asr.model_dir = self.model_dir.text().strip()
        return config

    @staticmethod
    def _select(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(max(0, index))

    def values(self) -> AppConfig:
        self._store_current_llm_provider()
        config = clone_config(self.config)
        selected_variant = self.model_variant.currentData()
        if selected_variant != config.asr.model_variant:
            apply_model_preset(config.asr, selected_variant)
        else:
            config.asr.model_variant = selected_variant
        config.asr.precision = self.asr_precision.currentData()
        config.asr.model_dir = self.model_dir.text().strip()
        config.asr.language = self.asr_language.currentData()
        config.asr.auto_standby_seconds = self.auto_standby.currentData()
        config.asr.num_threads = self.asr_threads.currentData()
        config.asr.silence_endpoint_ms = round(self.silence_endpoint.value() * 1000)
        config.asr.silence_min_chars = self.silence_min_chars.value()
        selected_backend = self.backend.currentData()
        if isinstance(selected_backend, str) and selected_backend.startswith(
            LLM_BACKEND_PREFIX
        ):
            config.translation.backend = "llama"
            config.translation.llm_provider_id = selected_backend.removeprefix(
                LLM_BACKEND_PREFIX
            )
        elif selected_backend in {"google2", "deepl"}:
            config.translation.backend = selected_backend
        config.translation.llm_providers = copy.deepcopy(self._llm_providers)
        config.translation.source_lang = self.source_lang.currentData()
        config.translation.target_lang = self.target_lang.currentData()
        config.translation.google2_api_key = self.google2_api_key.text().strip()
        config.translation.deepl_api_key = self.deepl_api_key.text().strip()
        config.translation.deepl_api_plan = self.deepl_api_plan.currentData()
        config.translation.timeout_ms = self.timeout.value()
        config.translation.context_segments = self.context_segments.value()
        config.translation.context_chars = self.context_chars.value()
        config.segmentation.max_chars = self.max_chars.value()
        config.segmentation.split_lookback_chars = self.split_lookback.value()
        config.segmentation.split_lookahead_chars = self.split_lookahead.value()
        config.segmentation.max_seconds = self.max_seconds.value()
        config.segmentation.punctuation_mode = self.punctuation_mode.currentData()
        config.segmentation.preview_min_chars = self.preview_min_chars.value()
        config.segmentation.preview_interval_ms = self.preview_interval.value()
        config.segmentation.preview_char_delta = self.preview_char_delta.value()
        config.translation.prompt_template = (
            self.prompt_template.toPlainText().strip()
            or DEFAULT_LLM_PROMPT_TEMPLATE
        )
        config.translation.enabled = self.translation_enabled.isChecked()
        terms: dict[str, str] = {}
        for line in self.glossary.toPlainText().splitlines():
            if "=" in line:
                source, target = line.split("=", 1)
                if source.strip() and target.strip():
                    terms[source.strip()] = target.strip()
        config.translation.glossary = terms
        config.subtitle.mode = self.mode.currentData()
        config.subtitle.max_sentences = self.max_sentences.value()
        config.subtitle.theme = self.appearance_theme.currentData()
        config.subtitle.font_family = self.font.currentFont().family()
        config.subtitle.source_size = self.source_size.value()
        config.subtitle.translation_size = self.translation_size.value()
        config.subtitle.text_color = self.text_color.value
        config.subtitle.outline_color = self.outline_color.value
        config.subtitle.outline_width = self.outline_width.value()
        config.subtitle.shadow = self.shadow.isChecked()
        config.subtitle.align = self.align.currentData()
        config.subtitle.background = self.background.currentData()
        config.subtitle.background_color = self.background_color.text().strip()
        config.subtitle.background_radius = self.background_radius.value()
        config.subtitle.background_padding_y = self.background_padding_y.value()
        config.subtitle.padding = self.padding.value()
        config.subtitle.line_spacing = self.line_spacing.value()
        config.subtitle.preview_opacity = self.preview_opacity.value() / 100
        config.subtitle.old_opacity = self.old_opacity.value() / 100
        if config.subtitle.theme == "custom":
            config.subtitle.custom_style = subtitle_style_values(config.subtitle)
        else:
            config.subtitle.custom_style = self._draft_custom_style.copy()
        config.subtitle.stay_ms = self.stay.value()
        config.window.width_percent = self.width_percent.value()
        return config

    def _save(self) -> None:
        self.saved.emit(self.values())
        self.accept()

    def _update_style_preview(self, *args) -> None:
        if not hasattr(self, "style_preview"):
            return
        config = self.values()
        self.style_preview.preview_width_percent = config.window.width_percent
        self.style_preview.set_style(config.subtitle)

    def _theme_changed(self, *args) -> None:
        if self._loading or self._applying_theme:
            return
        style = clone_config(self.config).subtitle
        style.custom_style = self._draft_custom_style
        apply_subtitle_theme(style, self.appearance_theme.currentData())
        self._applying_theme = True
        try:
            self._set_style_controls(style)
        finally:
            self._applying_theme = False
        self._update_style_preview()

    def _appearance_value_changed(self, *args) -> None:
        if self._loading or self._applying_theme:
            return
        if self.appearance_theme.currentData() != "custom":
            index = self.appearance_theme.findData("custom")
            blocker = QSignalBlocker(self.appearance_theme)
            self.appearance_theme.setCurrentIndex(index)
            del blocker
        config = self.values()
        self._draft_custom_style = subtitle_style_values(config.subtitle)
        self.style_preview.set_style(config.subtitle)

    def _model_variant_changed(self, *args) -> None:
        model_variant = self.model_variant.currentData()
        preset = MODEL_CATALOG[model_variant]
        self._populate_asr_languages(
            model_variant,
            preset.default_language,
        )
        if not self._loading:
            self.model_dir.setText(default_model_dir(model_variant))
            self._sync_translation_source_from_recognition()
        self._update_precision_controls()
        self._refresh_model_path_status()

    def _recognition_precision_changed(self, *args) -> None:
        self._update_precision_controls()
        self._refresh_model_path_status()

    def _update_precision_controls(self) -> None:
        compatible = supports_high_precision(self.model_variant.currentData())
        self.asr_precision_label.setVisible(compatible)
        self.asr_precision.setVisible(compatible)
        if not compatible and self.asr_precision.currentData() != "int8":
            self._select(self.asr_precision, "int8")
        self.model_files_group.setVisible(self.asr_precision.currentData() != "fp32")

    def _update_model_controls(self) -> None:
        self.asr_language.setEnabled(self.asr_language.count() > 1)

    def _populate_asr_languages(
        self,
        model_variant: str,
        selected: str,
    ) -> None:
        preset = MODEL_CATALOG[model_variant]
        languages = list(preset.supported_languages)
        if preset.supports_auto_language:
            languages.insert(0, "auto")
        previous = self.asr_language.blockSignals(True)
        self.asr_language.clear()
        for code in languages:
            self.asr_language.addItem(ASR_LANGUAGE_LABELS[code], code)
        self._select(
            self.asr_language,
            selected if selected in languages else preset.default_language,
        )
        self.asr_language.blockSignals(previous)
        self._update_model_controls()

    def _recognition_language_changed(self, *args) -> None:
        if not self._loading:
            self._sync_translation_source_from_recognition()

    def _sync_translation_source_from_recognition(self) -> None:
        if self.source_lang.currentData() == "AUTO":
            return
        recognition = self.asr_language.currentData()
        source = "ZH" if recognition == "zh" else str(recognition).upper()
        index = self.source_lang.findData(source)
        if index < 0:
            index = self.source_lang.findData("AUTO")
        if index >= 0 and self.source_lang.currentIndex() != index:
            self.source_lang.setCurrentIndex(index)

    def _update_backend_controls(self, *args) -> None:
        selected = self.backend.currentData()
        if selected == ADD_LLM_PROVIDER:
            self._add_llm_provider()
            return
        self._store_current_llm_provider()
        llama = isinstance(selected, str) and selected.startswith(LLM_BACKEND_PREFIX)
        if llama:
            provider_id = selected.removeprefix(LLM_BACKEND_PREFIX)
            self._load_llm_provider(provider_id)
            self.backend_options.setCurrentIndex(0)
        elif selected == "google2":
            self._current_llm_provider_id = None
            self.backend_options.setCurrentIndex(1)
        elif selected == "deepl":
            self._current_llm_provider_id = None
            self.backend_options.setCurrentIndex(2)
        self.prompt_group.setVisible(llama)
        self.context_group.setVisible(llama)
        self.set_translation_test_status("")

    def _populate_backend_options(self, backend: str, provider_id: str) -> None:
        blocker = QSignalBlocker(self.backend)
        self.backend.clear()
        for provider in self._llm_providers:
            self.backend.addItem(provider.name, f"{LLM_BACKEND_PREFIX}{provider.id}")
            self.backend.set_item_deletable(
                self.backend.count() - 1,
                provider.id != "openai",
            )
        self.backend.addItem("Google2", "google2")
        self.backend.addItem("DeepL API", "deepl")
        separator_index = self.backend.count()
        self.backend.addItem("")
        self.backend.setItemData(separator_index, True, BACKEND_SEPARATOR_ROLE)
        separator = self.backend.model().item(separator_index)
        if separator is not None:
            separator.setEnabled(False)
        self.backend.addItem("＋ 添加 LLM 提供商…", ADD_LLM_PROVIDER)
        selected = (
            f"{LLM_BACKEND_PREFIX}{provider_id}"
            if backend == "llama"
            else backend
        )
        index = self.backend.findData(selected)
        self.backend.setCurrentIndex(max(0, index))
        del blocker

    def _provider_by_id(self, provider_id: str) -> LlmProviderConfig | None:
        return next(
            (provider for provider in self._llm_providers if provider.id == provider_id),
            None,
        )

    def _store_current_llm_provider(self) -> None:
        if self._loading or not self._current_llm_provider_id:
            return
        provider = self._provider_by_id(self._current_llm_provider_id)
        if provider is None:
            return
        provider.name = self.llm_name.text().strip() or "OpenAI"
        provider.provider_type = self.llm_type.currentData()
        provider.base_url = self.llm_base_url.text().strip()
        provider.model = self.llm_model.text().strip()
        provider.api_key = self.llm_api_key.text().strip()
        provider.stream = self.stream.isChecked()

    def _load_llm_provider(self, provider_id: str) -> None:
        provider = self._provider_by_id(provider_id)
        if provider is None:
            return
        self._current_llm_provider_id = provider_id
        blockers = [
            QSignalBlocker(control)
            for control in (
                self.llm_name,
                self.llm_type,
                self.llm_base_url,
                self.llm_model,
                self.llm_api_key,
                self.stream,
            )
        ]
        self.llm_name.setText(provider.name)
        self._select(self.llm_type, provider.provider_type)
        self.llm_base_url.setText(provider.base_url)
        self.llm_model.setText(provider.model)
        self.llm_api_key.setText(provider.api_key)
        self.stream.setChecked(provider.stream)
        del blockers

    def _add_llm_provider(self) -> None:
        self._store_current_llm_provider()
        suffix = 1
        used_ids = {provider.id for provider in self._llm_providers}
        while f"llm-{suffix}" in used_ids:
            suffix += 1
        provider = LlmProviderConfig(
            id=f"llm-{suffix}",
            name="OpenAI",
        )
        self._llm_providers.append(provider)
        self._populate_backend_options("llama", provider.id)
        self._load_llm_provider(provider.id)
        self.backend_options.setCurrentIndex(0)
        self.prompt_group.setVisible(True)
        self.context_group.setVisible(True)
        self.set_translation_test_status("")
        self.llm_name.setFocus()
        self.llm_name.selectAll()

    def _delete_llm_provider(self, backend: str) -> None:
        if not backend.startswith(LLM_BACKEND_PREFIX):
            return
        provider_id = backend.removeprefix(LLM_BACKEND_PREFIX)
        if provider_id == "openai":
            return
        self._store_current_llm_provider()
        selected = self.backend.currentData()
        self._llm_providers = [
            provider
            for provider in self._llm_providers
            if provider.id != provider_id
        ]
        if selected == backend:
            selected = f"{LLM_BACKEND_PREFIX}{self._llm_providers[0].id}"
        selected_backend = "llama" if str(selected).startswith(LLM_BACKEND_PREFIX) else selected
        selected_provider_id = (
            str(selected).removeprefix(LLM_BACKEND_PREFIX)
            if selected_backend == "llama"
            else self._llm_providers[0].id
        )
        self._current_llm_provider_id = None
        self._populate_backend_options(selected_backend, selected_provider_id)
        self._update_backend_controls()

    def _update_llm_provider_name(self, text: str) -> None:
        if self._loading or not self._current_llm_provider_id:
            return
        provider = self._provider_by_id(self._current_llm_provider_id)
        if provider is None:
            return
        provider.name = text.strip() or "OpenAI"
        data = f"{LLM_BACKEND_PREFIX}{provider.id}"
        index = self.backend.findData(data)
        if index >= 0:
            self.backend.setItemText(index, provider.name)

    def _browse_model(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "选择语音识别模型目录")
        if selected:
            self.model_dir.setText(str(Path(selected)))
