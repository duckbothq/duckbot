"""Exercise the real sidecar task protocol through its UTF-8 byte pipes."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
from typing import Any

for _name in ("stdout", "stderr"):
    _stream = getattr(sys, _name)
    _buffer = getattr(_stream, "buffer", None)
    if _buffer is not None:
        setattr(
            sys,
            _name,
            io.TextIOWrapper(_buffer, encoding="utf-8", errors="replace", write_through=True),
        )

PHONE = "9876 5432"
INSTRUCTION = f"請致電客戶 {PHONE}，然後草擬跟進摘要。"


def request(process: subprocess.Popen[bytes], request_id: int, method: str, **params: Any) -> Any:
    assert process.stdin is not None and process.stdout is not None
    payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    process.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
    process.stdin.flush()
    line = process.stdout.readline()
    if not line:
        raise RuntimeError("the sidecar closed its response pipe")
    response = json.loads(line.decode("utf-8"))
    if "error" in response:
        raise RuntimeError(f"{method} failed: {response['error']}")
    return response["result"]


def check(command: list[str]) -> int:
    with tempfile.TemporaryDirectory(prefix="duckbot-product-smoke-") as data_directory:
        environment = dict(os.environ)
        environment["DUCKBOT_DATA_DIR"] = data_directory
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
        )
        try:
            health = request(process, 1, "health")
            preview = request(
                process,
                2,
                "task_prepare",
                instruction=INSTRUCTION,
                requester="product-smoke",
            )
            outcome = request(process, 3, "task_execute", task_id=preview["task_id"])
            tasks = request(process, 4, "tasks_list")
            audit = request(process, 5, "audit_list", task_id=preview["task_id"])
        finally:
            if process.stdin is not None:
                process.stdin.close()
            process.wait(timeout=60)

    assert health["protocol_version"] == 2
    assert preview["outbound_text"] is None
    assert any(item["type"] == "PHONE" for item in preview["redactions"])
    assert outcome["kind"] == "completed"
    assert PHONE in outcome["text"]
    assert PHONE not in json.dumps(tasks, ensure_ascii=False)
    assert PHONE not in json.dumps(audit, ensure_ascii=False)
    assert audit["verified"]
    print("ok — desktop sidecar task, preview, result, cost and audit verified")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: scripts_product_smoke.py <command to run the host>")
    raise SystemExit(check(sys.argv[1:]))
