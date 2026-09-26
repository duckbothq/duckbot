from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from duckbot_host.secret_store import (
    DpapiSecretStore,
    SecretStorageUnavailable,
    UnavailableSecretStore,
)
from duckbot_host.settings import DesktopSettings, SettingsRepository


def test_failed_replacement_preserves_previous_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = SettingsRepository(tmp_path / "settings.json")
    previous = repository.update({"per_task_budget_usd": "2.50"})

    def fail_replace(*_: object) -> None:
        raise OSError("simulated disk failure")

    monkeypatch.setattr("duckbot_host.atomic_file.os.replace", fail_replace)
    with pytest.raises(OSError, match="disk failure"):
        repository.update({"per_task_budget_usd": "5.00"})
    assert repository.load() == previous
    assert sorted(path.name for path in tmp_path.iterdir()) == ["settings.json"]


class ReversibleTestProtector:
    """Test double for DPAPI; production never selects this implementation."""

    def protect(self, value: bytes) -> bytes:
        return b"encrypted:" + value[::-1]

    def unprotect(self, value: bytes) -> bytes:
        if not value.startswith(b"encrypted:"):
            raise OSError("not an encrypted test blob")
        return value.removeprefix(b"encrypted:")[::-1]


def test_settings_round_trip_traditional_chinese_folder(tmp_path: Path) -> None:
    repository = SettingsRepository(tmp_path / "settings.json")
    saved = repository.update(
        {
            "connector_folder": str(tmp_path / "客戶文件"),
            "per_task_budget_usd": "2.50",
            "provider": "ollama",
        }
    )
    assert repository.load() == saved
    assert "客戶文件" in (tmp_path / "settings.json").read_text(encoding="utf-8")


def test_local_endpoint_cannot_quietly_point_at_another_computer() -> None:
    with pytest.raises(ValueError, match="loopback"):
        DesktopSettings(local_endpoint="https://models.example.com").validated()


def test_settings_file_has_no_place_for_an_api_key(tmp_path: Path) -> None:
    repository = SettingsRepository(tmp_path / "settings.json")
    with pytest.raises(ValueError, match="unsupported field"):
        repository.update({"api_key": "sk-plain-text-must-not-be-written"})
    assert not (tmp_path / "settings.json").exists()


def test_dpapi_store_writes_only_protected_bytes(tmp_path: Path) -> None:
    secret = "sk-極機密-123"
    store = DpapiSecretStore(tmp_path, ReversibleTestProtector())
    store.set("openai", secret)
    raw = (tmp_path / "openai.dpapi").read_bytes()
    assert secret.encode("utf-8") not in raw
    assert store.get("openai") == secret
    assert store.has("openai")
    assert store.delete("openai")
    assert not store.has("openai")


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI integration")
def test_real_windows_dpapi_round_trip_never_writes_plaintext(tmp_path: Path) -> None:
    secret = "sk-Duckbot-Windows-DPAPI-check"
    store = DpapiSecretStore(tmp_path)
    store.set("anthropic", secret)
    assert secret.encode("utf-8") not in (tmp_path / "anthropic.dpapi").read_bytes()
    assert store.get("anthropic") == secret


def test_secret_file_name_cannot_escape_its_directory(tmp_path: Path) -> None:
    store = DpapiSecretStore(tmp_path, ReversibleTestProtector())
    with pytest.raises(ValueError, match="provider name"):
        store.set("../other", "secret")


def test_unavailable_store_fails_closed_instead_of_using_plaintext() -> None:
    store = UnavailableSecretStore()
    with pytest.raises(SecretStorageUnavailable, match="Windows DPAPI"):
        store.set("openai", "secret")
    assert store.get("openai") is None


def test_settings_json_is_non_secret_and_utf8(tmp_path: Path) -> None:
    repository = SettingsRepository(tmp_path / "settings.json")
    repository.update({"connector_folder": str(tmp_path / "公司")})
    parsed = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert set(parsed) == set(DesktopSettings().to_wire())
