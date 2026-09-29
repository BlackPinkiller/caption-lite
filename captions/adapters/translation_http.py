"""Synchronous HTTPX cancellation and a shared request deadline.

Socket shutdown AND close wake a blocked read (shutdown alone does not wake
Python's timed socket select on Windows).
Only the socket owned by the current request is interrupted; healthy pooled
connections remain available. All HTTPX/httpcore extension use stays here.
"""
from __future__ import annotations

from concurrent.futures import CancelledError
from contextlib import contextmanager
import socket
import threading
import time

import httpx


class TranslationCancellation:
    def __init__(self, deadline: float | None = None) -> None:
        self.deadline = deadline
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._response: httpx.Response | None = None
        self._socket = None
        self._watching = False

    def is_set(self) -> bool:
        return self._event.is_set()

    def remaining(self) -> float:
        if self.deadline is None:
            raise ValueError("Request has no deadline")
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("翻译请求超过总时限")
        if self.is_set():
            raise CancelledError()
        return remaining

    def cancel(self) -> None:
        self._event.set()
        with self._lock:
            response = self._response
            if self._socket is not None:
                try:
                    self._socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                self._socket.close()
        if response is not None:
            try:
                response.close()
            except Exception:
                pass

    def attach(self, response: httpx.Response) -> None:
        with self._lock:
            close_now = self._event.is_set()
            if not close_now:
                self._response = response
                network = getattr(response, "extensions", {}).get("network_stream")
                if network is not None:
                    self._socket = network.get_extra_info("socket")
        if close_now:
            response.close()
            raise CancelledError()

    def detach(self, response: httpx.Response) -> None:
        with self._lock:
            if self._response is response:
                self._response = None
                self._socket = None

    def trace(self, event: str, info: dict) -> None:
        if self.deadline is None:
            return
        # Trace callbacks run immediately before HTTP/1.1 IO phases, including
        # requests using a pooled connection. Refresh their remaining budget.
        if event.endswith((
            "send_request_headers.started", "send_request_body.started",
            "receive_response_headers.started", "receive_response_body.started",
        )):
            remaining = self.remaining()
            request = info.get("request")
            if request is not None:
                request.extensions["timeout"] = dict.fromkeys(
                    ("connect", "read", "write", "pool"), remaining,
                )
        if event in {"connection.connect_tcp.complete", "connection.start_tls.complete"}:
            network = info.get("return_value")
            if network is not None:
                with self._lock:
                    self._socket = network.get_extra_info("socket")
                if self.is_set():
                    self.cancel()
                    raise CancelledError()

    @contextmanager
    def watch(self):
        remaining = self.remaining()
        with self._lock:
            self._watching = True
        def expire():
            # Serialize ownership with finally so an old timer cannot interrupt
            # a socket after it has been returned to the connection pool.
            with self._lock:
                if not self._watching:
                    return
                self._event.set()
                if self._socket is not None:
                    try:
                        self._socket.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    self._socket.close()
        timer = threading.Timer(remaining, expire)
        timer.daemon = True
        timer.start()
        try:
            yield
            self.remaining()
        except Exception as error:
            if self.deadline is not None and time.monotonic() >= self.deadline:
                raise TimeoutError("翻译请求超过总时限") from error
            if self.is_set():
                raise CancelledError() from error
            raise
        finally:
            with self._lock:
                self._watching = False
                self._socket = None
                self._response = None
            timer.cancel()


class DeadlineClient:
    """Use one cancellation/deadline for all calls, redirects and retries."""
    def __init__(self, client: httpx.Client, cancellation: TranslationCancellation):
        self.client = client
        self.cancellation = cancellation

    @contextmanager
    def stream(self, method, url, **kwargs):
        kwargs["timeout"] = self.cancellation.remaining()
        kwargs["extensions"] = {"trace": self.cancellation.trace}
        with self.client.stream(method, url, **kwargs) as response:
            self.cancellation.attach(response)
            try:
                yield response
            finally:
                self.cancellation.detach(response)

    def post(self, url, **kwargs):
        return self._read("POST", url, **kwargs)

    def get(self, url, **kwargs):
        return self._read("GET", url, **kwargs)

    def _read(self, method, url, **kwargs):
        with self.stream(method, url, **kwargs) as response:
            response.read()
            self.cancellation.remaining()
            return response
