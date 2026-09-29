from __future__ import annotations

import json
import os
import re
import threading
import time
from copy import deepcopy
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from typing import Callable

import httpx
from PySide6.QtCore import QObject, Signal

from captions.adapters.translation_http import DeadlineClient, TranslationCancellation
from captions.adapters.translation_progress import TimedStreamProgress
from captions.adapters.translation_recovery import (
    IncompleteStreamError,
    recover_interrupted_stream,
)
from captions.core.settings import (
    TranslationConfig,
    active_llm_provider,
    llm_chat_completions_url,
    translation_secret_values,
)
from captions.core.translation import (
    HistoryRecord,
    StaleTranslationError,
    translation_queue_expired,
    build_hymt_prompt,
)
from captions.core.privacy import redact_sensitive_text

GOOGLE2_BOOTSTRAP_URL = (
    "https://translate.google.com/translate_a/element.js"
    "?cb=googleTranslateElementInit"
)
MAX_PENDING_FINAL_TRANSLATIONS = 32
MAX_STREAM_RESPONSE_CHARS = 16_384
LLAMA_MAX_TOKENS = 1_024


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


class TranslationSignals(QObject):
    started = Signal(int)
    restarted = Signal(int)
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
        google2_key_config: TranslationConfig | None = None,
    ) -> int:
        with self._lock:
            if self._closing:
                raise RuntimeError("翻译器正在关闭")
        self._generation += 1
        generation = self._generation
        if on_registered is not None:
            on_registered(generation)
        key_config = google2_key_config if google2_key_config is not None else config
        original_google2_key = config.google2_api_key
        config = deepcopy(config)
        context_segments = max(0, int(config.context_segments))
        snapshot = deepcopy(history[-context_segments:]) if context_segments else []
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
            # Keep the established queue-expiry policy. Sharing that budget
            # with execution dropped more final cues in the paired overload
            # replay. The request itself (including retries) has one deadline.
            cancellation.deadline = time.monotonic() + max(1.0, config.timeout_ms / 1000)
            self.signals.started.emit(generation)
            try:
                with cancellation.watch():
                    def attempt() -> str:
                        return self._request(
                            text,
                            snapshot,
                            config,
                            lambda partial: self.signals.progress.emit(generation, partial),
                            client=client,
                            cancellation=cancellation,
                        )
                    if (
                        not preview
                        and config.backend == "llama"
                        and active_llm_provider(config).stream
                    ):
                        return recover_interrupted_stream(
                            attempt, cancellation,
                            lambda: self.signals.restarted.emit(generation),
                        )
                    return attempt()
            finally:
                # Request settings are snapshots, but automatically renewed keys
                # must survive them. Never overwrite a key edited meanwhile.
                if (
                    config.backend == "google2"
                    and config.google2_api_key != original_google2_key
                    and key_config.google2_api_key == original_google2_key
                ):
                    key_config.google2_api_key = config.google2_api_key

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
                self.signals.error.emit(
                    generation,
                    redact_sensitive_text(str(error), (
                        *translation_secret_values(config), original_google2_key,
                        os.environ.get("DEEPL_API_KEY", ""),
                    )),
                )
            else:
                self.signals.result.emit(generation, result)
            if close_clients:
                self._preview_client.close()
                self._final_client.close()

        future.add_done_callback(done)
        return generation

    def deliver_cached(
        self, text: str, *, on_registered: Callable[[int], None],
    ) -> int:
        """Use the same queued lifecycle as a worker, without another request."""
        with self._lock:
            if self._closing:
                raise RuntimeError("翻译器正在关闭")
            self._generation += 1
            generation = self._generation
        on_registered(generation)
        self.signals.started.emit(generation)
        self.signals.result.emit(generation, text)
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
        if cancellation is not None and cancellation.deadline is not None:
            timeout = cancellation.remaining()
            if client is not None:
                client = DeadlineClient(client, cancellation)
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
                choice = data["choices"][0]
                if choice.get("finish_reason") not in (None, "stop"):
                    raise RuntimeError("翻译未完整生成")
                result = choice["message"]["content"].strip()
        if cancellation is not None and cancellation.is_set():
            raise CancelledError()
        if not result.strip():
            raise RuntimeError("翻译服务返回空译文")
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
        completed = False
        started_at = time.monotonic()
        updates = TimedStreamProgress(
            lambda value: progress(value)
            if cancellation is None or not cancellation.is_set() else None
        )
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
                        if data == "[DONE]":
                            completed = True
                            break
                        if not data:
                            continue
                        event = json.loads(data)
                        choices = event.get("choices") or [{}]
                        choice = choices[0]
                        reason = choice.get("finish_reason")
                        if reason is not None:
                            if reason != "stop":
                                raise RuntimeError("流式翻译未完整生成")
                            completed = True
                        delta = (choice.get("delta") or {}).get("content") or ""
                        if not delta and not completed:
                            continue
                        if cancellation is not None and cancellation.is_set():
                            raise CancelledError()
                        if len(text) + len(delta) > MAX_STREAM_RESPONSE_CHARS:
                            raise RuntimeError("流式翻译响应过长")
                        text += delta
                        updates.update(text.strip())
                        if completed:
                            break
                finally:
                    if cancellation is not None:
                        cancellation.detach(response)
        except (httpx.HTTPError, RuntimeError) as error:
            if cancellation is not None and cancellation.is_set():
                raise CancelledError() from error
            raise
        finally:
            updates.close()
        if cancellation is not None and cancellation.is_set():
            raise CancelledError()
        if not completed:
            raise IncompleteStreamError("流式翻译提前结束")
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
        for attempt in range(2):
            try:
                response = post(url, headers=headers, json=payload, timeout=timeout)
                if response.status_code in {401, 403} and attempt == 0:
                    api_key = Translator.acquire_google2_api_key(
                        timeout,
                        client=client,
                    )
                    config.google2_api_key = api_key
                    headers["X-Goog-API-Key"] = api_key
                    continue
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
