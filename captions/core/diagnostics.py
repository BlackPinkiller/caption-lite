from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from captions.core.privacy import diagnostic_fields


class Diagnostics:
    """Low-volume lifecycle trace for the recognition/translation pipeline."""

    def __init__(
        self, enabled: bool = False, path: Path | None = None,
        *, include_text: bool = False, secrets: tuple[str, ...] = (),
    ) -> None:
        self.enabled = bool(enabled)
        self.include_text = bool(include_text)
        self._secrets = secrets
        self.path = path
        self.session_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        self._started_at = time.monotonic()
        self._lock = threading.Lock()
        self.max_bytes = 5 * 1024 * 1024

    def configure(
        self, enabled: bool, path: Path | None = None,
        *, include_text: bool | None = None, secrets: tuple[str, ...] | None = None,
    ) -> None:
        self.enabled = bool(enabled)
        if include_text is not None:
            self.include_text = bool(include_text)
        if secrets is not None:
            self._secrets = secrets
        if path is not None:
            self.path = path

    def event(self, name: str, **fields: Any) -> None:
        if not self.enabled or self.path is None:
            return
        payload = {
            "time": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "elapsed_ms": round((time.monotonic() - self._started_at) * 1000),
            "session": self.session_id,
            "event": name,
            **diagnostic_fields(fields, include_text=self.include_text, secrets=self._secrets),
        }
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        try:
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                if self.path.exists() and self.path.stat().st_size >= self.max_bytes:
                    backup = self.path.with_suffix(self.path.suffix + ".1")
                    self.path.replace(backup)
                with self.path.open("a", encoding="utf-8") as stream:
                    stream.write(line + "\n")
        except OSError:
            # Diagnostics must never interrupt recognition or translation.
            return


NULL_DIAGNOSTICS = Diagnostics()
