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

from captions.config import (
    TranslationConfig,
    active_llm_provider,
    llm_chat_completions_url,
)
from captions.core.prompt_template import render_prompt_template

GOOGLE2_BOOTSTRAP_URL = (
    "https://translate.google.com/translate_a/element.js"
    "?cb=googleTranslateElementInit"
)
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


class StaleTranslationError(RuntimeError):
    pass


class TranslationCancellation:
    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._response: httpx.Response | None = None

    def is_set(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()
        with self._lock:
            response = self._response
        if response is not None:
            try:
                response.close()
            except Exception:
                pass

    def attach(self, response: httpx.Response) -> None:
        with self._lock:
            if self._event.is_set():
                close_now = True
            else:
                self._response = response
                close_now = False
        if close_now:
            response.close()
            raise CancelledError()

    def detach(self, response: httpx.Response) -> None:
        with self._lock:
            if self._response is response:
                self._response = None


def translation_queue_expired(
    submitted_at: float, timeout_ms: int, *, now: float | None = None
) -> bool:
    now = time.monotonic() if now is None else now
    maximum_age = max(1.0, timeout_ms / 1000)
    return now - submitted_at > maximum_age


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
    terms = matching_glossary(config.glossary, searchable)
    context_block = (
        f"仅供消歧的上文（不要翻译）：\n{background}" if background else ""
    )
    glossary_block = (
        "必须遵守的术语：" + "".join(f"\n{s} = {t}" for s, t in terms)
        if terms
        else ""
    )
    return render_prompt_template(
        config.prompt_template,
        {
            "src": source,
            "dst": target,
            "ctx": context_block,
            "terms": glossary_block,
            "text": current,
        },
    )


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
        self._cancellations: dict[Future, TranslationCancellation] = {}
        self._pending_preview: Future | None = None
        self._preview_cancel: TranslationCancellation | None = None
        self._lock = threading.Lock()
        limits = httpx.Limits(
            max_connections=2,
            max_keepalive_connections=1,
            keepalive_expiry=5.0,
        )
        self._preview_client = httpx.Client(limits=limits, http2=False)
        self._final_client = httpx.Client(limits=limits, http2=False)
        self._closing = False
        self._clients_closed = False

    def translate(
        self,
        text: str,
        history: list[HistoryRecord],
        config: TranslationConfig,
        *,
        preview: bool = False,
        on_registered: Callable[[int], None] | None = None,
    ) -> int:
        with self._lock:
            if self._closing:
                raise RuntimeError("翻译器正在关闭")
        self._generation += 1
        generation = self._generation
        if on_registered is not None:
            on_registered(generation)
        context_segments = max(0, int(config.context_segments))
        snapshot = list(history[-context_segments:]) if context_segments else []
        if preview:
            self._cancel_preview()
        if not preview:
            self._make_room_for_final_translation()
        executor = self._preview_executor if preview else self._final_executor
        client = self._preview_client if preview else self._final_client
        submitted_at = time.monotonic()
        cancellation = TranslationCancellation()

        def request() -> str:
            if cancellation is not None and cancellation.is_set():
                raise CancelledError()
            if not preview and translation_queue_expired(
                submitted_at, config.timeout_ms
            ):
                raise StaleTranslationError()
            self.signals.started.emit(generation)
            return self._request(
                text,
                snapshot,
                config,
                lambda partial: self.signals.progress.emit(generation, partial),
                client=client,
                cancellation=cancellation,
            )

        future = executor.submit(request)
        with self._lock:
            if preview:
                self._pending_preview = future
                self._preview_cancel = cancellation
            else:
                self._final_futures.append(future)
            self._cancellations[future] = cancellation
            self._futures.add(future)

        def done(completed: Future) -> None:
            with self._lock:
                overloaded = completed in self._overload_cancellations
                closing = self._closing
                self._overload_cancellations.discard(completed)
                self._cancellations.pop(completed, None)
                self._futures.discard(completed)
                if completed in self._final_futures:
                    self._final_futures.remove(completed)
                if self._pending_preview is completed:
                    self._pending_preview = None
                    self._preview_cancel = None
                close_clients = (
                    self._closing and not self._futures and not self._clients_closed
                )
                if close_clients:
                    self._clients_closed = True
            if closing:
                return
            try:
                result = completed.result()
            except StaleTranslationError:
                self.signals.cancelled.emit(generation)
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
            if close_clients:
                self._preview_client.close()
                self._final_client.close()

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
        self._cancel_preview()

    def cancel_all(self) -> None:
        with self._lock:
            self._generation += 1
            cancellations = list(self._cancellations.values())
            futures = list(self._futures)
        for cancellation in cancellations:
            cancellation.cancel()
        for future in futures:
            future.cancel()

    def _cancel_preview(self) -> None:
        with self._lock:
            pending_preview = self._pending_preview
            preview_cancel = self._preview_cancel
        if preview_cancel is not None:
            preview_cancel.cancel()
        if pending_preview is not None:
            pending_preview.cancel()

    def close(self) -> None:
        with self._lock:
            if self._closing:
                return
            self._closing = True
            cancellations = list(self._cancellations.values())
            futures = list(self._futures)
        for cancellation in cancellations:
            cancellation.cancel()
        for future in futures:
            future.cancel()
        try:
            self._preview_client.close()
        except Exception:
            pass
        try:
            self._final_client.close()
        except Exception:
            pass
        with self._lock:
            self._clients_closed = True
        self._preview_executor.shutdown(wait=False, cancel_futures=True)
        self._final_executor.shutdown(wait=False, cancel_futures=True)

    def wait_closed(self) -> None:
        self.close()
        self._preview_executor.shutdown(wait=True, cancel_futures=True)
        self._final_executor.shutdown(wait=True, cancel_futures=True)

    @staticmethod
    def acquire_google2_api_key(
        timeout: float = 10.0,
        *,
        client: httpx.Client | None = None,
    ) -> str:
        get = client.get if client is not None else httpx.get
        headers = {"User-Agent": "Mozilla/5.0"}
        bootstrap = get(
            GOOGLE2_BOOTSTRAP_URL,
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
        )
        bootstrap.raise_for_status()
        candidates = re.findall(r"_loadJs\('([^']+)'\)", bootstrap.text)
        main_url = ""
        for candidate in candidates:
            decoded = re.sub(
                r"\\x([0-9a-fA-F]{2})",
                lambda match: chr(int(match.group(1), 16)),
                candidate,
            )
            decoded = re.sub(
                r"\\u([0-9a-fA-F]{4})",
                lambda match: chr(int(match.group(1), 16)),
                decoded,
            ).replace(r"\/", "/")
            if (
                decoded.startswith("https://translate.googleapis.com/")
                and "translate_http" in decoded
                and decoded.endswith("/m=el_main")
            ):
                main_url = decoded
                break
        if not main_url:
            raise RuntimeError("Google 翻译组件未提供主脚本地址")

        main_script = get(
            main_url,
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
        )
        main_script.raise_for_status()
        match = re.search(
            r'/v1/translateHtml.{0,500}?X-goog-api-key"?:"(AIza[0-9A-Za-z_-]{35})"',
            main_script.text,
            re.IGNORECASE | re.DOTALL,
        )
        if match is None:
            raise RuntimeError("Google 翻译组件未提供 translateHtml 密钥")
        return match.group(1)

    @staticmethod
    def _request(
        text: str,
        history: list[HistoryRecord],
        config: TranslationConfig,
        progress: Callable[[str], None],
        *,
        client: httpx.Client | None = None,
        cancellation: TranslationCancellation | None = None,
    ) -> str:
        if cancellation is not None and cancellation.is_set():
            raise CancelledError()
        timeout = max(1.0, config.timeout_ms / 1000)
        if config.backend == "google2":
            result = Translator._google2(text, config, timeout, client=client)
        elif config.backend == "deepl":
            result = Translator._deepl(text, config, timeout, client=client)
        else:
            provider = active_llm_provider(config)
            url = llm_chat_completions_url(provider)
            if not url:
                raise RuntimeError("请填写 LLM API 地址")
            prompt = build_hymt_prompt(text, history, config)
            payload = {
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "stream": provider.stream,
                "max_tokens": LLAMA_MAX_TOKENS,
            }
            if provider.model:
                payload["model"] = provider.model
            headers = {}
            if provider.api_key:
                headers["Authorization"] = f"Bearer {provider.api_key}"
            if provider.stream:
                result = Translator._llama_stream(
                    url,
                    payload,
                    timeout,
                    progress,
                    headers=headers,
                    client=client,
                    cancellation=cancellation,
                )
            else:
                post = client.post if client is not None else httpx.post
                response = post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=timeout,
                )
                response.raise_for_status()
                data = response.json()
                result = data["choices"][0]["message"]["content"].strip()
        if cancellation is not None and cancellation.is_set():
            raise CancelledError()
        return result

    @staticmethod
    def _llama_stream(
        url: str,
        payload: dict,
        timeout: float,
        progress: Callable[[str], None],
        *,
        headers: dict[str, str] | None = None,
        client: httpx.Client | None = None,
        cancellation: TranslationCancellation | None = None,
    ) -> str:
        if cancellation is not None and cancellation.is_set():
            raise CancelledError()
        text = ""
        started_at = time.monotonic()
        stream = client.stream if client is not None else httpx.stream
        try:
            with stream(
                "POST",
                url,
                json=payload,
                headers=headers or {},
                timeout=timeout,
            ) as response:
                if cancellation is not None:
                    cancellation.attach(response)
                try:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if cancellation is not None and cancellation.is_set():
                            raise CancelledError()
                        if time.monotonic() - started_at > timeout:
                            raise TimeoutError("翻译请求超过总时限")
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data or data == "[DONE]":
                            continue
                        event = json.loads(data)
                        delta = event.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if not delta:
                            continue
                        if cancellation is not None and cancellation.is_set():
                            raise CancelledError()
                        if len(text) + len(delta) > MAX_STREAM_RESPONSE_CHARS:
                            raise RuntimeError("流式翻译响应过长")
                        text += delta
                        progress(text.strip())
                finally:
                    if cancellation is not None:
                        cancellation.detach(response)
        except (httpx.HTTPError, RuntimeError) as error:
            if cancellation is not None and cancellation.is_set():
                raise CancelledError() from error
            raise
        if cancellation is not None and cancellation.is_set():
            raise CancelledError()
        return text.strip()

    @staticmethod
    def _google2(
        text: str,
        config: TranslationConfig,
        timeout: float,
        *,
        client: httpx.Client | None = None,
    ) -> str:
        url = "https://translate-pa.googleapis.com/v1/translateHtml"
        api_key = config.google2_api_key.strip()
        if not api_key:
            api_key = Translator.acquire_google2_api_key(
                timeout,
                client=client,
            )
            config.google2_api_key = api_key
        source_lang = GOOGLE_LANGUAGE_CODES.get(config.source_lang, "en")
        target_lang = GOOGLE_LANGUAGE_CODES.get(config.target_lang, "zh-CN")
        payload = [[[text], source_lang, target_lang], "wt_lib"]
        headers = {
            "Content-Type": "application/json+protobuf",
            "X-Goog-API-Key": api_key,
        }
        last_error: Exception | None = None
        post = client.post if client is not None else httpx.post
        for _ in range(2):
            try:
                response = post(url, headers=headers, json=payload, timeout=timeout)
                response.raise_for_status()
                data = response.json()
                return str(data[0][0])
            except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError) as error:
                last_error = error
        raise RuntimeError(f"Google2 翻译失败：{last_error}")

    @staticmethod
    def _deepl(
        text: str,
        config: TranslationConfig,
        timeout: float,
        *,
        client: httpx.Client | None = None,
    ) -> str:
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
        post = client.post if client is not None else httpx.post
        response = post(
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
