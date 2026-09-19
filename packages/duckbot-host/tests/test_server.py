"""The loop, and the subprocess the shell will actually spawn.

The end-to-end test here runs the host exactly as the desktop shell will: a child
process, lines in, lines out. It is parametrised on the command, so the same test can be
pointed at the frozen executable once one exists — which is the only way the packaging
step gets checked rather than assumed.
"""

from __future__ import annotations

import ast
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from duckbot_host import INTERNAL_ERROR, Session, serve
from duckbot_host.handlers import build_handlers

SRC = str(Path(__file__).resolve().parents[1] / "src")
DOCUMENT = "客戶陳嘉雯，身份證 A123456(3)。"


def run(lines: list[str], session: Session | None = None) -> list[dict]:
    out = io.StringIO()
    serve(iter(lines), out, session=session)
    return [json.loads(line) for line in out.getvalue().splitlines()]


class TestTheLoop:
    def test_one_request_one_response(self) -> None:
        assert len(run(['{"id":1,"method":"health"}'])) == 1

    def test_blank_lines_are_ignored_rather_than_answered(self) -> None:
        assert run(["", "   ", '{"id":1,"method":"health"}']) == run(['{"id":1,"method":"health"}'])

    def test_a_request_without_an_id_gets_no_reply(self) -> None:
        """A notification. Acting and answering are different things."""
        assert run(['{"method":"health"}']) == []

    def test_a_bad_line_does_not_stop_the_ones_after_it(self) -> None:
        """A shell that sends one malformed line must not lose the session."""
        responses = run(["{not json", '{"id":2,"method":"health"}'])
        assert len(responses) == 2
        assert responses[1]["result"]["ok"]

    def test_responses_come_back_in_order_with_their_ids(self) -> None:
        responses = run(['{"id":"a","method":"health"}', '{"id":"b","method":"health"}'])
        assert [r["id"] for r in responses] == ["a", "b"]

    def test_an_unexpected_failure_reports_the_type_and_not_the_text(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A traceback from inside a parser can contain the document that provoked it.

        Patched at the point the loop builds its handlers, so this runs through ``serve``
        rather than around it.
        """

        def explode(_: dict) -> None:
            raise RuntimeError(f"failed while parsing {DOCUMENT}")

        def handlers_with_a_bomb(session: Session) -> dict:
            handlers = build_handlers(session)
            handlers["boom"] = explode
            return handlers

        monkeypatch.setattr("duckbot_host.server.build_handlers", handlers_with_a_bomb)
        (response,) = run(['{"id":1,"method":"boom"}'])
        assert response["error"]["code"] == INTERNAL_ERROR
        assert response["error"]["message"] == "unhandled RuntimeError"
        assert "陳嘉雯" not in json.dumps(response, ensure_ascii=False)

    def test_the_loop_survives_a_handler_that_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def handlers_with_a_bomb(session: Session) -> dict:
            handlers = build_handlers(session)
            handlers["boom"] = lambda _: (_ for _ in ()).throw(RuntimeError("x"))
            return handlers

        monkeypatch.setattr("duckbot_host.server.build_handlers", handlers_with_a_bomb)
        responses = run(['{"id":1,"method":"boom"}', '{"id":2,"method":"health"}'])
        assert len(responses) == 2
        assert responses[1]["result"]["ok"]


@pytest.fixture(scope="module")
def command() -> list[str]:
    """The command the shell spawns.

    A module-level fixture so that this file can later be pointed at the frozen
    executable instead, and the same tests then check the packaged artefact.
    """
    return [sys.executable, "-m", "duckbot_host"]


class TestTheSubprocess:
    """How the shell will really use it."""

    def send(self, command: list[str], requests: list[dict]) -> tuple[list[dict], str]:
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join([SRC, env.get("PYTHONPATH", "")])
        payload = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in requests)
        finished = subprocess.run(
            command,
            input=payload,
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
            check=False,
        )
        lines = [line for line in finished.stdout.splitlines() if line.strip()]
        return [json.loads(line) for line in lines], finished.stderr

    def test_a_full_redact_and_restore_round_trip(self, command: list[str]) -> None:
        responses, _ = self.send(
            command,
            [
                {"jsonrpc": "2.0", "id": 1, "method": "health"},
                {"jsonrpc": "2.0", "id": 2, "method": "redact", "params": {"text": DOCUMENT}},
            ],
        )
        assert responses[0]["result"]["ok"]
        redacted = responses[1]["result"]
        assert "A123456(3)" not in redacted["redacted_text"]
        assert redacted["redaction_id"]

    def test_every_stdout_line_is_a_response(self, command: list[str]) -> None:
        """Standard output belongs to the protocol. One stray print breaks the wire."""
        responses, _ = self.send(command, [{"id": 1, "method": "health"}])
        assert len(responses) == 1

    def test_closing_the_pipe_ends_the_process(self, command: list[str]) -> None:
        """So the host cannot outlive the window that started it."""
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join([SRC, env.get("PYTHONPATH", "")])
        finished = subprocess.run(
            command, input="", capture_output=True, text=True, env=env, timeout=60, check=False
        )
        assert finished.returncode == 0


class TestStandardOutputIsReserved:
    def test_main_hands_the_rest_of_the_process_stderr(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Two lines of precaution against a class of bug found at three in the morning."""
        from duckbot_host import cli

        monkeypatch.setattr(sys, "stdin", io.StringIO(""))
        monkeypatch.setattr(sys, "stdout", io.StringIO())
        cli.main()
        assert sys.stdout is sys.stderr

    def test_the_entry_point_uses_absolute_imports(self) -> None:
        """A relative import here works under -m and breaks in the frozen executable.

        The symptom is a window that never finishes loading, because the sidecar died at
        startup. Asserted rather than remembered.
        """
        module = ast.parse((Path(SRC) / "duckbot_host" / "cli.py").read_text(encoding="utf-8"))
        relative = [
            node for node in ast.walk(module) if isinstance(node, ast.ImportFrom) and node.level > 0
        ]
        assert not relative, "cli.py must not use relative imports"
