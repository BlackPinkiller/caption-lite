"""Redact credentials and keep transcript logging explicitly opt-in."""
from __future__ import annotations

import re
from typing import Any, Iterable


_GOOGLE_KEY = re.compile(r"AIza[0-9A-Za-z_-]{35}")
_URL = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_CONTENT_FIELDS = {
    "text", "source", "translation", "committed", "preview", "remainder",
    "context", "prompt", "transcript", "audio",
}
_SECRET_FIELDS = {"key", "api_key", "apikey", "authorization", "password", "secret", "access_token"}


def redact_sensitive_text(text: str, secrets: Iterable[str] = ()) -> str:
    for secret in sorted({value for value in secrets if value}, key=len, reverse=True):
        text = text.replace(secret, "[REDACTED]")
    text = _GOOGLE_KEY.sub("[REDACTED]", text)
    # Error strings can contain credentials in userinfo, query or URL paths.
    return _URL.sub("[URL]", text)


def diagnostic_fields(fields: dict[str, Any], *, include_text: bool, secrets=()) -> dict[str, Any]:
    def clean(value):
        if isinstance(value, str):
            return redact_sensitive_text(value, secrets)
        if isinstance(value, dict):
            return diagnostic_fields(value, include_text=include_text, secrets=secrets)
        if isinstance(value, (list, tuple)):
            return [clean(item) for item in value]
        return value

    output = {}
    for key, value in fields.items():
        normalized = key.lower()
        if normalized in _SECRET_FIELDS or normalized.endswith("_api_key"):
            continue
        if not include_text and normalized in _CONTENT_FIELDS:
            if isinstance(value, str):
                output[f"{key}_chars"] = len(value)
            elif isinstance(value, (list, tuple)):
                output[f"{key}_items"] = len(value)
            continue
        output[key] = clean(value)
    return output
