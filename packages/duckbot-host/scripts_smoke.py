"""Smoke-test a built host executable with content the product actually carries.

    python scripts_smoke.py dist/duckbot-host
    python scripts_smoke.py dist/duckbot-host.exe
    python scripts_smoke.py python -m duckbot_host

Why this exists, and why it is not a `health` check.

The Windows build originally verified the frozen sidecar by sending it `health` and
checking for `ok`. That passes on a binary that has silently stopped working: `health` is
pure ASCII, and the bug that was actually there — stdio bound to the platform code page
instead of UTF-8 — only shows up on content with Chinese in it. A Traditional Chinese
product whose smoke test contains no Chinese is not being tested.

So this sends a Hong Kong document and checks the three things that break when the pipe
is wrong:

* the personal name is still detected — under a single-byte code page it silently is not;
* the reported offsets still index the original text — under mojibake they drift;
* the Chinese survives the round trip byte for byte.

Bytes are written and read explicitly, never through the harness's own text layer, so
this script cannot accidentally be the thing that is correct while the subject is not.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys

# This script had the same bug as the thing it tests: it prints the document back for a
# human to read, and on a Windows console that is the platform code page, so the report
# crashed while the subject was fine. The assumption is that pervasive. Bind our own
# output to UTF-8 before writing anything.
for _name in ("stdout", "stderr"):
    _stream = getattr(sys, _name)
    _buffer = getattr(_stream, "buffer", None)
    if _buffer is not None:
        setattr(
            sys,
            _name,
            io.TextIOWrapper(_buffer, encoding="utf-8", errors="replace", write_through=True),
        )

NAME = "陳嘉雯"
HKID = "A123456(3)"
DOCUMENT = f"客戶{NAME}，身份證 {HKID}，電話 9876 5432。"


def run(command: list[str]) -> list[dict]:
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "health"},
        {"jsonrpc": "2.0", "id": 2, "method": "classify", "params": {"text": DOCUMENT}},
        {"jsonrpc": "2.0", "id": 3, "method": "redact", "params": {"text": DOCUMENT}},
    ]
    payload = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in requests)
    finished = subprocess.run(
        command,
        input=payload.encode("utf-8"),
        capture_output=True,
        timeout=120,
        check=False,
    )
    if finished.returncode != 0:
        sys.stderr.write(finished.stderr.decode("utf-8", "replace"))
        raise SystemExit(f"the host exited with {finished.returncode}")
    lines = [ln for ln in finished.stdout.decode("utf-8").splitlines() if ln.strip()]
    return [json.loads(ln) for ln in lines]


def check(command: list[str]) -> int:
    health, classification, redaction = (r["result"] for r in run(command))

    failures: list[str] = []

    if not health.get("ok"):
        failures.append("health did not report ok")

    entities = classification["entities"]
    names = [e for e in entities if e["type"] == "PERSON_NAME"]
    if not names:
        failures.append(
            "no PERSON_NAME was detected. This is what a non-UTF-8 pipe looks like: the "
            "detector ran against mojibake and found nothing, without raising."
        )
    else:
        found = DOCUMENT[names[0]["start"] : names[0]["end"]]
        if found != NAME:
            failures.append(
                f"the name offsets index {found!r}, not {NAME!r} — the offsets have "
                "drifted, which means the window would highlight the wrong characters"
            )

    if not any(e["type"] == "HKID" for e in entities):
        failures.append("no HKID was detected")

    redacted = redaction["redacted_text"]
    for value in (NAME, HKID):
        if value in redacted:
            failures.append(f"{value!r} survived redaction")
    if "客戶" not in redacted or "電話" not in redacted:
        failures.append(f"the surrounding Chinese did not survive the round trip: {redacted!r}")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1

    print(f"ok — {len(entities)} entities, name at {names[0]['start']}–{names[0]['end']}")
    print(f"     redacted: {redacted}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: scripts_smoke.py <command to run the host>")
    raise SystemExit(check(sys.argv[1:]))
