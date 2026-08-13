from __future__ import annotations

import sys

from captions.ports.secret_store import SecretStore, SecretStoreError


class UnsupportedSecretStore:
    def protect(self, value: str) -> str:
        if not value.strip():
            return ""
        raise SecretStoreError("此平台尚未配置安全密钥存储")

    def unprotect(self, value: str) -> str:
        if not value or not value.startswith("dpapi:"):
            return value
        raise SecretStoreError("此平台无法读取 Windows DPAPI 密钥")


def create_secret_store() -> SecretStore:
    if sys.platform == "win32":
        from captions.platforms.windows.secret_store import WindowsDpapiSecretStore

        return WindowsDpapiSecretStore()
    return UnsupportedSecretStore()


DEFAULT_SECRET_STORE = create_secret_store()
