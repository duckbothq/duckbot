"""What the host will and will not tell the shell.

The tests that matter are the ones asserting a value is *absent* from a response. The
shell is a window; it does not need an identity card number to draw a window.

Every value here is invented.
"""

from __future__ import annotations

import json

from duckbot_host import Request, Session, serve_request

NAME = "陳嘉雯"
HKID = "A123456(3)"
PHONE = "9876 5432"
DOCUMENT = f"客戶{NAME}，身份證 {HKID}，電話 {PHONE}。"


def call(method: str, params: dict | None = None, session: Session | None = None) -> dict:
    response = serve_request(Request(method=method, params=params or {}, id=1), session=session)
    return json.loads(response.to_json())


class TestHealth:
    def test_it_reports_the_versions_the_shell_checks(self) -> None:
        result = call("health")["result"]
        assert result["ok"]
        assert result["protocol_version"] >= 1
        assert result["host_version"]
        assert result["schema_version"] >= 1


class TestClassify:
    def test_it_reports_what_was_found(self) -> None:
        result = call("classify", {"text": DOCUMENT})["result"]
        assert result["sensitivity"] == "LOCAL_ONLY"
        assert {e["type"] for e in result["entities"]} >= {"HKID", "PHONE"}

    def test_it_reports_offsets_and_never_values(self) -> None:
        """The shell can highlight a span without being told what is inside it."""
        raw = json.dumps(call("classify", {"text": DOCUMENT}), ensure_ascii=False)
        for value in (NAME, HKID, PHONE):
            assert value not in raw
        for entity in call("classify", {"text": DOCUMENT})["result"]["entities"]:
            assert DOCUMENT[entity["start"] : entity["end"]]

    def test_clean_text_is_public(self) -> None:
        assert call("classify", {"text": "本季度營運開支下降。"})["result"]["sensitivity"] == (
            "PUBLIC"
        )


class TestRedactAndRestore:
    def test_the_redacted_text_carries_no_original_value(self) -> None:
        result = call("redact", {"text": DOCUMENT})["result"]
        for value in (NAME, HKID, PHONE):
            assert value not in result["redacted_text"]

    def test_the_map_is_a_handle_not_the_map(self) -> None:
        """The most sensitive artefact in the system does not cross the process boundary."""
        raw = json.dumps(call("redact", {"text": DOCUMENT}), ensure_ascii=False)
        for value in (NAME, HKID, PHONE):
            assert value not in raw
        assert "redaction_id" in raw

    def test_the_handle_restores(self) -> None:
        session = Session()
        redacted = call("redact", {"text": DOCUMENT}, session)["result"]
        restored = call(
            "restore",
            {"redaction_id": redacted["redaction_id"], "text": redacted["redacted_text"]},
            session,
        )["result"]
        assert restored["text"] == DOCUMENT

    def test_a_model_reply_containing_tokens_restores(self) -> None:
        session = Session()
        redacted = call("redact", {"text": DOCUMENT}, session)["result"]
        token = next(t for t in redacted["tokens"] if t.startswith("[PHONE_"))
        reply = f"建議致電 {token} 確認。"
        assert (
            call("restore", {"redaction_id": redacted["redaction_id"], "text": reply}, session)[
                "result"
            ]["text"]
            == f"建議致電 {PHONE} 確認。"
        )

    def test_an_unknown_handle_says_so_rather_than_silently_doing_nothing(self) -> None:
        """A quiet no-op would leave placeholder tokens in text the user is about to read."""
        response = call("restore", {"redaction_id": "red_missing", "text": "x"})
        assert "unknown redaction_id" in response["error"]["message"]

    def test_forgetting_a_handle_drops_the_values(self) -> None:
        session = Session()
        redacted = call("redact", {"text": DOCUMENT}, session)["result"]
        assert call("forget", {"redaction_id": redacted["redaction_id"]}, session)["result"][
            "forgotten"
        ]
        assert session.open_redactions == 0
        assert "error" in call(
            "restore", {"redaction_id": redacted["redaction_id"], "text": "x"}, session
        )

    def test_maps_do_not_leak_between_sessions(self) -> None:
        first = Session()
        redacted = call("redact", {"text": DOCUMENT}, first)["result"]
        assert "error" in call(
            "restore",
            {"redaction_id": redacted["redaction_id"], "text": redacted["redacted_text"]},
            Session(),
        )


class TestErrors:
    def test_an_unknown_method_is_named(self) -> None:
        assert "no such method" in call("nonsense")["error"]["message"]

    def test_missing_text_is_a_parameter_error(self) -> None:
        assert call("classify", {})["error"]["code"] == -32602

    def test_an_error_never_quotes_the_document(self) -> None:
        """A crash report is exactly the thing a user forwards to a vendor."""
        response = call("restore", {"redaction_id": 5, "text": DOCUMENT})
        assert HKID not in json.dumps(response, ensure_ascii=False)
