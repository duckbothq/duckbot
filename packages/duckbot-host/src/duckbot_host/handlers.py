"""What the shell can ask the host to do.

One rule shapes every method here: **a value the user's document contains never crosses
the wire.** The shell is a window; it does not need the identity card number to draw a
window. So ``classify`` returns offsets and entity types, and ``redact`` returns the
redacted text plus a *handle* — the placeholder map itself stays in this process, in
memory, and is reachable only by giving the handle back.

That is the same guarantee ``PlaceholderMap`` makes inside the Python, extended across
the process boundary: the map has no ``model_dump``, so it cannot be serialised by
accident, and here it is never serialised on purpose either.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from duckbot_privacy import PrivacyGateway
from duckbot_schemas import SCHEMA_VERSION, PlaceholderMap, new_id

from .protocol import INVALID_PARAMS, PROTOCOL_VERSION, Request, Response, error

HOST_VERSION = "0.1.0"

Handler = Callable[[dict[str, Any]], Any]


@dataclass
class Session:
    """The host's memory for the life of one desktop session.

    Redaction maps live here and nowhere else. They are not written to disk, not included
    in any response, and they die with the process — which is the correct lifetime for
    the most sensitive artefact in the system.
    """

    gateway: PrivacyGateway = field(default_factory=PrivacyGateway)
    _maps: dict[str, PlaceholderMap] = field(default_factory=dict)

    def keep(self, mapping: PlaceholderMap) -> str:
        handle = new_id("red")
        self._maps[handle] = mapping
        return handle

    def get(self, handle: str) -> PlaceholderMap | None:
        return self._maps.get(handle)

    def forget(self, handle: str) -> bool:
        return self._maps.pop(handle, None) is not None

    @property
    def open_redactions(self) -> int:
        return len(self._maps)


def _text(params: dict[str, Any]) -> str:
    value = params.get("text")
    if not isinstance(value, str) or not value:
        raise ValueError("text must be a non-empty string")
    return value


def build_handlers(session: Session) -> dict[str, Handler]:
    def health(_: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "protocol_version": PROTOCOL_VERSION,
            "host_version": HOST_VERSION,
            "schema_version": SCHEMA_VERSION,
            "open_redactions": session.open_redactions,
        }

    def classify(params: dict[str, Any]) -> dict[str, Any]:
        classification, _ = session.gateway.classify(
            _text(params), content_id=str(params.get("content_id") or new_id("doc"))
        )
        return {
            "content_id": classification.content_id,
            "sensitivity": classification.sensitivity.name,
            # Offsets and types only. The shell can highlight a span without being told
            # what is inside it.
            "entities": [
                {
                    "type": e.entity_type,
                    "start": e.start,
                    "end": e.end,
                    "confidence": e.confidence,
                }
                for e in classification.entities
            ],
        }

    def redact(params: dict[str, Any]) -> dict[str, Any]:
        result = session.gateway.redact(
            _text(params), content_id=str(params.get("content_id") or new_id("doc"))
        )
        return {
            "redaction_id": session.keep(result.placeholder_map),
            "redacted_text": result.redacted_text,
            "sensitivity": result.classification.sensitivity.name,
            "tokens": result.tokens,
        }

    def restore(params: dict[str, Any]) -> dict[str, Any]:
        handle = params.get("redaction_id")
        if not isinstance(handle, str):
            raise ValueError("redaction_id must be a string")
        mapping = session.get(handle)
        if mapping is None:
            # Not an error the shell should retry: the handle is gone because the host
            # restarted, which means the real values are gone with it. Saying so plainly
            # is better than an empty restoration that silently leaves tokens in place.
            raise ValueError("unknown redaction_id; the host may have restarted")
        return {"text": mapping.restore(_text(params))}

    def forget(params: dict[str, Any]) -> dict[str, Any]:
        handle = params.get("redaction_id")
        if not isinstance(handle, str):
            raise ValueError("redaction_id must be a string")
        return {"forgotten": session.forget(handle)}

    return {
        "health": health,
        "classify": classify,
        "redact": redact,
        "restore": restore,
        "forget": forget,
    }


def dispatch(handlers: dict[str, Handler], request: Request) -> Response:
    handler = handlers.get(request.method)
    if handler is None:
        from .protocol import METHOD_NOT_FOUND

        return error(METHOD_NOT_FOUND, f"no such method: {request.method}", request.id)
    try:
        return Response(id=request.id, result=handler(request.params))
    except ValueError as exc:
        # ValueError is the handlers' way of saying the parameters were wrong. Its
        # message is written by us and contains no document content.
        return error(INVALID_PARAMS, str(exc), request.id)
