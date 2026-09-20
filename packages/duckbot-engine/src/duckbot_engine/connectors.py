"""Small, Duckbot-owned connector boundary and the v1 local-file adapter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from duckbot_core import AuditLog, UntrustedContent
from duckbot_schemas import AuditAction

DEFAULT_MAX_FILE_BYTES = 2 * 1024 * 1024
SUPPORTED_TEXT_SUFFIXES = frozenset({".csv", ".json", ".log", ".md", ".txt"})
SUPPORTED_ENCODINGS = frozenset({"utf-8", "utf-8-sig", "cp950"})


@dataclass(frozen=True)
class ConnectorDocument:
    """A locally retrieved document, typed as data rather than instruction."""

    relative_path: str
    size_bytes: int
    content: UntrustedContent


class Connector(Protocol):
    """The intentionally small boundary future connector adapters must implement."""

    def list_files(self) -> tuple[str, ...]: ...

    def read(
        self,
        relative_path: str,
        *,
        actor: str,
        task_id: str | None = None,
        encoding: str = "utf-8",
    ) -> ConnectorDocument: ...


class LocalFileConnector:
    """Read UTF text only from one explicitly selected directory tree.

    There is deliberately no write method in v1. A read-only connector cannot
    accidentally write outside the selected output location.
    """

    def __init__(
        self,
        root: Path | str,
        *,
        audit: AuditLog | None = None,
        max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
        suffixes: frozenset[str] = SUPPORTED_TEXT_SUFFIXES,
    ) -> None:
        selected = Path(root).resolve(strict=True)
        if not selected.is_dir():
            raise ValueError("the selected connector scope must be a directory")
        if max_file_bytes <= 0:
            raise ValueError("the file-size limit must be positive")
        self._root = selected
        self._audit = audit
        self._max_file_bytes = max_file_bytes
        self._suffixes = frozenset(item.lower() for item in suffixes)

    @property
    def root(self) -> Path:
        return self._root

    def list_files(self) -> tuple[str, ...]:
        files: list[str] = []
        for candidate in self._root.rglob("*"):
            try:
                resolved = candidate.resolve(strict=True)
            except OSError:
                continue
            if not resolved.is_file() or resolved.suffix.lower() not in self._suffixes:
                continue
            try:
                relative = resolved.relative_to(self._root)
            except ValueError:
                # A symlink or junction escaped the selected scope.
                continue
            files.append(relative.as_posix())
        return tuple(sorted(set(files), key=str.casefold))

    def read(
        self,
        relative_path: str,
        *,
        actor: str,
        task_id: str | None = None,
        encoding: str = "utf-8",
    ) -> ConnectorDocument:
        if encoding not in SUPPORTED_ENCODINGS:
            raise ValueError("file encoding must be explicitly utf-8, utf-8-sig, or cp950")
        relative = Path(relative_path)
        if relative.is_absolute() or not relative.parts or relative_path.strip() == "":
            raise ValueError("file path must be relative to the selected folder")
        try:
            target = (self._root / relative).resolve(strict=True)
            safe_relative = target.relative_to(self._root)
        except (OSError, ValueError) as exc:
            raise ValueError("file is outside the selected folder or does not exist") from exc
        if not target.is_file() or target.suffix.lower() not in self._suffixes:
            raise ValueError("file type is not supported by the local connector")

        with target.open("rb") as stream:
            payload = stream.read(self._max_file_bytes + 1)
        if len(payload) > self._max_file_bytes:
            raise ValueError("file exceeds the configured size limit")
        try:
            text = payload.decode(encoding, errors="strict")
        except UnicodeDecodeError as exc:
            raise ValueError(
                f"file is not valid {encoding}; choose its encoding explicitly"
            ) from exc

        source = f"file:{safe_relative.as_posix()}"
        if self._audit is not None:
            self._audit.record(
                actor=actor,
                action=AuditAction.EXTERNAL_ACTION,
                target=source,
                task_id=task_id,
                result="read",
                detail=f"read {len(payload)} bytes from the selected local folder",
            )
        return ConnectorDocument(
            relative_path=safe_relative.as_posix(),
            size_bytes=len(payload),
            content=UntrustedContent(text=text, source=source),
        )
