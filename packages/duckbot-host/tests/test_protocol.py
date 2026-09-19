"""The wire format, including the malformed input a shell will eventually send."""

from __future__ import annotations

import json

from duckbot_host import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    PARSE_ERROR,
    Request,
    Response,
    parse,
)


def as_dict(response: Response) -> dict:
    return json.loads(response.to_json())


class TestParsing:
    def test_a_well_formed_request(self) -> None:
        parsed = parse('{"jsonrpc":"2.0","id":1,"method":"health","params":{}}')
        assert isinstance(parsed, Request)
        assert parsed.method == "health"
        assert parsed.id == 1

    def test_params_may_be_omitted(self) -> None:
        parsed = parse('{"id":1,"method":"health"}')
        assert isinstance(parsed, Request) and parsed.params == {}

    def test_broken_json_is_an_error_not_an_exception(self) -> None:
        response = parse("{not json")
        assert isinstance(response, Response)
        assert as_dict(response)["error"]["code"] == PARSE_ERROR

    def test_a_json_array_is_not_a_request(self) -> None:
        response = parse("[1, 2, 3]")
        assert isinstance(response, Response)
        assert as_dict(response)["error"]["code"] == INVALID_REQUEST

    def test_a_request_must_name_a_method(self) -> None:
        response = parse('{"id":1}')
        assert isinstance(response, Response)
        assert as_dict(response)["error"]["code"] == INVALID_REQUEST

    def test_params_must_be_an_object(self) -> None:
        response = parse('{"id":1,"method":"health","params":[1]}')
        assert isinstance(response, Response)
        assert as_dict(response)["error"]["code"] == INVALID_PARAMS

    def test_a_string_id_is_allowed(self) -> None:
        parsed = parse('{"id":"abc","method":"health"}')
        assert isinstance(parsed, Request) and parsed.id == "abc"

    def test_a_structured_id_is_refused(self) -> None:
        response = parse('{"id":{"a":1},"method":"health"}')
        assert isinstance(response, Response)


class TestResponses:
    def test_a_result_carries_the_id(self) -> None:
        assert as_dict(Response(id=7, result={"ok": True})) == {
            "jsonrpc": "2.0",
            "id": 7,
            "result": {"ok": True},
        }

    def test_a_response_is_one_line(self) -> None:
        """Newline framing only works if a response never contains one."""
        rendered = Response(id=1, result={"text": "第一行\n第二行"}).to_json()
        assert "\n" not in rendered

    def test_chinese_survives_unescaped(self) -> None:
        """So a human debugging the pipe can read it."""
        assert "陳嘉雯" in Response(id=1, result={"name": "陳嘉雯"}).to_json()
