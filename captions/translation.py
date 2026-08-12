from __future__ import annotations

import json
import os
import re
import threading
import time
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

import httpx
from PySide6.QtCore import QObject, Signal

from captions.config import TranslationConfig

GOOGLE2_API_KEY = "REDACTED_GOOGLE_API_KEY"
MAX_PENDING_FINAL_TRANSLATIONS = 32
MAX_STREAM_RESPONSE_CHARS = 16_384
LLAMA_MAX_TOKENS = 1_024

LANGUAGE_NAMES = {
    "AUTO": "自动识别的语言",
    "EN": "英语",
    "ZH": "中文",
    "ZH-HANS": "简体中文",
    "ZH-HANT": "繁体中文",
    "EN-US": "英语",
    "DE": "德语",
    "FR": "法语",
    "ES": "西班牙语",
    "IT": "意大利语",
    "PT": "葡萄牙语",
    "JA": "日语",
    "KO": "韩语",
    "NL": "荷兰语",
    "RU": "俄语",
}

GOOGLE_LANGUAGE_CODES = {
    "AUTO": "auto",
    "EN": "en",
    "EN-US": "en",
    "ZH": "zh-CN",
    "ZH-HANS": "zh-CN",
    "ZH-HANT": "zh-TW",
    "DE": "de",
    "FR": "fr",
    "ES": "es",
    "IT": "it",
    "PT": "pt",
    "JA": "ja",
    "KO": "ko",
    "NL": "nl",
    "RU": "ru",
}

@dataclass
class HistoryRecord:
    time: str
    source: str
    translation: str
    backend: str
    forced: bool = False


def matching_glossary(glossary: dict[str, str], text: str) -> list[tuple[str, str]]:
    matches: list[tuple[str, str]] = []
    for source, target in glossary.items():
        if re.search(rf"(?<!\w){re.escape(source)}(?!\w)", text, re.IGNORECASE):
            matches.append((source, target))
    return sorted(matches, key=lambda item: len(item[0]), reverse=True)


def build_hymt_prompt(
    current: str, history: list[HistoryRecord], config: TranslationConfig
) -> str:
    context: list[str] = []
    chars = 0
    for item in reversed(history[-config.context_segments :]):
        if chars + len(item.source) > config.context_chars:
            break
        context.insert(0, item.source)
        chars += len(item.source)
    background = "\n".join(context)
    searchable = f"{background}\n{current}"
    source = LANGUAGE_NAMES.get(config.source_lang, config.source_lang)
    target = LANGUAGE_NAMES.get(config.target_lang, config.target_lang)
    if config.source_lang == "AUTO":
        direction = f"自动识别下面字幕的语言，并翻译成{target}。"
    else:
        direction = f"将下面未完成或完整的{source}字幕翻译成{target}。"
    prompt = (
        direction
        + "只输出当前文本的译文，不要解释，不要续写或补全尚未说出的内容。"
    )
    if config.preference.strip():
        prompt += f"\n翻译偏好：{config.preference.strip()}"
    if background:
        prompt += f"\n仅供消歧的上文（不要翻译）：\n{background}"
    terms = matching_glossary(config.glossary, searchable)
    if terms:
        prompt += "\n必须遵守的术语：" + "".join(f"\n{s} = {t}" for s, t in terms)
    return f"{prompt}\n\n当前文本：\n{current}"


class TranslationSignals(QObject):
    started = Signal(int)
    progress = Signal(int, str)
    result = Signal(int, str)
    error = Signal(int, str)
    cancelled = Signal(int)


