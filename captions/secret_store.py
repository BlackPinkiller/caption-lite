"""Backward-compatible helpers for the active platform secret store."""

from captions.platforms.secret_store import DEFAULT_SECRET_STORE
from captions.ports.secret_store import SecretStoreError


def protect_secret(value: str) -> str:
    return DEFAULT_SECRET_STORE.protect(value)


def unprotect_secret(value: str) -> str:
    return DEFAULT_SECRET_STORE.unprotect(value)
