from __future__ import annotations

from typing import Protocol


class SecretStoreError(RuntimeError):
    pass


class SecretStore(Protocol):
    """Protect and restore credentials for the current platform user."""

    def protect(self, value: str) -> str:
        ...

    def unprotect(self, value: str) -> str:
        ...
