from __future__ import annotations

from pathlib import Path

import pytest
from duckbot_core import AuditLog, InMemoryAuditStore

from duckbot_engine import LocalFileConnector


def test_reads_synthetic_hong_kong_document_and_audits_relative_path(tmp_path: Path) -> None:
    selected = tmp_path / "客戶文件"
    selected.mkdir()
    document = selected / "報價.txt"
    content = "客戶陳嘉雯，身份證 A123456(3)，電話 9876 5432。"
    document.write_text(content, encoding="utf-8", newline="\n")
    audit = AuditLog(InMemoryAuditStore())
    connector = LocalFileConnector(selected, audit=audit)

    loaded = connector.read("報價.txt", actor="office-manager", task_id="task_1")

    assert loaded.content.as_data() == content
    assert loaded.content.source == "file:報價.txt"
    assert connector.list_files() == ("報價.txt",)
    assert "file:報價.txt" in audit.export_text()
    assert "A123456(3)" not in audit.export_text()
    audit.verify()


@pytest.mark.parametrize("path", ["../outside.txt", "..\\outside.txt"])
def test_traversal_cannot_escape_selected_folder(tmp_path: Path, path: str) -> None:
    selected = tmp_path / "selected"
    selected.mkdir()
    (tmp_path / "outside.txt").write_text("secret", encoding="utf-8")
    connector = LocalFileConnector(selected)

    with pytest.raises(ValueError, match="outside the selected folder"):
        connector.read(path, actor="office-manager")


def test_absolute_path_is_rejected_even_when_it_points_inside_scope(tmp_path: Path) -> None:
    selected = tmp_path / "selected"
    selected.mkdir()
    document = selected / "inside.txt"
    document.write_text("text", encoding="utf-8")

    with pytest.raises(ValueError, match="relative"):
        LocalFileConnector(selected).read(str(document), actor="office-manager")


def test_binary_and_oversized_files_fail_without_quoting_content(tmp_path: Path) -> None:
    selected = tmp_path / "selected"
    selected.mkdir()
    (selected / "image.exe").write_bytes(b"private")
    (selected / "large.txt").write_text("sensitive-value", encoding="utf-8")
    connector = LocalFileConnector(selected, max_file_bytes=4)

    with pytest.raises(ValueError, match="file type") as binary_error:
        connector.read("image.exe", actor="office-manager")
    with pytest.raises(ValueError, match="size limit") as size_error:
        connector.read("large.txt", actor="office-manager")
    assert "private" not in str(binary_error.value)
    assert "sensitive-value" not in str(size_error.value)


def test_cp950_must_be_selected_explicitly(tmp_path: Path) -> None:
    selected = tmp_path / "selected"
    selected.mkdir()
    text = "香港中小企"
    (selected / "legacy.txt").write_bytes(text.encode("cp950"))
    connector = LocalFileConnector(selected)

    with pytest.raises(ValueError, match="valid utf-8"):
        connector.read("legacy.txt", actor="office-manager")
    loaded = connector.read("legacy.txt", actor="office-manager", encoding="cp950")
    assert loaded.content.as_data() == text
