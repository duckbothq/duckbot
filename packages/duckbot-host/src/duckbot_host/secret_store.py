"""Windows-bound secret storage for desktop provider credentials.

The settings JSON deliberately has no field capable of carrying an API key.  On
Windows, key material is encrypted with DPAPI for the current user before the encrypted
blob is written below LocalAppData.  DPAPI gives us an operating-system supported,
per-user boundary without adding a dependency or inventing a vault protocol.

The JSON-RPC layer only exposes ``has``/``set``/``delete``.  ``get`` exists for the
engine adapter that constructs a provider client, but its value must never be returned
to the shell, an audit record, or an exception message.
"""

from __future__ import annotations

import ctypes
import re
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Any, Protocol

from .atomic_file import atomic_write

_KEY_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_ENTROPY = b"Duckbot desktop provider key v1"
_CRYPTPROTECT_UI_FORBIDDEN = 0x01


class SecretStorageUnavailable(RuntimeError):
    """The platform cannot provide the secure storage guarantee Duckbot requires."""


class SecretStore(Protocol):
    """The deliberately small interface used by settings and provider construction."""

    @property
    def available(self) -> bool: ...

    @property
    def backend(self) -> str: ...

    def set(self, name: str, secret: str) -> None: ...

    def get(self, name: str) -> str | None: ...

    def has(self, name: str) -> bool: ...

    def delete(self, name: str) -> bool: ...


class DataProtector(Protocol):
    def protect(self, value: bytes) -> bytes: ...

    def unprotect(self, value: bytes) -> bytes: ...


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _input_blob(value: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_char]]:
    # create_string_buffer owns the input memory for the duration of the native call.
    # Keep it in the returned tuple so it cannot be collected before CryptProtectData
    # has read it.
    buffer = ctypes.create_string_buffer(value)
    pointer = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
    return _DataBlob(len(value), pointer), buffer


def _last_windows_error() -> int:
    """``ctypes.get_last_error`` exists only on Windows, and the type stubs say so.

    :class:`WindowsDataProtector` refuses to construct anywhere else, so the second
    branch is unreachable in practice. It is written out rather than silenced because
    this file is type-checked on Linux in CI, where the attribute is genuinely absent,
    and a blanket ``type: ignore`` here would also hide a real error later.
    """
    if sys.platform == "win32":
        return ctypes.get_last_error()
    raise SecretStorageUnavailable("Windows DPAPI is unavailable on this platform")


class WindowsDataProtector:
    """A minimal ctypes wrapper around CryptProtectData/CryptUnprotectData."""

    def __init__(self) -> None:
        # `sys.platform`, not `os.name`: both are true only on Windows, but the type
        # checker narrows on this one, which is what makes the Windows-only ctypes
        # attributes below check cleanly on a Linux CI runner.
        if sys.platform != "win32":
            raise SecretStorageUnavailable("Windows DPAPI is unavailable on this platform")
        self._crypt32: Any = ctypes.WinDLL("crypt32", use_last_error=True)
        self._kernel32: Any = ctypes.WinDLL("kernel32", use_last_error=True)

    def protect(self, value: bytes) -> bytes:
        return self._transform("CryptProtectData", value)

    def unprotect(self, value: bytes) -> bytes:
        return self._transform("CryptUnprotectData", value)

    def _transform(self, operation: str, value: bytes) -> bytes:
        source, source_buffer = _input_blob(value)
        entropy, entropy_buffer = _input_blob(_ENTROPY)
        destination = _DataBlob()
        function = getattr(self._crypt32, operation)
        # source_buffer and entropy_buffer are intentionally referenced after the call;
        # otherwise a future refactor could shorten their lifetime while native code is
        # still reading them.
        succeeded = function(
            ctypes.byref(source),
            None,
            ctypes.byref(entropy),
            None,
            None,
            _CRYPTPROTECT_UI_FORBIDDEN,
            ctypes.byref(destination),
        )
        _ = source_buffer, entropy_buffer
        if not succeeded:
            error_code = _last_windows_error()
            raise OSError(error_code, f"{operation} failed")
        try:
            return ctypes.string_at(destination.pbData, destination.cbData)
        finally:
            self._kernel32.LocalFree(destination.pbData)


class DpapiSecretStore:
    """Encrypted blobs scoped to the current Windows user via DPAPI."""

    def __init__(self, directory: Path, protector: DataProtector | None = None) -> None:
        self._directory = directory
        self._protector = protector or WindowsDataProtector()

    @property
    def available(self) -> bool:
        return True

    @property
    def backend(self) -> str:
        return "windows-dpapi-current-user"

    def set(self, name: str, secret: str) -> None:
        if not secret:
            raise ValueError("API key must not be empty")
        target = self._path(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        encrypted = self._protector.protect(secret.encode("utf-8"))
        atomic_write(target, encrypted)

    def get(self, name: str) -> str | None:
        target = self._path(name)
        if not target.exists():
            return None
        try:
            return self._protector.unprotect(target.read_bytes()).decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            # The exception deliberately says nothing about the secret or encrypted
            # payload.  A copied blob from another Windows account should fail closed.
            raise SecretStorageUnavailable("the saved API key could not be unlocked") from exc

    def has(self, name: str) -> bool:
        return self._path(name).is_file()

    def delete(self, name: str) -> bool:
        target = self._path(name)
        if not target.exists():
            return False
        target.unlink()
        return True

    def _path(self, name: str) -> Path:
        if not _KEY_NAME.fullmatch(name):
            raise ValueError("provider name contains unsupported characters")
        return self._directory / f"{name}.dpapi"


class UnavailableSecretStore:
    """Fail closed instead of silently persisting plaintext on non-Windows hosts."""

    @property
    def available(self) -> bool:
        return False

    @property
    def backend(self) -> str:
        return "unavailable"

    def set(self, name: str, secret: str) -> None:
        del name, secret
        raise SecretStorageUnavailable("secure API-key storage requires Windows DPAPI")

    def get(self, name: str) -> str | None:
        del name
        return None

    def has(self, name: str) -> bool:
        del name
        return False

    def delete(self, name: str) -> bool:
        del name
        return False


def default_secret_store(data_directory: Path) -> SecretStore:
    if sys.platform != "win32":
        return UnavailableSecretStore()
    return DpapiSecretStore(data_directory / "secrets")
