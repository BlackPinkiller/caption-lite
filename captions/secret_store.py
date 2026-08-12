from __future__ import annotations

import base64
import ctypes
import sys
from ctypes import wintypes


PROTECTED_PREFIX = "dpapi:"
CRYPTPROTECT_UI_FORBIDDEN = 0x1


class SecretStoreError(RuntimeError):
    pass


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _input_blob(data: bytes) -> tuple[_DataBlob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data)
    blob = _DataBlob(
        len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
    )
    return blob, buffer


def _crypt_protect(data: bytes) -> bytes:
    source, source_buffer = _input_blob(data)
    output = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    crypt32.CryptProtectData.restype = wintypes.BOOL
    ok = crypt32.CryptProtectData(
        ctypes.byref(source),
        "RealtimeSubtitle",
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(output),
    )
    del source_buffer
    if not ok:
        raise SecretStoreError(str(ctypes.WinError()))
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(output.pbData)


def _crypt_unprotect(data: bytes) -> bytes:
    source, source_buffer = _input_blob(data)
    output = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(source),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(output),
    )
    del source_buffer
    if not ok:
        raise SecretStoreError(str(ctypes.WinError()))
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(output.pbData)


def protect_secret(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if sys.platform != "win32":
        raise SecretStoreError("此平台不支持 Windows DPAPI")
    protected = _crypt_protect(value.encode("utf-8"))
    encoded = base64.urlsafe_b64encode(protected).decode("ascii")
    return PROTECTED_PREFIX + encoded


def unprotect_secret(value: str) -> str:
    if not value:
        return ""
    if not value.startswith(PROTECTED_PREFIX):
        return value
    if sys.platform != "win32":
        raise SecretStoreError("此平台不支持 Windows DPAPI")
    try:
        protected = base64.urlsafe_b64decode(value[len(PROTECTED_PREFIX) :])
        return _crypt_unprotect(protected).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as error:
        raise SecretStoreError("DeepL 密钥数据已损坏") from error
