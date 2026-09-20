"""Non-secret desktop settings.

Provider keys are intentionally absent from :class:`DesktopSettings`.  They live in the
Windows DPAPI store in :mod:`duckbot_host.secret_store`; this file is ordinary UTF-8 JSON
and is safe to inspect, back up, or include in a support bundle.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, replace
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

PROVIDERS = frozenset({"offline", "ollama", "openai", "anthropic"})
_UPDATABLE = frozenset(
    {
        "provider",
        "provider_model",
        "hosted_endpoint",
        "local_endpoint",
        "local_model",
        "input_per_mtok",
        "output_per_mtok",
        "price_currency",
        "price_source",
        "price_checked_on",
        "per_task_budget_usd",
        "monthly_budget_usd",
        "max_context_tokens",
        "reserve_reply_tokens",
        "connector_folder",
        "connector_encoding",
    }
)


@dataclass(frozen=True)
class DesktopSettings:
    """The minimum v1 settings the engine and local-file connector consume."""

    provider: str = "offline"
    provider_model: str = ""
    hosted_endpoint: str = ""
    local_endpoint: str = "http://127.0.0.1:11434"
    local_model: str = "qwen2.5:3b"
    input_per_mtok: str = ""
    output_per_mtok: str = ""
    price_currency: str = "USD"
    price_source: str = ""
    price_checked_on: str = ""
    per_task_budget_usd: str = "1.00"
    monthly_budget_usd: str = "25.00"
    max_context_tokens: str = "4096"
    reserve_reply_tokens: str = "1024"
    connector_folder: str = ""
    connector_encoding: str = "utf-8"

    def validated(self) -> DesktopSettings:
        if self.provider not in PROVIDERS:
            raise ValueError("provider is not supported")
        _validate_local_endpoint(self.local_endpoint)
        _validate_hosted_endpoint(self.hosted_endpoint)
        if not self.local_model.strip():
            raise ValueError("local model must not be empty")
        if self.provider in {"openai", "anthropic"} and not self.provider_model.strip():
            raise ValueError("hosted providers require a model name")
        if self.provider in {"openai", "anthropic"}:
            _budget(self.input_per_mtok, "input price")
            _budget(self.output_per_mtok, "output price")
            if not self.price_source.strip():
                raise ValueError("hosted providers require a price source")
            try:
                date.fromisoformat(self.price_checked_on)
            except ValueError as exc:
                raise ValueError("hosted providers require an ISO price-check date") from exc
        if not self.price_currency.isalpha() or len(self.price_currency) != 3:
            raise ValueError("price currency must be a three-letter code")
        if self.provider in {"openai", "anthropic"} and self.price_currency.upper() != "USD":
            raise ValueError("desktop hosted-provider budgets currently use USD")
        _budget(self.per_task_budget_usd, "per-task budget")
        _budget(self.monthly_budget_usd, "monthly budget")
        maximum = _positive_integer(self.max_context_tokens, "context token budget")
        reserve = _positive_integer(
            self.reserve_reply_tokens, "reply token reserve", allow_zero=True
        )
        if reserve >= maximum:
            raise ValueError("reply token reserve must be smaller than the context budget")
        if self.connector_folder and not Path(self.connector_folder).is_absolute():
            raise ValueError("connector folder must be an absolute path")
        if self.connector_encoding not in {"utf-8", "utf-8-sig", "cp950"}:
            raise ValueError("connector encoding must be utf-8, utf-8-sig, or cp950")
        return self

    def to_wire(self) -> dict[str, str]:
        return asdict(self)


def _budget(value: str, label: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label} must be a number") from exc
    if not parsed.is_finite() or parsed < 0 or parsed > Decimal("1000000"):
        raise ValueError(f"{label} must be between 0 and 1000000")
    return parsed


def _positive_integer(value: str, label: str, *, allow_zero: bool = False) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be a whole number") from exc
    minimum = 0 if allow_zero else 1
    if parsed < minimum or parsed > 1_000_000:
        raise ValueError(f"{label} is outside the supported range")
    return parsed


def _validate_local_endpoint(value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("local endpoint must be an HTTP URL")
    # A model labelled local is a privacy boundary.  Do not let configuration quietly
    # point it at another computer and still receive LOCAL_ONLY content.
    if parsed.hostname.lower() not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("local endpoint must use localhost or a loopback address")
    if parsed.username or parsed.password:
        raise ValueError("local endpoint must not contain credentials")


def _validate_hosted_endpoint(value: str) -> None:
    if not value:
        return
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("hosted endpoint must be an HTTPS URL")
    if parsed.username or parsed.password:
        raise ValueError("hosted endpoint must not contain credentials")


def default_data_directory() -> Path:
    override = os.environ.get("DUCKBOT_DATA_DIR")
    if override:
        selected = Path(override)
        if not selected.is_absolute():
            raise ValueError("DUCKBOT_DATA_DIR must be an absolute path")
        return selected
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "Duckbot"
    # Used by non-Windows developer/test environments.  It stores only non-secret
    # settings; secret storage remains unavailable and fails closed there.
    return Path.home() / ".duckbot"


class SettingsRepository:
    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> DesktopSettings:
        if not self._path.exists():
            return DesktopSettings()
        try:
            payload: Any = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("saved settings could not be read") from exc
        if not isinstance(payload, dict):
            raise ValueError("saved settings must be a JSON object")
        known = {key: payload[key] for key in _UPDATABLE if key in payload}
        if not all(isinstance(value, str) for value in known.values()):
            raise ValueError("saved settings contain an invalid value")
        try:
            return DesktopSettings(**known).validated()
        except TypeError as exc:  # pragma: no cover - guarded by the known-key filter
            raise ValueError("saved settings contain an invalid field") from exc

    def update(self, changes: dict[str, Any]) -> DesktopSettings:
        unknown = changes.keys() - _UPDATABLE
        if unknown:
            raise ValueError("settings contain an unsupported field")
        if not all(isinstance(value, str) for value in changes.values()):
            raise ValueError("settings values must be strings")
        updated = replace(self.load(), **changes).validated()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(updated.to_wire(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return updated


def default_settings_repository(data_directory: Path | None = None) -> SettingsRepository:
    directory = data_directory or default_data_directory()
    return SettingsRepository(directory / "settings.json")


class SettingsStore(Protocol):
    def load(self) -> DesktopSettings: ...

    def update(self, changes: dict[str, Any]) -> DesktopSettings: ...


class InMemorySettingsRepository:
    """Process-local settings for tests; production uses the UTF-8 repository above."""

    def __init__(self, settings: DesktopSettings | None = None) -> None:
        self._settings = (settings or DesktopSettings()).validated()

    def load(self) -> DesktopSettings:
        return self._settings

    def update(self, changes: dict[str, Any]) -> DesktopSettings:
        unknown = changes.keys() - _UPDATABLE
        if unknown:
            raise ValueError("settings contain an unsupported field")
        if not all(isinstance(value, str) for value in changes.values()):
            raise ValueError("settings values must be strings")
        self._settings = replace(self._settings, **changes).validated()
        return self._settings
