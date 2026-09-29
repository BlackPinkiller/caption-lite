"""Bounded recovery for an interrupted, read-only LLM translation stream."""
from __future__ import annotations

from collections.abc import Callable

import httpx

from captions.adapters.translation_http import TranslationCancellation


class IncompleteStreamError(RuntimeError):
    """The provider disconnected without a successful completion marker."""


def recover_interrupted_stream(
    request: Callable[[], str],
    cancellation: TranslationCancellation,
    restarted: Callable[[], None],
) -> str:
    """Try once more using the SAME deadline; never retry semantic/API errors.

    Only final translations use this path. Retrying expendable previews would
    delay their latest source. Timeouts, auth/rate limits, invalid output and
    token limits need a different remedy and must not double the request load.
    """
    try:
        return request()
    except (IncompleteStreamError, httpx.ReadError, httpx.RemoteProtocolError):
        if cancellation.remaining() < 0.25:
            raise
        # The failed stream has closed and flushed its progress timer before
        # this event. Clear its fragment before the new stream starts emitting.
        restarted()
        return request()
