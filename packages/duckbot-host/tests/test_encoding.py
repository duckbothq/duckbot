"""The pipe carries Traditional Chinese, whatever the platform thinks its encoding is.

This file exists because of a bug found on a Windows machine that CI could not see.

Python binds standard input and output to the platform's preferred encoding. On Linux
that is UTF-8. On Windows it is the ANSI code page — cp1252 on a Western install, cp950
on a Traditional Chinese one. A single-byte codec then decodes our UTF-8 bytes into
mojibake, the detectors run against the mojibake, and re-encoding sends the *same bytes*
back out. The text on screen looks right. Nothing raises. And Chinese name detection has
silently stopped working.

Measured on the same input before the fix: UTF-8 stdio found PERSON_NAME at 2–5 and HKID
at 10–20; cp1252 stdio found no PERSON_NAME at all and put HKID at 28–38.

``PYTHONIOENCODING`` reproduces it exactly on any platform, so these run everywhere —
which matters, because the machine where the bug appears is the one CI does not use for
this check.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SRC = str(Path(__file__).resolve().parents[1] / "src")
NAME = "陳嘉雯"
HKID = "A123456(3)"
DOCUMENT = f"客戶{NAME}，身份證 {HKID}，電話 9876 5432。"

NARROW_ENCODINGS = [
    pytest.param("cp1252", id="cp1252-western-windows"),
    pytest.param("cp950", id="cp950-traditional-chinese-windows"),
    pytest.param("latin-1", id="latin-1"),
]


def ask(
    requests: list[dict], encoding: str | None = None, *, substitute: bool = False
) -> list[dict]:
    """Run the host as a child process, speaking bytes, as the shell does.

    With ``substitute``, the placeholders ``@1`` and ``@1-redacted`` in a later request
    are replaced by the first response's ``redaction_id`` and ``redacted_text``. The two
    requests have to reach the same process — the handle is held in memory there and
    nowhere else — so they cannot simply be two calls.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([SRC, env.get("PYTHONPATH", "")])
    if encoding:
        env["PYTHONIOENCODING"] = encoding

    if substitute:
        return _ask_with_substitution(requests, env)

    payload = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in requests)
    finished = subprocess.run(
        [sys.executable, "-m", "duckbot_host"],
        input=payload.encode("utf-8"),
        capture_output=True,
        env=env,
        timeout=120,
        check=False,
    )
    assert finished.returncode == 0, finished.stderr.decode("utf-8", "replace")
    lines = [ln for ln in finished.stdout.decode("utf-8").splitlines() if ln.strip()]
    return [json.loads(ln) for ln in lines]


def _ask_with_substitution(requests: list[dict], env: dict[str, str]) -> list[dict]:
    process = subprocess.Popen(
        [sys.executable, "-m", "duckbot_host"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    assert process.stdin is not None and process.stdout is not None

    responses: list[dict] = []
    first: dict = {}
    try:
        for request in requests:
            filled = json.loads(
                json.dumps(request, ensure_ascii=False)
                .replace("@1-redacted", first.get("redacted_text", ""))
                .replace("@1", first.get("redaction_id", ""))
            )
            process.stdin.write((json.dumps(filled, ensure_ascii=False) + "\n").encode("utf-8"))
            process.stdin.flush()
            line = process.stdout.readline()
            assert line, "the host closed the pipe"
            response = json.loads(line.decode("utf-8"))
            responses.append(response)
            if not first:
                first = response.get("result", {})
    finally:
        process.stdin.close()
        process.wait(timeout=60)
    return responses


@pytest.mark.parametrize("encoding", NARROW_ENCODINGS)
class TestANarrowPlatformEncodingChangesNothing:
    def test_a_chinese_name_is_still_detected(self, encoding: str) -> None:
        """The failure this file exists for. It does not raise; it just stops working."""
        (response,) = ask([{"id": 1, "method": "classify", "params": {"text": DOCUMENT}}], encoding)
        types = [e["type"] for e in response["result"]["entities"]]
        assert "PERSON_NAME" in types

    def test_the_offsets_still_index_the_original_text(self, encoding: str) -> None:
        """Under mojibake they drift, and the window highlights the wrong characters."""
        (response,) = ask([{"id": 1, "method": "classify", "params": {"text": DOCUMENT}}], encoding)
        (name,) = [e for e in response["result"]["entities"] if e["type"] == "PERSON_NAME"]
        assert DOCUMENT[name["start"] : name["end"]] == NAME

    def test_redaction_removes_the_name_rather_than_missing_it(self, encoding: str) -> None:
        (response,) = ask([{"id": 1, "method": "redact", "params": {"text": DOCUMENT}}], encoding)
        assert NAME not in response["result"]["redacted_text"]
        assert HKID not in response["result"]["redacted_text"]

    def test_the_surrounding_chinese_survives_intact(self, encoding: str) -> None:
        (response,) = ask([{"id": 1, "method": "redact", "params": {"text": DOCUMENT}}], encoding)
        redacted = response["result"]["redacted_text"]
        assert redacted.startswith("客戶")
        assert "，電話 " in redacted

    def test_a_restore_round_trip_returns_the_original_exactly(self, encoding: str) -> None:
        """Redact and restore in one session: the handle lives in that process only."""
        _redaction, restoration = ask(
            [
                {"id": 1, "method": "redact", "params": {"text": DOCUMENT}},
                {
                    "id": 2,
                    "method": "restore",
                    "params": {"redaction_id": "@1", "text": "@1-redacted"},
                },
            ],
            encoding,
            substitute=True,
        )
        assert restoration["result"]["text"] == DOCUMENT


class TestTheResultsAreIdenticalAcrossEncodings:
    def test_classification_does_not_depend_on_the_platform_code_page(self) -> None:
        """The property that matters: the same document classifies the same everywhere."""

        def entities(encoding: str | None) -> list[tuple[str, int, int]]:
            (response,) = ask(
                [{"id": 1, "method": "classify", "params": {"text": DOCUMENT}}], encoding
            )
            return sorted((e["type"], e["start"], e["end"]) for e in response["result"]["entities"])

        assert entities(None) == entities("cp1252") == entities("cp950")


class TestLineEndings:
    def test_a_response_is_one_line_with_no_carriage_return(self) -> None:
        """Windows text mode would turn the protocol's newline into CRLF."""
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join([SRC, env.get("PYTHONPATH", "")])
        finished = subprocess.run(
            [sys.executable, "-m", "duckbot_host"],
            input=b'{"id":1,"method":"health"}\n',
            capture_output=True,
            env=env,
            timeout=120,
            check=False,
        )
        assert b"\r\n" not in finished.stdout
