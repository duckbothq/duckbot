"""The wire between the desktop shell and the Python that does the work.

**Nothing listens on a port.** The shell spawns this process and talks to it over its
standard input and output. That is the whole security argument, and it is a short one: a
local HTTP server, however carefully bound to 127.0.0.1, is reachable by every other
process on the machine, shows up in port scans, collides with whatever else wanted 8080,
and has to be explained to a customer's IT department. A pipe between a parent and its
own child is reachable by neither. For a product whose pitch is that the data stays on
the machine, "nothing is listening" is a sentence worth being able to say.

The framing is newline-delimited JSON — one request per line, one response per line.
Length-prefixed framing is more robust in principle; newline framing is debuggable by a
human with a terminal, and JSON cannot contain a raw newline, so the failure it guards
against does not arise.

The error codes follow JSON-RPC 2.0 so that a shell written against any JSON-RPC client
library behaves sensibly, but this is not a full JSON-RPC implementation and does not
claim to be: no batching, no notifications, no server-initiated calls.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

PROTOCOL_VERSION = 2
"""Bumped when the shape of a request or response changes.

The shell checks it at startup and refuses to run against a host it does not understand,
because a desktop application and its sidecar are updated as one unit and a mismatch
means the installer went wrong.
"""


@dataclass(frozen=True)
class Request:
    method: str
    params: dict[str, Any] = field(default_factory=dict)
    id: int | str | None = None


@dataclass(frozen=True)
class Response:
    id: int | str | None
    result: Any = None
    error: dict[str, Any] | None = None

    def to_json(self) -> str:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": self.id}
        if self.error is not None:
            payload["error"] = self.error
        else:
            payload["result"] = self.result
        return json.dumps(payload, ensure_ascii=False)


def error(code: int, message: str, request_id: int | str | None = None) -> Response:
    """An error response.

    ``message`` is for a developer reading a log. It must never contain content the host
    was given: an error that quotes the document defeats the point of the document never
    leaving the machine in the first place — and a crash report is exactly the thing a
    user forwards to a vendor.
    """
    return Response(id=request_id, error={"code": code, "message": message})


def parse(line: str) -> Request | Response:
    """Parse one line. Returns a :class:`Response` when the line cannot be a request."""
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return error(PARSE_ERROR, "the line was not valid JSON")
    if not isinstance(payload, dict):
        return error(INVALID_REQUEST, "a request must be a JSON object")

    method = payload.get("method")
    if not isinstance(method, str) or not method:
        return error(INVALID_REQUEST, "a request must name a method", payload.get("id"))

    params = payload.get("params", {})
    if not isinstance(params, dict):
        return error(INVALID_PARAMS, "params must be an object", payload.get("id"))

    request_id = payload.get("id")
    if request_id is not None and not isinstance(request_id, int | str):
        return error(INVALID_REQUEST, "id must be a number or a string", None)

    return Request(method=method, params=params, id=request_id)