class Translator(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.signals = TranslationSignals()
        self._preview_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="translation-preview"
        )
        self._final_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="translation-final"
        )
        self._generation = 0
        self._futures: set[Future] = set()
        self._final_futures: list[Future] = []
        self._overload_cancellations: set[Future] = set()
        self._pending_preview: Future | None = None
        self._lock = threading.Lock()

    def translate(
        self,
        text: str,
        history: list[HistoryRecord],
        config: TranslationConfig,
        *,
        preview: bool = False,
    ) -> int:
        self._generation += 1
        generation = self._generation
        context_segments = max(0, int(config.context_segments))
        snapshot = list(history[-context_segments:]) if context_segments else []
        if preview and self._pending_preview is not None:
            self._pending_preview.cancel()
        if not preview:
            self._make_room_for_final_translation()
        executor = self._preview_executor if preview else self._final_executor
        def request() -> str:
            self.signals.started.emit(generation)
            return self._request(
                text,
                snapshot,
                config,
                lambda partial: self.signals.progress.emit(generation, partial),
            )

        future = executor.submit(request)
        with self._lock:
            if preview:
                self._pending_preview = future
            else:
                self._final_futures.append(future)
            self._futures.add(future)

        def done(completed: Future) -> None:
            with self._lock:
                overloaded = completed in self._overload_cancellations
                self._overload_cancellations.discard(completed)
                self._futures.discard(completed)
                if completed in self._final_futures:
                    self._final_futures.remove(completed)
                if self._pending_preview is completed:
                    self._pending_preview = None
            try:
                result = completed.result()
            except CancelledError:
                if overloaded:
                    self.signals.error.emit(
                        generation,
                        "翻译积压过多，已跳过较旧的待处理字幕",
                    )
                else:
                    self.signals.cancelled.emit(generation)
            except Exception as error:
                self.signals.error.emit(generation, str(error))
            else:
                self.signals.result.emit(generation, result)

        future.add_done_callback(done)
        return generation

    def _make_room_for_final_translation(self) -> None:
        with self._lock:
            pending = [future for future in self._final_futures if not future.done()]
        excess = len(pending) - MAX_PENDING_FINAL_TRANSLATIONS + 1
        if excess <= 0:
            return
        for future in pending:
            if excess <= 0:
                break
            if future.running():
                continue
            with self._lock:
                self._overload_cancellations.add(future)
            if future.cancel():
                excess -= 1
            else:
                with self._lock:
                    self._overload_cancellations.discard(future)

    def cancel_pending(self) -> None:
        self._generation += 1
        with self._lock:
            pending_preview = self._pending_preview
        if pending_preview is not None:
            pending_preview.cancel()

    def close(self) -> None:
        self.cancel_pending()
        self._preview_executor.shutdown(wait=False, cancel_futures=True)
        self._final_executor.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def _request(
        text: str,
        history: list[HistoryRecord],
        config: TranslationConfig,
        progress: Callable[[str], None],
    ) -> str:
        timeout = max(1.0, config.timeout_ms / 1000)
        if config.backend == "google2":
            return Translator._google2(text, config, timeout)
        if config.backend == "deepl":
            return Translator._deepl(text, config, timeout)
        prompt = build_hymt_prompt(text, history, config)
        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "stream": config.stream,
            "max_tokens": LLAMA_MAX_TOKENS,
        }
        if config.stream:
            return Translator._llama_stream(config.llama_url, payload, timeout, progress)
        response = httpx.post(config.llama_url, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()

    @staticmethod
    def _llama_stream(
        url: str,
        payload: dict,
        timeout: float,
        progress: Callable[[str], None],
    ) -> str:
        text = ""
        started_at = time.monotonic()
        with httpx.stream("POST", url, json=payload, timeout=timeout) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if time.monotonic() - started_at > timeout:
                    raise TimeoutError("翻译请求超过总时限")
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                event = json.loads(data)
                delta = event.get("choices", [{}])[0].get("delta", {}).get("content", "")
                if delta:
                    if len(text) + len(delta) > MAX_STREAM_RESPONSE_CHARS:
                        raise RuntimeError("流式翻译响应过长")
                    text += delta
                    progress(text.strip())
        return text.strip()

    @staticmethod
    def _google2(text: str, config: TranslationConfig, timeout: float) -> str:
        url = "https://translate-pa.googleapis.com/v1/translateHtml"
        source_lang = GOOGLE_LANGUAGE_CODES.get(config.source_lang, "en")
        target_lang = GOOGLE_LANGUAGE_CODES.get(config.target_lang, "zh-CN")
        payload = [[[text], source_lang, target_lang], "wt_lib"]
        headers = {
            "Content-Type": "application/json+protobuf",
            "X-Goog-API-Key": GOOGLE2_API_KEY,
        }
        last_error: Exception | None = None
        for _ in range(2):
            try:
                response = httpx.post(url, headers=headers, json=payload, timeout=timeout)
                response.raise_for_status()
                data = response.json()
                return str(data[0][0])
            except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError) as error:
                last_error = error
        raise RuntimeError(f"Google2 翻译失败：{last_error}")

    @staticmethod
    def _deepl(text: str, config: TranslationConfig, timeout: float) -> str:
        api_key = config.deepl_api_key.strip() or os.environ.get("DEEPL_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("尚未填写 DeepL API 密钥")
        host = "api.deepl.com" if config.deepl_api_plan == "pro" else "api-free.deepl.com"
        payload = {
            "text": [text],
            "target_lang": config.target_lang or "ZH-HANS",
        }
        if config.source_lang and config.source_lang != "AUTO":
            payload["source_lang"] = "ZH" if config.source_lang.startswith("ZH-") else config.source_lang
        response = httpx.post(
            f"https://{host}/v2/translate",
            headers={
                "Authorization": f"DeepL-Auth-Key {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "RealtimeSubtitle/1.0",
            },
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        try:
            return str(response.json()["translations"][0]["text"]).strip()
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
            raise RuntimeError("DeepL 返回了无法识别的响应") from error
